# -*- coding: utf-8 -*-
"""Phase 7-8 真实 Repair 路径回归验收（真实 API，产生费用）。

两档：
  natural（默认）：现有真实项目直接跑，观察 COMMANDER_ACTIONS_LT_3 是否自然出现并触发真实 Repair。
  controlled    ：若自然档未触发，跑此档——Commander 首次调用仍是真实 LLM，
                  仅在进入 Validator 前受控注入"行动项不足"格式缺陷（不改 Prompt、不伪造 LLM），
                  Repair 仍走真实 API，再走真实 Validator。

重点证据（7 字段）：Run ID / Commander 首次 validation / repair 是否触发 /
                  repair 次数 / issues_before / issues_after / repair_evidence。

运行：
  python tests/system/phase_7_8_real_repair.py
  python tests/system/phase_7_8_real_repair.py controlled
"""
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from agents.registry import registry, AgentSpec
from agents.commander_agent import CommanderAgent
import agents.base_agent as ba
from core.config import PROJECT_ROOT
from core.result_validator import _ACTION_BULLET_RE, _COMMANDER_STAGES
from core.result_validator import validate_result
from core.result_validator import SEVERITY_WARNING
from core.run_store import RunStore
from pipeline.orchestrator import CommitteePipeline

PROJECT_INPUT = """创想∞ AI创业委员会：面向高校创新创业场景的 AI 评审系统。学生提交创业想法后，12个AI委员模拟真实创业委员会进行全链路审查。
目标用户：高校创新创业学生（免费），学校创业学院/教务处（机构版采购）
商业模式：学生免费，学校机构版按年采购。基于大模型API直接上线对外服务。
已有验证：目前2所学校创业学院老师口头表示感兴趣。"""


def inject_actions_defect(natural_raw: str) -> str:
    """把真实 Commander 输出受控改写为"行动项不足"缺陷版本。

    保持：阶段判断行（想法验证/方案修正/…）+ 足够长度（≥250字，避开 OUTPUT_TOO_SHORT）。
    去除：所有编号行动行（Phase 7-9 起含①②③等全部编号格式）与含"行动/建议/下一步/优先"的行。
    末尾只留 1 条编号行动 → 编号行=1 < 3。
    """
    lines = [l.strip() for l in natural_raw.split("\n") if l.strip()]
    stage_lines = [l for l in lines if any(k in l for k in _COMMANDER_STAGES)]
    # 保留不含编号、不含行动关键词的正文行
    body_lines = [l for l in lines
                  if not _ACTION_BULLET_RE.match(l)
                  and not any(k in l for k in ("行动", "建议", "下一步", "优先"))]
    kept = list(dict.fromkeys((stage_lines + body_lines)))  # 保序去重，阶段行置顶
    text = "\n".join(kept)
    # 保证 ≥250 字（不引入任何行动行，仅重复正文）
    if len(text) < 260:
        filler = "。".join(body_lines[:6]) or "项目处于早期阶段，需要系统梳理核心矛盾与关键假设。"
        while len(text) < 260:
            text += "\n" + filler
    defective = text + "\n行动建议：\n1. 先做用户访谈验证核心痛点是否真实存在。\n"
    return defective


def install_controlled_commander(generate_log):
    """仅对 commander 注入：真实 LLM 首输出 → 受控缺陷改写。其余 11 棒完全真实。

    同时在 llm.generate 上记日志（耗时/字数），用于证明 Repair 是真实 API 调用。
    """
    orig_build = AgentSpec.build_agent
    orig_generate = ba.llm.generate

    def logged_generate(system_prompt, user_content, **kwargs):
        t0 = time.time()
        content = orig_generate(system_prompt, user_content, **kwargs)
        generate_log.append({
            "elapsed_s": round(time.time() - t0, 1),
            "chars": len(content),
            "system_head": system_prompt[:40].replace("\n", " "),
            "is_repair_call": "系统校验反馈" in user_content,
        })
        return content

    ba.llm.generate = logged_generate

    injected = {"done": False, "natural_chars": 0, "defective_chars": 0,
                "first_vr": None}

    def patched_build(spec_self):
        agent = orig_build(spec_self)
        if spec_self.name != "commander":
            return agent
        orig_run = agent.run

        def wrapped_run(project_input, context=None):
            result = orig_run(project_input, context)  # 真实 LLM 首次调用
            if not injected["done"]:
                injected["done"] = True
                natural_raw = result.raw_output
                defective = inject_actions_defect(natural_raw)
                # 同步缓存：Repair 喂给真实 LLM 的"上一版输出"即缺陷版本
                result.raw_output = defective
                if agent._last_result is not None:
                    agent._last_result.raw_output = defective
                vr = validate_result(result)
                injected["natural_chars"] = len(natural_raw)
                injected["defective_chars"] = len(defective)
                injected["first_vr"] = {
                    "accepted": vr.accepted,
                    "needs_repair": vr.needs_repair,
                    "errors": [i.code for i in vr.errors],
                    "repairable": [i.code for i in vr.repairable_issues],
                    "warnings": [i.code for i in vr.warnings],
                }
            return result

        agent.run = wrapped_run
        return agent

    AgentSpec.build_agent = patched_build
    return orig_build, orig_generate, injected


def commander_evidence(store, run_id: str) -> dict:
    row = next((a for a in store.list_agent_runs(run_id) if a.agent_name == "commander"), None)
    if not row:
        return {}
    return {
        "agent_status": row.status,
        "retry_count": row.retry_count,
        "repaired": row.metadata.get("repaired", False),
        "validation_warnings": row.metadata.get("validation_warnings", []),
        "repair_evidence": row.metadata.get("repair_evidence", {}),
        "conclusion": row.conclusion,
        "output_exists": bool(row.output_path and Path(row.output_path).exists()),
    }


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "natural"
    assert mode in ("natural", "controlled"), f"未知模式: {mode}"

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = PROJECT_ROOT / "reports" / f"phase_7_8_real_{mode}_{stamp}"
    report_dir.mkdir(parents=True, exist_ok=True)

    store = RunStore()
    pipe = CommitteePipeline(report_dir=str(report_dir), run_store=store)

    generate_log = []
    injected = None
    if mode == "controlled":
        orig_build, orig_generate, injected = install_controlled_commander(generate_log)

    t0 = time.time()
    try:
        ctx = pipe.run(PROJECT_INPUT)
    finally:
        if mode == "controlled":
            AgentSpec.build_agent = orig_build
            ba.llm.generate = orig_generate
    wall = round(time.time() - t0, 1)

    run_id = pipe.current_run_id
    run = store.get_run(run_id)
    cev = commander_evidence(store, run_id)
    ev_repair = cev.get("repair_evidence", {})
    repair_calls = [g for g in generate_log if g["is_repair_call"]]

    # 全 Run 返工概览
    all_agents = store.list_agent_runs(run_id)
    repaired_agents = [
        {"name": a.agent_name,
         "issues_before": a.metadata.get("repair_evidence", {}).get("issues_before", []),
         "issues_after": a.metadata.get("repair_evidence", {}).get("issues_after", []),
         "all_resolved": a.metadata.get("repair_evidence", {}).get("all_resolved")}
        for a in all_agents if a.metadata.get("repaired")
    ]

    first_vr = injected["first_vr"] if injected else None
    evidence = {
        "mode": mode,
        "run_id": run_id,
        "run_status": run.status,
        "wall_s": wall,
        "report_dir": str(report_dir),
        "commander": {
            "first_validation_after_injection": first_vr,
            "repair_triggered": cev.get("repaired", False),
            "repair_count": 1 if cev.get("repaired") else 0,
            "issues_before": ev_repair.get("issues_before", []),
            "issues_after": ev_repair.get("issues_after", []),
            "resolved": ev_repair.get("resolved", []),
            "all_resolved": ev_repair.get("all_resolved"),
            "repair_evidence": ev_repair,
            "final_status": cev.get("agent_status"),
            "validation_warnings": cev.get("validation_warnings", []),
            "output_exists": cev.get("output_exists"),
        },
        "real_repair_api_calls": repair_calls,
        "all_repaired_agents": repaired_agents,
        "success_count": sum(1 for a in all_agents if a.status == "success"),
        "graph_non_success": [f"{a.agent_name}={a.status}" for a in all_agents
                              if a.status not in ("success", "degraded")],
    }

    print("\n" + "=" * 60)
    print("=== Phase 7-8 REAL REPAIR EVIDENCE ===")
    print(json.dumps(evidence, ensure_ascii=False, indent=2, default=str))
    print("=== Phase 7-8 REAL REPAIR EVIDENCE END ===")
    print("=" * 60)

    target_hit = "COMMANDER_ACTIONS_LT_3" in (ev_repair.get("issues_before") or [])
    if mode == "natural":
        ok = target_hit and cev.get("repaired") and cev.get("agent_status") == "success"
        print("\n═══ Phase 7-8 自然档判定 ═══")
        print(f"  {'✅' if target_hit else '➖'} COMMANDER_ACTIONS_LT_3 自然出现并进入 issues_before")
        print(f"  {'✅' if cev.get('repaired') else '➖'} commander repaired=True（真实 Repair 已触发）")
        print(f"  {'✅' if cev.get('agent_status') == 'success' else '❌'} commander 终态 success")
        if ok:
            print("判定：✅ 真实 Repair 路径已自然验证，Phase 7-8 可封板")
        else:
            print("判定：➖ 自然档未触发目标 warning，需运行 controlled 档做受控故障注入")
        sys.exit(0 if ok else 2)
    else:
        injection_ok = (
            first_vr is not None
            and first_vr["accepted"] is True            # 注入缺陷不是 error（证明纯 warning 路径）
            and first_vr["needs_repair"] is True
            and "COMMANDER_ACTIONS_LT_3" in first_vr["repairable"]
            and "COMMANDER_ACTIONS_LT_3" not in first_vr["errors"]
        )
        real_api_ok = len(repair_calls) >= 1 and all(g["elapsed_s"] >= 1 and g["chars"] >= 200
                                                     for g in repair_calls)
        final_ok = (cev.get("repaired") is True and target_hit
                    and cev.get("agent_status") == "success" and cev.get("output_exists"))
        checks = {
            "1_受控注入精确触发": injection_ok,
            "2_注入缺陷是纯warning非error": first_vr and first_vr["accepted"] is True,
            "3_Repair真实调用LLM_API": real_api_ok,
            "4_issues_before含ACTIONS_LT_3": target_hit,
            "5_issues_after已消除": "COMMANDER_ACTIONS_LT_3" not in (ev_repair.get("issues_after") or []),
            "6_commander终态success有产出": final_ok,
        }
        print("\n═══ Phase 7-8 受控档判定 ═══")
        for k, v in checks.items():
            print(f"  {'✅' if v else '❌'} {k}")
        ok = all(checks.values())
        print(f"\n判定：{'✅ 真实 Repair 路径受控验证通过，Phase 7-8 可封板' if ok else '❌ 未达标'}")
        print(f"  Run={run.status}｜总耗时={wall}s｜repair API 调用={len(repair_calls)} 次")
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
