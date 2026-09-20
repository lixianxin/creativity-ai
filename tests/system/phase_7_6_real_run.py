# -*- coding: utf-8 -*-
"""Phase 7-6 真实 12-Agent 全链路回归驱动（会真实调用 DeepSeek API，产生费用）。

证据链：
  真实 API → 12 Agent → Validator → Repair → RunStore/Checkpoint
          → Commander → Reviewer → Pitch → 决策链一致性检查 → final_report.md

运行后产出（均可人工复查）：
  1. RunStore 真实库 data/creativity_runs.db 中的 runs / agent_runs 记录；
  2. reports/phase_7_6_real_<时间戳>/ 下 12 份棒次报告 + final_report.md；
  3. 控制台结构化证据块（=== Phase 7-6 EVIDENCE ===）。

运行：python tests/system/phase_7_6_real_run.py
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


def main():
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = PROJECT_ROOT / "reports" / f"phase_7_6_real_{stamp}"
    report_dir.mkdir(parents=True, exist_ok=True)

    # 真实生产 RunStore（data/creativity_runs.db），保证证据在真实库可查
    store = RunStore()
    pipe = CommitteePipeline(report_dir=str(report_dir), run_store=store)

    t0 = time.time()
    ctx = pipe.run(PROJECT_INPUT)
    wall = round(time.time() - t0, 1)

    run_id = pipe.current_run_id
    run = store.get_run(run_id)
    agent_rows = store.list_agent_runs(run_id)
    chain_issues = cross_check_decisions(ctx.reports)

    evidence = {
        "run_id": run_id,
        "run_status": run.status,
        "pause_reason": run.pause_reason,
        "error": run.error,
        "wall_s": wall,
        "report_dir": str(report_dir),
        "stats": pipe.stats,
        "agents": [
            {
                "seq": a.stage_seq, "name": a.agent_name, "label": a.label,
                "status": a.status, "retry_count": a.retry_count,
                "conclusion": a.conclusion, "error": a.error[:200],
                "warnings": a.metadata.get("warnings", 0),
                "repaired": a.metadata.get("repaired", False),
                "elapsed_s": a.metadata.get("elapsed_s", 0),
                "output_exists": bool(a.output_path and Path(a.output_path).exists()),
            }
            for a in agent_rows
        ],
        "decision_chain": {
            name: {
                "status": (r.status if (r := ctx.get_report(name)) else "missing"),
                "conclusion": (r.conclusion if r else ""),
                "blocking": (r.metadata.get("blocking") if r else None),
                "redline_triggered": (r.metadata.get("redline_triggered") if r else None),
                "redline_forced_by_system": (r.metadata.get("redline_forced_by_system") if r else None),
                "validation_warnings": (r.metadata.get("validation_warnings", []) if r else []),
            }
            for name in ("risk_review", "commander", "project_review", "pitch_defense")
        },
        "chain_issues": [
            {"severity": i.severity, "code": i.code, "message": i.message}
            for i in chain_issues
        ],
        "final_report_exists": (report_dir / "final_report.md").exists(),
    }

    print("\n" + "=" * 60)
    print("=== Phase 7-6 EVIDENCE ===")
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    print("=== Phase 7-6 EVIDENCE END ===")
    print("=" * 60)

    # 判定（真实标准，不粉饰）
    success_n = sum(1 for a in agent_rows if a.status == "success")
    hard_chain_errors = [i for i in chain_issues if i.severity == "error"]
    ok = (
        run.status == "success"
        and success_n == 12
        and evidence["final_report_exists"]
        and all(a["output_exists"] for a in evidence["agents"])
        and not hard_chain_errors
    )
    print(f"\n判定：{'✅ 真实全链路通过' if ok else '❌ 未达验收标准'}")
    print(f"  Run 状态={run.status}｜成功棒次={success_n}/12｜总耗时={wall}s")
    print(f"  最终报告={'存在' if evidence['final_report_exists'] else '缺失'}")
    print(f"  决策链硬冲突={len(hard_chain_errors)} 条｜warning={len(chain_issues) - len(hard_chain_errors)} 条")
    if run.pause_reason:
        print(f"  暂停原因：{run.pause_reason}")
    if run.error:
        print(f"  Run 错误：{run.error}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
