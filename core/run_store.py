# -*- coding: utf-8 -*-
"""RunStore：Run / AgentRun 的 SQLite 持久化（Phase 7-5）。

借鉴 BossHunter scoring_run_store：
- 每个 Agent 完成立即 checkpoint（status + output_path + validation + 耗时）；
- 终态 run 不允许被回写覆盖；
- 应用启动时把异常退出遗留的 running/queued run 接管为 paused（可恢复）；
- resume 时精确返回未成功的 Agent 列表，已成功的直接跳过。

刻意只建两张表，不复制 BossHunter 几十张表的迁移体系。
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from core.config import PROJECT_ROOT
from core.run import (
    Run, AgentRun,
    RUN_QUEUED, RUN_RUNNING, RUN_SUCCESS, RUN_COMPLETED_WITH_ERRORS, RUN_FAILED, RUN_PAUSED,
    TERMINAL_RUN_STATUSES,
    AGENT_QUEUED, AGENT_RUNNING, AGENT_SUCCESS, AGENT_FAILED, AGENT_PAUSED,
    AGENT_BLOCKED, AGENT_DEGRADED, AGENT_SKIPPED,
    AGENT_DONE_STATUSES, AGENT_RESUMABLE_STATUSES,
)

DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "creativity_runs.db"


def _now_expr_terminal(status: Optional[str]) -> Optional[str]:
    return "CURRENT_TIMESTAMP" if status in TERMINAL_RUN_STATUSES else None


class RunStore:
    """每次操作开短连接，天然支持并行阶段（1-7 Agent）多线程写入。"""

    def __init__(self, db_path=None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_tables()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_tables(self):
        with self._connect() as conn:
            # WAL：1-7 专家 Agent 并行落 checkpoint 时避免写锁互相阻塞
            conn.execute("PRAGMA journal_mode=WAL")
            # 兼容旧库迁移：若 runs 表已存在但缺少 user_id 列则补上
            cols = {r[1] for r in conn.execute("PRAGMA table_info(runs)").fetchall()}
            if cols and "user_id" not in cols:
                conn.execute("ALTER TABLE runs ADD COLUMN user_id TEXT DEFAULT ''")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_user ON runs(user_id)")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    user_id TEXT DEFAULT '',
                    project_id TEXT DEFAULT '',
                    status TEXT NOT NULL,
                    current_stage TEXT DEFAULT '',
                    project_input TEXT DEFAULT '',
                    report_dir TEXT DEFAULT '',
                    error TEXT DEFAULT '',
                    pause_reason TEXT DEFAULT '',
                    metadata_json TEXT DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    finished_at TIMESTAMP NULL
                );
                CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
                CREATE INDEX IF NOT EXISTS idx_runs_user ON runs(user_id);

                CREATE TABLE IF NOT EXISTS agent_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    agent_name TEXT NOT NULL,
                    stage_seq TEXT DEFAULT '',
                    stage_key TEXT DEFAULT '',
                    label TEXT DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'queued',
                    started_at TIMESTAMP NULL,
                    finished_at TIMESTAMP NULL,
                    retry_count INTEGER DEFAULT 0,
                    conclusion TEXT DEFAULT '',
                    output_path TEXT DEFAULT '',
                    error TEXT DEFAULT '',
                    validation_json TEXT DEFAULT '{}',
                    metadata_json TEXT DEFAULT '{}',
                    UNIQUE(run_id, agent_name)
                );
                CREATE INDEX IF NOT EXISTS idx_agent_runs_run ON agent_runs(run_id, stage_seq);
                """
            )

    # ── Run ──

    def create_run(
        self,
        project_input: str,
        stage_specs: Sequence[Tuple[str, str, str, str]],
        *,
        project_id: str = "",
        report_dir: str = "",
        run_id: Optional[str] = None,
        metadata: Optional[dict] = None,
        user_id: str = "",
    ) -> Run:
        """创建 Run，并把 12 棒预置为 queued（resume 时据此知道哪些没跑过）。"""
        run_id = run_id or f"run_{uuid.uuid4().hex[:12]}"
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO runs (run_id, user_id, project_id, status, project_input, report_dir, metadata_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (run_id, user_id, project_id, RUN_QUEUED, project_input, report_dir,
                 json.dumps(metadata or {}, ensure_ascii=False)),
            )
            conn.executemany(
                """INSERT INTO agent_runs (run_id, agent_name, stage_seq, stage_key, label, status)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                [(run_id, agent_name, seq, key, label, AGENT_QUEUED)
                 for seq, key, agent_name, label in stage_specs],
            )
        return self.get_run(run_id)

    def get_run(self, run_id: str) -> Optional[Run]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        return self._row_to_run(row) if row else None

    def list_recent_runs(self, limit: int = 10) -> List[Run]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM runs ORDER BY created_at DESC, updated_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._row_to_run(r) for r in rows]

    def list_user_runs(self, user_id: str, limit: int = 20) -> List[Run]:
        """只返回属于该用户的 Run（user_id 隔离）。"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM runs WHERE user_id = ? ORDER BY created_at DESC, updated_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        return [self._row_to_run(r) for r in rows]

    def mark_run_running(self, run_id: str):
        self._update_run(run_id, status=RUN_RUNNING, clear_pause=True)

    def pause_run(self, run_id: str, reason: str, *, error: str = ""):
        """服务级故障（额度等）：整条 Run 安全暂停，未完成 Agent 一并转 paused。"""
        with self._connect() as conn:
            self._update_run_conn(conn, run_id, status=RUN_PAUSED, pause_reason=reason, error=error)
            conn.execute(
                """UPDATE agent_runs SET status = ?, finished_at = CURRENT_TIMESTAMP
                   WHERE run_id = ? AND status IN (?, ?)""",
                (AGENT_PAUSED, run_id, AGENT_QUEUED, AGENT_RUNNING),
            )

    def resume_run(self, run_id: str):
        """把可恢复 Run 重新置为 running。

        所有未产出完成态的 Agent（paused/failed/queued/running/blocked/skipped）
        回到 queued，由 ExecutionPlanner 重新计算 ready set；
        success/degraded 保持完成态、不重跑。
        """
        with self._connect() as conn:
            row = conn.execute("SELECT status FROM runs WHERE run_id = ?", (run_id,)).fetchone()
            if not row:
                raise ValueError(f"Run 不存在: {run_id}")
            if row["status"] not in (RUN_PAUSED, RUN_FAILED, RUN_COMPLETED_WITH_ERRORS):
                raise ValueError(f"Run 状态为 {row['status']}，不可恢复（仅 paused/failed/completed_with_errors 可恢复）")
            self._update_run_conn(conn, run_id, status=RUN_RUNNING, clear_pause=True)
            placeholders = ", ".join("?" for _ in AGENT_RESUMABLE_STATUSES)
            conn.execute(
                f"""UPDATE agent_runs SET status = ?, started_at = NULL, finished_at = NULL
                   WHERE run_id = ? AND status IN ({placeholders})""",
                [AGENT_QUEUED, run_id, *AGENT_RESUMABLE_STATUSES],
            )

    def finish_run(self, run_id: str, *, success_count: int, fail_count: int):
        status = RUN_SUCCESS if fail_count == 0 else RUN_COMPLETED_WITH_ERRORS
        self._update_run(run_id, status=status)
        return status

    def fail_run(self, run_id: str, error: str):
        self._update_run(run_id, status=RUN_FAILED, error=error)

    def update_current_stage(self, run_id: str, stage_key: str):
        self._update_run(run_id, current_stage=stage_key)

    # ── AgentRun（Checkpoint） ──

    def start_agent(self, run_id: str, agent_name: str):
        with self._connect() as conn:
            conn.execute(
                """UPDATE agent_runs SET status = ?, started_at = CURRENT_TIMESTAMP,
                   finished_at = NULL, error = ''
                   WHERE run_id = ? AND agent_name = ?""",
                (AGENT_RUNNING, run_id, agent_name),
            )
            # 同层并行下，其他线程可能已把 Run 置为 paused/failed（quota/auth）：
            # 只在 Run 仍处于 queued/running 时推进为 running，绝不覆盖暂停/失败/终态。
            conn.execute(
                """UPDATE runs SET status = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE run_id = ? AND status IN (?, ?)""",
                (RUN_RUNNING, run_id, RUN_QUEUED, RUN_RUNNING),
            )

    def finish_agent(
        self,
        run_id: str,
        agent_name: str,
        status: str,
        *,
        conclusion: str = "",
        output_path: str = "",
        error: str = "",
        validation: Optional[dict] = None,
        metadata: Optional[dict] = None,
        increment_retry: bool = False,
    ):
        """单个 Agent 终态 checkpoint。success/failed/skipped 立即落库。"""
        sets = ["status = ?", "finished_at = CURRENT_TIMESTAMP",
                "conclusion = ?", "output_path = ?", "error = ?",
                "validation_json = ?", "metadata_json = ?"]
        params: list = [status, conclusion[:500], output_path[:500], error[:2000],
                        json.dumps(validation or {}, ensure_ascii=False),
                        json.dumps(metadata or {}, ensure_ascii=False)]
        if increment_retry:
            sets.append("retry_count = retry_count + 1")
        params.extend([run_id, agent_name])
        with self._connect() as conn:
            conn.execute(
                f"UPDATE agent_runs SET {', '.join(sets)} WHERE run_id = ? AND agent_name = ?",
                params,
            )

    def list_agent_runs(self, run_id: str) -> List[AgentRun]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM agent_runs WHERE run_id = ? ORDER BY stage_seq", (run_id,)
            ).fetchall()
        return [self._row_to_agent_run(r) for r in rows]

    def get_resume_plan(self, run_id: str) -> dict:
        """恢复计划：完成态（success/degraded，output_path 可回读）与待重跑。

        待重跑包含 failed/paused/queued/running/blocked/skipped——
        blocked/skipped 也必须重新进入图结算：若其上游本次重跑成功，
        它们会被 ExecutionPlanner 重新判为 READY，而不是永远阻断。
        """
        run = self.get_run(run_id)
        if not run:
            raise ValueError(f"Run 不存在: {run_id}")
        agents = self.list_agent_runs(run_id)
        return {
            "run": run,
            "succeeded": [a for a in agents if a.status in AGENT_DONE_STATUSES],
            "pending": [a for a in agents if a.status not in AGENT_DONE_STATUSES],
        }

    def agent_states(self, run_id: str) -> dict:
        """导出 {agent_name: status}，供 ExecutionPlanner 做图状态快照/ready set 重算。"""
        return {a.agent_name: a.status for a in self.list_agent_runs(run_id)}

    def mark_orphaned_runs_paused(self) -> int:
        """进程异常退出后，启动时调用：running/queued run 一律转为可恢复暂停态。"""
        with self._connect() as conn:
            cursor = conn.execute(
                """UPDATE runs
                   SET status = ?, pause_reason = '应用已重启，可从断点继续',
                       updated_at = CURRENT_TIMESTAMP
                   WHERE status IN (?, ?)""",
                (RUN_PAUSED, RUN_RUNNING, RUN_QUEUED),
            )
            conn.execute(
                """UPDATE agent_runs SET status = ?
                   WHERE status IN (?, ?)""",
                (AGENT_PAUSED, AGENT_RUNNING, AGENT_QUEUED),
            )
            return cursor.rowcount

    # ── 内部 ──

    def _update_run(
        self, run_id: str, *, status: Optional[str] = None, current_stage: Optional[str] = None,
        error: Optional[str] = None, pause_reason: Optional[str] = None,
        clear_pause: bool = False,
    ):
        with self._connect() as conn:
            self._update_run_conn(conn, run_id, status=status, current_stage=current_stage,
                                  error=error, pause_reason=pause_reason, clear_pause=clear_pause)

    def _update_run_conn(
        self, conn: sqlite3.Connection, run_id: str, *, status: Optional[str] = None,
        current_stage: Optional[str] = None, error: Optional[str] = None,
        pause_reason: Optional[str] = None, clear_pause: bool = False,
    ):
        sets = ["updated_at = CURRENT_TIMESTAMP"]
        params: list = []
        if status is not None:
            sets.append("status = ?")
            params.append(status)
            if status in TERMINAL_RUN_STATUSES:
                sets.append("finished_at = CURRENT_TIMESTAMP")
        if current_stage is not None:
            sets.append("current_stage = ?")
            params.append(current_stage[:100])
        if error is not None:
            sets.append("error = ?")
            params.append(error[:2000])
        if pause_reason is not None:
            sets.append("pause_reason = ?")
            params.append(pause_reason[:500])
        if clear_pause:
            sets.extend(["pause_reason = ''", "finished_at = NULL"])

        # 终态保护：已结束的 Run 不允许被回写覆盖
        where = "run_id = ?"
        if status in (RUN_RUNNING, RUN_PAUSED, RUN_QUEUED):
            where += " AND status NOT IN ('success', 'completed_with_errors', 'failed')"
        params.append(run_id)
        conn.execute(f"UPDATE runs SET {', '.join(sets)} WHERE {where}", params)

    @staticmethod
    def _row_to_run(row: sqlite3.Row) -> Run:
        # 兼容旧库（无 user_id 列时取空串）
        user_id = row["user_id"] if "user_id" in row.keys() else ""
        return Run(
            run_id=row["run_id"], project_id=row["project_id"], status=row["status"],
            current_stage=row["current_stage"] or "", project_input=row["project_input"] or "",
            report_dir=row["report_dir"] or "", error=row["error"] or "",
            pause_reason=row["pause_reason"] or "",
            metadata=json.loads(row["metadata_json"] or "{}"),
            created_at=row["created_at"] or "", updated_at=row["updated_at"] or "",
            finished_at=row["finished_at"],
            user_id=user_id or "",
        )

    @staticmethod
    def _row_to_agent_run(row: sqlite3.Row) -> AgentRun:
        return AgentRun(
            run_id=row["run_id"], agent_name=row["agent_name"], stage_seq=row["stage_seq"],
            stage_key=row["stage_key"], label=row["label"], status=row["status"],
            started_at=row["started_at"], finished_at=row["finished_at"],
            retry_count=row["retry_count"] or 0, conclusion=row["conclusion"] or "",
            output_path=row["output_path"] or "", error=row["error"] or "",
            validation=json.loads(row["validation_json"] or "{}"),
            metadata=json.loads(row["metadata_json"] or "{}"),
        )
