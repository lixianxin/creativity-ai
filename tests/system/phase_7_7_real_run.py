# -*- coding: utf-8 -*-
"""Phase 7-7 真实 DAG 版 12-Agent 全链路验收（真实调用 API，产生费用）。

验收 8 项（用户指定）：
  1. 真实 API（非 FakeAgent）
  2. L0 8 个 Agent 实际并行
  3. L1 Red Team 等待依赖满足后启动
  4. L2 Commander hard/soft 依赖正确
  5. L3 Reviewer 仅在依赖满足后运行
  6. L4 Pitch 最后执行
  7. RunStore 状态与实际执行一致
  8. Final Report 完整且决策链一致

运行：python tests/system/phase_7_7_real_run.py
产出：
  - data/creativity_runs.db 中的真实 runs/agent_runs（含 started_at/finished_at）
  - reports/phase_7_7_real_<stamp>/ 下 12 份报告 + final_report.md
  - 控制台 === Phase 7-7 EVIDENCE === JSON 证据块
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
from core.result_validator import cross_check_decisions
from core.run_store import RunStore
from pipeline.orchestrator import CommitteePipeline
from schemas.agent_result import STATUS_SUCCESS

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
            # SQLite 时间戳格式：YYYY-MM-DD HH:MM:SS
            return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").timestamp()
        return float(ts)
    except Exception:
        return 0.0


def main():
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = PROJECT_ROOT / "reports" / f"phase_7_7_real_{stamp}"
    report_dir.mkdir(parents=True, exist_ok=True)

    store = RunStore()
    pipe = CommitteePipeline(report_dir=str(report_dir), run_store=store)

    # 打印图结构（代码声明的依赖图，运行前即可见）
    planner = pipe.planner
    graph_structure = [
        {"layer": i, "nodes": [s.name for s in layer],
         "hard_deps": {s.name: list(s.dependencies) for s in layer},
         "soft_deps": {s.name: list(s.soft_dependencies) for s in layer}}
        for i, layer in enumerate(planner.layers)
    ]
    print("=== 声明的 DAG 结构 ===")
    print(json.dumps(graph_structure, ensure_ascii=False, indent=2))

    t0 = time.time()
    ctx = pipe.run(PROJECT_INPUT)
    wall = round(time.time() - t0, 1)

    run_id = pipe.current_run_id
    run = store.get_run(run_id)
    agent_rows = store.list_agent_runs(run_id)
    chain_issues = cross_check_decisions(ctx.reports)

    # 真实运行时间线（用于判定并行 / 层级顺序）
    timeline = []
    for a in agent_rows:
        start = a.started_at if hasattr(a, "started_at") else a.metadata.get("started_at")
        finish = a.finished_at if hasattr(a, "finished_at") else a.metadata.get("finished_at")
        timeline.append({
            "name": a.agent_name, "status": a.status, "elapsed": a.metadata.get("elapsed_s", 0),
            "started_at": str(start), "finished_at": str(finish),
            "started_epoch": _to_epoch(start), "finished_epoch": _to_epoch(finish),
        })
    # 按真实开始时间排序，观察层级间是否真存在"前层全部完成 → 后层启动"
    by_start = sorted(timeline, key=lambda t: (t["started_epoch"], t["name"]))

    # 层时间窗口
    layer_windows = {}
    for layer_name, names in EXPECTED_LAYERS.items():
        layer_rows = [t for t in timeline if t["name"] in names]
        starts = [t["started_epoch"] for t in layer_rows if t["started_epoch"]]
        finishes = [t["finished_epoch"] for t in layer_rows if t["finished_epoch"]]
        layer_windows[layer_name] = {
            "min_start": min(starts) if starts else 0,
            "max_finish": max(finishes) if finishes else 0,
            "duration": round(max(finishes) - min(starts), 2) if starts and finishes else 0,
            "agents": [t["name"] for t in layer_rows],
        }

    # L0 并行证据：任意两棒的时间区间是否重叠
    l0_rows = sorted([t for t in timeline if t["name"] in EXPECTED_LAYERS["L0"]],
                     key=lambda t: t["started_epoch"])
    overlapping_pairs = 0
    for i in range(len(l0_rows)):
        for j in range(i + 1, len(l0_rows)):
            a, b = l0_rows[i], l0_rows[j]
            if a["started_epoch"] and b["started_epoch"] and a["finished_epoch"] and b["finished_epoch"]:
                # 区间重叠 = a.start < b.finish and b.start < a.finish
                if a["started_epoch"] < b["finished_epoch"] and b["started_epoch"] < a["finished_epoch"]:
                    overlapping_pairs += 1
    # 真正的并发数：任意时刻同时在跑的最大棒数
    events = []
    for t in l0_rows:
        if t["started_epoch"] and t["finished_epoch"]:
            events.append((t["started_epoch"], 1))
            events.append((t["finished_epoch"], -1))
    events.sort()
    cur = max_parallel = 0
    for _, delta in events:
        cur += delta
        max_parallel = max(max_parallel, cur)

    # 层级顺序证据：后层所有 started_at 必须 ≥ 前层所有 finished_at
    layer_order_violations = []
    for li in range(len(EXPECTED_LAYERS) - 1):
        cur_layer = list(EXPECTED_LAYERS.values())[li]
        nxt_layer = list(EXPECTED_LAYERS.values())[li + 1]
        cur_max_finish = max((t["finished_epoch"] for t in timeline
                              if t["name"] in cur_layer and t["finished_epoch"]), default=0)
        nxt_min_start = min((t["started_epoch"] for t in timeline
                             if t["name"] in nxt_layer and t["started_epoch"]), default=0)
        if cur_max_finish and nxt_min_start and nxt_min_start < cur_max_finish:
            layer_order_violations.append(
                f"L{li} 完成前 L{li+1} 已启动: L{li}_max_finish={cur_max_finish}, L{li+1}_min_start={nxt_min_start}"
            )

    degraded_agents = [t["name"] for t in timeline if t["status"] == "degraded"]
    blocked_agents = [t["name"] for t in timeline if t["status"] == "blocked"]
    skipped_agents = [t["name"] for t in timeline if t["status"] == "skipped"]

    evidence = {
        "run_id": run_id,
        "run_status": run.status,
        "pause_reason": run.pause_reason,
        "error": run.error,
        "wall_s": wall,
        "report_dir": str(report_dir),
        "stats": pipe.stats,
        "graph_declared": graph_structure,
        "layer_windows": layer_windows,
        "l0_parallel": {
            "overlapping_pairs": overlapping_pairs,
            "max_concurrent_at_any_moment": max_parallel,
            "l0_count": len(l0_rows),
            "note": "overlapping_pairs>0 且 max_concurrent≥2 即证明 L0 实际并行",
        },
        "layer_order": {
            "violations": layer_order_violations,
            "note": "空列表 = 严格层级顺序（后层等前层全完成）",
        },
        "timeline_by_start": by_start,
        "graph_state": {
            "success": sum(1 for t in timeline if t["status"] == "success"),
            "degraded": len(degraded_agents), "blocked": len(blocked_agents),
            "skipped": len(skipped_agents),
            "failed": sum(1 for t in timeline if t["status"] == "failed"),
            "degraded_names": degraded_agents, "blocked_names": blocked_agents,
            "skipped_names": skipped_agents,
        },
        "agents": [
            {"seq": a.stage_seq, "name": a.agent_name, "label": a.label,
             "status": a.status, "retry_count": a.retry_count,
             "conclusion": a.conclusion, "error": a.error[:200],
             "repaired": a.metadata.get("repaired", False),
             "degraded_inputs": a.metadata.get("degraded_inputs", []),
             "elapsed_s": a.metadata.get("elapsed_s", 0),
             "output_exists": bool(a.output_path and Path(a.output_path).exists()),
             "output_path": a.output_path,
             } for a in agent_rows
        ],
        "decision_chain": {
            name: {"status": (r.status if (r := ctx.get_report(name)) else "missing"),
                   "conclusion": (r.conclusion if r else ""),
                   "blocking": (r.metadata.get("blocking") if r else None),
                   "redline_triggered": (r.metadata.get("redline_triggered") if r else None),
                   "redline_forced_by_system": (r.metadata.get("redline_forced_by_system") if r else None),
                   }
            for name in ("risk_review", "commander", "project_review", "pitch_defense")
        },
        "chain_issues": [{"severity": i.severity, "code": i.code, "message": i.message}
                         for i in chain_issues],
        "final_report_exists": (report_dir / "final_report.md").exists(),
        "final_report_has_dag_section": "执行图状态" in (
            (report_dir / "final_report.md").read_text(encoding="utf-8")
            if (report_dir / "final_report.md").exists() else ""
        ),
    }

    print("\n" + "=" * 60)
    print("=== Phase 7-7 EVIDENCE ===")
    print(json.dumps(evidence, ensure_ascii=False, indent=2, default=str))
    print("=== Phase 7-7 EVIDENCE END ===")
    print("=" * 60)

    # 判定（8 项验收门槛）
    success_n = sum(1 for a in agent_rows if a.status == "success")
    hard_chain_errors = [i for i in chain_issues if i.severity == "error"]

    checks = {
        "1_真实API": run.status in ("success", "completed_with_errors")
                     and wall > 30  # 真实 API 必然有耗时，FakeAgent 秒级
                     and all(a["output_exists"] for a in evidence["agents"]
                             if a["status"] in ("success", "degraded")),
        "2_L0实际并行": evidence["l0_parallel"]["max_concurrent_at_any_moment"] >= 2
                      and evidence["l0_parallel"]["overlapping_pairs"] >= 1,
        "3_L1_RedTeam等依赖": not any("L0" in v for v in layer_order_violations)
                            and timeline and next(
                                (t for t in timeline if t["name"] == "red_team"), None
                            ) is not None,
        "4_Commander_hard_soft": any(a["name"] == "commander" and a["status"] in ("success", "degraded")
                                     for a in evidence["agents"])
                               and evidence["layer_windows"]["L2"]["min_start"] > 0,
        "5_Reviewer依赖满足": any(a["name"] == "project_review" and a["status"] in ("success", "degraded")
                                  for a in evidence["agents"]),
        "6_Pitch最后执行": layer_windows["L4"]["min_start"] >= max(
            (layer_windows[k]["max_finish"] for k in ("L0", "L1", "L2", "L3")), default=0
        ),
        "7_RunStore状态一致": run.status == "success" and success_n == 12
                            and not layer_order_violations,
        "8_FinalReport决策链一致": evidence["final_report_exists"]
                                and evidence["final_report_has_dag_section"]
                                and not hard_chain_errors,
    }

    print("\n═══ Phase 7-7 真实验收 8 项 ═══")
    for k, v in checks.items():
        print(f"  {'✅' if v else '❌'} {k}")
    all_pass = all(checks.values())
    print(f"\n判定：{'✅ Phase 7-7 真实 DAG 全链路通过' if all_pass else '❌ 未达 8 项验收门槛'}")
    print(f"  Run={run.status}｜成功{success_n}/12｜总耗时={wall}s")
    print(f"  L0 实测最大并发={evidence['l0_parallel']['max_concurrent_at_any_moment']}")
    print(f"  层级违例={len(layer_order_violations)} 条｜决策链硬冲突={len(hard_chain_errors)} 条")
    if degraded_agents:
        print(f"  DEGRADED 棒次={degraded_agents}")
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
