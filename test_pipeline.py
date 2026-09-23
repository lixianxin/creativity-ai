# -*- coding: utf-8 -*-
"""Phase 7-3 验收：完整 12 Agent Pipeline + 结论链验证。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from pipeline.orchestrator import CommitteePipeline

PROJECT = """创想∞ AI创业委员会：面向高校创新创业场景的 AI 评审系统。
学生提交创业想法后，12个AI委员模拟真实创业委员会进行全链路审查。
学生免费，学校机构版按年采购。
基于大模型API直接上线对外服务。
目前2所学校创业学院老师口头表示感兴趣。"""


def main():
    # 清空旧报告
    report_dir = ROOT / "reports"
    if report_dir.exists():
        for f in report_dir.glob("*.md"):
            f.unlink()

    pipe = CommitteePipeline()
    ctx = pipe.run(PROJECT, save=True)

    # 结论链验证
    print("\n" + "=" * 60)
    print("Phase 7-3 结论链验证")
    print("=" * 60)

    commander = ctx.get_report("commander")
    reviewer = ctx.get_report("project_review")
    pitch = ctx.get_report("pitch_defense")

    checks = []
    # 1. 总指挥有阶段判断
    has_stage = commander and any(k in (commander.conclusion or "") for k in ["想法验证", "产品验证", "市场验证"])
    checks.append(("总指挥阶段判断", has_stage, commander.conclusion if commander else "无"))
    print(f"{'✅' if has_stage else '❌'} 总指挥阶段: {commander.conclusion if commander else '无'}")

    # 2. 评审官有终审结论
    has_verdict = reviewer and any(k in (reviewer.conclusion or "") for k in ["准入", "暂缓", "材料不齐"])
    checks.append(("评审官终审结论", has_verdict, reviewer.conclusion if reviewer else "无"))
    print(f"{'✅' if has_verdict else '❌'} 评审官结论: {reviewer.conclusion if reviewer else '无'}")

    # 3. 红线一票否决
    has_redline = reviewer and reviewer.metadata.get("redline_triggered", False)
    checks.append(("红线一票否决", has_redline, "触发" if has_redline else "未触发"))
    print(f"{'✅' if has_redline else '⚠️'} 红线一票否决: {'触发' if has_redline else '未触发'}")

    # 4. 答辩官有路演结论
    has_pitch = pitch and any(k in (pitch.conclusion or "") for k in ["路演", "不建议", "无法评估"])
    checks.append(("答辩官路演结论", has_pitch, pitch.conclusion if pitch else "无"))
    print(f"{'✅' if has_pitch else '❌'} 答辩官结论: {pitch.conclusion if pitch else '无'}")

    # 5. final_report 落盘
    final_exists = (report_dir / "final_report.md").exists()
    checks.append(("final_report 落盘", final_exists, ""))
    print(f"{'✅' if final_exists else '❌'} final_report.md 落盘")

    # 12 报告检查
    print(f"\n12 份报告:")
    all_ok = True
    for i in range(1, 13):
        files = list(report_dir.glob(f"{i:02d}_*.md"))
        if files:
            print(f"  ✅ {files[0].name} ({files[0].stat().st_size} 字节)")
        else:
            print(f"  ❌ 第{i:02d}棒 缺失")
            all_ok = False

    passed = all(c[1] for c in checks) and all_ok
    print(f"\n{'='*60}")
    print(f"Phase 7-3 验收: {'✅ 通过' if passed else '❌ 未通过'}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
