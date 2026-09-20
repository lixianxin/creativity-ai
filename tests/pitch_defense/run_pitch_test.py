# -*- coding: utf-8 -*-
"""
路演答辩官 V1.0 实测脚本
- 加载 agents/prompts/pitch_defense_v1.md
- 输入：项目信息+路演陈述（BP口径）+ 委员会各报告结论摘要
- 5 案例：二手书全薄弱 / B2B2C部分可防御 / BP口径与报告矛盾 / BP大话 / 信息不足
输出：tests/pitch_defense/outputs/case_N.md
用法: python run_pitch_test.py [case编号 ...]
"""
import sys
import time
import json
from pathlib import Path

from openai import OpenAI

ROOT = Path(__file__).resolve().parents[2]
PROMPT_FILE = ROOT / "agents" / "prompts" / "pitch_defense_v1.md"
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

CASE1 = """项目名称：校园二手书交易平台
项目描述：校园二手书交易撮合平台，目标用户全国大学生，平台从每笔订单抽5%服务费，第一年目标10万用户。
【路演陈述/BP口径】我们做校园二手书交易平台，市场巨大，全国3000万大学生都是我们的用户。平台轻资产运营，通过校园社群裂变快速获客，第一年10万用户完全没问题。我们有先发优势，团队执行力强，闲鱼做不了校园这种熟人场景。
==== 委员会各Agent报告结论摘要 ====
【用户洞察报告】证据不足。“全国大学生”是统计口径非画像；痛点栏未提供；零访谈零行为证据。
【市场分析报告】证据不足。TAM/SAM/SOM均无依据；3000万大学生总消费≠项目市场。
【竞品分析报告】竞争假设存疑。闲鱼/微信群/跳蚤市场/学长赠送为免费替代；无差异化证据。
【产品设计报告】信息不足。无核心任务定义；建议先人工MVP。
【商业模式报告】信息不足。付费方价值未证明；存在去中介化断点。
【财务分析报告】当前无法可靠计算。客单价/频次/CAC全缺；假设演示下年收入量级难覆盖团队成本。
【增长运营报告】信息不足。核心任务未定义，激活无法定义；泛渠道全部延后。
【风险审查报告】存在致命风险，待处置。致命1个：平台代收货款无牌照涉嫌二清。
【红队审查报告】暂缓通过。致命2个：需求零证据；迁移与抽佣无基础。
【项目评审报告】暂缓，回到修改循环。五维1/1/1/2/1，二清红线未清除。
"""

CASE2 = """项目名称：创想∞ AI创业委员会
项目描述：面向大学生创新创业教育的多智能体创业项目审查与模拟路演空间；学生免费，学校机构版按年采购；产品原型已完成，2所学校创业学院老师口头表示感兴趣。
【路演陈述/BP口径】我们是AI时代的创业教育基础设施。学生输入创业想法，12个AI专家委员给出结构化审查和模拟路演反馈。学生端免费形成流量，学校按年采购机构版用于课程教学和项目筛选。目前已有2所学校明确表达合作意向，预计明年进入20所学校。
==== 委员会各Agent报告结论摘要 ====
【用户洞察报告】部分成立，待补证。学生侧痛点有2所学校老师背书但学生访谈样本小；学校侧需求为老师口头兴趣（弱态度，影响者≠预算决策者）。
【市场分析报告】部分成立，待补证。高校创新创业教育采购市场边界清晰；单校采购预算与采购周期数据待验证。
【竞品分析报告】部分清晰，待补证。通用大模型可自行完成部分审查为替代；多Agent委员会结构+教学流程嵌入的差异化待验证。
【产品设计报告】MVP部分成立，待补证。核心路径（提交→报告→修改→二审）完整；机构版管理功能未定义。
【商业模式报告】部分成立，待补证。B2B2C结构可画出；老师口头兴趣≠采购承诺；免费与机构版价值分界线待验证。
【财务分析报告】当前无法可靠计算。机构版定价、采购转化率、交付成本参数缺失。
【增长运营报告】增长路径部分成立，待补证。老师课堂任务为主渠道假设；无自然飞轮，推广停止增长停止。
【风险审查报告】存在致命风险，待处置。致命2个：学生项目内容做脱敏数据服务缺授权且去标识化≠匿名化；大模型API直接对公众上线未完成生成式AI备案与安评。
【红队审查报告】有条件通过。无致命；高风险2个（学校付费仅口头兴趣、通用大模型免费替代）。
【项目评审报告】暂缓（红线一票否决）；商业与财务维2分、风险与合规维1分。
"""

CASE3 = """项目名称：考研自习室预约平台
项目描述：面向本校考研学生的自习室预约小程序；3家自习室，空位靠微信群登记；已访谈120名学生；学生到店直付商家，平台向商家抽每笔预约10%佣金。
【路演陈述/BP口径】我们的需求已经充分验证：访谈显示90%以上的学生强烈需要我们的产品，68人已经明确愿意付费，商业模式完全跑通。我们和自习室老板关系很好，他们都愿意接入。预计上线后第一个月就能实现盈利。
==== 委员会各Agent报告结论摘要 ====
【用户洞察报告】部分成立，待补证。120人访谈、68人口头愿意付300元/月，属弱态度级证据（口头愿意≠付费）；访谈对象只有学生，供给侧自习室商家零访谈、零证据。
【商业模式报告】商业模式假设存疑。资金流在线下（学生直付商家），平台无法触发和监督抽佣，标注【商业闭环断点：去中介化】；满座商家无付佣动机；学生付300元≠商家付佣金。
【财务分析报告】数字倾向不成立。抽佣闭环大概率不成立；极致乐观假设下年佣金上限仍难覆盖人力成本。
【红队审查报告】暂缓通过。致命1个：付费方错位——学生愿意付费≠商家愿意付佣；态度数据≠行为数据。
【项目评审报告】暂缓，退回想法验证：商业与财务维2分，需补供给侧商家行为证据与真实资金流测试。
（其余报告本轮未提交。）
"""

CASE4 = """项目名称：大学生综合服务超级平台
项目描述：面向大学生的综合服务平台。
【路演陈述/BP口径】我们站在万亿级校园经济的风口，打造大学生一站式生活服务超级入口。团队来自顶尖高校，拥有丰富的校园资源和深厚的技术积累，商业模式已被验证，将通过生态化反、矩阵式增长迅速占领全国市场，三年内成为校园经济第一股。我们的壁垒是团队、情怀和对大学生的深刻理解。
==== 委员会各Agent报告结论摘要 ====
（本项目尚未提交任何Agent审查报告；项目方仅提供以上BP陈述。）
"""

CASE5 = """项目名称：未命名校园产品
项目描述：我要做一个校园产品，具体功能还没想好，但我觉得市场很大，先做起来再说。
【路演陈述/BP口径】无。
==== 委员会各Agent报告结论摘要 ====
（无。）
"""

CASES = [
    {"id": 1, "name": "二手书-全薄弱多击穿", "input": CASE1},
    {"id": 2, "name": "AI创业委员会-部分可防御+红线", "input": CASE2},
    {"id": 3, "name": "自习室-BP口径与报告矛盾", "input": CASE3},
    {"id": 4, "name": "BP大话无报告", "input": CASE4},
    {"id": 5, "name": "信息不足", "input": CASE5},
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
            f"# 路演答辩官案例{case['id']}：{case['name']}\n\n"
            f"- 平台：{meta.get('platform')} / {meta.get('model')}\n"
            f"- 耗时：{meta.get('seconds')}s，tokens：{meta.get('prompt_tokens')}+{meta.get('completion_tokens')}\n\n"
            f"## 输入\n\n{case['input']}\n\n"
            f"## 模拟路演答辩输出\n\n{content}\n", encoding="utf-8")
        print(f"[已保存] {out_file}")
        results.append({"case": case["id"], **meta})
    (OUT_DIR / "run_meta.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n全部完成。")


if __name__ == "__main__":
    main()
