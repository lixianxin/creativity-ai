# -*- coding: utf-8 -*-
"""智能体空间发布包生成器（Phase 7-10）。
从 agents/registry.py 与 agents/prompts/*.md 生成 12 份可直接粘贴到
智能体平台（扣子/腾讯元器/Trae 空间等）的发布文件：名称/简介/开场白/系统提示词。
运行：python submission/build_space_pack.py
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agents.registry import registry

OUT = Path(__file__).resolve().parent / "space_agents"

# 平台列表用一句话简介（≤30 字）与默认开场白
META = {
    "user_insight": ("剖析目标用户画像、使用场景与真实痛点，拒绝凭空臆测。",
                     "请粘贴你的创业项目描述（目标用户、使用场景、现有验证），我将做用户洞察分析。"),
    "market_analysis": ("估算市场规模与分层结构，所有数字要求来源，拒绝编造。",
                        "请粘贴创业项目描述，我将做市场规模、TAM/SAM/SOM 与增长驱动分析。"),
    "competitor_analysis": ("用直接/间接/替代三层视角穷举竞品并找差异化。",
                            "请粘贴创业项目描述，我将做三层竞品分析与差异化定位。"),
    "product_design": ("定义最小可行产品与核心使用闭环，区分功能与噱头。",
                       "请粘贴创业项目描述，我将给出 MVP 范围与核心闭环设计建议。"),
    "business_model": ("拆解付费方、收入来源与成本骨架，验证单位经济。",
                       "请粘贴创业项目描述，我将拆解商业模式与付费逻辑。"),
    "finance": ("以保守假设测算单位经济与盈亏平衡，无数据就明说不可算。",
                "请粘贴创业项目描述与已知财务参数，我将做财务可行性测算。"),
    "growth_ops": ("检验获客框架、渠道假设与增长推导链，拒绝拍脑袋数字。",
                   "请粘贴创业项目描述与增长计划，我将做增长路径压力测试。"),
    "risk_review": ("六类风险独立审查，致命红线一票否决，不留情面。",
                    "请粘贴创业项目描述，我将独立审查合规、数据、内容、安全、伦理与落地风险。"),
    "red_team": ("只攻击不安慰：对需求/付费/竞争/增长/壁垒五维做对抗性质疑。",
                 "请粘贴创业项目描述，我将以红队身份逐维攻击其核心假设（只质疑，不安慰）。"),
    "commander": ("汇总风险与红队结论，判定项目阶段，拍板下一步验证行动。",
                  "请粘贴创业项目描述与已有审查结论，我将给出委员会阶段结论与 3 条行动。"),
    "project_review": ("五维成熟度终审、证据审计与冲突仲裁，决定是否准入路演。",
                       "请粘贴创业项目及委员会各报告，我将做终审裁决与红线把关。"),
    "pitch_defense": ("模拟评委连环追问，诊断路演薄弱环节并准备答辩。",
                      "请粘贴创业项目与终审结论，我将以评委身份发起路演追问。"),
}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    index = ["# 智能体空间发布包（12 个）\n",
             "每个文件含：空间名称 / 一句话简介 / 建议开场白 / 系统提示词（全文）。",
             "在智能体平台逐个新建智能体并粘贴对应内容即可；12 个均为可独立使用的有效智能体，",
             "满足 A 赛道“空间内 ≥10 个有效智能体”门禁。完整委员会串联流程由在线应用承载（见部署指南）。\n",
             "| # | 空间名称 | 所属委员会 | 一句话简介 |",
             "|---|---|---|---|"]
    for spec in registry.all():
        desc, opener = META[spec.name]
        prompt_file = ROOT / "agents" / "prompts" / f"{spec.name}_v1.md"
        prompt_text = prompt_file.read_text(encoding="utf-8")
        content = f"""# {spec.label}

## 空间名称
创想∞·{spec.label}

## 一句话简介
{desc}

## 建议开场白
{opener}

## 系统提示词（复制以下全部内容到平台“系统指令/人设与回复逻辑”）

{prompt_text}
"""
        fname = f"{spec.seq}_{spec.label}.md"
        (OUT / fname).write_text(content, encoding="utf-8")
        index.append(f"| {spec.seq} | 创想∞·{spec.label} | {spec.group} | {desc} |")
    (OUT / "00_发布清单.md").write_text("\n".join(index) + "\n", encoding="utf-8")
    print(f"generated 12 agent files + index in {OUT}")


if __name__ == "__main__":
    main()
