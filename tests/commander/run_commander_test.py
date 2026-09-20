# -*- coding: utf-8 -*-
"""
创业总指挥 V1.0 独立测试脚本
- 加载 agents/prompts/commander_v1.md
- 案例1：使用红队/财务对二手书项目的【真实输出】作为输入
- 案例2：只有红队报告（缺财务）
- 案例3：只有财务报告（缺红队）
- 案例4：报告假冲突（财务说数字成立，红队说需求证据不足）
- 案例5：双报告均正面（测试不会永远说暂缓）
输出：tests/commander/outputs/case_N.md
用法: python run_commander_test.py [case编号 ...]
"""
import sys
import time
import json
import re
from pathlib import Path

from openai import OpenAI

ROOT = Path(__file__).resolve().parents[2]
PROMPT_FILE = ROOT / "agents" / "prompts" / "commander_v1.md"
REDTEAM_OUT = ROOT / "tests" / "redteam" / "outputs"
FINANCE_OUT = ROOT / "tests" / "finance" / "outputs"
OUT_DIR = Path(__file__).resolve().parent / "outputs"
OUT_DIR.mkdir(parents=True, exist_ok=True)

PLATFORMS = [
    {"name": "deepseek", "base_url": "https://api.deepseek.com",
     "api_key": "", "model": "deepseek-v4-flash"},
    {"name": "bailian",
     "base_url": "https://llm-969nmsfu6bcf8ozc.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
     "api_key": "", "model": "qwen-plus"},
    {"name": "zhipu", "base_url": "https://open.bigmodel.cn/api/paas/v4",
     "api_key": "", "model": "glm-5.1"},
]

MISSING = "【本报告缺失】"


def body_of(md_path, marker):
    """从测试输出 md 中提取 Agent 报告正文（marker 之后的部分）。"""
    text = Path(md_path).read_text(encoding="utf-8")
    idx = text.find(marker)
    return text[idx + len(marker):].strip() if idx >= 0 else ""


def build_user_msg(project, finance_report, redteam_report):
    return (
        f"项目名称：\n{project['name']}\n\n"
        f"项目描述：\n{project['desc']}\n\n"
        f"目标用户：\n{project.get('users', '未提供')}\n\n"
        f"核心痛点：\n{project.get('pain', '未提供')}\n\n"
        f"解决方案：\n{project.get('solution', '未提供')}\n\n"
        f"商业模式：\n{project.get('model', '未提供')}\n\n"
        f"当前阶段：\n{project.get('stage', '未提供')}\n\n"
        f"===== 财务分析报告 =====\n{finance_report}\n\n"
        f"===== 红队审查报告 =====\n{redteam_report}\n"
    )


BOOKS = {
    "name": "校园二手书交易平台",
    "desc": "我要做一个校园二手书交易平台，目标用户是全国大学生，平台从每笔订单抽取5%服务费，我预计第一年做到10万用户。",
    "users": "全国大学生（项目方原文，未进一步细分）",
    "pain": "未提供",
    "solution": "校园二手书交易撮合平台",
    "model": "每笔订单抽取5%服务费；其余未提供",
    "stage": "想法阶段（未提供团队、进展、资源信息）",
}

# 真实报告正文
RT_BOOKS = body_of(REDTEAM_OUT / "case_1.md", "## 红队输出")
FIN_BOOKS = body_of(FINANCE_OUT / "case_1.md", "## 财务分析输出")

CONFLICT_FIN = """【财务可行性分析报告】
分析结论：数字成立
一句话依据：在项目方提供的保守参数下，基准情景单位经济为正，BEP可在第14个月达到。

三情景（基准）：付费用户转化8%，客单价199元/年，毛利率65%，CAC 45元，LTV 320元，LTV/CAC≈7.1；
固定成本年约120万元，BEP约需付费用户6200人，按渠道推导第14个月可达。
现金流：预收费模式，回款周期为正，达到BEP前需资金约90万元。
财务致命问题：无。高风险项：续费率假设（基准70%）待试点验证。
必须补充的财务数据：①真实续费率 ②渠道CAC实测。"""

CONFLICT_RT = """【红队审查报告】
审查结论：暂缓通过
致命问题：1个
高风险问题：1个

②【需求假设｜致命】项目方未提供任何需求证据：没有访谈记录、没有试用数据、没有用户现在如何解决问题的说明。
“用户需要这个产品”目前完全是项目方主观判断，在需求证伪之前，财务模型中的8%付费转化与199元客单价均无事实基础。
③【竞争假设｜高】未分析替代方案，用户迁移理由不明。
证据缺口：真实用户访谈、现有替代行为、付费意愿证据。
必须回答的问题：①访谈过多少目标用户 ②用户现在怎么解决 ③多少人表达过真实付费意向。
修改方向：必须先完成需求验证，再讨论增长。"""

POSITIVE_FIN = """【财务可行性分析报告】
分析结论：数字成立
一句话依据：基于试点真实数据，基准情景单位经济为正，BEP已在试点月跑通。

关键数字（来自试点3个月真实数据）：付费转化率11%，客单价299元/年，毛利率72%，
实测CAC 38元，首年LTV 260元（已含续费率58%实测），边际贡献为正；
固定成本月8万元，试点月收入12.3万元，已越过BEP。
压力测试：CAC翻倍至76元时LTV/CAC仍>3；转化率减半时BEP推迟约5个月，现金流可覆盖。
财务致命问题：无。高风险项：规模放大后CAC是否漂移（待持续监测）。"""

POSITIVE_RT = """【红队审查报告】
审查结论：有条件通过
致命问题：0个
高风险问题：1个
一般问题：2个

五维审查：用户假设已收窄到具体人群（本校+邻校考研学生，试点画像清晰）；
需求假设有真实证据（120人访谈、试点3个月付费转化11%、有持续使用记录）；
竞争假设：替代方案已穷举，试点数据显示用户迁移理由成立（微信群登记确实抢不到、投诉率高）；
商业假设：抽佣闭环已跑通，支付在小程序内完成，试点期无跳单；
壁垒假设｜高：目前壁垒仍弱，网络效应尚未形成，巨头进入风险仍在，需要在扩张期验证。
证据缺口：跨校复制数据、续费长期数据。
必须回答的问题：①第二所学校复制时转化率是否保持 ②续费第二年数据。
修改方向：必须在扩张中验证壁垒形成路径，不影响当前试点结论。"""

CASES = [
    {"id": 1, "name": "二手书-双真实报告-预期暂缓通过",
     "project": BOOKS, "finance": FIN_BOOKS, "redteam": RT_BOOKS},
    {"id": 2, "name": "缺财务报告-最高有条件通过",
     "project": BOOKS, "finance": MISSING, "redteam": RT_BOOKS},
    {"id": 3, "name": "缺红队报告-最高有条件通过",
     "project": BOOKS, "finance": FIN_BOOKS, "redteam": MISSING},
    {"id": 4, "name": "假冲突-财务成立但红队致命需求缺口",
     "project": {"name": "某订阅制学习工具", "desc": "（略）面向考研学生的订阅制学习工具，客单价199元/年。",
                 "users": "考研学生", "model": "订阅制199元/年", "stage": "想法阶段"},
     "finance": CONFLICT_FIN, "redteam": CONFLICT_RT},
    {"id": 5, "name": "双报告正面-试点已验证-预期通过/有条件通过",
     "project": {"name": "本校考研自习室预约小程序（试点版）",
                 "desc": "面向本校考研学生的自习室预约小程序，已试点3个月，支付在小程序内完成。",
                 "users": "本校及邻校考研学生", "model": "向自习室抽佣10%，试点已跑通支付闭环",
                 "stage": "试点运营阶段（有3个月真实数据）"},
     "finance": POSITIVE_FIN, "redteam": POSITIVE_RT},
]


def pick_client():
    for p in PLATFORMS:
        try:
            client = OpenAI(api_key=p["api_key"], base_url=p["base_url"], timeout=60)
            r = client.chat.completions.create(
                model=p["model"],
                messages=[{"role": "user", "content": "回复两个字：在的"}],
                max_tokens=200, temperature=0)
            msg = r.choices[0].message
            probe = msg.content or getattr(msg, "reasoning_content", None) or ""
            print(f"[平台] {p['name']} / {p['model']} 连通 -> {probe[:50]!r}")
            return client, p
        except Exception as e:
            print(f"[平台] {p['name']} / {p['model']} 不可用: {str(e)[:200]}")
    raise RuntimeError("所有平台均不可用")


def run_case(client, plat, system_prompt, case):
    user_msg = build_user_msg(case["project"], case["finance"], case["redteam"])
    t0 = time.time()
    resp = client.chat.completions.create(
        model=plat["model"],
        messages=[{"role": "system", "content": system_prompt},
                  {"role": "user", "content": user_msg}],
        temperature=0.3, max_tokens=16000)
    dt = time.time() - t0
    msg = resp.choices[0].message.content
    if not msg:
        rc = getattr(resp.choices[0].message, "reasoning_content", None)
        raise RuntimeError(f"正文为空。reasoning片段: {(rc or '')[:200]}")
    usage = resp.usage
    return msg, {"seconds": round(dt, 1), "prompt_tokens": usage.prompt_tokens,
                 "completion_tokens": usage.completion_tokens,
                 "platform": plat["name"], "model": plat["model"]}


def main():
    only = [int(x) for x in sys.argv[1:]] if len(sys.argv) > 1 else None
    system_prompt = PROMPT_FILE.read_text(encoding="utf-8")
    client, plat = pick_client()
    results = []
    for case in CASES:
        if only and case["id"] not in only:
            continue
        print(f"\n===== 案例{case['id']}：{case['name']} =====")
        try:
            content, meta = run_case(client, plat, system_prompt, case)
        except Exception as e:
            print(f"[错误] {e}")
            content, meta = f"[API错误] {e}", {"platform": plat["name"], "model": plat["model"]}
        out_file = OUT_DIR / f"case_{case['id']}.md"
        fin_note = "缺失" if case["finance"] == MISSING else f"{len(case['finance'])}字"
        rt_note = "缺失" if case["redteam"] == MISSING else f"{len(case['redteam'])}字"
        out_file.write_text(
            f"# 总指挥单测案例{case['id']}：{case['name']}\n\n"
            f"- 平台：{meta.get('platform')} / {meta.get('model')}\n"
            f"- 耗时：{meta.get('seconds')}s，tokens：{meta.get('prompt_tokens')}+{meta.get('completion_tokens')}\n"
            f"- 输入：财务报告[{fin_note}]，红队报告[{rt_note}]\n\n"
            f"## 总指挥输出\n\n{content}\n", encoding="utf-8")
        print(f"[已保存] {out_file}")
        results.append({"case": case["id"], **meta})
    (OUT_DIR / "run_meta.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n全部完成。")


if __name__ == "__main__":
    main()
