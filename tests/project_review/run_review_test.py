# -*- coding: utf-8 -*-
"""
项目评审官 V1.0 实测脚本
- 加载 agents/prompts/project_review_v1.md
- 输入：项目信息 + 各Agent报告结论摘要（模拟统一项目上下文注入）
- 5 案例：二手书全负面 / 财务红队假冲突 / 风险红线一票否决 / 普遍待补证 / 关键报告缺失
输出：tests/project_review/outputs/case_N.md
用法: python run_review_test.py [case编号 ...]
"""
import sys
import time
import json
from pathlib import Path

from openai import OpenAI

ROOT = Path(__file__).resolve().parents[2]
PROMPT_FILE = ROOT / "agents" / "prompts" / "project_review_v1.md"
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

PROJECT_BOOK = "项目名称：校园二手书交易平台\n项目描述：校园二手书交易撮合平台，目标用户全国大学生，平台代收货款后打给卖家，抽5%服务费，第一年目标10万用户。\n"

CASE1 = PROJECT_BOOK + """
==== 委员会各Agent报告结论摘要 ====
【用户洞察报告】结论：证据不足。“全国大学生”是统计口径非画像；痛点栏未提供；无任何访谈或行为证据；买卖双边启动问题未定义。
【市场分析报告】结论：证据不足。全国大学生非初期市场边界；TAM/SAM/SOM均无依据；SOM不得拍1%。
【竞品分析报告】结论：竞争假设存疑。闲鱼/微信群/跳蚤市场/学长赠送构成免费替代；无差异化证据；综合平台加频道成本极低。
【产品设计报告】结论：信息不足，无法可靠判断。无核心任务定义；建议先做人工MVP不开发系统；物流/社区/会员等功能明确不做。
【商业模式报告】结论：信息不足，无法可靠判断。付费方（卖家）付费价值未证明；资金虽过平台但同校面交后复购可绕开，存在去中介化断点。
【财务分析报告】结论：当前无法可靠计算。客单价/频次/CAC全缺；三情景演示下年收入量级难以覆盖团队固定成本（假设均待验证）。
【增长运营报告】结论：信息不足，无法可靠判断。核心任务未定义则激活无法定义；泛渠道全部延后。
【风险审查报告】结论：存在致命风险，待处置。致命1个：平台代收货款无支付牌照涉嫌二清；高风险6个（盗版资料、线下交易安全、学生身份核验等）。
【红队审查报告】结论：暂缓通过。致命2个：需求零证据（无任何用户访谈）；迁移与抽佣无基础（免费替代+5%抽佣方向相反）；高风险4个（画像过宽、10万用户无推导、壁垒不明等）。
【创业总指挥结论】暂缓通过；项目阶段：想法验证。
"""

CASE2 = """项目名称：某校园配送项目
项目描述：面向本校学生的零食夜宵即时配送，学生下单后30分钟送达，每单收配送费3元。
==== 委员会各Agent报告结论摘要 ====
【用户洞察报告】结论：证据不足。未提供任何访谈或行为证据；目标用户写“本校学生”未细分；夜宵需求频率与支付意愿待验证。
【财务分析报告】结论：数字成立（在假设前提下）。按日均800单、客单价25元、毛利35%假设，模型测算LTV/CAC=7.1，BEP在第8个月可达；注：转化率、单量、CAC均为假设值（待验证），尚无真实运营数据。
【红队审查报告】结论：暂缓通过。致命1个：需求假设——项目方未做任何用户调研，“夜宵配送需求强烈”为主观判断，且学校周边便利店/外卖平台已覆盖该时段；高风险2个（配送履约、壁垒）。
【风险审查报告】结论：部分可控，需前置应对。无致命风险；高风险为食品经营资质、骑手用工安全，上线前补齐即可。
（注：市场分析、竞品分析、产品设计、商业模式、增长运营报告本轮未提交。）
"""

CASE3 = """项目名称：创想∞ AI创业委员会
项目描述：面向大学生创新创业教育的多智能体创业项目审查与模拟路演空间，学生免费使用，学校购买机构版用于创业课程教学、大创筛选、大赛初评；产品基于大模型API开发，计划直接上线；项目方会收集学生提交的创业项目内容并考虑做脱敏数据服务对外提供；目前2所学校创业学院老师口头表示感兴趣。
==== 委员会各Agent报告结论摘要 ====
【用户洞察报告】结论：部分成立，待补证。学生侧“想法需要被质疑”的痛点有2所学校老师背书但学生访谈样本小；学校侧（老师/创业学院）需求以口头兴趣为主，属弱态度证据；建议真实课程试点验证。
【市场分析报告】结论：部分成立，待补证。高校创新创业教育采购市场边界清晰；单校采购预算与采购周期数据待验证。
【竞品分析报告】结论：部分清晰，待补证。通用大模型可自行完成部分审查为替代；差异化（多Agent委员会结构+教学流程嵌入）声称待验证。
【产品设计报告】结论：MVP部分成立，待补证。核心路径（提交想法→委员会报告→修改→二次审议）完整；机构版管理功能未定义。
【商业模式报告】结论：部分成立，待补证。B2B2C结构可画出；学校采购为付费方向，当前机构付费意向仅为老师口头兴趣（影响者≠预算决策者）；学生免费版与机构版价值分界线待验证。
【财务分析报告】结论：当前无法可靠计算。机构版定价、采购转化率、交付成本参数缺失；SaaS订阅收入参数待验证。
【增长运营报告】结论：增长路径部分成立，待补证。老师课堂任务为主渠道假设；无自然飞轮，推广停止增长停止。
【风险审查报告】结论：存在致命风险，待处置。致命2个：①计划把学生提交的创业项目内容脱敏后做数据服务对外提供，缺乏授权且去标识化≠匿名化；②基于大模型API直接对公众上线，未完成生成式AI服务备案与安全评估核验。
【红队审查报告】结论：有条件通过。无致命问题；高风险2个（学校付费意愿仅为老师口头兴趣、通用大模型为免费替代壁垒不明）；建议补真实采购意向与试点证据后复审。
【创业总指挥结论】有条件通过；项目阶段：方案修正。
"""

CASE4 = """项目名称：考研自习室预约平台
项目描述：面向本校考研学生的自习室预约小程序；学校周边3家自习室，空位靠微信群登记；已访谈120名学生，68人表示愿意每月付300元买固定座位；学生到店直接把座位费付给自习室商家，平台向商家抽每笔预约10%佣金。
==== 委员会各Agent报告结论摘要 ====
【用户洞察报告】结论：部分成立，待补证。120人访谈68人愿意付300元/月，弱态度级；访谈对象只有学生，无商家访谈。
【市场分析报告】结论：部分成立，待补证。边界清晰；座位供给刚性约束容量；规模数据待验证。
【竞品分析报告】结论：部分清晰，待补证。微信群+腾讯文档接龙为免费替代；商家可绕开平台。
【产品设计报告】结论：MVP部分成立，待补证。路径完整；预约锁定与核销闭环待真实测试。
【商业模式报告】结论：商业模式假设存疑。资金流在线下（学生直付商家），平台无法触发和监督抽佣，标注【商业闭环断点：去中介化】；满座商家无付佣动机；学生付300元≠商家付佣金。
【财务分析报告】结论：数字倾向不成立。抽佣闭环大概率不成立；极致乐观假设下年佣金上限仍难覆盖人力成本（假设均待验证）。
【增长运营报告】结论：增长路径部分成立，待补证。微信群为初始渠道；无自然飞轮。
【风险审查报告】结论：部分可控，需前置应对。无致命风险；高风险为预付资金与线下到店安全，机制可前置解决。
【红队审查报告】结论：暂缓通过。致命1个：付费方错位——需求侧学生愿意付费，但供给侧满座商家没有为平台付佣的动机，且资金不经平台；态度数据≠行为数据。
【创业总指挥结论】暂缓通过；项目阶段：想法验证。
"""

CASE5 = PROJECT_BOOK + """
==== 委员会各Agent报告结论摘要 ====
【财务分析报告】结论：当前无法可靠计算。客单价/频次/CAC全缺。
【红队审查报告】结论：暂缓通过。致命2个（需求零证据、迁移与抽佣无基础）。
（注：本轮只完成了财务分析与红队审查；用户洞察、市场、竞品、产品、商业模式、增长、风险审查报告均未提交；总指挥尚未汇总。）
"""

CASES = [
    {"id": 1, "name": "二手书-十报告齐备但多负面+二清红线", "input": CASE1},
    {"id": 2, "name": "财务成立vs红队需求致命-假冲突终裁", "input": CASE2},
    {"id": 3, "name": "各维尚可但风险红线-一票否决", "input": CASE3},
    {"id": 4, "name": "普遍待补证+红队致命-退回修改", "input": CASE4},
    {"id": 5, "name": "关键报告缺失-不予终审", "input": CASE5},
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
    t0 = time.time()
    resp = client.chat.completions.create(
        model=plat["model"],
        messages=[{"role": "system", "content": system_prompt},
                  {"role": "user", "content": case["input"]}],
        temperature=0.3, max_tokens=16000)
    dt = time.time() - t0
    content = resp.choices[0].message.content
    if not content:
        rc = getattr(resp.choices[0].message, "reasoning_content", None)
        raise RuntimeError(f"正文为空。reasoning片段: {(rc or '')[:200]}")
    usage = resp.usage
    return content, {"seconds": round(dt, 1), "prompt_tokens": usage.prompt_tokens,
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
        out_file.write_text(
            f"# 项目评审官案例{case['id']}：{case['name']}\n\n"
            f"- 平台：{meta.get('platform')} / {meta.get('model')}\n"
            f"- 耗时：{meta.get('seconds')}s，tokens：{meta.get('prompt_tokens')}+{meta.get('completion_tokens')}\n\n"
            f"## 输入\n\n{case['input']}\n\n"
            f"## 项目终审输出\n\n{content}\n", encoding="utf-8")
        print(f"[已保存] {out_file}")
        results.append({"case": case["id"], **meta})
    (OUT_DIR / "run_meta.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n全部完成。")


if __name__ == "__main__":
    main()
