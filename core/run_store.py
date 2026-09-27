# -*- coding: utf-8 -*-
"""RunStore：Run / AgentRun 持久化（Phase 7-5 起，SQLite / PostgreSQL 双后端）。

借鉴 BossHunter scoring_run_store：
- 每个 Agent 完成立即 checkpoint（status + output_path + validation + 耗时）；
- 终态 run 不允许被回写覆盖；
- 应用启动时把异常退出遗留的 running/queued run 接管为 paused（可恢复）；
- resume 时精确返回未成功的 Agent 列表，已成功的直接跳过。

刻意只建两张表，不复制 BossHunter 几十张表的迁移体系。

后端选择（显式配置切换，非静默回退）：
- 构造时传 db_path（全部离线测试的用法）→ SQLite；
- 不传 db_path 且环境变量 SUPABASE_DB_URL 存在 → PostgreSQL（Supabase，
  直连 session pooler；行级隔离由 RLS 按 app.user_id 会话变量强制执行）；
- 其余（本地开发无 PG 配置）→ SQLite 默认路径。

两种后端共用同一份业务 SQL（? 占位符），方言差异由 _PgConn 适配器消化。
"""
from __future__ import annotations

import json
import os
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


def _ts(v) -> Optional[str]:
    """时间戳归一：SQLite 返回 str，PG 返回 datetime；统一为 str 供 Run 模型使用。"""
    if v is None:
        return None
    if hasattr(v, "isoformat"):
        return v.isoformat(sep=" ")
    return v


def _json(v):
    """JSON 列归一：PG 的 JSONB 由 psycopg2 反序列化为 dict，SQLite 是 str。"""
    if isinstance(v, (dict, list)):
        return v
    return json.loads(v or "{}")


class _PgConn:
    """psycopg2 连接适配器：让 PG 后端复用同一份 SQLite 方言（? 占位符）SQL。

    语义对齐 sqlite3.Connection 的用法：
    - execute/executemany：`?` → `%s` 后透传（本仓库 SQL 无字面量 `?`，已核实）；
      每次 execute 返回独立 cursor（sqlite3 语义），保证 rowcount 在多次
      execute 之间互不覆盖（mark_orphaned_runs_paused 依赖此行为）；
    - with 语句：成功 commit / 异常 rollback / 退出 close（短连接模式）；
    - 建连即以事务级 set_config 绑定 app.user_id，RLS 据此隔离行。
    """

    def __init__(self, conn, user_id: str):
        import psycopg2.extras
        self._conn = conn
        self._dict_cur = lambda: conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        with self._dict_cur() as cur:
            cur.execute("SELECT set_config('app.user_id', %s, true)", (user_id or "",))

    def execute(self, sql: str, params=()):
        cur = self._dict_cur()
        cur.execute(sql.replace("?", "%s"), tuple(params))
        return cur

    def executemany(self, sql: str, seq):
        cur = self._dict_cur()
        cur.executemany(sql.replace("?", "%s"), [tuple(p) for p in seq])
        return cur

    def executescript(self, script: str):
        with self._conn.cursor() as cur:
            cur.execute(script)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type is None:
                self._conn.commit()
            else:
                self._conn.rollback()
        finally:
            self._conn.close()
        return False


class RunStore:
    """每次操作开短连接，天然支持并行阶段（1-7 Agent）多线程写入。

    user_id 在构造时绑定（前端传当前登录用户）：create_run 未显式传
    user_id 时自动回填绑定值；PG 后端据此以 RLS 强制行级隔离。
    """

    def __init__(self, db_path=None, user_id: str = ""):
        self.user_id = user_id or ""
        self.use_pg = db_path is None and bool(os.environ.get("SUPABASE_DB_URL"))
        if self.use_pg:
            self.db_path = None
        else:
            self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_tables()

    def _connect(self):
        if self.use_pg:
            return self._connect_pg()
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def _connect_pg(self):
        import psycopg2  # 延迟导入：SQLite 路径与离线测试环境无需安装
        conn = psycopg2.connect(os.environ["SUPABASE_DB_URL"], connect_timeout=10)
        return _PgConn(conn, self.user_id)

    def _init_tables(self):
        if self.use_pg:
            self._init_tables_pg()
            return
        with self._connect() as conn:
            # WAL：1-7 专家 Agent 并行落 checkpoint 时避免写锁互相阻塞
            conn.execute("PRAGMA journal_mode=WAL")
            # 兼容旧库迁移：若 runs 表已存在但缺少 user_id 列则补上
            cols = {r[1] for r in conn.execute("PRAGMA table_info(runs)").fetchall()}
            if cols and "user_id" not in cols:
                conn.execute("ALTER TABLE runs ADD COLUMN user_id TEXT DEFAULT ''")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_user ON runs(user_id)")
            # agent_runs.user_id：与 PG 版对齐的反规范化隔离列
            cols = {r[1] for r in conn.execute("PRAGMA table_info(agent_runs)").fetchall()}
            if cols and "user_id" not in cols:
                conn.execute("ALTER TABLE agent_runs ADD COLUMN user_id TEXT DEFAULT ''")
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
                    user_id TEXT DEFAULT '',
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

    def _init_tables_pg(self):
        """PG 建表/RLS：唯一 DDL 源在 supabase/migrations/0001_runstore.sql。

        生产应用以最小权限角色 runstore_app 连接（无权 CREATE/ALTER/POLICY），
        表须由迁移脚本以 postgres 身份预先开通；两张表都在则直接返回。
        仅当表缺失时才尝试执行 DDL（此时连接通常是 postgres，如本地/新环境）。
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT to_regclass('public.runs') AS r, "
                "to_regclass('public.agent_runs') AS a"
            ).fetchone()
            if row["r"] and row["a"]:
                return
            ddl_path = PROJECT_ROOT / "supabase" / "migrations" / "0001_runstore.sql"
            conn.executescript(ddl_path.read_text(encoding="utf-8"))

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
        """创建 Run，并把 12 棒预置为 queued（resume 时据此知道哪些没跑过）。

        user_id 未显式传时回退到构造时绑定的 self.user_id（前端注入当前登录用户）。
        """
        run_id = run_id or f"run_{uuid.uuid4().hex[:12]}"
        user_id = user_id or self.user_id
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO runs (run_id, user_id, project_id, status, project_input, report_dir, metadata_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (run_id, user_id, project_id, RUN_QUEUED, project_input, report_dir,
                 json.dumps(metadata or {}, ensure_ascii=False)),
            )
            conn.executemany(
                """INSERT INTO agent_runs (run_id, user_id, agent_name, stage_seq, stage_key, label, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                [(run_id, user_id, agent_name, seq, key, label, AGENT_QUEUED)
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
        self, conn, run_id: str, *, status: Optional[str] = None,
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
    def _row_to_run(row) -> Run:
        # 兼容旧库（无 user_id 列时取空串）
        user_id = row["user_id"] if "user_id" in row.keys() else ""
        return Run(
            run_id=row["run_id"], project_id=row["project_id"], status=row["status"],
            current_stage=row["current_stage"] or "", project_input=row["project_input"] or "",
            report_dir=row["report_dir"] or "", error=row["error"] or "",
            pause_reason=row["pause_reason"] or "",
            metadata=_json(row["metadata_json"]),
            created_at=_ts(row["created_at"]) or "", updated_at=_ts(row["updated_at"]) or "",
            finished_at=_ts(row["finished_at"]),
            user_id=user_id or "",
        )

    @staticmethod
    def _row_to_agent_run(row) -> AgentRun:
        return AgentRun(
            run_id=row["run_id"], agent_name=row["agent_name"], stage_seq=row["stage_seq"],
            stage_key=row["stage_key"], label=row["label"], status=row["status"],
            started_at=_ts(row["started_at"]), finished_at=_ts(row["finished_at"]),
            retry_count=row["retry_count"] or 0, conclusion=row["conclusion"] or "",
            output_path=row["output_path"] or "", error=row["error"] or "",
            validation=_json(row["validation_json"]),
            metadata=_json(row["metadata_json"]),
        )
