# -*- coding: utf-8 -*-
"""Phase 7-8 Critic / Repair 工程化验收。

核心目标：把 Validator（Critic）与 Repair 形成统一闭环——
  Agent → LLM Output → Critic(validate_result) → needs_repair?
       → Repair(带因返工1次) → 再校验 → 留痕(repair_evidence)

关键变化（相对 Phase 7-6/7-7）：
  1. 返工触发条件从「有 error」扩展为「有 error 或结构性可修 warning」；
     如 COMMANDER_ACTIONS_LT_3（行动项不足 3 条）现在会触发返工修复。
  2. 纯信息类 warning（MARKET_UNSOURCED_NUMBERS 等）不触发返工，仅留痕。
  3. 每次返工留下 repair_evidence：issues_before / issues_after / resolved / all_resolved。
  4. 最多返工 1 次，不引入多轮循环。

运行：python tests/system/test_phase_7_8_critic_repair.py
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "system"))

import test_v2_runtime as tv
import test_phase_7_6_acceptance as t76
from test_phase_7_6_acceptance import check, install_agents
import agents.base_agent as ba
from agents.registry import registry, AgentSpec
from core.run_store import RunStore
from pipeline.orchestrator import CommitteePipeline
from schemas.agent_result import STATUS_SUCCESS

# 指挥官首输出：有阶段判断（避免 COMMANDER_NO_STAGE），但行动项仅 1 条 → 触发
# COMMANDER_ACTIONS_LT_3（可修 warning）。正文≥200 字避免 OUTPUT_TOO_SHORT。
COMMANDER_ACTIONS_BAD = (
    "项目阶段判断：想法验证阶段。" * 14 + "\n"
    "行动建议：\n"
    "1. 先做用户访谈验证核心痛点是否真实存在。"
)

# 市场报告：含 TAM/SAM/SOM（无 error），但规模数字无来源 → MARKET_UNSOURCED_NUMBERS
# （信息类 warning，不可修，不应触发返工）。
MARKET_UNSOURCED_BAD = (
    "TAM 100亿元。SAM 50亿元。SOM 10亿元。" * 8 +
    "市场规模可观，用户付费意愿强。" * 4
)


def test_a_repairable_warning_triggers_repair():
    """A: COMMANDER_ACTIONS_LT_3（可修 warning）触发返工，修复后 warning 消失。"""
    print("\n【A】可修 warning 触发返工：COMMANDER_ACTIONS_LT_3 → 修复 → 消失")
    tmp = Path(tempfile.mkdtemp())
    tv.CALLS.clear()
    orig_gen = ba.llm.generate
    orig_build = install_agents(tv.GOOD_TEXTS, first_outputs={"commander": COMMANDER_ACTIONS_BAD})
    try:
        gen_calls = {"n": 0}
        def _gen(*a, **k):
            gen_calls["n"] += 1
            return tv.GOOD_TEXTS["commander"]
        ba.llm.generate = _gen
        pipe = CommitteePipeline(report_dir=str(tmp / "a"), run_store=RunStore(str(tmp / "a.db")))
        spec = registry.get("commander")
        outcome = pipe._execute_agent(spec, "测试项目", None, run_id=None)

        check("返工实际触发（llm.generate 被调用=repair）", gen_calls["n"] == 1,
              str(gen_calls["n"]))
        check("返工后结果 accepted（无 error）", outcome.vr.accepted)
        check("repaired 标记=True", outcome.result.metadata.get("repaired") is True)
        ev = outcome.result.metadata.get("repair_evidence", {})
        check("repair_evidence 已记录", bool(ev), str(outcome.result.metadata))
        check("issues_before 含 COMMANDER_ACTIONS_LT_3",
              "COMMANDER_ACTIONS_LT_3" in ev.get("issues_before", []),
              str(ev.get("issues_before")))
        check("issues_after 不再含 COMMANDER_ACTIONS_LT_3",
              "COMMANDER_ACTIONS_LT_3" not in ev.get("issues_after", []),
              str(ev.get("issues_after")))
        check("all_resolved=True", ev.get("all_resolved") is True, str(ev))
        check("业务结果 success（warning 不致 failed）",
              outcome.result.status == STATUS_SUCCESS)
    finally:
        AgentSpec.build_agent = orig_build
        ba.llm.generate = orig_gen


def test_b_non_repairable_warning_no_repair():
    """B: 纯信息 warning（MARKET_UNSOURCED_NUMBERS）不触发返工，仅留痕。"""
    print("\n【B】信息类 warning 不返工：MARKET_UNSOURCED_NUMBERS 仅留痕不修复")
    tmp = Path(tempfile.mkdtemp())
    tv.CALLS.clear()
    orig_gen = ba.llm.generate
    orig_build = install_agents(tv.GOOD_TEXTS, first_outputs={"market_analysis": MARKET_UNSOURCED_BAD})
    try:
        # 即便打桩 generate，也不应被调用（无返工）
        ba.llm.generate = lambda *a, **k: "SHOULD_NOT_BE_CALLED"
        pipe = CommitteePipeline(report_dir=str(tmp / "b"), run_store=RunStore(str(tmp / "b.db")))
        spec = registry.get("market_analysis")
        outcome = pipe._execute_agent(spec, "测试项目", None, run_id=None)

        check("无返工（CALLS=1：仅 run）", tv.CALLS.get("market_analysis") == 1,
              str(tv.CALLS.get("market_analysis")))
        check("repaired=False", outcome.result.metadata.get("repaired") is None
              or outcome.result.metadata.get("repaired") is False)
        check("无 repair_evidence", "repair_evidence" not in outcome.result.metadata)
        check("warning 仍留痕在 validation_warnings",
              any("MARKET_UNSOURCED_NUMBERS" in str(w)
                  for w in outcome.result.metadata.get("validation_warnings", [])),
              str(outcome.result.metadata.get("validation_warnings")))
        check("accepted=True（warning 不阻断）", outcome.vr.accepted)
        check("业务结果 success", outcome.result.status == STATUS_SUCCESS)
    finally:
        AgentSpec.build_agent = orig_build
        ba.llm.generate = orig_gen


def test_c_error_repair_partial_resolution_evidence():
    """C: error 返工修复部分问题，repair_evidence 完整记录 before/after/resolved。"""
    print("\n【C】返工证据链：issues_before / issues_after / resolved / all_resolved")
    tmp = Path(tempfile.mkdtemp())
    tv.CALLS.clear()
    orig_gen = ba.llm.generate
    # 首输出同时缺 SAM/SOM（error）且行动项不足（commander 的 warning），
    # 但用 market_analysis 来测：缺 SAM/SOM → MARKET_MISSING_TIERS error。
    market_bad = "市场分析：TAM 约 300 亿元。市场在增长，值得关注。"  # 缺 SAM/SOM
    orig_build = install_agents(tv.GOOD_TEXTS, first_outputs={"market_analysis": market_bad})
    try:
        ba.llm.generate = lambda *a, **k: tv.GOOD_TEXTS["market_analysis"]
        pipe = CommitteePipeline(report_dir=str(tmp / "c"), run_store=RunStore(str(tmp / "c.db")))
        spec = registry.get("market_analysis")
        outcome = pipe._execute_agent(spec, "测试项目", None, run_id=None)

        ev = outcome.result.metadata.get("repair_evidence", {})
        check("返工触发", outcome.result.metadata.get("repaired") is True)
        check("issues_before 含 MARKET_MISSING_TIERS",
              "MARKET_MISSING_TIERS" in ev.get("issues_before", []))
        check("resolved 含 MARKET_MISSING_TIERS",
              "MARKET_MISSING_TIERS" in ev.get("resolved", []))
        check("issues_after 不含 MARKET_MISSING_TIERS（已修复）",
              "MARKET_MISSING_TIERS" not in ev.get("issues_after", []))
        check("all_resolved=True", ev.get("all_resolved") is True)
        check("返工后 accepted", outcome.vr.accepted)
    finally:
        AgentSpec.build_agent = orig_build
        ba.llm.generate = orig_gen


def test_d_repair_unsuccessful_keeps_warning_but_no_fail():
    """D: 可修 warning 返工后仍未修掉 → 不 failed，warning 留痕，all_resolved=False。"""
    print("\n【D】返工未修掉可修 warning：不 failed，warning 留痕，all_resolved=False")
    tmp = Path(tempfile.mkdtemp())
    tv.CALLS.clear()
    orig_gen = ba.llm.generate
    # 首输出和返工输出都只含 1 条行动项 → COMMANDER_ACTIONS_LT_3 始终存在
    orig_build = install_agents(tv.GOOD_TEXTS, first_outputs={"commander": COMMANDER_ACTIONS_BAD})
    try:
        gen_calls = {"n": 0}
        def _gen(*a, **k):
            gen_calls["n"] += 1
            return COMMANDER_ACTIONS_BAD
        ba.llm.generate = _gen
        pipe = CommitteePipeline(report_dir=str(tmp / "d"), run_store=RunStore(str(tmp / "d.db")))
        spec = registry.get("commander")
        outcome = pipe._execute_agent(spec, "测试项目", None, run_id=None)

        check("返工仍触发一次（llm.generate 调用 1 次）", gen_calls["n"] == 1,
              str(gen_calls["n"]))
        check("repaired=True", outcome.result.metadata.get("repaired") is True)
        ev = outcome.result.metadata.get("repair_evidence", {})
        check("all_resolved=False（warning 未修掉）", ev.get("all_resolved") is False)
        check("issues_after 仍含 COMMANDER_ACTIONS_LT_3",
              "COMMANDER_ACTIONS_LT_3" in ev.get("issues_after", []))
        check("accepted=True（warning 不致 failed）", outcome.vr.accepted)
        check("图状态 success（单 warning 不连坐、不 failed）",
              outcome.graph_status == "success")
        check("warning 留痕在 validation_warnings",
              any("COMMANDER_ACTIONS_LT_3" in str(w)
                  for w in outcome.result.metadata.get("validation_warnings", [])))
    finally:
        AgentSpec.build_agent = orig_build
        ba.llm.generate = orig_gen


def test_e_no_issues_no_repair():
    """E: 首输出无任何问题 → 不返工，无 repair_evidence。"""
    print("\n【E】无问题不返工：首输出合格 → 零返工、无 repair_evidence")
    tmp = Path(tempfile.mkdtemp())
    tv.CALLS.clear()
    orig_gen = ba.llm.generate
    orig_build = install_agents(tv.GOOD_TEXTS)
    try:
        ba.llm.generate = lambda *a, **k: "SHOULD_NOT_BE_CALLED"
        pipe = CommitteePipeline(report_dir=str(tmp / "e"), run_store=RunStore(str(tmp / "e.db")))
        spec = registry.get("user_insight")
        outcome = pipe._execute_agent(spec, "测试项目", None, run_id=None)
        check("CALLS=1（仅 run，无返工）", tv.CALLS.get("user_insight") == 1)
        check("repaired=False", outcome.result.metadata.get("repaired") is None)
        check("无 repair_evidence", "repair_evidence" not in outcome.result.metadata)
    finally:
        AgentSpec.build_agent = orig_build
        ba.llm.generate = orig_gen


def test_f_repair_evidence_persisted_to_checkpoint():
    """F: 修复证据必须随 checkpoint 落 RunStore（真实 run_id 路径，回归 7-8 真实验收发现的缺口）。"""
    print("\n【F】证据落库：repair_evidence 随 checkpoint 落 RunStore，可从 DB 复查")
    tmp = Path(tempfile.mkdtemp())
    orig_gen = ba.llm.generate
    orig_build = install_agents(tv.GOOD_TEXTS, first_outputs={"commander": COMMANDER_ACTIONS_BAD})
    try:
        ba.llm.generate = lambda *a, **k: tv.GOOD_TEXTS["commander"]
        rdir = str(tmp / "f")
        store = RunStore(str(tmp / "f.db"))
        pipe = CommitteePipeline(report_dir=rdir, run_store=store)
        run = store.create_run("测试项目", registry.stage_specs_tuples(), report_dir=rdir)
        store.mark_run_running(run.run_id)
        spec = registry.get("commander")
        pipe._execute_agent(spec, "测试项目", None, run_id=run.run_id)

        row = next(a for a in store.list_agent_runs(run.run_id) if a.agent_name == "commander")
        check("DB status=success", row.status == "success")
        check("DB repaired=True", row.metadata.get("repaired") is True)
        ev = row.metadata.get("repair_evidence", {})
        check("DB repair_evidence 非空", bool(ev), str(sorted(row.metadata.keys())))
        check("DB issues_before 含 COMMANDER_ACTIONS_LT_3",
              "COMMANDER_ACTIONS_LT_3" in ev.get("issues_before", []),
              str(ev.get("issues_before")))
        check("DB all_resolved=True", ev.get("all_resolved") is True)
    finally:
        AgentSpec.build_agent = orig_build
        ba.llm.generate = orig_gen


def test_g_failed_path_keeps_repair_evidence():
    """G: error 返工后仍败 → failed 棒的 repair_evidence 也必须落库（返工后仍败可审计）。"""
    print("\n【G】失败路径证据：返工后仍 error → failed 棒 DB 仍有 issues_before")
    tmp = Path(tempfile.mkdtemp())
    orig_gen = ba.llm.generate
    orig_build = install_agents(tv.GOOD_TEXTS, first_outputs={"market_analysis": "测试"})
    try:
        ba.llm.generate = lambda *a, **k: "测试"  # 返工仍输出短文本
        rdir = str(tmp / "g")
        store = RunStore(str(tmp / "g.db"))
        pipe = CommitteePipeline(report_dir=rdir, run_store=store)
        run = store.create_run("测试项目", registry.stage_specs_tuples(), report_dir=rdir)
        store.mark_run_running(run.run_id)
        spec = registry.get("market_analysis")
        outcome = pipe._execute_agent(spec, "测试项目", None, run_id=run.run_id)

        check("图状态 failed", outcome.graph_status == "failed")
        row = next(a for a in store.list_agent_runs(run.run_id) if a.agent_name == "market_analysis")
        check("DB status=failed", row.status == "failed")
        ev = row.metadata.get("repair_evidence", {})
        check("failed 棒仍落 repair_evidence", bool(ev), str(sorted(row.metadata.keys())))
        check("issues_before 含 OUTPUT_TOO_SHORT",
              "OUTPUT_TOO_SHORT" in ev.get("issues_before", []), str(ev.get("issues_before")))
    finally:
        AgentSpec.build_agent = orig_build
        ba.llm.generate = orig_gen


if __name__ == "__main__":
    test_a_repairable_warning_triggers_repair()
    test_b_non_repairable_warning_no_repair()
    test_c_error_repair_partial_resolution_evidence()
    test_d_repair_unsuccessful_keeps_warning_but_no_fail()
    test_e_no_issues_no_repair()
    test_f_repair_evidence_persisted_to_checkpoint()
    test_g_failed_path_keeps_repair_evidence()
    print("\n" + "=" * 60)
    print(f"Phase 7-8 Critic/Repair 验收：{t76._PASSED} 通过 / {t76._FAILED} 失败")
    sys.exit(0 if t76._FAILED == 0 else 1)
