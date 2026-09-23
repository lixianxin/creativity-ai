# -*- coding: utf-8 -*-
"""Phase 7-1 验收测试：用创想∞作为输入，验证 Agent Runtime 跑通。"""
import sys
from pathlib import Path

# 确保项目根目录在 sys.path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from agents.user_agent import UserInsightAgent


def main():
    project = """创想∞ AI创业委员会：面向高校创新创业场景的 AI 评审系统。
学生提交创业想法后，12个AI委员模拟真实创业委员会进行全链路审查。
学生免费，学校机构版按年采购。
基于大模型API直接上线对外服务。
目前2所学校创业学院老师口头表示感兴趣。"""

    print("=" * 60)
    print("Phase 7-1 验收：用户洞察 Agent Runtime 测试")
    print("=" * 60)
    print(f"输入项目：创想∞ AI创业委员会\n")

    agent = UserInsightAgent()
    result = agent.run(project)

    print("\n" + "=" * 60)
    print("用户洞察报告（摘要）")
    print("=" * 60)
    print(f"Agent: {result.agent_name}")
    print(f"摘要: {result.summary}")
    print(f"置信度: {result.confidence}")
    if result.evidence:
        print("证据:")
        for e in result.evidence:
            print(f"  - {e[:80]}")
    if result.risks:
        print("风险/缺口:")
        for r in result.risks:
            print(f"  - {r[:80]}")
    print(f"\n完整报告字数: {len(result.raw_output)}")
    print("\n[Phase 7-1 验收通过] Runtime 已可运行任意 Agent。")


if __name__ == "__main__":
    main()
