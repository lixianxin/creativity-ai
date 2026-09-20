# -*- coding: utf-8 -*-
"""
风险审查官 V1.0 实测脚本
- 加载 agents/prompts/risk_review_v1.md
- 5 案例：二手书(盗版/面交/资金) / AI学习助手(双减/未成年广告/AI内容)
        / 匿名树洞(UGC/实名/网暴/危机) / AI创业委员会(AI备案/IP/免责) / 信息不足
输出：tests/risk_review/outputs/case_N.md
用法: python run_risk_test.py [case编号 ...]
"""
import sys
import time
import json
from pathlib import Path

from openai import OpenAI

ROOT = Path(__file__).resolve().parents[2]
PROMPT_FILE = ROOT / "agents" / "prompts" / "risk_review_v1.md"
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
    {"id": 1, "name": "二手书-盗版面交资金风险",
     "input": "项目名称：校园二手书交易平台\n项目描述：我要做一个校园二手书交易平台，目标用户是全国大学生，学生可以在上面买卖二手教材和资料，平台撮合后学生线下见面交易，钱先付给平台、确认收货后平台再打给卖家，平台从每笔订单抽5%服务费。第一年目标10万用户。\n目标用户：全国大学生\n核心痛点：未提供\n解决方案：校园二手书交易撮合平台，平台代收货款\n商业模式：平台代收代付货款，抽5%服务费\n当前阶段：想法阶段"},
    {"id": 2, "name": "AI学习助手-双减与未成年广告",
     "input": "项目名称：AI学习助手\n项目描述：我要做一个AI学习助手，面向所有学生（包括中小学生），可以拍照搜题、AI讲题、批改作业，完全免费靠广告盈利，广告包括游戏广告和培训课程广告。我们会收集学生的学习记录和做题数据用来优化推荐。第一年目标100万用户。\n目标用户：所有学生，含中小学生\n核心痛点：未提供\n解决方案：AI拍照搜题+讲题+作业批改\n商业模式：免费+广告（游戏、培训课程广告）\n当前阶段：想法阶段"},
    {"id": 3, "name": "匿名树洞-UGC内容责任",
     "input": "项目名称：校园树洞\n项目描述：我们做一个校园匿名树洞小程序，学生可以匿名发表白、吐槽、心事、挂人，完全不需要注册手机号，打开就能发帖，也可以评论别人的帖子。我们认为绝对匿名才有人敢说真话，所以不做任何审核，学生发什么都可以，也不设举报功能。\n目标用户：在校大学生\n核心痛点：想匿名表达\n解决方案：无注册、无审核的匿名发帖小程序\n商业模式：未提供\n当前阶段：想法阶段"},
    {"id": 4, "name": "AI创业委员会-生成式AI合规与IP",
     "input": "项目名称：创想∞ AI创业委员会\n项目描述：这是面向大学生创新创业教育的多智能体创业项目审查与模拟路演空间。学生把创业想法输入后，AI委员会给出结构化审查报告和修改建议，学生免费；学校购买机构版用于创业课程教学、大创项目筛选、创业大赛初赛评审，项目方会收集学生提交的创业项目内容和报告数据，并考虑把脱敏后的项目数据做成数据服务对外提供。产品基于大模型API开发，计划直接上线对外服务。\n目标用户：有创业想法的大学生；高校创业学院\n核心痛点：学生创业想法缺乏专业质疑；学校指导师资不足\n解决方案：多智能体AI审查SaaS\n商业模式：学生免费；学校机构版采购；数据服务\n当前阶段：产品原型阶段"},
    {"id": 5, "name": "信息不足",
     "input": "项目名称：未命名校园产品\n项目描述：我要做一个校园产品，具体功能还没想好，但我觉得市场很大，先做起来再说，合规什么的等用户多了再考虑。\n目标用户：未提供\n核心痛点：未提供\n解决方案：未提供\n商业模式：未提供\n当前阶段：想法阶段"},
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
            f"# 风险审查官案例{case['id']}：{case['name']}\n\n"
            f"- 平台：{meta.get('platform')} / {meta.get('model')}\n"
            f"- 耗时：{meta.get('seconds')}s，tokens：{meta.get('prompt_tokens')}+{meta.get('completion_tokens')}\n\n"
            f"## 输入\n\n{case['input']}\n\n"
            f"## 风险审查输出\n\n{content}\n", encoding="utf-8")
        print(f"[已保存] {out_file}")
        results.append({"case": case["id"], **meta})
    (OUT_DIR / "run_meta.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n全部完成。")


if __name__ == "__main__":
    main()
