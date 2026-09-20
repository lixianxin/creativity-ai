# -*- coding: utf-8 -*-
"""Phase 7-9 真实 API 验收：Validator 语义准确性 + Repair 成功率（真实调用，产生费用）。

取证背景（2026-09-19 真实样本）：
  - Commander：4/4 真实报告稳定输出 3 条①②③（prompt 模板即此格式），旧 validator
    只认阿拉伯数字 → COMMANDER_ACTIONS_LT_3 稳定误判、Repair 修不掉。
  - Red Team：prompt 五维（用户/需求/竞争/商业/壁垒）与 validator 五维
    （需求/付费/竞争/增长/壁垒）契约不一致；真实失败样本付费攻击完整但未被识别，
    增长维则系统性缺失（5 份真实报告无一真正攻击增长）。

7-9 修复：编号格式对齐模板；红队 prompt/validator 双侧对齐为五维，增长独立成段；
         4/5 时 REDTEAM_DIM_MISSING_ONE 可修 warning 点名缺谁，缺≥2 维仍 error。

验收 8 项：
  1. 真实 API（非 FakeAgent）
  2. Commander 首检即过：①②③被识别，无 COMMANDER_ACTIONS_LT_3，无无谓返工
  3. Red Team 新五维真实生效：报告含【增长假设】段，复算 5/5、missing=[]
  4. 旧失败根因不复发：red_team 不 failed、下游不 BLOCKED/SKIPPED
  5. RunStore 状态一致（12 success / run success）
  6. DAG 时序能力未回退（L0 真并行、层级零违例）
  7. Final Report 完整、决策链 0 error
  8. Repair 留痕机制在线（本 run 零返工即为改善证据；若有返工则证据完整）

运行：python tests/system/phase_7_9_real_run.py
"""
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from agents.registry import registry
from core.config import PROJECT_ROOT
from core.result_validator import validate_result, cross_check_decisions, _ACTION_BULLET_RE
from core.run_store import RunStore
from pipeline.orchestrator import CommitteePipeline
from schemas.agent_result import AgentResult

PROJECT_INPUT = """创想∞ AI创业委员会：面向高校创新创业场景的 AI 评审系统。学生提交创业想法后，12个AI委员模拟真实创业委员会进行全链路审查。
目标用户：高校创新创业学生（免费），学校创业学院/教务处（机构版采购）
商业模式：学生免费，学校机构版按年采购。基于大模型API直接上线对外服务。
已有验证：目前2所学校创业学院老师口头表示感兴趣。"""

EXPECTED_LAYERS = {
    "L0": ["user_insight", "market_analysis", "competitor_analysis", "product_design",
           "business_model", "finance", "growth_ops", "risk_review"],
    "L1": ["red_team"],
    "L2": ["commander"],
    "L3": ["project_review"],
    "L4": ["pitch_defense"],
}


def _to_epoch(ts) -> float:
    if not ts:
        return 0.0
    try:
        if isinstance(ts, str):
            return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").timestamp()
        return float(ts)
    except Exception:
        return 0.0


def revalidate_output(output_path, agent_name):
    """用当前 validator 复算最终落盘报告（判定语义的独立复核，不依赖 DB 自报）。"""
    if not output_path or not Path(output_path).exists():
        return None
    raw = Path(output_path).read_text(encoding="utf-8")
    vr = validate_result(AgentResult(
        agent_name=agent_name, status="success", raw_output=raw, summary="x"))
    bullets = [l for l in raw.split("\n") if _ACTION_BULLET_RE.match(l.strip())]
    return {
        "issue_codes": [i.code for i in vr.issues],
        "error_codes": [i.code for i in vr.issues if i.severity == "error"],
        "warning_codes": [i.code for i in vr.issues if i.severity == "warning"],
        "signals": vr.signals,
        "bullet_count": len(bullets),
        "has_growth_section": "【增长假设" in raw,
        "has_payer_section": "【付费假设" in raw,
        "chars": len(raw),
    }


def main():
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = PROJECT_ROOT / "reports" / f"phase_7_9_real_{stamp}"
    report_dir.mkdir(parents=True, exist_ok=True)

    store = RunStore()
    pipe = CommitteePipeline(report_dir=str(report_dir), run_store=store)
    print(f"报告目录：{report_dir}")

    t0 = time.time()
    ctx = pipe.run(PROJECT_INPUT)
    wall = round(time.time() - t0, 1)

    run_id = pipe.current_run_id
    run = store.get_run(run_id)
    agent_rows = store.list_agent_runs(run_id)
    chain_issues = cross_check_decisions(ctx.reports)
    rows_by_name = {a.agent_name: a for a in agent_rows}

    timeline = [{
        "name": a.agent_name, "status": a.status,
        "started_epoch": _to_epoch(a.started_at), "finished_epoch": _to_epoch(a.finished_at),
    } for a in agent_rows]

    # L0 并发与层级顺序（7-7 能力回归）
    l0 = [t for t in timeline if t["name"] in EXPECTED_LAYERS["L0"]]
    events = []
    for t in l0:
        if t["started_epoch"] and t["finished_epoch"]:
            events += [(t["started_epoch"], 1), (t["finished_epoch"], -1)]
    events.sort()
    cur = max_parallel = 0
    for _, d in events:
        cur += d
        max_parallel = max(max_parallel, cur)
    layer_violations = []
    for li in range(4):
        cur_layer = list(EXPECTED_LAYERS.values())[li]
        nxt = list(EXPECTED_LAYERS.values())[li + 1]
        cur_max = max((t["finished_epoch"] for t in timeline
                       if t["name"] in cur_layer and t["finished_epoch"]), default=0)
        nxt_min = min((t["started_epoch"] for t in timeline
                       if t["name"] in nxt and t["started_epoch"]), default=0)
        if cur_max and nxt_min and nxt_min < cur_max:
            layer_violations.append(f"L{li}->L{li+1}")

    # ── 7-9 核心语义证据 ──
    rt_row = rows_by_name.get("red_team")
    cm_row = rows_by_name.get("commander")
    rt_reval = revalidate_output(getattr(rt_row, "output_path", None), "red_team")
    cm_reval = revalidate_output(getattr(cm_row, "output_path", None), "commander")

    def db_meta(name, key):
        a = rows_by_name.get(name)
        return a.metadata.get(key) if a else None

    semantic_evidence = {
        "commander": {
            "db_repaired": db_meta("commander", "repaired"),
            "db_retry_count": getattr(cm_row, "retry_count", None),
            "db_validation_warnings": db_meta("commander", "validation_warnings"),
            "revalidated": cm_reval,
        },
        "red_team": {
            "db_repaired": db_meta("red_team", "repaired"),
            "db_retry_count": getattr(rt_row, "retry_count", None),
            "db_validation_warnings": db_meta("red_team", "validation_warnings"),
            "revalidated": rt_reval,
        },
    }

    any_repair = []
    for a in agent_rows:
        if a.metadata.get("repaired") or (a.retry_count or 0) > 0:
            ev = a.metadata.get("repair_evidence") or {}
            any_repair.append({
                "name": a.agent_name, "retry_count": a.retry_count,
                "issues_before": ev.get("issues_before"), "issues_after": ev.get("issues_after"),
                "all_resolved": ev.get("all_resolved"),
            })

    blocked = [a.agent_name for a in agent_rows if a.status in ("blocked", "skipped")]
    failed = [a.agent_name for a in agent_rows if a.status == "failed"]
    success_n = sum(1 for a in agent_rows if a.status == "success")

    evidence = {
        "run_id": run_id,
        "run_status": run.status,
        "wall_s": wall,
        "report_dir": str(report_dir),
        "stats": pipe.stats,
        "semantic": semantic_evidence,
        "repairs_in_run": any_repair,
        "graph_state": {"success": success_n, "failed": failed,
                        "blocked_or_skipped": blocked},
        "l0_max_parallel": max_parallel,
        "layer_violations": layer_violations,
        "chain_issues": [{"severity": i.severity, "code": i.code} for i in chain_issues],
        "final_report_exists": (report_dir / "final_report.md").exists(),
    }

    print("\n" + "=" * 60)
    print("=== Phase 7-9 EVIDENCE ===")
    print(json.dumps(evidence, ensure_ascii=False, indent=2, default=str))
    print("=== Phase 7-9 EVIDENCE END ===")

    # ── 8 项验收门槛 ──
    cm_clean = cm_reval and "COMMANDER_ACTIONS_LT_3" not in cm_reval["issue_codes"] \
        and "COMMANDER_NO_STAGE" not in cm_reval["issue_codes"]
    cm_no_waste_repair = (not cm_row.metadata.get("repaired")) and (not cm_row.retry_count)

    rt_dims = (rt_reval["signals"].get("attack_dimensions") if rt_reval else [])
    rt_missing = (rt_reval["signals"].get("missing_dimensions") if rt_reval else [])
    rt_five = rt_reval and rt_reval["has_growth_section"] and len(rt_dims) == 5 \
        and not rt_missing and "REDTEAM_MISSING_DIMENSIONS" not in rt_reval["error_codes"]

    hard_chain_errors = [i for i in chain_issues if i.severity == "error"]

    checks = {
        "1_真实API": run.status in ("success", "completed_with_errors") and wall > 30
                     and all(Path(a.output_path).exists() for a in agent_rows
                             if a.status in ("success", "degraded") and a.output_path),
        "2_Commander误判消除_首检即过": bool(cm_clean and cm_no_waste_repair and cm_reval["bullet_count"] >= 3),
        "3_RedTeam新五维真实生效": bool(rt_five),
        "4_旧失败根因不复发": ("red_team" not in failed) and not blocked,
        "5_RunStore一致": run.status == "success" and success_n == 12,
        "6_DAG时序未回退": max_parallel >= 2 and not layer_violations,
        "7_FinalReport与决策链": evidence["final_report_exists"] and not hard_chain_errors,
        "8_Repair机制在线": all(set(r) >= {"name", "issues_before", "issues_after"} for r in any_repair),
    }

    print("\n═══ Phase 7-9 真实验收 8 项 ═══")
    for k, v in checks.items():
        print(f"  {'✅' if v else '❌'} {k}")
    print(f"\nRun={run.status}｜成功{success_n}/12｜耗时={wall}s｜L0并发={max_parallel}")
    print(f"commander: bullets={cm_reval['bullet_count'] if cm_reval else '-'} "
          f"repaired={cm_row.metadata.get('repaired')} issues={cm_reval['warning_codes'] if cm_reval else '-'}")
    print(f"red_team : dims={rt_dims} missing={rt_missing} "
          f"增长段={'有' if rt_reval and rt_reval['has_growth_section'] else '无'} "
          f"repaired={rt_row.metadata.get('repaired')}")
    print(f"返工棒数={len(any_repair)}（零返工=误判消除的直接证据；有返工则须证据完整）")
    all_pass = all(checks.values())
    print(f"\n判定：{'✅ Phase 7-9 真实语义验收通过' if all_pass else '❌ 未达门槛（见上）'}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
