# -*- coding: utf-8 -*-
"""Phase 7-7 Execution Graph（DAG）专项离线验收（不触网、不花 API）。

对应 Phase 7-7 五件事的验收：
  A 组：DAG 结构 —— 默认 12 棒拓扑分层 / 环检测 / 合成图 ready·blocked·skipped·degraded 分类
  B 组：端到端故障隔离 —— B FAILED → D BLOCKED（零 API 调用）/ E SUCCESS / F SKIPPED
  C 组：soft 依赖 —— B FAILED → G DEGRADED 继续（有产出、留痕缺失输入）
  D 组：resume 图重算 —— 修复 B 后，原 BLOCKED 的 D 重新 READY；ready set 按图重算
  E 组：kill/orphan —— 合成图中断后恢复，已完成节点零调用

运行：python tests/system/test_phase_7_7_dag.py
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import agents.base_agent as ba
from agents.registry import AgentRegistry, AgentSpec
from core.execution_graph import (
    ExecutionPlanner, CyclicDependencyError,
    NODE_READY, NODE_BLOCKED, NODE_SKIPPED,
)
from core.run import (
    RUN_SUCCESS, RUN_COMPLETED_WITH_ERRORS, RUN_PAUSED,
    AGENT_SUCCESS, AGENT_FAILED, AGENT_BLOCKED, AGENT_SKIPPED, AGENT_DEGRADED,
)
from core.run_store import RunStore
from pipeline.orchestrator import CommitteePipeline

import test_v2_runtime as tv
from test_v2_runtime import FakeAgent, GOOD_TEXTS

_PASSED = 0
_FAILED = 0


def check(name, passed, detail=""):
    global _PASSED, _FAILED
    icon = "✅" if passed else "❌"
    print(f"  {icon} {name}" + (f" — {detail}" if detail else ""))
    if passed:
        _PASSED += 1
    else:
        _FAILED += 1


# 合成节点通用合格文本（合成 agent_name 不命中任何专属校验，仅过通用长度/拒绝规则）
GOOD = GOOD_TEXTS["user_insight"]
BAD = "这是一段无法通过校验的非常短输出。"


# ───────────────────────── 合成 Registry ─────────────────────────

def _spec(seq, name, hard=None, soft=None):
    return AgentSpec(
        name=name, seq=seq, stage_key=name, label=f"节点{name.upper()}",
        group="合成图", import_path="synthetic.none", class_name="NoneAgent",
        dependencies=hard or [], soft_dependencies=soft or [],
    )


def registry_hard_chain():
    """A/B/C 无依赖；D hard(A,B)；E hard(C)；F hard(D)。"""
    reg = AgentRegistry()
    for s in [
        _spec("01", "a"), _spec("02", "b"), _spec("03", "c"),
        _spec("04", "d", hard=["a", "b"]),
        _spec("05", "e", hard=["c"]),
        _spec("06", "f", hard=["d"]),
    ]:
        reg.register(s)
    return reg


def registry_soft_chain():
    """A/B 无依赖；G hard(A) soft(B)。"""
    reg = AgentRegistry()
    for s in [
        _spec("01", "a"), _spec("02", "b"),
        _spec("03", "g", hard=["a"], soft=["b"]),
    ]:
        reg.register(s)
    return reg


class SynthFake(FakeAgent):
    """合成节点假 Agent：不加载 prompt 文件（合成名无对应 md），其余与 FakeAgent 一致。"""

    def __init__(self, name, texts):
        self.prompt_name = name
        self.system_prompt = "(synthetic test prompt)"
        self._texts = texts
        self._last_user_content = None
        self._last_max_tokens = 16000
        self._last_result = None


def install_fakes(texts):
    """所有 AgentSpec.build_agent → SynthFake（texts: {name: raw}）。"""
    def fake_build(self):
        return SynthFake(self.name, texts)
    orig = AgentSpec.build_agent
    AgentSpec.build_agent = fake_build
    return orig


def all_good(names):
    return {n: GOOD for n in names}


# ───────────────────────── A 组：DAG 结构与分类 ─────────────────────────

def test_a_structure():
    print("\n【A】默认 12 棒 DAG：拓扑分层 / hard·soft 边")
    from agents.registry import build_default_registry
    p = ExecutionPlanner(build_default_registry().all())
    layers = [[s.name for s in layer] for layer in p.layers]
    check("分层数 = 5", layers == [
        ["user_insight", "market_analysis", "competitor_analysis", "product_design",
         "business_model", "finance", "growth_ops", "risk_review"],
        ["red_team"], ["commander"], ["project_review"], ["pitch_defense"],
    ], str([len(l) for l in layers]))

    rt = p.get("red_team")
    check("red_team 无硬依赖、4 软依赖", rt.dependencies == [] and
          set(rt.soft_dependencies) == {"user_insight", "market_analysis",
                                        "competitor_analysis", "business_model"})
    cm = p.get("commander")
    check("commander hard=[risk,red_team] soft=7专家",
          set(cm.dependencies) == {"risk_review", "red_team"}
          and len(cm.soft_dependencies) == 7)
    rv = p.get("project_review")
    check("review hard=[commander,risk,red_team]",
          set(rv.dependencies) == {"commander", "risk_review", "red_team"})
    pt = p.get("pitch_defense")
    check("pitch hard=[review,commander]",
          set(pt.dependencies) == {"project_review", "commander"})

    # 环检测 / 悬空依赖
    cyc = AgentRegistry()
    cyc.register(_spec("01", "x", hard=["y"]))
    cyc.register(_spec("02", "y", hard=["x"]))
    try:
        ExecutionPlanner(cyc.all())
        check("环依赖抛 CyclicDependencyError", False)
    except CyclicDependencyError:
        check("环依赖抛 CyclicDependencyError", True)

    dangling = AgentRegistry()
    dangling.register(_spec("01", "x", hard=["ghost"]))
    try:
        ExecutionPlanner(dangling.all())
        check("悬空依赖抛 ValueError", False)
    except ValueError:
        check("悬空依赖抛 ValueError", True)


def test_a_classify():
    print("\n【A】合成图分类：B FAILED → D BLOCKED / E READY / F SKIPPED")
    p = ExecutionPlanner(registry_hard_chain().all())

    # 初始：A/B/C ready
    ready0 = {s.name for s, _ in p.ready_set({})}
    check("初始 ready set = {a,b,c}", ready0 == {"a", "b", "c"}, str(ready0))

    states = {"a": AGENT_SUCCESS, "b": AGENT_FAILED, "c": AGENT_SUCCESS}
    v_d, deg_d, why_d = p.classify(p.get("d"), states)
    check("D（hard A,B）B 失败 → BLOCKED", v_d == NODE_BLOCKED and "节点B" in why_d, why_d)
    v_e, deg_e, _ = p.classify(p.get("e"), states)
    check("E（hard C）C 成功 → READY", v_e == NODE_READY and deg_e == set())

    # F 在执行器结算前仍为 queued：对 queued 节点做一次分类即得 SKIPPED（不虚拟落状态）
    v_f_pre, _, _ = p.classify(p.get("f"), {**states, "d": AGENT_BLOCKED})
    check("F（hard D）D 阻断 → 分类 SKIPPED", v_f_pre == NODE_SKIPPED)

    states2 = {**states, "d": AGENT_BLOCKED, "e": AGENT_SUCCESS}
    # ready_set 全图视图：b 已 failed 不再 ready；d/e/f 均不可执行
    rs = {s.name for s, _ in p.ready_set(states2)}
    check("当前 ready set 为空（无脏调度）", rs == set(), str(rs))

    snap = p.graph_snapshot(states2)
    # f 尚未经执行器结算（无状态记录），视图中为 pending；分类结果另由上一条断言验证
    check("图快照分类正确（f 未结算→pending）",
          set(snap["success"]) == {"a", "c", "e"} and snap["failed"] == ["b"]
          and snap["blocked"] == ["d"] and snap["pending"] == ["f"],
          str({k: v for k, v in snap.items() if v}))


def test_a_soft_classify():
    print("\n【A】soft 依赖分类：B FAILED → G READY 且携带 degraded_inputs")
    p = ExecutionPlanner(registry_soft_chain().all())
    states = {"a": AGENT_SUCCESS, "b": AGENT_FAILED}
    v, deg, _ = p.classify(p.get("g"), states)
    check("G 判 READY", v == NODE_READY)
    check("degraded_inputs = {b}", deg == {"b"}, str(deg))

    # soft 依赖被 blocked 也属于缺失；hard 失败仍优先 BLOCKED
    states2 = {"a": AGENT_FAILED, "b": AGENT_SUCCESS}
    v2, deg2, _ = p.classify(p.get("g"), states2)
    check("hard A 失败 → BLOCKED（soft 不豁免硬依赖）",
          v2 == NODE_BLOCKED and deg2 == set())


# ───────────────────────── B 组：端到端 hard 阻断不连坐 ─────────────────────────

def test_b_hard_block_end_to_end():
    print("\n【B】端到端：B 失败 → D BLOCKED 零调用 / E SUCCESS / F SKIPPED")
    tmp = Path(tempfile.mkdtemp(prefix="p77_b_"))
    db, rdir = tmp / "t.db", tmp / "reports"
    reg = registry_hard_chain()
    names = [s.name for s in reg.all()]
    store = RunStore(db_path=str(db))
    pipe = CommitteePipeline(report_dir=str(rdir), run_store=store, agent_registry=reg)

    tv.CALLS.clear()
    orig_gen = ba.llm.generate
    ba.llm.generate = lambda *a, **k: BAD  # 返工也返回坏文本 → failed 定论
    # b 永久坏输出，其余节点合格
    texts = all_good(names)
    texts["b"] = BAD
    orig_build = install_fakes(texts)
    try:
        ctx = pipe.run("合成图故障注入：B 永久失败", save=True)
    finally:
        AgentSpec.build_agent = orig_build
        ba.llm.generate = orig_gen

    rid = pipe.current_run_id
    run = store.get_run(rid)
    db_states = {a.agent_name: a.status for a in store.list_agent_runs(rid)}
    check("Run = completed_with_errors", run.status == RUN_COMPLETED_WITH_ERRORS, run.status)
    check("A/C/E = success",
          db_states["a"] == db_states["c"] == db_states["e"] == AGENT_SUCCESS,
          str(db_states))
    check("B = failed", db_states["b"] == AGENT_FAILED)
    check("D = blocked", db_states["d"] == AGENT_BLOCKED, str(db_states))
    check("F = skipped", db_states["f"] == AGENT_SKIPPED, str(db_states))
    check("BLOCKED/SKIPPED 零 AI 调用",
          tv.CALLS.get("d", 0) == 0 and tv.CALLS.get("f", 0) == 0, str(tv.CALLS))
    check("E 正常执行 1 次", tv.CALLS.get("e") == 1, str(tv.CALLS))

    aruns = {a.agent_name: a for a in store.list_agent_runs(rid)}
    check("D/F 无 output_path（未产出）",
          aruns["d"].output_path == "" and aruns["f"].output_path == "")
    check("BLOCKED 留痕原因含硬依赖", "b" in aruns["d"].error or "B" in aruns["d"].error,
          aruns["d"].error)

    d_res = ctx.get_report("d")
    f_res = ctx.get_report("f")
    check("下游 context 中为 blocked/skipped 占位（无 success 脏数据）",
          d_res.status == "blocked" and f_res.status == "skipped")
    check("阻断/跳过占位文件落盘",
          (rdir / "04_d_BLOCKED.md").exists() and (rdir / "06_f_SKIPPED.md").exists())
    check("stats 阻断1 跳过1",
          pipe.stats["blocked_count"] == 1 and pipe.stats["skipped_count"] == 1
          and pipe.stats["degraded_count"] == 0)
    check("final_report 落盘", (rdir / "final_report.md").exists())
    return str(db), str(rdir), rid


# ───────────────────────── C 组：soft 降级继续 ─────────────────────────

def test_c_soft_degrade_end_to_end():
    print("\n【C】端到端：B 失败 → G DEGRADED 继续（有产出、留痕缺失输入）")
    tmp = Path(tempfile.mkdtemp(prefix="p77_c_"))
    db, rdir = tmp / "t.db", tmp / "reports"
    reg = registry_soft_chain()
    names = [s.name for s in reg.all()]
    store = RunStore(db_path=str(db))
    pipe = CommitteePipeline(report_dir=str(rdir), run_store=store, agent_registry=reg)

    spy = {}
    orig_build_holder = {}

    class SpyG(SynthFake):
        def run(self, project_input, context=None):
            spy["ctx"] = context
            return super().run(project_input, context)

    def fake_build(self):
        if self.name == "g":
            return SpyG("g", texts)
        return SynthFake(self.name, texts)

    texts = all_good(names)
    texts["b"] = BAD
    tv.CALLS.clear()
    orig_build_holder["o"] = AgentSpec.build_agent
    AgentSpec.build_agent = fake_build
    orig_gen = ba.llm.generate
    ba.llm.generate = lambda *a, **k: BAD
    try:
        ctx = pipe.run("合成图 soft 降级", save=True)
    finally:
        AgentSpec.build_agent = orig_build_holder["o"]
        ba.llm.generate = orig_gen

    rid = pipe.current_run_id
    states = {a.agent_name: a.status for a in store.list_agent_runs(rid)}
    check("A success / B failed / G degraded",
          states == {"a": AGENT_SUCCESS, "b": AGENT_FAILED, "g": AGENT_DEGRADED},
          str(states))
    check("G 实际执行 1 次（降级也调 AI）", tv.CALLS.get("g") == 1, str(tv.CALLS))
    g_ar = next(a for a in store.list_agent_runs(rid) if a.agent_name == "g")
    check("G 有 output_path（降级仍产出）",
          bool(g_ar.output_path) and Path(g_ar.output_path).exists())
    check("G metadata 留痕 degraded_inputs=[b]",
          g_ar.metadata.get("degraded_inputs") == ["b"], str(g_ar.metadata))
    g_res = ctx.get_report("g")
    check("业务结果仍 success（图状态为 degraded）",
          g_res.status == "success" and g_res.metadata.get("degraded_inputs") == ["b"])
    # G 的输入上下文：A 成功报告 + B 失败占位都可见
    ctx_names = [r.agent_name for r in (spy.get("ctx") or {}).get("reports", [])]
    check("G 收到 A 成功报告与 B 失败占位",
          set(ctx_names) == {"a", "b"}, str(ctx_names))
    check("Run = completed_with_errors（降级非完美）",
          store.get_run(rid).status == RUN_COMPLETED_WITH_ERRORS)
    check("stats degraded=1 blocked=0 skipped=0",
          pipe.stats["degraded_count"] == 1 and pipe.stats["blocked_count"] == 0
          and pipe.stats["skipped_count"] == 0)


# ───────────────────────── D 组：resume 图重算（解除阻断） ─────────────────────────

def test_d_resume_recomputes_ready_set(db_path: str, rdir: str, rid: str):
    print("\n【D】resume：修好 B 后 D/F 按图重新 READY（原 BLOCKED/SKIPPED 解除）")
    reg = registry_hard_chain()
    names = [s.name for s in reg.all()]

    # 恢复前（新 store 实例，模拟进程重启）：orphan 接管，再看图 ready set
    store = RunStore(db_path=db_path)
    store.mark_orphaned_runs_paused()
    planner = ExecutionPlanner(reg.all())

    # resume_run 后立即（未续跑）用 checkpoint 图状态重算 ready set
    store.resume_run(rid)
    states0 = store.agent_states(rid)
    ready0 = {s.name for s, _ in planner.ready_set(states0)}
    check("恢复瞬间 ready set 仅 {b}（D/F 依赖未满足，不脏调）",
          ready0 == {"b"}, f"states={states0} ready={ready0}")

    tv.CALLS.clear()
    # 修好 B：首输出仍 BAD，返工返回 GOOD 通过校验
    texts = all_good(names)
    texts["b"] = BAD
    orig_build = install_fakes(texts)
    orig_gen = ba.llm.generate
    ba.llm.generate = lambda *a, **k: GOOD
    pipe = CommitteePipeline(report_dir=rdir, run_store=store, agent_registry=reg)
    try:
        ctx = pipe.resume(rid, save=True)
    finally:
        AgentSpec.build_agent = orig_build
        ba.llm.generate = orig_gen

    states = {a.agent_name: a.status for a in store.list_agent_runs(rid)}
    check("续跑后全节点 success",
          all(v == AGENT_SUCCESS for v in states.values()), str(states))
    check("Run = success", store.get_run(rid).status == RUN_SUCCESS)
    check("已完成 A/C/E 零调用（checkpoint 回读）",
          all(tv.CALLS.get(n, 0) == 0 for n in ("a", "c", "e")), str(tv.CALLS))
    check("B 重跑 1 次、D/F 图重算后各执行 1 次",
          tv.CALLS.get("b") == 1 and tv.CALLS.get("d") == 1 and tv.CALLS.get("f") == 1,
          str(tv.CALLS))
    check("6 份节点报告齐全（无 BLOCKED/SKIPPED 占位残留）",
          all((Path(rdir) / f"0{i}_{n}.md").exists()
              for i, n in enumerate(["a", "b", "c", "d", "e", "f"], start=1)))
    check("阻断占位文件已被正常产出覆盖语义（无 _BLOCKED/_SKIPPED）",
          not (Path(rdir) / "04_d_BLOCKED.md").exists()
          and not (Path(rdir) / "06_f_SKIPPED.md").exists())
    check("final_report 重生成", (Path(rdir) / "final_report.md").exists())


# ───────────────────────── E 组：kill/orphan 图恢复 ─────────────────────────

def test_e_kill_resume_on_graph():
    print("\n【E】合成图 kill -9：A/B 完成后崩溃 → orphan 接管 → 图恢复")
    tmp = Path(tempfile.mkdtemp(prefix="p77_e_"))
    db, rdir = tmp / "t.db", tmp / "reports"
    rdir.mkdir(parents=True, exist_ok=True)
    reg = registry_hard_chain()
    names = [s.name for s in reg.all()]

    # 进程 1：create_run 后只手动跑完 A/B（写产出文件），Run 停留 running（不 finish）
    store1 = RunStore(db_path=str(db))
    run = store1.create_run("合成图 kill 演练", reg.stage_specs_tuples(),
                            report_dir=str(rdir))
    rid = run.run_id
    for name in ("a", "b"):
        spec = reg.get(name)
        store1.start_agent(rid, name)
        (rdir / f"{spec.seq}_{name}.md").write_text(GOOD, encoding="utf-8")
        store1.finish_agent(rid, name, AGENT_SUCCESS, output_path=str(rdir / f"{spec.seq}_{name}.md"))
    check("崩溃前 Run 停留 running", store1.get_run(rid).status == "running")

    # 进程 2：启动接管僵死 Run
    store2 = RunStore(db_path=str(db))
    n = store2.mark_orphaned_runs_paused()
    check("orphan 接管为 paused（C 随转 paused）",
          store2.get_run(rid).status == RUN_PAUSED and n >= 1)

    tv.CALLS.clear()
    orig_build = install_fakes(all_good(names))
    pipe = CommitteePipeline(report_dir=str(rdir), run_store=store2, agent_registry=reg)
    try:
        pipe.resume(rid, save=True)
    finally:
        AgentSpec.build_agent = orig_build

    states = {a.agent_name: a.status for a in store2.list_agent_runs(rid)}
    check("恢复后 6 节点全 success",
          all(v == AGENT_SUCCESS for v in states.values()), str(states))
    check("A/B 零重复调用", tv.CALLS.get("a", 0) == 0 and tv.CALLS.get("b", 0) == 0,
          str(tv.CALLS))
    check("C/D/E/F 各执行 1 次（D 等 A/B、F 等 D，由图自动排序）",
          all(tv.CALLS.get(x) == 1 for x in ("c", "d", "e", "f")), str(tv.CALLS))
    check("Run = success", store2.get_run(rid).status == RUN_SUCCESS)
    check("final_report 完整", (rdir / "final_report.md").exists())


def main():
    print("=" * 60)
    print("Phase 7-7 Execution Graph（DAG）专项离线验收")
    print("=" * 60)
    test_a_structure()
    test_a_classify()
    test_a_soft_classify()
    db_path, rdir, rid = test_b_hard_block_end_to_end()
    test_c_soft_degrade_end_to_end()
    test_d_resume_recomputes_ready_set(db_path, rdir, rid)
    test_e_kill_resume_on_graph()
    print("\n" + "=" * 60)
    print(f"结果：{_PASSED} 通过 / {_FAILED} 失败")
    print("=" * 60)
    if _FAILED:
        sys.exit(1)


if __name__ == "__main__":
    main()
