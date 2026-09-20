# -*- coding: utf-8 -*-
"""用户洞察 Agent：复用 agents/prompts/user_insight_v1.md。"""
from agents.base_agent import BaseAgent
from schemas.agent_result import AgentResult


class UserInsightAgent(BaseAgent):
    prompt_name = "user_insight"

    def run(self, project_input: str, context: dict = None) -> AgentResult:
        user_content = project_input
        raw = self._call_llm(user_content)

        # 从原始输出中提取摘要和风险（简单启发式，MVP 阶段够用）
        lines = [l.strip() for l in raw.split("\n") if l.strip()]
        summary = lines[0][:100] if lines else raw[:100]
        risks = [l for l in lines if "风险" in l or "缺口" in l or "不足" in l or "待验证" in l][:5]
        evidence = [l for l in lines if "证据" in l or "数据" in l or "访谈" in l][:5]

        return self._build_result(
            summary=summary,
            raw_output=raw,
            evidence=evidence,
            risks=risks,
            confidence=0.5,  # MVP 阶段默认中等置信度
            metadata={"chars": len(raw)},
        )
