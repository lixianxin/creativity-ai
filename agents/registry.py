# -*- coding: utf-8 -*-
"""AgentRegistry：Agent 注册器 + 显式依赖声明（Phase 7-7 升级为 Execution Graph 事实源）。

Pipeline 不再关心"这个类叫不叫 RiskAgent"，只关心"我要运行 risk_review"。
新增第 13 个 Agent 时，只需 register 一个 AgentSpec，无需改编排器分支。

Phase 7-7 起，依赖分为两条边（failure policy 附着在边上，而非节点上）：
- dependencies（hard，硬依赖）：依赖 FAILED → 本节点 BLOCKED；
  依赖 BLOCKED/SKIPPED → 本节点 SKIPPED（断链传递）。
- soft_dependencies（soft，软依赖）：依赖 FAILED/BLOCKED/SKIPPED 时本节点
  仍被调度执行，以 DEGRADED 状态继续（metadata.degraded_inputs 记录缺失输入）。

ExecutionPlanner（core/execution_graph.py）据此生成 DAG、拓扑分层与 ready set，
并行不再写死在 orchestrator 里，而是"无依赖依赖满足的节点自然同层并行"。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


# 能力标记
CAP_ANALYSIS = "analysis"              # 专家分析
CAP_BLOCKING = "blocking"              # 可产出红线/阻断信号
CAP_ADVERSARIAL = "adversarial"        # 对抗角色（红队）
CAP_PROCESS_CHAIR = "process_chair"    # 流程主持（总指挥）
CAP_REDLINE_VETO = "redline_veto"      # 红线一票否决终裁
CAP_FINAL_JUDGE = "final_judge"        # 准入终审
CAP_DEFENSE_COACH = "defense_coach"    # 路演诊断

GROUP_EXPERT = "专家委员会"
GROUP_ADVERSARIAL = "对抗委员会"
GROUP_DECISION = "决策委员会"


@dataclass(frozen=True)
class AgentSpec:
    name: str                                   # 唯一标识 = prompt_name = agent_name
    seq: str                                    # 棒次 "01"
    stage_key: str                              # 报告文件 key，如 "risk"
    label: str                                  # 中文角色名
    group: str
    import_path: str                            # 模块路径
    class_name: str                             # Agent 类名
    dependencies: List[str] = field(default_factory=list)       # 硬依赖：失败→BLOCKED
    soft_dependencies: List[str] = field(default_factory=list)  # 软依赖：失败→DEGRADED 继续
    capabilities: List[str] = field(default_factory=list)

    @property
    def all_dependencies(self) -> List[str]:
        """全部上游（硬依赖在前，软依赖在后，保序去重）。"""
        seen, out = set(), []
        for n in list(self.dependencies) + list(self.soft_dependencies):
            if n not in seen:
                seen.add(n)
                out.append(n)
        return out

    @property
    def needs_context(self) -> bool:
        return bool(self.dependencies or self.soft_dependencies)

    def build_agent(self):
        """动态导入并实例化。"""
        import importlib
        mod = importlib.import_module(self.import_path)
        return getattr(mod, self.class_name)()


class AgentRegistry:
    def __init__(self):
        self._specs: Dict[str, AgentSpec] = {}

    def register(self, spec: AgentSpec) -> None:
        if spec.name in self._specs:
            raise ValueError(f"Agent 重复注册: {spec.name}")
        self._specs[spec.name] = spec

    def get(self, name: str) -> AgentSpec:
        if name not in self._specs:
            raise KeyError(f"未注册的 Agent: {name}")
        return self._specs[name]

    def has(self, name: str) -> bool:
        return name in self._specs

    def all(self) -> List[AgentSpec]:
        """按棒次顺序返回全部 spec。"""
        return sorted(self._specs.values(), key=lambda s: s.seq)

    def by_group(self, group: str) -> List[AgentSpec]:
        return [s for s in self.all() if s.group == group]

    def parallel_ready(self) -> List[AgentSpec]:
        """无任何前置依赖、可立即并行的 Agent（DAG 第 0 层：8 个独立分析节点）。"""
        return [s for s in self.all() if not s.all_dependencies]

    def stage_specs_tuples(self):
        """给 RunStore 预置 checkpoint 用：(seq, stage_key, name, label)。"""
        return [(s.seq, s.stage_key, s.name, s.label) for s in self.all()]


# ── 12 Agent 注册（DAG 单一事实源，Phase 7-7 显式依赖图） ──
_EXPERT_7 = [
    ("01", "user",       "user_insight",       "用户洞察官", "agents.user_agent",       "UserInsightAgent"),
    ("02", "market",     "market_analysis",    "市场分析官", "agents.market_agent",     "MarketAgent"),
    ("03", "competitor", "competitor_analysis","竞品分析官", "agents.competitor_agent", "CompetitorAgent"),
    ("04", "product",    "product_design",     "产品设计官", "agents.product_agent",    "ProductAgent"),
    ("05", "business",   "business_model",     "商业模式官", "agents.business_agent",   "BusinessAgent"),
    ("06", "finance",    "finance",            "财务分析官", "agents.finance_agent",    "FinanceAgent"),
    ("07", "growth",     "growth_ops",         "增长运营官", "agents.growth_agent",     "GrowthAgent"),
]
_EXPERT_NAMES = [name for _, _, name, _, _, _ in _EXPERT_7]

# 红队输入：4 份专家报告（用户/市场/竞品/商业模式）。缺任一份不致命——
# 红队仍可对其余假设发起攻击，故全部声明为软依赖（失败 → DEGRADED 继续）。
_RED_TEAM_SOFT = ["user_insight", "market_analysis", "competitor_analysis", "business_model"]


def build_default_registry() -> AgentRegistry:
    reg = AgentRegistry()

    # 1-7 专家：只读项目输入，无前置依赖（DAG 第 0 层，天然可并行）
    for seq, key, name, label, path, cls in _EXPERT_7:
        reg.register(AgentSpec(
            name=name, seq=seq, stage_key=key, label=label, group=GROUP_EXPERT,
            import_path=path, class_name=cls,
            capabilities=[CAP_ANALYSIS],
        ))

    # 8 风险审查官：独立审查原始想法的六类风险（合规/数据/内容/安全/伦理/落地），
    # 不前置消费专家报告，与 7 专家同处 DAG 第 0 层并行。
    reg.register(AgentSpec(
        name="risk_review", seq="08", stage_key="risk", label="风险审查官",
        group=GROUP_EXPERT, import_path="agents.risk_agent", class_name="RiskAgent",
        capabilities=[CAP_ANALYSIS, CAP_BLOCKING],
    ))

    # 9 红队质疑官：软依赖 4 份专家报告，缺失则降级继续
    reg.register(AgentSpec(
        name="red_team", seq="09", stage_key="red_team", label="红队质疑官",
        group=GROUP_ADVERSARIAL, import_path="agents.red_team_agent", class_name="RedTeamAgent",
        soft_dependencies=list(_RED_TEAM_SOFT),
        capabilities=[CAP_ADVERSARIAL, CAP_BLOCKING],
    ))

    # 10 总指挥：硬依赖风险结论与红队攻击（决策核心不可缺）；
    # 7 专家报告为软依赖——单份专家失败只降级综合，不阻断总指挥。
    reg.register(AgentSpec(
        name="commander", seq="10", stage_key="commander", label="创业总指挥",
        group=GROUP_DECISION, import_path="agents.commander_agent", class_name="CommanderAgent",
        dependencies=["risk_review", "red_team"],
        soft_dependencies=list(_EXPERT_NAMES),
        capabilities=[CAP_PROCESS_CHAIR, CAP_ANALYSIS],
    ))

    # 11 项目评审官：终审必须拿到总指挥结论、风险结论与红队攻击（全部硬依赖）
    reg.register(AgentSpec(
        name="project_review", seq="11", stage_key="review", label="项目评审官",
        group=GROUP_DECISION, import_path="agents.reviewer_agent", class_name="ReviewerAgent",
        dependencies=["commander", "risk_review", "red_team"],
        capabilities=[CAP_FINAL_JUDGE, CAP_REDLINE_VETO],
    ))

    # 12 路演答辩官：必须有评审结论与总指挥结论（全部硬依赖）
    reg.register(AgentSpec(
        name="pitch_defense", seq="12", stage_key="pitch", label="路演答辩官",
        group=GROUP_DECISION, import_path="agents.pitch_agent", class_name="PitchAgent",
        dependencies=["project_review", "commander"],
        capabilities=[CAP_DEFENSE_COACH],
    ))
    return reg


# 全局单例
registry = build_default_registry()
