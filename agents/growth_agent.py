# -*- coding: utf-8 -*-
"""增长运营 Agent：AARRR飞轮/冷启动/渠道，不算CAC只判断飞轮是否存在。"""
from agents.base_agent import BaseAgent
from schemas.agent_result import AgentResult


class GrowthAgent(BaseAgent):
    prompt_name = "growth_ops"

    def run(self, project_input: str, context: dict = None) -> AgentResult:
        raw = self._call_llm(project_input)
        lines = [l.strip() for l in raw.split("\n") if l.strip()]
        summary = lines[0][:100] if lines else raw[:100]
        risks = [l for l in lines if any(k in l for k in ["无飞轮", "风险", "缺口", "待验证", "停止", "不可持续"])][:5]
        evidence = [l for l in lines if any(k in l for k in ["飞轮", "AARRR", "渠道", "激活", "留存", "冷启动"])][:5]
        return self._build_result(summary=summary, raw_output=raw, evidence=evidence, risks=risks, confidence=0.5, metadata={"chars": len(raw)})
