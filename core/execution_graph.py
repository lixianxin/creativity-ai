# -*- coding: utf-8 -*-
"""ExecutionPlanner：Agent Execution Graph（Phase 7-7 核心）。

把"按棒次顺序写死的执行脚本"升级为显式 DAG 驱动：

  AgentSpec(hard/soft dependencies)
    → 拓扑分层（Kahn）+ 环检测
    → 逐层结算：依据上游图状态判定 READY / BLOCKED / SKIPPED
    → 同层 READY 节点天然并行（并行是图的结果，不是硬编码的并发数）
    → soft 依赖失败 → READY 但携带 degraded_inputs（DEGRADED 继续）

图状态权威定义在 core/run.py：
  success/degraded 为完成态（有产出、满足下游、resume 不重跑）；
  failed/blocked/skipped/paused/queued/running 在 resume 时重新进入 queued，
  由本 planner 重新计算 ready set。
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Set, Tuple

from agents.registry import AgentSpec
from core.run import (
    AGENT_BLOCKED, AGENT_DEGRADED, AGENT_FAILED, AGENT_PAUSED, AGENT_QUEUED,
    AGENT_RUNNING, AGENT_SKIPPED, AGENT_SUCCESS,
)

# 单节点在当前图状态下的调度判定
NODE_READY = "ready"        # 依赖满足，可执行（可能携带 degraded_inputs）
NODE_BLOCKED = "blocked"    # 硬依赖 FAILED
NODE_SKIPPED = "skipped"    # 硬依赖 BLOCKED/SKIPPED（断链传递）
NODE_WAITING = "waiting"    # 仍有依赖未结算（逐层调度下理论上不应出现，防御性保留）

# 软依赖视为"输入缺失、可降级"的上游状态
SOFT_MISSING_STATUSES = {AGENT_FAILED, AGENT_BLOCKED, AGENT_SKIPPED}
# 硬依赖断链状态
HARD_CHAIN_BROKEN = {AGENT_BLOCKED, AGENT_SKIPPED}
# 尚未结算的状态（出现意味着当前轮次还不该评估本节点）
UNRESOLVED_STATUSES = {AGENT_QUEUED, AGENT_RUNNING, AGENT_PAUSED}


class CyclicDependencyError(ValueError):
    """DAG 中存在环。"""


class ExecutionPlanner:
    """依据 AgentSpec 列表构建不可变 DAG，并对运行时图状态做结算。"""

    def __init__(self, specs: Sequence[AgentSpec]):
        self._specs: Dict[str, AgentSpec] = {}
        for s in specs:
            if s.name in self._specs:
                raise ValueError(f"Agent 重复注册: {s.name}")
            self._specs[s.name] = s
        self._validate_references()
        self._layers: List[List[AgentSpec]] = self._build_layers()
        self._layer_of: Dict[str, int] = {
            s.name: i for i, layer in enumerate(self._layers) for s in layer
        }

    # ── 图结构 ──

    def _validate_references(self):
        for s in self._specs.values():
            for d in list(s.dependencies) + list(s.soft_dependencies):
                if d not in self._specs:
                    raise ValueError(f"Agent {s.name} 声明了不存在的依赖: {d}")
                if d == s.name:
                    raise ValueError(f"Agent {s.name} 不能依赖自身")

    def _build_layers(self) -> List[List[AgentSpec]]:
        """Kahn 拓扑分层：每个节点所在层 = max(依赖层) + 1。有环则抛错。"""
        remaining = dict(self._specs)
        layers: List[List[AgentSpec]] = []
        settled: Set[str] = set()
        while remaining:
            current = [
                s for s in remaining.values()
                if all(d in settled for d in s.all_dependencies)
            ]
            if not current:
                cyc = ", ".join(sorted(remaining))
                raise CyclicDependencyError(f"依赖图存在环或无法结算的节点: {cyc}")
            current.sort(key=lambda s: s.seq)
            layers.append(current)
            for s in current:
                settled.add(s.name)
                remaining.pop(s.name)
        return layers

    @property
    def layers(self) -> List[List[AgentSpec]]:
        """拓扑层（每层为可同时结算的 AgentSpec 列表，按棒次排序）。"""
        return self._layers

    @property
    def node_names(self) -> List[str]:
        return [s.name for layer in self._layers for s in layer]

    def layer_of(self, name: str) -> int:
        return self._layer_of[name]

    def get(self, name: str) -> AgentSpec:
        return self._specs[name]

    def describe_edges(self) -> List[Tuple[str, str, str]]:
        """全部依赖边：(upstream, downstream, hard|soft)，供报告/展示。"""
        edges: List[Tuple[str, str, str]] = []
        for s in self.node_names:
            spec = self._specs[s]
            for d in spec.dependencies:
                edges.append((d, s, "hard"))
            for d in spec.soft_dependencies:
                edges.append((d, s, "soft"))
        return edges

    # ── 运行时结算 ──

    def classify(
        self, spec: AgentSpec, states: Dict[str, str]
    ) -> Tuple[str, Set[str], str]:
        """依据上游图状态判定节点调度方式。

        Returns:
            (verdict, degraded_inputs, reason)
            verdict: NODE_READY / NODE_BLOCKED / NODE_SKIPPED / NODE_WAITING
            degraded_inputs: 缺失的软依赖名集合（仅 READY 时可能非空）
            reason: BLOCKED/SKIPPED/WAITING 的人类可读原因
        """
        hard_states = {d: states.get(d, AGENT_QUEUED) for d in spec.dependencies}
        soft_states = {d: states.get(d, AGENT_QUEUED) for d in spec.soft_dependencies}

        failed_hard = sorted(d for d, st in hard_states.items() if st == AGENT_FAILED)
        if failed_hard:
            return (NODE_BLOCKED, set(),
                    f"硬依赖失败（FAILED）：{self._labels(failed_hard)}")

        broken_hard = sorted(d for d, st in hard_states.items() if st in HARD_CHAIN_BROKEN)
        if broken_hard:
            return (NODE_SKIPPED, set(),
                    f"上游链路已阻断（BLOCKED/SKIPPED）：{self._labels(broken_hard)}")

        unfinished = sorted(
            d for d, st in {**hard_states, **soft_states}.items()
            if st in UNRESOLVED_STATUSES
        )
        if unfinished:
            return (NODE_WAITING, set(),
                    f"依赖尚未结算完成：{self._labels(unfinished)}")

        # 至此：hard 全部完成（success/degraded）；soft 可能 failed/broken（可降级）
        degraded_inputs = {
            d for d, st in soft_states.items() if st in SOFT_MISSING_STATUSES
        }
        return NODE_READY, degraded_inputs, ""

    def _labels(self, names: Sequence[str]) -> str:
        return "、".join(self._specs[n].label if n in self._specs else n for n in names)

    def ready_set(
        self, states: Dict[str, str]
    ) -> List[Tuple[AgentSpec, Set[str]]]:
        """全图扫描：当前处于 queued 且可立即执行的节点（含降级输入集合）。

        Resume 后用它"重新计算 Ready Set"，而不是按棒次找续跑位置。
        """
        out: List[Tuple[AgentSpec, Set[str]]] = []
        for name in self.node_names:
            if states.get(name, AGENT_QUEUED) != AGENT_QUEUED:
                continue
            verdict, degraded_inputs, _ = self.classify(self._specs[name], states)
            if verdict == NODE_READY:
                out.append((self._specs[name], degraded_inputs))
        return out

    def graph_snapshot(self, states: Dict[str, str]) -> Dict[str, List[str]]:
        """导出图状态（Checkpoint Graph State 的视图）。

        分类：success / degraded / failed / blocked / skipped / running /
              paused / ready（queued 且依赖满足）/ pending（queued 且仍需等待）
        """
        snap: Dict[str, List[str]] = {
            AGENT_SUCCESS: [], AGENT_DEGRADED: [], AGENT_FAILED: [],
            AGENT_BLOCKED: [], AGENT_SKIPPED: [], AGENT_RUNNING: [],
            AGENT_PAUSED: [], "ready": [], "pending": [],
        }
        for name in self.node_names:
            st = states.get(name, AGENT_QUEUED)
            if st == AGENT_QUEUED:
                verdict, _, _ = self.classify(self._specs[name], states)
                snap["ready" if verdict == NODE_READY else "pending"].append(name)
            else:
                snap.setdefault(st, []).append(name)
        return snap
