# -*- coding: utf-8 -*-
"""统一 Agent 输出结构。所有 Agent 必须返回此结构，便于后续 Agent 串联读取。"""
from dataclasses import dataclass, field
from typing import List, Dict, Any


# Agent 运行状态枚举（业务结果层）
STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"
# Phase 7-7：图状态层（AgentRun.status 权威集合见 core/run.py）。
# degraded 的业务结果本身仍为 success（metadata.degraded_inputs 标记缺失输入）；
# blocked/skipped 仅用于不调用 LLM 的图占位结果。
STATUS_BLOCKED = "blocked"      # 硬依赖 FAILED，本节点被阻断、未执行
STATUS_DEGRADED = "degraded"    # 软依赖缺失但本节点仍成功执行（图状态）
STATUS_SKIPPED = "skipped"      # 硬依赖被阻断/跳过（断链传递），未执行


@dataclass
class AgentResult:
    agent_name: str              # Agent 名称，如 "user_insight"
    status: str = STATUS_PENDING # 运行状态：pending/running/success/failed
    summary: str = ""            # 一句话结论摘要
    conclusion: str = ""         # 结论档位（如"暂缓""暂不建议路演"等）
    evidence: List[str] = field(default_factory=list)   # 证据/依据列表
    risks: List[str] = field(default_factory=list)      # 风险/缺口列表
    confidence: float = 0.0      # 置信度 0.0-1.0
    raw_output: str = ""         # 原始 LLM 输出（完整报告）
    metadata: Dict[str, Any] = field(default_factory=dict)  # 附加信息（耗时/token等）

    def to_dict(self) -> dict:
        return {
            "agent_name": self.agent_name,
            "status": self.status,
            "summary": self.summary,
            "conclusion": self.conclusion,
            "evidence": self.evidence,
            "risks": self.risks,
            "confidence": self.confidence,
            "raw_output": self.raw_output,
            "metadata": self.metadata,
        }
