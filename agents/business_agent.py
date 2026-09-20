# -*- coding: utf-8 -*-
"""商业模式 Agent：判断付费方、收入来源、成本结构假设，不给出定价方案。"""
from agents.base_agent import BaseAgent
from schemas.agent_result import AgentResult


class BusinessAgent(BaseAgent):
    prompt_name = "business_model"

    def run(self, project_input: str, context: dict = None) -> AgentResult:
        user_content = project_input
        raw = self._call_llm(user_content)

        lines = [l.strip() for l in raw.split("\n") if l.strip()]
        summary = lines[0][:100] if lines else raw[:100]
        risks = [l for l in lines if any(k in l for k in ["风险", "断点", "不成立", "待验证", "缺失", "付费"] )][:5]
        evidence = [l for l in lines if any(k in l for k in ["付费", "收入", "成本", "价值交换", "模式"])][:5]

        return self._build_result(
            summary=summary,
            raw_output=raw,
            evidence=evidence,
            risks=risks,
            confidence=0.5,
            metadata={"chars": len(raw)},
        )
