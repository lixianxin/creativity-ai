# -*- coding: utf-8 -*-
"""
商业模式官 V1.0 实测脚本
- 加载 agents/prompts/business_model_v1.md
- 5 案例：二手书抽佣 / 免费+广告 / 自习室双边抽佣 / AI创业委员会B2B2C / 收入大杂烩
输出：tests/business_model/outputs/case_N.md
用法: python run_business_model_test.py [case编号 ...]
"""
import sys
import time
import json
from pathlib import Path

from openai import OpenAI

ROOT = Path(__file__).resolve().parents[2]
PROMPT_FILE = ROOT / "agents" / "prompts" / "business_model_v1.md"
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

CASES = [
    {"id": 1, "name": "二手书-双边抽佣与去中介化",
     "input": "项目名称：校园二手书交易平台\n项目描述：我要做一个校园二手书交易平台，目标用户是全国大学生。学生可以在上面买书和卖书，平台负责撮合。我们计划向卖家抽取每笔订单5%的服务费，第一年目标10万用户。\n目标用户：全国大学生（买书和卖书的学生）\n核心痛点：未提供\n解决方案：校园二手书交易撮合平台\n商业模式：向卖家每笔订单抽5%服务费\n当前阶段：想法阶段"},
    {"id": 2, "name": "AI学习助手-用户多=广告赚钱?",
     "input": "项目名称：AI学习助手\n项目描述：我要做一个AI学习助手，面向所有学生，完全免费。我们的逻辑是：学生很多、用户量会很大，学生每天都要用，所以广告商一定愿意来投放广告，我们靠广告收入就能盈利，第一年目标100万用户。\n目标用户：所有学生\n核心痛点：未提供\n解决方案：AI学习助手\n商业模式：学生免费，广告收入\n当前阶段：想法阶段"},
    {"id": 3, "name": "自习室-商家付佣与绕开平台",
     "input": "项目名称：本校考研自习室预约小程序\n项目描述：我只做本校考研学生的自习室预约。学生在小程序上查找空座位并预约，到店后直接把座位费付给自习室商家，平台向自习室商家收取每笔预约10%的佣金。学校周边有3家自习室，目前空位靠微信群登记、经常抢不到。已访谈120名备考学生，68人表示愿意每月付300元买固定座位。\n目标用户：本校考研学生\n核心痛点：自习室抢不到座位\n解决方案：微信小程序预约\n商业模式：向自习室商家抽取每笔预约10%佣金（学生到店直接付给商家）\n当前阶段：想法阶段（有120人访谈，未上线）"},
    {"id": 4, "name": "AI创业委员会-学生免费学校采购",
     "input": "项目名称：创想∞ AI创业委员会\n项目描述：这是一个面向大学生创新创业教育的多智能体创业项目验证、审议与路演空间。学生把创业想法输入后，AI委员会（用户洞察、市场分析、竞品分析、产品设计、商业模式、财务分析、红队质疑、总指挥、项目评审、路演答辩等Agent）会给出结构化的项目审查报告、修改建议和模拟路演反馈。学生端免费使用。我们同时在和学校谈：学校可以购买机构版，用于创业课程教学、创新创业训练计划的项目筛选、以及创业大赛初赛评审，按学校/学院年度采购付费。目前有2所学校的创业学院老师表示感兴趣。\n目标用户：有创业想法的大学生（使用者）；高校创业学院/创新创业教育中心（可能的付费方）\n核心痛点：学生创业想法缺乏专业、即时的质疑与打磨；学校创业指导师资不足、项目筛选工作量大\n解决方案：多智能体AI创业委员会SaaS\n商业模式：学生免费；学校/学院机构版年度采购（B2B2C）\n当前阶段：产品原型阶段，2所学校老师口头表示感兴趣"},
    {"id": 5, "name": "收入大杂烩-拒绝堆砌",
     "input": "项目名称：大学生AI学习效率平台\n项目描述：这是一个帮助大学生提升学习效率的AI平台，目前用户增长很快（具体数据还没统计）。未来盈利方式很多：可以卖会员、可以接广告、可以卖课程、可以做电商抽佣、可以和企业合作、还可以卖数据服务。我们觉得变现路径非常丰富，商业模式很成熟。\n目标用户：大学生\n核心痛点：学习效率低\n解决方案：AI学习效率平台\n商业模式：会员+广告+课程+电商抽佣+企业合作+数据服务\n当前阶段：想法阶段"},
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
            f"# 商业模式官案例{case['id']}：{case['name']}\n\n"
            f"- 平台：{meta.get('platform')} / {meta.get('model')}\n"
            f"- 耗时：{meta.get('seconds')}s，tokens：{meta.get('prompt_tokens')}+{meta.get('completion_tokens')}\n\n"
            f"## 输入\n\n{case['input']}\n\n"
            f"## 商业模式分析输出\n\n{content}\n", encoding="utf-8")
        print(f"[已保存] {out_file}")
        results.append({"case": case["id"], **meta})
    (OUT_DIR / "run_meta.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n全部完成。")


if __name__ == "__main__":
    main()
