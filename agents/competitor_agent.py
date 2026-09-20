# -*- coding: utf-8 -*-
"""竞品分析 Agent：三分法+去中介化+免费替代威胁。"""
from agents.base_agent import BaseAgent
from schemas.agent_result import AgentResult


class CompetitorAgent(BaseAgent):
    prompt_name = "competitor_analysis"

    def run(self, project_input: str, context: dict = None) -> AgentResult:
        raw = self._call_llm(project_input)
        lines = [l.strip() for l in raw.split("\n") if l.strip()]
        summary = lines[0][:100] if lines else raw[:100]
        risks = [l for l in lines if any(k in l for k in ["替代", "去中介化", "风险", "不成立", "待验证", "壁垒"])][:5]
        evidence = [l for l in lines if any(k in l for k in ["竞品", "三分法", "差异", "直接", "间接"])][:5]
        return self._build_result(summary=summary, raw_output=raw, evidence=evidence, risks=risks, confidence=0.5, metadata={"chars": len(raw)})
