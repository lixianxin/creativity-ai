# -*- coding: utf-8 -*-
"""Run / AgentRun 数据模型与状态机（Phase 7-5）。

把"我有 12 个 Agent"升级为"我有一套可恢复的多 Agent 执行系统"：
- Run：一次完整的 12 棒委员会审查；
- AgentRun：Run 内单个 Agent 的执行记录（checkpoint）。

状态流转：
  Run:      queued → running → success / completed_with_errors
                              ↘ failed / paused（paused 可 resume）
  AgentRun: queued → running → success / degraded / failed
                     ↘ paused（随 Run 暂停）
  图阻断（Phase 7-7，不调用 LLM）：
    hard 依赖 FAILED                 → blocked（被硬阻断）
    hard 依赖 blocked/skipped        → skipped（断链传递）
    soft 依赖失败/阻断但本节点执行成功 → degraded（降级继续）
  resume 时 failed/blocked/skipped/paused/queued 全部回到 queued，
  由 ExecutionPlanner 依据最新图状态重新计算 ready set；success/degraded 不重跑。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ── Run 状态 ──
RUN_QUEUED = "queued"
RUN_RUNNING = "running"
RUN_SUCCESS = "success"
RUN_COMPLETED_WITH_ERRORS = "completed_with_errors"
RUN_FAILED = "failed"
RUN_PAUSED = "paused"

TERMINAL_RUN_STATUSES = {RUN_SUCCESS, RUN_COMPLETED_WITH_ERRORS, RUN_FAILED}

# ── AgentRun 状态（图状态机，单一权威定义） ──
AGENT_QUEUED = "queued"
AGENT_RUNNING = "running"
AGENT_SUCCESS = "success"
AGENT_FAILED = "failed"
AGENT_PAUSED = "paused"
AGENT_BLOCKED = "blocked"      # 硬依赖 FAILED：本节点不执行
AGENT_DEGRADED = "degraded"    # 软依赖缺失，本节点仍成功执行（有产出）
AGENT_SKIPPED = "skipped"      # 硬依赖 blocked/skipped：断链，本节点不执行

# 已有产出、可满足下游依赖、resume 直接回读不重跑的完成态
AGENT_DONE_STATUSES = {AGENT_SUCCESS, AGENT_DEGRADED}
# resume 时需要重新进入 queued 由图重新结算的未完成态
AGENT_RESUMABLE_STATUSES = {
    AGENT_PAUSED, AGENT_FAILED, AGENT_QUEUED, AGENT_RUNNING,
    AGENT_BLOCKED, AGENT_SKIPPED,
}
# 已结算的终态（checkpoint 写 finished_at）
TERMINAL_AGENT_STATUSES = {
    AGENT_SUCCESS, AGENT_FAILED, AGENT_SKIPPED,
    AGENT_BLOCKED, AGENT_DEGRADED,
}


@dataclass
class Run:
    run_id: str
    project_id: str = ""
    status: str = RUN_QUEUED
    current_stage: str = ""              # 当前/最后执行到的 stage key
    project_input: str = ""
    report_dir: str = ""
    error: str = ""
    pause_reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    finished_at: Optional[str] = None

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class AgentRun:
    run_id: str
    agent_name: str                     # prompt_name，如 risk_review
    stage_seq: str = ""                 # "01"
    stage_key: str = ""                 # "risk"
    label: str = ""
    status: str = AGENT_QUEUED
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    retry_count: int = 0
    conclusion: str = ""
    output_path: str = ""
    error: str = ""
    validation: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return self.__dict__.copy()
