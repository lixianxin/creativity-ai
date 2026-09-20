# -*- coding: utf-8 -*-
"""财务分析 Agent：收入测算/成本结构/单位经济，不算金额只判断可计算性。"""
from agents.base_agent import BaseAgent
from schemas.agent_result import AgentResult


class FinanceAgent(BaseAgent):
    prompt_name = "finance"

    def run(self, project_input: str, context: dict = None) -> AgentResult:
        raw = self._call_llm(project_input)
        lines = [l.strip() for l in raw.split("\n") if l.strip()]
        summary = lines[0][:100] if lines else raw[:100]
        risks = [l for l in lines if any(k in l for k in ["无法", "缺失", "不足", "风险", "待验证", "不可靠"])][:5]
        evidence = [l for l in lines if any(k in l for k in ["LTV", "CAC", "收入", "成本", "利润", "模型"])][:5]
        conclusion = "无法可靠计算" if any(k in raw for k in ["无法可靠计算", "无法计算", "不可靠"]) else "可计算"
        return self._build_result(summary=summary, raw_output=raw, evidence=evidence, risks=risks, confidence=0.4, conclusion=conclusion, metadata={"chars": len(raw)})
