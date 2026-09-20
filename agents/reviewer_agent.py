# -*- coding: utf-8 -*-
"""项目评审官 Agent：五维评分+证据链审计+冲突终裁+红线一票否决+路演准入。
与总指挥区别：总指挥管'现在做什么'，评审官管'够不够格路演'。"""
from agents.base_agent import BaseAgent
from schemas.agent_result import AgentResult


class ReviewerAgent(BaseAgent):
    prompt_name = "project_review"

    def run(self, project_input: str, context: dict = None) -> AgentResult:
        reports = (context or {}).get("reports", [])
        report_text = self._format_reports(reports)
        user_content = (
            f"{project_input}\n\n"
            f"==== 委员会各Agent报告 ====\n{report_text}\n\n"
            f"请基于上述报告进行五维终审评分、证据链审计、冲突终裁、红线检查，给出终审结论。"
        )
        raw = self._call_llm(user_content, max_tokens=20000)

        lines = [l.strip() for l in raw.split("\n") if l.strip()]
        summary = lines[0][:100] if lines else raw[:100]

        # 提取终审结论：优先找"终审结论"标题下的行，避免抓到引用红队报告的行
        conclusion = ""
        for i, line in enumerate(lines):
            if "终审结论" in line and i + 1 < len(lines):
                conclusion = lines[i + 1].strip()
                break
        # 回退：找不含"报告"且含结论关键词的行
        if not conclusion:
            for line in lines:
                if any(k in line for k in ["准入路演", "有条件准入", "暂缓", "材料不齐", "不予终审"]):
                    if "报告" not in line and "红队" not in line:
                        conclusion = line.strip()
                        break
        if not conclusion and "暂缓" in raw:
            conclusion = "暂缓"

        # 红线检查
        redline = any(k in raw for k in ["一票否决", "不得直接准入", "红线未清"])
        risks = [l for l in lines if any(k in l for k in ["致命", "红线", "一票否决", "阻断", "不得"])][:6]

        return self._build_result(
            summary=summary,
            raw_output=raw,
            evidence=[],
            risks=risks,
            confidence=0.7,
            conclusion=conclusion,
            metadata={"redline_triggered": redline, "chars": len(raw)},
        )

    def _format_reports(self, reports):
        labels = {
            "user_insight": "用户洞察官", "market_analysis": "市场分析官",
            "competitor_analysis": "竞品分析官", "product_design": "产品设计官",
            "business_model": "商业模式官", "finance": "财务分析官",
            "growth_ops": "增长运营官", "risk_review": "风险审查官",
            "red_team": "红队质疑官", "commander": "创业总指挥",
        }
        parts = []
        for r in reports:
            name = labels.get(r.agent_name, r.agent_name)
            parts.append(f"【{name}报告】\n{r.raw_output}")
        return "\n\n".join(parts)
