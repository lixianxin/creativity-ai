# -*- coding: utf-8 -*-
"""Phase 7-9 Validator 语义准确性验收（离线，纯 validator 单测）。

取证依据（tests/system/reports 真实样本，2026-09-19）：
  A. Commander：4/4 真实报告稳定输出 3 条①②③行动项（prompt 模板即如此规定），
     旧正则只认阿拉伯数字 → 稳定误判、Repair 无信息可改。
  B. Red Team：prompt 五维（用户/需求/竞争/商业/壁垒）与 validator 五维
     （需求/付费/竞争/增长/壁垒）是两套契约；真实失败样本付费攻击完整但用词
     "付费者/采购/预算权"未被识别（措辞误判），增长维则是真实系统性缺失。

本文件不依赖 LLM/DB，直接对 validate_result 做判定验证。
运行：python tests/system/test_phase_7_9_validator_semantics.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.result_validator import (
    validate_result, REPAIRABLE_WARNING_CODES, _ACTION_BULLET_RE,
)
from schemas.agent_result import AgentResult

PASS = 0
FAIL = 0


def check(name, ok, detail=""):
    global PASS, FAIL
    mark = "✅" if ok else "❌"
    if ok:
        PASS += 1
    else:
        FAIL += 1
    print(f"  {mark} {name}" + (f" — {detail}" if detail and not ok else ""))


def vr_of(agent_name, raw):
    return validate_result(AgentResult(
        agent_name=agent_name, status="success", raw_output=raw, summary="x"))


def codes(vr):
    return {i.code for i in vr.issues}


def warning_codes(vr):
    return {i.code for i in vr.issues if i.severity == "warning"}


def error_codes(vr):
    return {i.code for i in vr.issues if i.severity == "error"}


# ── 合成文本部件 ──

def commander_text(bullets, stage="项目阶段：想法验证", extra_body=""):
    body = "【委员会阶段结论】\n" + stage + "\n核心矛盾：早期项目的关键假设均未验证。\n"
    body += extra_body + ("核心矛盾内容。" * 40) + "\n下一步行动：\n"
    body += "\n".join(bullets)
    return body


# 五维攻击片段：每段都带"待验证/证据"锚点
DIM_PARTS = {
    "需求假设": "①【需求假设｜高】攻击：目标用户画像过宽，痛点证据不足，什么人在什么场景用未定义。待验证：30 名种子用户访谈。",
    "付费假设": "②【付费假设｜致命】攻击：付费方与使用者分离，付费意愿、采购预算与决策链均无证据，客单价缺失。待验证：意向函。",
    "竞争假设": "③【竞争假设｜高】攻击：微信群与免费模板是替代方案，迁移成本为零而迁移理由缺失。待验证：迁移意愿数据。",
    "增长假设": "④【增长假设｜致命】攻击：获客渠道×流量×转化率没有推导链，冷启动路径空白，用户留存无方案。待验证：地推单价。",
    "壁垒假设": "⑤【壁垒假设｜高】攻击：无护城河、无数据壁垒，巨头可随手复制。待验证：独家资源清单。",
}


def redteam_text(dims):
    head = "【红队审查报告】\n审查结论：暂缓通过\n致命问题：1个\n高风险问题：3个\n一般问题：0个\n核心漏洞：\n"
    body = "\n".join(DIM_PARTS[d] for d in dims)
    tail = "\n证据缺口：\n- 上述待验证项均未提供。\n修改方向：\n- 必须补齐证据。"
    return head + body + tail


# ════════════════════════════════════════════════════════════════════
# A 组：Commander 行动项编号格式矩阵（与 commander_v1.md 模板对齐）
# ════════════════════════════════════════════════════════════════════

def test_a_commander_bullets():
    print("\n【A】Commander 行动项编号格式矩阵")
    cases = [
        ("圆圈数字（prompt 模板格式）", ["① 第一行动", "② 第二行动", "③ 第三行动"]),
        ("阿拉伯数字+点", ["1. 第一行动", "2. 第二行动", "3. 第三行动"]),
        ("阿拉伯数字+顿点", ["1、第一行动", "2、第二行动", "3、第三行动"]),
        ("半括号", ["1) 第一行动", "2) 第二行动", "3) 第三行动"]),
        ("圆括号数字", ["（1）第一行动", "（2）第二行动", "（3）第三行动"]),
        ("中文数字+顿号", ["一、第一行动", "二、第二行动", "三、第三行动"]),
    ]
    for label, bullets in cases:
        vr = vr_of("commander", commander_text(bullets))
        check(f"{label} 计为 3 条 → 无 ACTIONS warning",
              "COMMANDER_ACTIONS_LT_3" not in codes(vr), str(codes(vr)))

    # 仅 2 条 → 仍 warning
    vr = vr_of("commander", commander_text(["① 第一行动", "② 第二行动"]))
    check("仅 2 条行动 → COMMANDER_ACTIONS_LT_3",
          "COMMANDER_ACTIONS_LT_3" in warning_codes(vr))

    # 无编号、无"行动"字样
    vr = vr_of("commander", commander_text([]).replace("下一步行动：", "后续安排："))
    check("无任何编号行动行 → warning", "COMMANDER_ACTIONS_LT_3" in warning_codes(vr))

    # 正则单元：非编号行首不被误判
    check("正则不误伤普通正文", _ACTION_BULLET_RE.match("项目需要先验证核心假设。") is None)
    check("正则不误伤行内编号", _ACTION_BULLET_RE.match("我们将在第1阶段完成验证。") is None)


def test_a2_commander_stage():
    print("\n【A2】Commander 阶段词与 prompt 模板四选一一致")
    for stage in ("项目阶段：想法验证", "项目阶段：方案修正",
                  "项目阶段：路演准备", "项目阶段：可进入路演"):
        vr = vr_of("commander", commander_text(["① a", "② b", "③ c"], stage=stage))
        check(f"{stage} → 无 NO_STAGE", "COMMANDER_NO_STAGE" not in codes(vr))
        check(f"conclusion 信号已归一", stage.split("：")[1] in (vr.signals.get("conclusion") or ""))
    # 旧契约词不再被识别（防止两套模板并存）
    vr = vr_of("commander", commander_text(["① a", "② b", "③ c"], stage="项目阶段：产品验证"))
    check("旧词'产品验证'不再被识别 → NO_STAGE", "COMMANDER_NO_STAGE" in warning_codes(vr))
    check("旧词下 conclusion 为空", not vr.signals.get("conclusion"))


# ════════════════════════════════════════════════════════════════════
# B 组：Red Team 五维覆盖与单维缺失语义
# ════════════════════════════════════════════════════════════════════

def test_b_redteam_dimensions():
    print("\n【B】Red Team 五维覆盖判定")
    five = ["需求假设", "付费假设", "竞争假设", "增长假设", "壁垒假设"]
    vr = vr_of("red_team", redteam_text(five))
    check("五维齐 → accepted、无 DIM issue",
          vr.accepted and not [c for c in codes(vr) if "DIM" in c])
    check("signals.attack_dimensions 五维", vr.signals["attack_dimensions"] == five)
    check("signals.missing_dimensions 为空", vr.signals["missing_dimensions"] == [])

    # 缺 2 维 → error 失败，且文案可执行（点名缺谁）
    three = ["需求假设", "竞争假设", "壁垒假设"]
    vr = vr_of("red_team", redteam_text(three))
    err = [i for i in vr.issues if i.code == "REDTEAM_MISSING_DIMENSIONS"]
    check("缺付费+增长 → REDTEAM_MISSING_DIMENSIONS error",
          bool(err) and not vr.accepted)
    check("error 文案点名缺失维（可执行）",
          err and "付费假设" in err[0].message and "增长假设" in err[0].message,
          err[0].message if err else "")

    # 恰好 4 维 → accepted + 单维 warning 点名
    four = ["需求假设", "竞争假设", "增长假设", "壁垒假设"]
    vr = vr_of("red_team", redteam_text(four))
    one = [i for i in vr.issues if i.code == "REDTEAM_DIM_MISSING_ONE"]
    check("4/5 → accepted", vr.accepted)
    check("4/5 → REDTEAM_DIM_MISSING_ONE warning", bool(one))
    check("warning 点名缺失的付费假设", one and "付费假设" in one[0].message)
    check("signals.missing_dimensions=['付费假设']",
          vr.signals["missing_dimensions"] == ["付费假设"])
    check("REDTEAM_DIM_MISSING_ONE 属可修 warning（驱动一次返工）",
          "REDTEAM_DIM_MISSING_ONE" in REPAIRABLE_WARNING_CODES)


def test_b2_synonym_recognition():
    print("\n【B2】真实措辞同义词识别（防措辞误判）")
    # 付费维：模型真实写法（失败样本即如此），不出现"付费假设"四字
    pay_syn = ("【红队审查报告】\n审查结论：暂缓通过\n核心漏洞：\n"
               "①【需求假设｜致命】攻击：痛点是伪需求，用户画像缺失。待验证：访谈证据。\n"
               "②【竞争假设｜高】攻击：替代方案成熟，迁移成本为零。待验证：迁移意愿。\n"
               "③【增长假设｜致命】攻击：获客渠道与冷启动路径空白，转化率无依据。待验证：地推数据。\n"
               "④【壁垒假设｜高】攻击：无护城河，巨头可复制。待验证：独家资源。\n"
               "⑤【付费方攻击】使用者与付费者分离，学校采购意愿、预算权、审批流程均无证据。待验证：意向函。\n")
    vr = vr_of("red_team", pay_syn)
    check("'付费者/采购意愿/预算权'识别为付费维",
          "付费假设" in vr.signals["attack_dimensions"], str(vr.signals))
    check("'迁移成本'识别为竞争维", "竞争假设" in vr.signals["attack_dimensions"])
    check("五维齐 → 无 DIM issue", not [c for c in codes(vr) if "DIM" in c])


def test_b3_false_positive_guards():
    print("\n【B3】假阳性防护（关键词不是语义本身）")
    # 真实失败样本的误判源：'API 调用量指数级增长'（动词）不得算增长维
    raw = redteam_text(["需求假设", "付费假设", "竞争假设", "壁垒假设"])
    raw += "\n补充：API 调用量随提交量指数级增长，成本侧需测算。"
    vr = vr_of("red_team", raw)
    check("'指数级增长'(动词) 不构成增长维",
          "增长假设" not in vr.signals["attack_dimensions"],
          str(vr.signals["attack_dimensions"]))
    check("此时 4/5 并点名增长缺失",
          "REDTEAM_DIM_MISSING_ONE" in warning_codes(vr)
          and vr.signals["missing_dimensions"] == ["增长假设"])

    # 受控样本误判源：'数据留存校内服务器'（合规语境）不得算增长维
    raw2 = redteam_text(["需求假设", "付费假设", "竞争假设", "壁垒假设"])
    raw2 += "\n补充：高校要求所有数据留存校内服务器，模型推理须本地化。"
    vr2 = vr_of("red_team", raw2)
    check("'数据留存校内'(合规语境) 不构成增长维",
          "增长假设" not in vr2.signals["attack_dimensions"])


# ════════════════════════════════════════════════════════════════════
# C 组：真实报告回放（reports/ 为真实验收证据，缺失则跳过）
# ════════════════════════════════════════════════════════════════════

def test_c_real_samples():
    print("\n【C】真实报告回放（Phase 7-7/7-8 真实 Run 产物）")
    reports = ROOT / "reports"
    if not reports.exists():
        print("  ⚠️ reports/ 不存在，跳过真实样本回放")
        return

    commander_samples = [
        ("7-6", reports / "phase_7_6_real_20260918_204649" / "10_commander.md"),
        ("7-7", reports / "phase_7_7_real_20260919_140841" / "10_commander.md"),
        ("7-8自然repair后", reports / "phase_7_8_real_natural_20260919_150025" / "10_commander.md"),
        ("7-8受控repair后", reports / "phase_7_8_real_controlled_20260919_151411" / "10_commander.md"),
    ]
    found = False
    for label, p in commander_samples:
        if not p.exists():
            continue
        found = True
        vr = vr_of("commander", p.read_text(encoding="utf-8"))
        check(f"真实 commander {label}：①②③被识别，无 ACTIONS warning",
              "COMMANDER_ACTIONS_LT_3" not in codes(vr), str(codes(vr)))

    failed_rt = reports / "phase_7_8_real_natural_20260919_150855" / "09_red_team_FAILED.md"
    if failed_rt.exists():
        found = True
        # 该文件含失败占位头，取 LLM 输出部分
        raw = failed_rt.read_text(encoding="utf-8").split("## LLM 输出", 1)[-1]
        vr = vr_of("red_team", raw)
        check("真实失败样本：付费维被正确识别（措辞误判已纠正）",
              "付费假设" in vr.signals["attack_dimensions"])
        check("真实失败样本：增长维真实缺失 → missing 点名",
              vr.signals["missing_dimensions"] == ["增长假设"])
        check("真实失败样本：accepted + 单维 warning（不再整棒 error）",
              vr.accepted and "REDTEAM_DIM_MISSING_ONE" in warning_codes(vr)
              and "REDTEAM_MISSING_DIMENSIONS" not in error_codes(vr))

    if not found:
        print("  ⚠️ 未找到任何真实样本文件，跳过回放")


def main():
    print("=" * 70)
    print("Phase 7-9 Validator 语义准确性验收")
    print("=" * 70)
    test_a_commander_bullets()
    test_a2_commander_stage()
    test_b_redteam_dimensions()
    test_b2_synonym_recognition()
    test_b3_false_positive_guards()
    test_c_real_samples()
    print("\n" + "=" * 70)
    print(f"结果：{PASS} 通过 / {FAIL} 失败")
    print("=" * 70)
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
