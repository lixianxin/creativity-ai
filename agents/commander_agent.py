# -*- coding: utf-8 -*-
"""创业总指挥 Agent：读取全部前置报告，输出阶段判断+核心矛盾+3行动。不重新分析。"""
from agents.base_agent import BaseAgent
from schemas.agent_result import AgentResult, STATUS_SUCCESS


class CommanderAgent(BaseAgent):
    prompt_name = "commander"

    def run(self, project_input: str, context: dict = None) -> AgentResult:
        reports = (context or {}).get("reports", [])
        # 格式化前置报告
        report_text = self._format_reports(reports)
        user_content = (
            f"{project_input}\n\n"
            f"==== 委员会各Agent报告 ====\n{report_text}\n\n"
            f"请基于上述报告，提炼核心矛盾、判定项目阶段、给出3个可执行行动。"
        )
        raw = self._call_llm(user_content, max_tokens=20000)

        lines = [l.strip() for l in raw.split("\n") if l.strip()]
        summary = lines[0][:100] if lines else raw[:100]

        # 提取阶段判断（Phase 7-9：与 commander_v1.md 模板四选一保持一致）
        conclusion = ""
        for line in lines:
            if any(k in line for k in ["想法验证", "方案修正", "路演准备", "可进入路演"]):
                conclusion = line.strip()
                break

        risks = [l for l in lines if any(k in l for k in ["致命", "高风险", "矛盾", "瓶颈", "阻断"])][:5]
        evidence = [l for l in lines if any(k in l for k in ["行动", "建议", "下一步", "优先"])][:5]

        return self._build_result(
            summary=summary,
            raw_output=raw,
            evidence=evidence,
            risks=risks,
            confidence=0.6,
            conclusion=conclusion,
            metadata={"chars": len(raw)},
        )

    def _format_reports(self, reports):
        labels = {
            "user_insight": "用户洞察官", "market_analysis": "市场分析官",
            "competitor_analysis": "竞品分析官", "product_design": "产品设计官",
            "business_model": "商业模式官", "finance": "财务分析官",
            "growth_ops": "增长运营官", "risk_review": "风险审查官",
            "red_team": "红队质疑官",
        }
        parts = []
        for r in reports:
            name = labels.get(r.agent_name, r.agent_name)
            parts.append(f"【{name}报告】\n{r.raw_output}")
        return "\n\n".join(parts)
