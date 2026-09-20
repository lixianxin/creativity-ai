# -*- coding: utf-8 -*-
"""红队质疑 Agent：不做分析，专门攻击核心假设。读取前置专家报告。"""
from agents.base_agent import BaseAgent
from schemas.agent_result import AgentResult


def _format_prior_reports(reports: list) -> str:
    """把前置报告格式化为红队可读的上下文。"""
    labels = {
        "user_insight": "用户洞察官", "market_analysis": "市场分析官",
        "product_design": "产品设计官", "business_model": "商业模式官",
        "finance": "财务分析官", "growth_ops": "增长运营官",
    }
    parts = []
    for r in reports:
        name = labels.get(r.agent_name, r.agent_name)
        parts.append(f"【{name}报告摘要】\n{r.summary}")
    return "\n\n".join(parts)


class RedTeamAgent(BaseAgent):
    prompt_name = "red_team"

    def run(self, project_input: str, context: dict = None) -> AgentResult:
        reports = (context or {}).get("reports", [])
        prior = _format_prior_reports(reports)
        user_content = (
            f"{project_input}\n\n"
            f"==== 前置专家报告 ====\n{prior}\n\n"
            f"请基于上述材料，攻击项目核心假设，找出致命与高风险问题。"
        )
        raw = self._call_llm(user_content)

        lines = [l.strip() for l in raw.split("\n") if l.strip()]
        summary = lines[0][:100] if lines else raw[:100]
        # 攻击点和评委追问
        attack_points = [l for l in lines if any(k in l for k in ["致命", "高风险", "假设", "不成立", "替代"])][:6]
        judge_questions = [l for l in lines if "？" in l or "?" in l or "凭什么" in l or "为什么" in l][:5]

        return self._build_result(
            summary=summary,
            raw_output=raw,
            evidence=judge_questions,
            risks=attack_points,
            confidence=0.5,
            metadata={"attack_points": attack_points, "judge_questions": judge_questions, "chars": len(raw)},
        )
