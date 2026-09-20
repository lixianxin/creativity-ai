# -*- coding: utf-8 -*-
"""委员会执行器（Phase 7-7：Execution Graph DAG 驱动）。

从"写得很好的流程脚本"升级为 Agent Execution Engine：

  Registry（显式 hard/soft 依赖）
    → ExecutionPlanner 生成 DAG 拓扑层与 ready set
    → 同层 ready 节点并行；逐层结算（并行是图的结果，不是硬编码并发数）
    → Agent.run（LLM 负责判断）
    → ResultValidator（程序负责校验/归一/接受与否）
    → 不接受则带因返工 1 次 → 再校验
    → 程序信号写回（红线/阻断/结论为系统规则）
    → Checkpoint 立即落 RunStore（可恢复）
    → 图故障隔离：
        hard 依赖 FAILED → 本节点 BLOCKED（不调 API）
        hard 依赖 BLOCKED/SKIPPED → 本节点 SKIPPED（断链传递）
        soft 依赖失败 → 本节点 DEGRADED 继续（metadata.degraded_inputs）
        单 Agent FAILED ≠ 整个 Run FAILED
    → 服务级故障：额度→Run 暂停；鉴权→Run 失败
    → resume：success/degraded 从 output_path 回读，其余重新进入图结算 ready set

兼容：STAGES / STAGE_INFO 从默认 Registry 派生，前端无需改动。
"""
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set

from agents.registry import registry, AgentSpec, AgentRegistry
from core.context import ProjectContext
from core.config import PROJECT_ROOT
from core.execution_graph import (
    ExecutionPlanner, NODE_READY, NODE_BLOCKED, NODE_SKIPPED,
)
from core.llm_errors import LLMRequestError, LLMErrorKind
from core.result_validator import (
    validate_result, apply_signals, format_issues_for_repair, ValidationResult,
    cross_check_decisions,
)
from core.run import (
    AGENT_SUCCESS, AGENT_FAILED, AGENT_BLOCKED, AGENT_DEGRADED, AGENT_SKIPPED,
)
from core.run_store import RunStore
from schemas.agent_result import (
    AgentResult, STATUS_SUCCESS, STATUS_FAILED, STATUS_BLOCKED, STATUS_SKIPPED,
)

# ── 兼容性别名：从默认 Registry 单一事实源派生（前端/旧测试仍 import STAGES） ──
STAGES = [(s.seq, s.stage_key, s.class_name, s.needs_context) for s in registry.all()]
STAGE_INFO = [
    {"seq": s.seq, "key": s.stage_key, "label": s.label,
     "group": s.group, "needs_context": s.needs_context}
    for s in registry.all()
]

# 服务级故障：整条 Run 必须停止
_HALT_KINDS = {LLMErrorKind.QUOTA, LLMErrorKind.AUTH}

# 图状态 → 报告图标
_GRAPH_ICONS = {
    AGENT_SUCCESS: "✅", AGENT_DEGRADED: "🟡", AGENT_FAILED: "❌",
    AGENT_BLOCKED: "🚫", AGENT_SKIPPED: "⏭️",
}


@dataclass
class StageOutcome:
    """单棒执行结果（执行器内部传递）。"""
    spec: AgentSpec
    result: AgentResult
    elapsed: float
    vr: Optional[ValidationResult] = None
    halt: bool = False            # 服务级故障，需停止整条 Run
    halt_kind: str = ""
    halt_message: str = ""
    graph_status: str = AGENT_SUCCESS   # 图状态：success/degraded/failed/blocked/skipped


class CommitteePipeline:
    """12 Agent 委员会执行器（DAG 驱动；可注入自定义 registry 做图测试）。"""

    STAGE_INFO = STAGE_INFO

    def __init__(self, report_dir: str = None, run_store: Optional[RunStore] = None,
                 agent_registry: Optional[AgentRegistry] = None):
        self.report_dir = Path(report_dir) if report_dir else PROJECT_ROOT / "reports"
        self.report_dir.mkdir(exist_ok=True)
        self.store = run_store or RunStore()
        self.registry = agent_registry or registry
        self.planner = ExecutionPlanner(self.registry.all())
        self.current_run_id: Optional[str] = None
        self._last_states: Dict[str, str] = {}
        self.stats = self._empty_stats()

    @staticmethod
    def _empty_stats() -> dict:
        return {
            "stages": [],
            "total_elapsed": 0,
            "success_count": 0,      # success + degraded（实际成功执行有产出）
            "fail_count": 0,         # failed + blocked + skipped + degraded（决定 Run 完美与否）
            "degraded_count": 0,
            "blocked_count": 0,
            "skipped_count": 0,
            "repaired_count": 0,
            "warning_count": 0,
            "halt_reason": "",
        }

    # ══════════════════════ 核心执行单元 ══════════════════════

    def _failed_result(self, spec: AgentSpec, err_msg: str, raw: str = "") -> AgentResult:
        return AgentResult(
            agent_name=spec.name, status=STATUS_FAILED,
            summary=f"[FAILED] {err_msg}",
            raw_output=raw or f"# 第{spec.seq}棒 {spec.label} 失败\n\n错误: {err_msg}",
            metadata={"stage_seq": spec.seq, "label": spec.label, "error": err_msg},
        )

    def _graph_nonrun_result(self, spec: AgentSpec, graph_status: str,
                             reason: str) -> AgentResult:
        """BLOCKED / SKIPPED 占位结果：不调用 LLM，仅记录图阻断原因。"""
        title = "阻断" if graph_status == AGENT_BLOCKED else "跳过"
        return AgentResult(
            agent_name=spec.name,
            status=STATUS_BLOCKED if graph_status == AGENT_BLOCKED else STATUS_SKIPPED,
            summary=f"[{graph_status.upper()}] {reason}",
            raw_output=(f"# 第{spec.seq}棒 {spec.label} {title}\n\n"
                        f"本棒未执行（未调用 AI），原因：{reason}\n"),
            metadata={"stage_seq": spec.seq, "label": spec.label,
                      "graph_reason": reason},
        )

    def _context_for(self, spec: AgentSpec, ctx: ProjectContext) -> Optional[dict]:
        """按 DAG 声明只传本节点依赖的上游报告（不再全量透传）。"""
        if not spec.all_dependencies:
            return None
        reports = [ctx.get_report(d) for d in spec.all_dependencies]
        return {"reports": [r for r in reports if r is not None]}

    def _execute_agent(self, spec: AgentSpec, project_input: str,
                       ctx_dict: Optional[dict], run_id: Optional[str] = None,
                       degraded_inputs: Optional[Set[str]] = None) -> StageOutcome:
        """LLM → 校验闸门 → 返工 → 信号归一。任何异常都收敛为 StageOutcome，不炸线程。"""
        degraded_inputs = degraded_inputs or set()
        t0 = time.time()
        agent = spec.build_agent()

        def elapsed():
            return round(time.time() - t0, 1)

        # 1) 首次调用
        try:
            if run_id:
                self.store.start_agent(run_id, spec.name)
            result = agent.run(project_input, context=ctx_dict)
        except LLMRequestError as e:
            return self._outcome_on_llm_error(spec, e, elapsed, run_id)
        except Exception as e:
            err_msg = f"{type(e).__name__}: {str(e)[:200]}"
            failed = self._failed_result(spec, err_msg,
                                         f"# 第{spec.seq}棒 {spec.label} 失败\n\n{err_msg}\n\n{traceback.format_exc()}")
            self._checkpoint_terminal(spec, failed, elapsed(), run_id, error=err_msg)
            return StageOutcome(spec, failed, elapsed(), graph_status=AGENT_FAILED)

        # 2) Critic 校验闸门（程序确定性规则，不信任 LLM 自证）
        vr = validate_result(result)
        repaired = False
        force_redline = False
        repair_evidence: dict = {}

        # 3) Critic 判定需返工 → 带因返工 1 次（最多一次，不引入无限循环）
        #    触发条件 = 有 error 或有"结构性可修 warning"（如 COMMANDER_ACTIONS_LT_3）
        if vr.needs_repair:
            issues_before = [i.code for i in vr.repairable_issues]
            repair_evidence = {"issues_before": issues_before,
                               "issues_before_count": len(issues_before)}
            try:
                new_raw = agent.repair(format_issues_for_repair(vr))
                result = agent.rebuild_after_repair(new_raw)
                vr = validate_result(result)
                repaired = True
                issues_after = [i.code for i in vr.repairable_issues]
                resolved = [c for c in issues_before if c not in issues_after]
                repair_evidence.update({
                    "issues_after": issues_after,
                    "issues_after_count": len(issues_after),
                    "resolved": resolved,
                    "resolved_count": len(resolved),
                    "all_resolved": len(issues_after) == 0,
                })
                # 红线冲突返工后仍存在：程序强制改判（系统规则高于 LLM）
                if any(i.code == "REDLINE_CONFLICT" for i in vr.errors):
                    force_redline = True
            except LLMRequestError as e:
                if e.kind in _HALT_KINDS:
                    return self._outcome_on_llm_error(spec, e, elapsed, run_id)
                # 返工遇到可恢复错误但已耗尽：保留首次结果，按首次校验结论定成败
                result.metadata["repair_error"] = f"{e.kind}: {e.user_message}"
                repair_evidence["repair_error"] = f"{e.kind}: {e.user_message}"
            except Exception as e:
                result.metadata["repair_error"] = f"{type(e).__name__}: {str(e)[:150]}"
                repair_evidence["repair_error"] = f"{type(e).__name__}: {str(e)[:150]}"

        # 4) 程序信号写回（blocking / redline_triggered / conclusion / pierced_count）
        apply_signals(result, vr, force_redline=force_redline)
        result.metadata["elapsed_s"] = elapsed()
        result.metadata["stage_seq"] = spec.seq
        result.metadata["label"] = spec.label
        if repaired:
            result.metadata["repaired"] = True
        if repair_evidence:
            result.metadata["repair_evidence"] = repair_evidence
        if degraded_inputs:
            # 图降级标记：业务结果仍为 success，但输入不完整（图状态记 degraded）
            result.metadata["degraded_inputs"] = sorted(degraded_inputs)

        # 5) 仍有 error 且未被红线强制改判 → 该 Agent failed（单棒失败，不连坐）
        #    warning（含未修掉的可修 warning）不致 failed，仅留痕在 validation_warnings
        if not vr.accepted and not force_redline:
            reasons = "; ".join(f"[{i.code}] {i.message}" for i in vr.errors)
            failed = self._failed_result(
                spec, f"校验未通过（返工后仍不合格）: {reasons}",
                f"# 第{spec.seq}棒 {spec.label} 校验未通过\n\n## 不合格原因\n{reasons}\n\n## LLM 输出\n{result.raw_output}")
            # 保留 LLM 输出供排查，但状态为 failed；修复证据一并落库（返工后仍败也可审计）
            if repair_evidence:
                failed.metadata["repair_evidence"] = repair_evidence
            self._checkpoint_terminal(spec, failed, elapsed(), run_id, error=reasons,
                                      validation=vr, repaired=repaired)
            return StageOutcome(spec, failed, elapsed(), vr, graph_status=AGENT_FAILED)

        graph_status = AGENT_DEGRADED if degraded_inputs else AGENT_SUCCESS
        self._checkpoint_terminal(spec, result, elapsed(), run_id, validation=vr,
                                  repaired=repaired, graph_status=graph_status)
        return StageOutcome(spec, result, elapsed(), vr, halt=False,
                            graph_status=graph_status)

    def _outcome_on_llm_error(self, spec: AgentSpec, e: LLMRequestError,
                              elapsed_fn, run_id: Optional[str]) -> StageOutcome:
        """LLM 服务级错误分类：QUOTA→暂停 Run；AUTH→失败 Run；其余→单棒失败。"""
        err_msg = f"{e.kind}: {e.user_message}"
        halt = e.kind in _HALT_KINDS
        failed = self._failed_result(
            spec, err_msg,
            f"# 第{spec.seq}棒 {spec.label} 失败\n\nLLM 服务错误：{err_msg}")
        failed.metadata["llm_error_kind"] = e.kind
        if run_id:
            self.store.finish_agent(
                run_id, spec.name, STATUS_FAILED, error=err_msg,
                metadata={"elapsed_s": elapsed_fn(), "llm_error_kind": e.kind})
            if e.kind == LLMErrorKind.QUOTA:
                self.store.pause_run(run_id, f"AI 额度/余额不足，已安全暂停：{e.user_message}", error=err_msg)
            elif e.kind == LLMErrorKind.AUTH:
                self.store.fail_run(run_id, f"AI API Key 无效或无权限：{e.user_message}")
        return StageOutcome(spec, failed, elapsed_fn(), halt=halt,
                            halt_kind=e.kind, halt_message=e.user_message,
                            graph_status=AGENT_FAILED)

    def _checkpoint_terminal(self, spec: AgentSpec, result: AgentResult, elapsed: float,
                             run_id: Optional[str], *, error: str = "",
                             validation: Optional[ValidationResult] = None,
                             repaired: bool = False,
                             graph_status: Optional[str] = None):
        """每棒终态立即落 checkpoint（BossHunter：Agent 完成马上落 Run+output_path）。"""
        if not run_id:
            return
        graph_status = graph_status or result.status
        # 只有真正成功产出（success/degraded）才写 output_path，resume 据此回读
        has_output = graph_status in (AGENT_SUCCESS, AGENT_DEGRADED)
        output_path = str(self.report_dir / f"{spec.seq}_{spec.stage_key}.md") if has_output else ""
        self.store.finish_agent(
            run_id, spec.name, graph_status,
            conclusion=result.conclusion or "",
            output_path=output_path,
            error=error or result.metadata.get("error", ""),
            validation=validation.to_dict() if validation else {},
            metadata={"elapsed_s": elapsed, "repaired": repaired,
                      "warnings": len(validation.warnings) if validation else 0,
                      "degraded_inputs": result.metadata.get("degraded_inputs", []),
                      # Phase 7-8：修复证据链必须随 checkpoint 落库（Resume/审计从 DB 可查）
                      "repair_evidence": result.metadata.get("repair_evidence", {}),
                      "validation_warnings": result.metadata.get("validation_warnings", [])},
            increment_retry=repaired,
        )
        self.store.update_current_stage(run_id, spec.stage_key)

    # ══════════════════════ 全量运行 ══════════════════════

    def run(self, project_input: str, save: bool = True, on_progress=None) -> ProjectContext:
        # 启动即接管上次异常退出遗留的僵死 Run
        self.store.mark_orphaned_runs_paused()
        self.stats = self._empty_stats()

        run = self.store.create_run(
            project_input=project_input,
            stage_specs=self.registry.stage_specs_tuples(),
            report_dir=str(self.report_dir),
        )
        self.current_run_id = run.run_id
        return self._drive(project_input, run.run_id, save=save, on_progress=on_progress,
                           pending_names=None, label="启动")

    def resume(self, run_id: str, save: bool = True, on_progress=None) -> ProjectContext:
        """从断点恢复：success/degraded 从 output_path 回读跳过，其余重新进入图结算。"""
        self.store.mark_orphaned_runs_paused()
        self.stats = self._empty_stats()
        plan = self.store.get_resume_plan(run_id)
        run = plan["run"]
        self.store.resume_run(run_id)
        self.current_run_id = run_id

        # 重建内存上下文：完成态棒次只读本地文件 + 纯本地信号恢复（不花 API）
        ctx = ProjectContext(project_info=run.project_input)
        succeeded = {a.agent_name: a for a in plan["succeeded"]}
        initial_states: Dict[str, str] = {}
        # 纵深防御：DB 记 success/degraded 但报告文件缺失（如 halt 时 outcome 未落盘、
        # 文件被外部删除）→ 不回读，强制该棒重跑，杜绝"图状态成功却无产出"裂缝。
        missing_output: set = set()
        for spec in self.registry.all():
            ar = succeeded.get(spec.name)
            if ar and (not ar.output_path or not Path(ar.output_path).exists()):
                missing_output.add(spec.name)
                continue
            if ar and ar.output_path and Path(ar.output_path).exists():
                raw = Path(ar.output_path).read_text(encoding="utf-8")
                result = AgentResult(agent_name=spec.name, status=STATUS_SUCCESS,
                                     summary=raw[:100], raw_output=raw)
                vr = validate_result(result)
                apply_signals(result, vr)
                degraded_inputs = ar.metadata.get("degraded_inputs", [])
                if degraded_inputs:
                    result.metadata["degraded_inputs"] = degraded_inputs
                if ar.metadata.get("repaired"):
                    result.metadata["repaired"] = True
                if ar.metadata.get("repair_evidence"):
                    result.metadata["repair_evidence"] = ar.metadata["repair_evidence"]
                result.metadata.update({"stage_seq": spec.seq, "label": spec.label,
                                        "elapsed_s": ar.metadata.get("elapsed_s", 0),
                                        "resumed_from_checkpoint": True})
                ctx.add_report(result)
                initial_states[spec.name] = ar.status  # success / degraded
                self._record_stat(spec, ar.status, ar.metadata.get("elapsed_s", 0),
                                  None, resumed=True,
                                  repaired=bool(ar.metadata.get("repaired")))

        pending_names = {a.agent_name for a in plan["pending"]} | missing_output
        if missing_output:
            print(f"[Resume] {sorted(missing_output)} 完成态产物缺失，强制重跑")
        print(f"[Resume] Run {run_id}：已恢复 {len(succeeded) - len(missing_output)} 棒，"
              f"待图结算 {sorted(pending_names)}")
        return self._drive(run.project_input, run_id, save=save, on_progress=on_progress,
                           pending_names=pending_names, label="恢复",
                           initial_ctx=ctx, initial_states=initial_states)

    def _drive(self, project_input: str, run_id: str, *, save: bool, on_progress,
               pending_names: Optional[set], label: str,
               initial_ctx: Optional[ProjectContext] = None,
               initial_states: Optional[Dict[str, str]] = None) -> ProjectContext:
        """DAG 层驱动：逐层结算 ready/blocked/skipped，同层 ready 并行。"""
        ctx = initial_ctx or ProjectContext(project_info=project_input)
        states: Dict[str, str] = dict(initial_states or {})
        self._last_states = states
        t_total = time.time()
        halt_reason = ""

        print("=" * 60)
        print(f"AI 创业委员会 12 Agent 执行器（Phase 7-7 DAG Runtime，{label}）")
        print(f"Run ID: {run_id}")
        print("=" * 60)
        self.store.mark_run_running(run_id)

        def should_run(name: str) -> bool:
            return pending_names is None or name in pending_names

        for layer_idx, layer in enumerate(self.planner.layers):
            if halt_reason:
                break

            # ── 图结算：本层每个待执行节点依据上游状态分类 ──
            ready_items: List[tuple] = []
            for spec in layer:
                if not should_run(spec.name):
                    continue
                verdict, degraded_inputs, reason = self.planner.classify(spec, states)
                if verdict == NODE_BLOCKED:
                    outcome = self._graph_outcome(spec, AGENT_BLOCKED, reason, run_id)
                    self._absorb_outcome(outcome, ctx, save, on_progress)
                    states[spec.name] = AGENT_BLOCKED
                    print(f"  🚫 {spec.label} 阻断未执行：{reason}")
                elif verdict == NODE_SKIPPED:
                    outcome = self._graph_outcome(spec, AGENT_SKIPPED, reason, run_id)
                    self._absorb_outcome(outcome, ctx, save, on_progress)
                    states[spec.name] = AGENT_SKIPPED
                    print(f"  ⏭️ {spec.label} 跳过未执行：{reason}")
                elif verdict == NODE_READY:
                    ready_items.append((spec, degraded_inputs))
                else:
                    # 防御性：逐层调度下不应出现 waiting——出现则当阻断处理避免脏调
                    reason = f"调度异常：{reason}"
                    outcome = self._graph_outcome(spec, AGENT_SKIPPED, reason, run_id)
                    self._absorb_outcome(outcome, ctx, save, on_progress)
                    states[spec.name] = AGENT_SKIPPED

            # ── 同层 ready 节点并行（并行度由图决定） ──
            if ready_items and not halt_reason:
                if len(ready_items) > 1:
                    print(f"\n[DAG 第{layer_idx}层] 同时启动 {len(ready_items)} 个 Agent...")
                with ThreadPoolExecutor(max_workers=max(1, len(ready_items))) as pool:
                    futures = {}
                    for spec, degraded_inputs in ready_items:
                        if on_progress:
                            on_progress(int(spec.seq) - 1, "running", None)
                        ctx_dict = self._context_for(spec, ctx)
                        print(f"\n[第{spec.seq}棒] {spec.label} 分析中"
                              f"{'（输入降级：缺 ' + '、'.join(sorted(degraded_inputs)) + '）'
                               if degraded_inputs else ''}...")
                        futures[pool.submit(
                            self._execute_agent, spec, project_input, ctx_dict,
                            run_id, degraded_inputs
                        )] = spec
                    for future in as_completed(futures):
                        outcome = self._absorb_outcome(future.result(), ctx, save, on_progress)
                        states[outcome.spec.name] = outcome.graph_status
                        # 服务级故障：记录 halt 但继续吸收完本层全部 outcome——
                        # pool 退出本就要等待所有已提交任务；不吸收会造成
                        # "checkpoint=success 但报告文件未落盘"的持久化裂缝。
                        if outcome and outcome.halt and not halt_reason:
                            halt_reason = f"{outcome.halt_kind}: {outcome.halt_message}"

        # ── 收尾 ──
        self.stats["total_elapsed"] = round(time.time() - t_total, 1)
        if halt_reason:
            self.stats["halt_reason"] = halt_reason
            print(f"\n⛔ Run 已停止（{halt_reason}），已完成棒次全部 checkpoint，可 resume 续跑")
        else:
            self.store.finish_run(run_id,
                                  success_count=self.stats["success_count"],
                                  fail_count=self.stats["fail_count"])
            if save:
                try:
                    self._save_final_report(ctx, run_id)
                except Exception as e:
                    print(f"  ⚠️ 最终报告生成失败: {e}")

        print("\n" + "=" * 60)
        print(f"Run 结束 | 成功 {self.stats['success_count']}/{len(self.registry.all())}"
              f"（降级 {self.stats['degraded_count']}）"
              f" | 阻断 {self.stats['blocked_count']} 跳过 {self.stats['skipped_count']}"
              f" | 返工 {self.stats['repaired_count']}"
              f" | 总耗时 {self.stats['total_elapsed']}s")
        print("=" * 60)
        return ctx

    def _graph_outcome(self, spec: AgentSpec, graph_status: str,
                       reason: str, run_id: Optional[str]) -> StageOutcome:
        """生成并 checkpoint 一个不调用 LLM 的图阻断/跳过结果。"""
        result = self._graph_nonrun_result(spec, graph_status, reason)
        if run_id:
            self.store.finish_agent(
                run_id, spec.name, graph_status, error=reason,
                metadata={"elapsed_s": 0.0, "graph_reason": reason},
            )
            self.store.update_current_stage(run_id, spec.stage_key)
        return StageOutcome(spec, result, 0.0, graph_status=graph_status)

    def _absorb_outcome(self, outcome: StageOutcome, ctx: ProjectContext,
                        save: bool, on_progress) -> Optional[StageOutcome]:
        """把一棒结果收入 ctx、存盘、更新统计与进度。"""
        spec, result = outcome.spec, outcome.result
        gs = outcome.graph_status
        ctx.add_report(result)

        if save:
            base = self.report_dir / f"{spec.seq}_{spec.stage_key}"
            if gs in (AGENT_SUCCESS, AGENT_DEGRADED):
                # 成功产出落盘前，清理同一节点上一轮（失败/阻断/跳过后被 resume 解阻）的陈旧占位
                for stale_suffix in ("_FAILED", "_BLOCKED", "_SKIPPED"):
                    stale = Path(f"{base}{stale_suffix}.md")
                    if stale.exists():
                        stale.unlink()
                self._save(f"{spec.seq}_{spec.stage_key}", result.raw_output)
            else:
                suffix = {AGENT_FAILED: "_FAILED", AGENT_BLOCKED: "_BLOCKED",
                          AGENT_SKIPPED: "_SKIPPED"}.get(gs, "_UNKNOWN")
                self._save(f"{spec.seq}_{spec.stage_key}{suffix}", result.raw_output)

        warnings_n = len(outcome.vr.warnings) if outcome.vr else 0
        self._record_stat(spec, gs, outcome.elapsed, outcome.vr,
                          repaired=bool(result.metadata.get("repaired")))

        icon = _GRAPH_ICONS.get(gs, "•")
        if gs == AGENT_SUCCESS:
            tail = f" | {result.conclusion[:40]}" if result.conclusion else ""
            repair_tag = " 🔧返工" if result.metadata.get("repaired") else ""
            warn_tag = f" ⚠️{warnings_n}警" if warnings_n else ""
            print(f"  {icon} {spec.label} ({outcome.elapsed}s){tail}{repair_tag}{warn_tag}")
        elif gs == AGENT_DEGRADED:
            missing = "、".join(result.metadata.get("degraded_inputs", []))
            print(f"  {icon} {spec.label} ({outcome.elapsed}s) 降级完成（缺：{missing}）")
        else:
            print(f"  {icon} {spec.label} ({outcome.elapsed}s) | {result.summary[:80]}")

        if on_progress:
            on_progress(int(spec.seq) - 1, gs, result)
        return outcome

    def _record_stat(self, spec: AgentSpec, graph_status: str, elapsed: float,
                     vr: Optional[ValidationResult], resumed: bool = False,
                     repaired: bool = False):
        """图状态计数：success/degraded 有产出；failed/blocked/skipped 计入未完美。"""
        if graph_status == AGENT_SUCCESS:
            self.stats["success_count"] += 1
            if vr:
                self.stats["warning_count"] += len(vr.warnings)
            if repaired:
                self.stats["repaired_count"] += 1
        elif graph_status == AGENT_DEGRADED:
            self.stats["success_count"] += 1
            self.stats["degraded_count"] += 1
            # degraded 也视为 Run 非完美（存在缺失输入）
            self.stats["fail_count"] += 1
            if vr:
                self.stats["warning_count"] += len(vr.warnings)
            if repaired:
                self.stats["repaired_count"] += 1
        elif graph_status == AGENT_FAILED:
            self.stats["fail_count"] += 1
        elif graph_status == AGENT_BLOCKED:
            self.stats["fail_count"] += 1
            self.stats["blocked_count"] += 1
        elif graph_status == AGENT_SKIPPED:
            self.stats["fail_count"] += 1
            self.stats["skipped_count"] += 1

        self.stats["stages"].append({
            "seq": spec.seq, "key": spec.stage_key, "label": spec.label,
            "status": graph_status, "elapsed_s": elapsed,
            "error": "",
            "repaired": repaired,
            "warnings": len(vr.warnings) if vr else 0,
            "resumed": resumed,
        })

    # ══════════════════════ UI 逐棒入口 ══════════════════════

    def run_stage(self, stage_idx: int, project_input: str, ctx: ProjectContext,
                  save: bool = True) -> AgentResult:
        """供 Streamlit 逐棒调用：同样过校验闸门与程序信号，不绑定 Run 记录。"""
        spec = self.registry.all()[stage_idx]
        t0 = time.time()
        try:
            ctx_dict = {"reports": list(ctx.reports)} if spec.needs_context else None
            outcome = self._execute_agent(spec, project_input, ctx_dict, run_id=None)
            result = outcome.result
            result.metadata["elapsed_s"] = round(time.time() - t0, 1)
            ctx.add_report(result)
            if save:
                suffix = "" if result.status == STATUS_SUCCESS else "_FAILED"
                self._save(f"{spec.seq}_{spec.stage_key}{suffix}", result.raw_output)
            return result
        except Exception as e:
            err_msg = f"{type(e).__name__}: {str(e)[:200]}"
            failed = self._failed_result(spec, err_msg)
            failed.metadata["elapsed_s"] = round(time.time() - t0, 1)
            ctx.add_report(failed)
            return failed

    def save_final_report(self, ctx: ProjectContext):
        self._save_final_report(ctx, self.current_run_id or "")

    # ══════════════════════ 存储 ══════════════════════

    def _save(self, name: str, content: str):
        (self.report_dir / f"{name}.md").write_text(content, encoding="utf-8")

    def _save_final_report(self, ctx: ProjectContext, run_id: str = ""):
        lines = ["# 创想∞ AI创业委员会 —— 创业项目诊断报告\n"]
        if run_id:
            lines.append(f"> Run ID：`{run_id}`（Phase 7-7 DAG Runtime，断点可恢复）\n")

        # 决策链（结论/红线均为程序信号，不再是 LLM 自述）
        lines.append("## 委员会决策链\n")
        for name, agent_name in [("风险审查官", "risk_review"), ("创业总指挥", "commander"),
                                 ("项目评审官", "project_review"), ("路演答辩官", "pitch_defense")]:
            r = ctx.get_report(agent_name)
            if r and r.status == STATUS_SUCCESS:
                lines.append(f"### {name}")
                if r.conclusion:
                    lines.append(f"- 结论：{r.conclusion}")
                elif agent_name == "risk_review":
                    lines.append("- 结论：（风险官不产出准入结论，以下方风险阻断信号为准）")
                else:
                    lines.append("- 结论：未提取")
                lines.append(f"- 摘要：{r.summary[:100]}")
                if r.metadata.get("redline_triggered") is not None:
                    forced = "（系统强制）" if r.metadata.get("redline_forced_by_system") else ""
                    lines.append(f"- 红线一票否决：{'是' if r.metadata['redline_triggered'] else '否'}{forced}")
                if r.metadata.get("pierced_count") is not None:
                    lines.append(f"- 被击穿问题数：{r.metadata['pierced_count']}")
                if r.metadata.get("blocking") is not None:
                    lines.append(f"- 风险阻断：{'是' if r.metadata['blocking'] else '否'}")
                lines.append("")
            elif r:
                lines.append(f"### {name}")
                lines.append(f"- 本棒未产出（图状态：{r.status}）｜{r.summary[:100]}")
                lines.append("")

        # 决策链跨层一致性（Phase 7-6：程序级制衡证据，不信任 LLM 自述）
        lines.append("## 决策链一致性检查（程序）\n")
        chain_issues = cross_check_decisions(ctx.reports)
        if not chain_issues:
            lines.append("✅ 风险 → 总指挥 → 评审 → 路演 结论链无程序级冲突。")
        else:
            for ci in chain_issues:
                icon = "⛔" if ci.severity == "error" else "⚠️"
                lines.append(f"- {icon} **[{ci.code}]** {ci.message}")
        lines.append("")

        # 执行图状态（Phase 7-7：DAG 拓扑层 + 每节点图状态）
        lines.append("## 执行图状态（DAG，程序结算）\n")
        spec_by_name = {s.name: s for s in self.registry.all()}
        for li, layer in enumerate(self.planner.layers):
            cells = []
            for s in layer:
                gs = self._last_states.get(s.name, "queued")
                cells.append(f"{_GRAPH_ICONS.get(gs, '⏳')} {s.label}`{gs}`")
            lines.append(f"- 第 {li} 层（{'并行' if len(layer) > 1 else '单节点'}）：" + "；".join(cells))
        lines.append("")
        lines.append("> 图例：✅ success ｜ 🟡 degraded（软依赖缺失，降级执行）｜ "
                     "❌ failed ｜ 🚫 blocked（硬依赖失败，未调用 AI）｜ "
                     "⏭️ skipped（上游断链，未调用 AI）")
        lines.append("")

        lines.append("\n## 12 Agent 报告概览\n")
        lines.append("| Agent | 图状态 | 结论 | 校验 | 字数 |")
        lines.append("|---|---|---|---|---|")
        for r in ctx.reports:
            label = spec_by_name.get(r.agent_name).label if r.agent_name in spec_by_name else r.agent_name
            gs = self._last_states.get(r.agent_name, r.status)
            icon = _GRAPH_ICONS.get(gs, "•")
            warn_n = len(r.metadata.get("validation_warnings", []))
            repaired = "🔧" if r.metadata.get("repaired") else ""
            check = f"{repaired}{'⚠️' + str(warn_n) if warn_n else '✓'}".strip() or "✓"
            lines.append(f"| {icon} {label} | {gs} | {r.conclusion or r.summary[:30]} | {check} | {len(r.raw_output)} |")

        lines.append("\n## 运行指标（Phase 7-7 DAG Runtime）\n")
        if self.stats["stages"]:
            lines.append("| Agent | 耗时(s) | 图状态 | 返工 | 校验警告 |")
            lines.append("|---|---|---|---|---|")
            for s in self.stats["stages"]:
                icon = _GRAPH_ICONS.get(s["status"], "•")
                lines.append(f"| {s['label']} | {s['elapsed_s']} | {icon} {s['status']} | "
                             f"{'是' if s.get('repaired') else ''} | {s.get('warnings', 0)} |")
            lines.append(f"\n**总耗时：{self.stats['total_elapsed']}s**")
            lines.append(f"**成功执行：{self.stats['success_count']}（其中降级 {self.stats['degraded_count']}）"
                         f"｜失败 {self.stats['fail_count']}"
                         f"（阻断 {self.stats['blocked_count']} / 跳过 {self.stats['skipped_count']}）**")
            lines.append(f"**校验返工：{self.stats['repaired_count']} 棒｜警告合计：{self.stats['warning_count']} 条**")
        if self.stats.get("halt_reason"):
            lines.append(f"\n> ⛔ 本次 Run 中断原因：`{self.stats['halt_reason']}`，可执行 resume 从断点续跑。")

        (self.report_dir / "final_report.md").write_text("\n".join(lines), encoding="utf-8")
