# -*- coding: utf-8 -*-
"""
增长运营官 V1.0 实测脚本
- 加载 agents/prompts/growth_ops_v1.md
- 5 案例：二手书社群获客 / 学习助手8渠道堆砌 / 树洞朋友圈裂变 / AI创业委员会B2B2C / 万能公式
输出：tests/growth/outputs/case_N.md
用法: python run_growth_test.py [case编号 ...]
"""
import sys
import time
import json
from pathlib import Path

from openai import OpenAI

ROOT = Path(__file__).resolve().parents[2]
PROMPT_FILE = ROOT / "agents" / "prompts" / "growth_ops_v1.md"
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
    {"id": 1, "name": "二手书-校园社群获客",
     "input": "项目名称：校园二手书交易平台\n项目描述：我要做一个校园二手书交易平台，目标用户是全国大学生，学生可以在上面买卖二手教材，平台撮合同校交易，从卖家抽5%服务费。第一批用户我们打算通过校园社群获取，第一年目标10万用户。\n目标用户：全国大学生\n核心痛点：未提供\n解决方案：校园二手书交易撮合平台\n商业模式：向卖家抽5%服务费\n当前阶段：想法阶段，产品未上线"},
    {"id": 2, "name": "AI学习助手-8渠道堆砌压力测试",
     "input": "项目名称：AI学习助手\n项目描述：我要做一个AI学习助手，面向所有学生，完全免费靠广告盈利。增长方面我们规划：拍抖音短视频、做小红书笔记、校园公众号投放、B站UP主合作、微博话题，同时投信息流广告、招募1000个校园大使、建500个学生社群、做邀请裂变活动。我们认为全渠道铺开，用户肯定会快速增长，第一年100万用户没问题。\n目标用户：所有学生\n核心痛点：未提供\n解决方案：AI学习助手\n商业模式：免费+广告\n当前阶段：想法阶段，产品未上线"},
    {"id": 3, "name": "树洞-朋友圈裂变陷阱",
     "input": "项目名称：校园树洞\n项目描述：我们做一个校园匿名树洞小程序，学生可以匿名发表白、吐槽、心事。我们的增长逻辑是：学生发帖以后可以一键分享到朋友圈，朋友们看到就会点进来，大家自发传播，所以一定会裂变增长。\n目标用户：在校大学生\n核心痛点：想匿名表达\n解决方案：匿名树洞小程序\n商业模式：未提供\n当前阶段：想法阶段"},
    {"id": 4, "name": "AI创业委员会-B2C加B2B2C双路径",
     "input": "项目名称：创想∞ AI创业委员会\n项目描述：这是面向大学生创新创业教育的多智能体创业项目验证、审议与路演空间。学生把创业想法输入后，AI委员会（用户洞察、市场、竞品、产品、商业模式、财务、红队、总指挥、评审、路演等Agent）给出结构化审查报告、修改建议和模拟路演反馈，学生端免费。学校可以购买机构版，用于创业课程教学、大创项目筛选、创业大赛初赛评审，按年采购。目前产品原型已完成，2所学校的创业学院老师口头表示感兴趣。增长上我们希望先把学生用户量做大，再拿学生数据去谈学校采购。\n目标用户：有创业想法的大学生（使用者）；高校创业学院（潜在付费方）\n核心痛点：学生创业想法缺乏专业质疑与打磨；学校创业指导师资不足、项目筛选工作量大\n解决方案：多智能体AI创业委员会SaaS\n商业模式：学生免费；学校机构版年度采购\n当前阶段：产品原型阶段"},
    {"id": 5, "name": "增长万能公式陷阱",
     "input": "项目名称：大学生综合服务平台\n项目描述：我们的产品很好，是一个面向大学生的综合服务平台。增长策略已经很清晰：招募10000个校园大使、准备100万广告预算投放、建100个校园社群、每天给用户推送消息、做邀请返现活动（邀请一个同学返5元）。我们认为只要把这五件事做足，用户就一定能增长。\n目标用户：大学生\n核心痛点：未提供\n解决方案：大学生综合服务平台\n商业模式：未提供\n当前阶段：想法阶段，产品未上线"},
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
            f"# 增长运营官案例{case['id']}：{case['name']}\n\n"
            f"- 平台：{meta.get('platform')} / {meta.get('model')}\n"
            f"- 耗时：{meta.get('seconds')}s，tokens：{meta.get('prompt_tokens')}+{meta.get('completion_tokens')}\n\n"
            f"## 输入\n\n{case['input']}\n\n"
            f"## 增长运营分析输出\n\n{content}\n", encoding="utf-8")
        print(f"[已保存] {out_file}")
        results.append({"case": case["id"], **meta})
    (OUT_DIR / "run_meta.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n全部完成。")


if __name__ == "__main__":
    main()
