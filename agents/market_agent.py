# -*- coding: utf-8 -*-
"""市场分析 Agent：关注市场空间、用户规模、替代方案、市场假设。"""
from agents.base_agent import BaseAgent
from schemas.agent_result import AgentResult


class MarketAgent(BaseAgent):
    prompt_name = "market_analysis"

    def run(self, project_input: str, context: dict = None) -> AgentResult:
        user_content = project_input
        raw = self._call_llm(user_content)

        lines = [l.strip() for l in raw.split("\n") if l.strip()]
        summary = lines[0][:100] if lines else raw[:100]
        risks = [l for l in lines if any(k in l for k in ["风险", "缺口", "不足", "待验证", "缺失", "替代"])][:5]
        evidence = [l for l in lines if any(k in l for k in ["TAM", "SAM", "SOM", "规模", "数据", "估算"])][:5]

        return self._build_result(
            summary=summary,
            raw_output=raw,
            evidence=evidence,
            risks=risks,
            confidence=0.5,
            metadata={"chars": len(raw)},
        )
