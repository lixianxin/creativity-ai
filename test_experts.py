# -*- coding: utf-8 -*-
"""Phase 7-2 验收：6 个专家/挑战 Agent 基于创想∞运行，产出结构化报告。"""
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
    pipe = CommitteePipeline()
    ctx = pipe.run(PROJECT, save=True)

    print("\n" + "=" * 60)
    print("专家委员会报告摘要")
    print("=" * 60)
    for r in ctx.reports:
        print(f"\n【{r.agent_name}】")
        print(f"  摘要: {r.summary[:60]}")
        print(f"  风险数: {len(r.risks)}，证据数: {len(r.evidence)}")
        if r.metadata.get("blocking") is not None:
            print(f"  红线阻断: {r.metadata['blocking']}")
            if r.metadata.get("fatal_risks"):
                for fr in r.metadata["fatal_risks"][:3]:
                    print(f"    - {fr[:70]}")

    print("\n" + "=" * 60)
    print("[Phase 7-2 验收] reports/ 目录应包含 6 份报告：")
    for name in ["user", "market", "product", "business", "red_team", "risk"]:
        f = ROOT / "reports" / f"{name}.md"
        status = "✅" if f.exists() and f.stat().st_size > 500 else "❌"
        size = f.stat().st_size if f.exists() else 0
        print(f"  {status} {name}.md ({size} 字节)")


if __name__ == "__main__":
    main()
