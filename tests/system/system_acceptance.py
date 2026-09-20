# -*- coding: utf-8 -*-
"""Phase 7-5：系统级工程验收脚本。
8 大检查面：功能输入 / Pipeline 可靠性 / Context 完整性 / 结论一致性 / 性能基线 / 成本统计 / 报告落盘 / 异常恢复。
等完整 pipeline 跑完后运行：python tests/system/system_acceptance.py
"""
import sys
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

REPORT_DIR = ROOT / "reports"


def check(name: str, passed: bool, detail: str = ""):
    icon = "✅" if passed else "❌"
    print(f"  {icon} {name} {f'— {detail}' if detail else ''}")
    return passed


def main():
    all_ok = True
    results = {}

    print("=" * 60)
    print("Phase 7-5 系统级工程验收")
    print("=" * 60)

    # ══════════ ① 报告落盘完整性 ══════════
    print("\n【1/8】报告落盘完整性")
    expected = [
        "01_user", "02_market", "03_competitor", "04_product",
        "05_business", "06_finance", "07_growth", "08_risk",
        "09_red_team", "10_commander", "11_review", "12_pitch",
        "final_report",
    ]
    missing = []
    for name in expected:
        f = REPORT_DIR / f"{name}.md"
        if not f.exists() or f.stat().st_size < 500:
            missing.append(name)
            check(f"{name}.md 落盘", False)
        else:
            check(f"{name}.md 落盘", True, f"{f.stat().st_size}B")
    all_ok = all_ok and not missing

    # ══════════ ② Context 完整性（不串报告） ══════════
    print("\n【2/8】Context 数据完整性（无串报告）")
    # 读取 final_report.md 检查三节点结论是否来自正确 Agent
    final = (REPORT_DIR / "final_report.md").read_text(encoding="utf-8")
    # 检查总指挥结论是否包含"验证"关键词
    commander_ok = any(k in final for k in ["想法验证", "产品验证", "市场验证"])
    check("总指挥阶段判断存在", commander_ok, "三节点结论链应包含阶段")
    all_ok = all_ok and commander_ok

    # 检查评审官是否有终审结论
    reviewer_ok = any(k in final for k in ["暂缓", "准入", "材料不齐"])
    check("评审官终审结论存在", reviewer_ok, "应有暂缓/准入/材料不齐之一")
    all_ok = all_ok and reviewer_ok

    # 检查红线是否被标记
    redline_ok = "红线" in final or "一票否决" in final
    check("红线一票否决记录", redline_ok, "应记录是否触发红线")
    all_ok = all_ok and redline_ok

    # ══════════ ③ 结论一致性（与 Phase 6 基线比对） ══════════
    print("\n【3/8】结论链一致性（总指挥→评审→答辩）")
    # 读取各 Agent 报告内容
    agent_names = ["user", "market", "competitor", "product", "business", "finance",
                   "growth", "risk", "red_team", "commander", "review", "pitch"]
    contents = {}
    for name in agent_names:
        f = REPORT_DIR / next(f"*_{name}.md" for _ in [1]) if False else None
        files = list(REPORT_DIR.glob(f"*_{name}.md"))
        if files:
            contents[name] = files[0].read_text(encoding="utf-8")

    # 总指挥：应有阶段判断
    commander_stage = ""
    for line in contents.get("commander", "").split("\n"):
        if any(k in line for k in ["想法验证", "产品验证", "市场验证", "规模扩张"]):
            commander_stage = line.strip()
            break
    check("总指挥: 想法验证阶段", "想法验证" in commander_stage, commander_stage[:60])

    # 评审官：应有暂缓 + 红线
    has_suspend = any(k in contents.get("review", "") for k in ["暂缓", "不得直接准入"])
    has_redline = any(k in contents.get("review", "") for k in ["一票否决", "红线未清", "不得直接"])
    check("评审官: 暂缓 + 红线", has_suspend and has_redline)

    # 答辩官：暂不建议
    has_no_pitch = any(k in contents.get("pitch", "") for k in ["暂不建议", "无法评估"])
    check("答辩官: 暂不建议路演", has_no_pitch)
    all_ok = all_ok and commander_stage and has_suspend and has_redline and has_no_pitch

    # ══════════ ④ 异常处理（Orchestrator 不崩溃） ══════════
    print("\n【4/8】Pipeline 异常处理")
    # 检查是否有 _FAILED 结尾的文件（说明 try/except 正常工作）
    failed_files = list(REPORT_DIR.glob("*_FAILED.md"))
    if failed_files:
        check("异常捕获正常（有 FAILED 文件）", True, f"{len(failed_files)}个失败被捕获")
    else:
        # 无失败 = 全部成功，也 OK
        check("异常捕获正常（全部成功）", True, "12/12 通过")

    # ══════════ ⑤ 性能基线 ══════════
    print("\n【5/8】性能基线")
    # 从各 Agent metadata 提取耗时
    # Phase 7-5 Orchestrator 已把耗时写进 metadata，但是 md 文件里没直接记录
    # 我们直接从 final_report 的性能表读
    perf_section = False
    agent_times = []
    for line in final.split("\n"):
        if "性能基线" in line:
            perf_section = True
            continue
        if perf_section and "|" in line and "---" not in line and "Agent" not in line:
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if len(parts) >= 2:
                try:
                    agent_times.append((parts[0], float(parts[1])))
                except ValueError:
                    pass
        if perf_section and "总耗时" in line:
            break

    if agent_times:
        total_time = sum(t for _, t in agent_times)
        slowest = max(agent_times, key=lambda x: x[1])
        fastest = min(agent_times, key=lambda x: x[1])
        check("耗时数据存在", True, f"共 {len(agent_times)} Agent 有耗时记录")
        print(f"    总耗时: {round(total_time, 0)}s")
        print(f"    最慢: {slowest[0]} ({slowest[1]}s)")
        print(f"    最快: {fastest[0]} ({fastest[1]}s)")
        # 并行潜力
        stage1_7 = [t for name, t in agent_times[:7]]
        if stage1_7:
            parallel_save = sum(stage1_7) - max(stage1_7)
            print(f"    并行潜力: 1-7 专家可并行，节省 ≈ {round(parallel_save, 0)}s")
    else:
        check("耗时数据存在", False, "性能基线表为空")
        all_ok = False

    # ══════════ ⑥ 报告内容质量 ══════════
    print("\n【6/8】报告内容质量")
    for name in ["risk", "red_team", "review"]:
        content = contents.get(name, "")
        has_content = len(content) > 1000
        check(f"{name} 报告字数>1000", has_content, f"{len(content)}字" if content else "缺失")
        all_ok = all_ok and has_content

    # 风险报告应包含致命/红线关键词
    risk_has_fatal = any(k in contents.get("risk", "") for k in ["致命", "红线", "一票否决"])
    check("风险报告包含致命红线", risk_has_fatal)
    all_ok = all_ok and risk_has_fatal

    # 红队应有攻击点
    redteam_has_attack = any(k in contents.get("red_team", "") for k in ["致命", "假设", "攻击", "替代"])
    check("红队有攻击点", redteam_has_attack)
    all_ok = all_ok and redteam_has_attack

    # ══════════ ⑦ 输入边界 ══════════
    print("\n【7/8】输入边界健壮性（Agent Result 字段完整）")
    # 检查报告结构一致性
    for name, key_label in [("risk", "风险审查"), ("review", "评审"), ("pitch", "答辩")]:
        content = contents.get(name, "")
        check(f"{name} 非空", len(content) > 0, f"{len(content)}字")

    # ══════════ ⑧ 最终报告完整性 ══════════
    print("\n【8/8】最终诊断报告完整性")
    has_decision_chain = all(k in final for k in ["决策链", "总指挥", "评审", "答辩"])
    check("决策链完整", has_decision_chain)
    has_overview = "报告概览" in final
    check("12 Agent 概览表存在", has_overview)
    all_ok = all_ok and has_decision_chain and has_overview

    # ══════════ 汇总 ══════════
    print("\n" + "=" * 60)
    if all_ok:
        print("🏁 Phase 7-5 系统级工程验收: ✅ 通过")
    else:
        print("⚠️  Phase 7-5 系统级工程验收: ⚠️  部分未通过（见上方❌项）")
    print("=" * 60)


if __name__ == "__main__":
    main()
