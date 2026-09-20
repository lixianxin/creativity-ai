# -*- coding: utf-8 -*-
"""项目上下文管理：保存项目信息与各 Agent 报告，供下游 Agent 读取。"""
from dataclasses import dataclass, field
from typing import List

from schemas.agent_result import AgentResult


@dataclass
class ProjectContext:
    """委员会运行时上下文。贯穿整个 pipeline。"""
    project_info: str
    reports: List[AgentResult] = field(default_factory=list)

    def add_report(self, report: AgentResult):
        self.reports.append(report)

    def get_report(self, agent_name: str) -> AgentResult:
        """按名称获取某份报告。"""
        for r in self.reports:
            if r.agent_name == agent_name:
                return r
        return None

    def format_reports_for(self, include_names: List[str] = None) -> str:
        """格式化指定报告为下游可读文本。不传 include_names 则返回全部。"""
        labels = {
            "user_insight": "用户洞察官", "market_analysis": "市场分析官",
            "competitor_analysis": "竞品分析官", "product_design": "产品设计官",
            "business_model": "商业模式官", "finance": "财务分析官",
            "growth_ops": "增长运营官", "risk_review": "风险审查官",
            "red_team": "红队质疑官", "commander": "创业总指挥",
            "project_review": "项目评审官", "pitch_defense": "路演答辩官",
        }
        parts = []
        for r in self.reports:
            if include_names and r.agent_name not in include_names:
                continue
            name = labels.get(r.agent_name, r.agent_name)
            parts.append(f"【{name}报告】\n{r.raw_output}")
        return "\n\n".join(parts)
