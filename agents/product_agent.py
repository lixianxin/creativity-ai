# -*- coding: utf-8 -*-
"""产品设计 Agent：判断产品闭环、MVP合理性，不设计产品方案。"""
from agents.base_agent import BaseAgent
from schemas.agent_result import AgentResult


class ProductAgent(BaseAgent):
    prompt_name = "product_design"

    def run(self, project_input: str, context: dict = None) -> AgentResult:
        user_content = project_input
        raw = self._call_llm(user_content)

        lines = [l.strip() for l in raw.split("\n") if l.strip()]
        summary = lines[0][:100] if lines else raw[:100]
        risks = [l for l in lines if any(k in l for k in ["风险", "缺口", "不成立", "待验证", "冗余", "断裂"])][:5]
        evidence = [l for l in lines if any(k in l for k in ["MVP", "闭环", "功能", "核心任务", "可行"])][:5]

        return self._build_result(
            summary=summary,
            raw_output=raw,
            evidence=evidence,
            risks=risks,
            confidence=0.5,
            metadata={"chars": len(raw)},
        )
