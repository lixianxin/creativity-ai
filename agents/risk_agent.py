# -*- coding: utf-8 -*-
"""风险审查 Agent：检查合规/数据/法律/安全，保留红线一票否决机制。读取所有前置报告。"""
from agents.base_agent import BaseAgent
from schemas.agent_result import AgentResult


def _format_all_reports(reports: list) -> str:
    """把所有前置报告（含红队）格式化为风险官可读上下文。"""
    labels = {
        "user_insight": "用户洞察官", "market_analysis": "市场分析官",
        "competitor_analysis": "竞品分析官", "product_design": "产品设计官",
        "business_model": "商业模式官", "finance": "财务分析官",
        "growth_ops": "增长运营官", "red_team": "红队质疑官",
    }
    parts = []
    for r in reports:
        name = labels.get(r.agent_name, r.agent_name)
        parts.append(f"【{name}报告摘要】\n{r.summary}")
    return "\n\n".join(parts)


class RiskAgent(BaseAgent):
    prompt_name = "risk_review"

    def run(self, project_input: str, context: dict = None) -> AgentResult:
        reports = (context or {}).get("reports", [])
        prior = _format_all_reports(reports)
        user_content = (
            f"{project_input}\n\n"
            f"==== 前置全部报告 ====\n{prior}\n\n"
            f"请审查合规/数据/内容/安全/伦理/落地六类风险，识别致命红线并判断是否阻断上线/路演。"
        )
        raw = self._call_llm(user_content)

        lines = [l.strip() for l in raw.split("\n") if l.strip()]
        summary = lines[0][:100] if lines else raw[:100]
        fatal_risks = [l for l in lines if any(k in l for k in ["致命", "红线", "一票否决", "阻断", "不得", "备案", "授权"])][:6]
        blocking = any(k in raw for k in ["致命风险", "一票否决", "不得直接", "阻断"])

        return self._build_result(
            summary=summary,
            raw_output=raw,
            evidence=[],
            risks=fatal_risks,
            confidence=0.6 if blocking else 0.4,
            metadata={"fatal_risks": fatal_risks, "blocking": blocking, "chars": len(raw)},
        )
