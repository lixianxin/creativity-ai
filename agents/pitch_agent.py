# -*- coding: utf-8 -*-
"""路演答辩官 Agent：模拟评委追问+手牌三档+口径雷区+击穿判断。
不替项目方编数字，不重做终审，只诊断'上台会不会被问穿'。"""
from agents.base_agent import BaseAgent
from schemas.agent_result import AgentResult


class PitchAgent(BaseAgent):
    prompt_name = "pitch_defense"

    def run(self, project_input: str, context: dict = None) -> AgentResult:
        reports = (context or {}).get("reports", [])
        report_text = self._format_reports(reports)
        user_content = (
            f"{project_input}\n\n"
            f"==== 委员会全部报告 ====\n{report_text}\n\n"
            f"请模拟真实评委/投资人追问，基于上述材料评估答辩表现，给出路演结论。"
        )
        raw = self._call_llm(user_content, max_tokens=20000)

        lines = [l.strip() for l in raw.split("\n") if l.strip()]
        summary = lines[0][:100] if lines else raw[:100]

        # 提取路演结论
        conclusion = ""
        for line in lines:
            if any(k in line for k in ["可以路演", "有条件路演", "暂不建议", "无法评估"]):
                conclusion = line.strip()
                break
        if not conclusion and "暂不建议" in raw:
            conclusion = "暂不建议路演"

        # 击穿统计
        pierced = raw.count("被击穿") + raw.count("击穿")
        risks = [l for l in lines if any(k in l for k in ["击穿", "无法回答", "雷区", "暂不建议"])][:6]
        evidence = [l for l in lines if any(k in l for k in ["亮点", "可防御", "有证据"])][:5]

        return self._build_result(
            summary=summary,
            raw_output=raw,
            evidence=evidence,
            risks=risks,
            confidence=0.6,
            conclusion=conclusion,
            metadata={"pierced_count": pierced, "chars": len(raw)},
        )

    def _format_reports(self, reports):
        labels = {
            "user_insight": "用户洞察官", "market_analysis": "市场分析官",
            "competitor_analysis": "竞品分析官", "product_design": "产品设计官",
            "business_model": "商业模式官", "finance": "财务分析官",
            "growth_ops": "增长运营官", "risk_review": "风险审查官",
            "red_team": "红队质疑官", "commander": "创业总指挥",
            "project_review": "项目评审官",
        }
        parts = []
        for r in reports:
            name = labels.get(r.agent_name, r.agent_name)
            parts.append(f"【{name}报告】\n{r.raw_output}")
        return "\n\n".join(parts)
