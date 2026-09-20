# -*- coding: utf-8 -*-
"""
用户洞察官 V1.0 实测脚本
- 加载 agents/prompts/user_insight_v1.md
- 5 个案例：画像过宽/过宽+免费广告/有访谈证据(应承认但指出局限)/使用者付费者分离/信息不足
输出：tests/user_insight/outputs/case_N.md
用法: python run_user_insight_test.py [case编号 ...]
"""
import sys
import time
import json
from pathlib import Path

from openai import OpenAI

ROOT = Path(__file__).resolve().parents[2]
PROMPT_FILE = ROOT / "agents" / "prompts" / "user_insight_v1.md"
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
    {"id": 1, "name": "二手书-画像过宽无证据",
     "input": "项目名称：校园二手书交易平台\n项目描述：我要做一个校园二手书交易平台，目标用户是全国大学生，平台从每笔订单抽取5%服务费，我预计第一年做到10万用户。\n目标用户：全国大学生\n核心痛点：未提供\n解决方案：校园二手书交易撮合平台\n商业模式：每笔订单抽5%服务费\n当前阶段：想法阶段"},
    {"id": 2, "name": "AI学习助手-所有学生+免费广告",
     "input": "项目名称：AI学习助手\n项目描述：我要做一个AI学习助手，面向所有学生，完全免费，未来靠广告盈利，预计第一年100万用户。\n目标用户：所有学生\n核心痛点：未提供\n解决方案：AI学习助手\n商业模式：免费+广告\n当前阶段：想法阶段"},
    {"id": 3, "name": "考研自习室-有访谈证据-考证据质量识别",
     "input": "项目名称：考研寄宿自习室预约与拼团平台\n项目描述：我要做一个面向本校考研学生的寄宿自习室预约与拼团平台，已访谈120名备考学生，68人表示愿意每月付300元买固定座位，目前学校周边3家自习室空位靠微信群登记、经常抢不到，我打算先做微信小程序，向自习室抽佣10%。\n目标用户：本校考研学生\n核心痛点：自习室空位靠微信群登记、经常抢不到\n解决方案：微信小程序预约+拼团\n商业模式：向自习室抽佣10%\n当前阶段：想法阶段（有120人访谈，无真实付费）"},
    {"id": 4, "name": "银发App-使用者付费者分离",
     "input": "项目名称：老年人智能手机教学App\n项目描述：我要做一个教老年人用智能手机的App，视频课程教他们用微信、挂号、打车，老人免费用，子女会员付费99元/年，预计第一年50万用户。\n目标用户：老年人\n核心痛点：老人不会用智能手机\n解决方案：视频课程App\n商业模式：老人免费，子女会员99元/年\n当前阶段：想法阶段"},
    {"id": 5, "name": "功能没想好-信息不足",
     "input": "项目名称：未命名校园AI产品\n项目描述：我要做一个校园AI产品，具体功能还没想好，但我觉得市场很大。\n目标用户：未提供\n核心痛点：未提供\n解决方案：未提供\n商业模式：未提供\n当前阶段：想法阶段"},
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
            f"# 用户洞察官案例{case['id']}：{case['name']}\n\n"
            f"- 平台：{meta.get('platform')} / {meta.get('model')}\n"
            f"- 耗时：{meta.get('seconds')}s，tokens：{meta.get('prompt_tokens')}+{meta.get('completion_tokens')}\n\n"
            f"## 输入\n\n{case['input']}\n\n"
            f"## 用户洞察输出\n\n{content}\n", encoding="utf-8")
        print(f"[已保存] {out_file}")
        results.append({"case": case["id"], **meta})
    (OUT_DIR / "run_meta.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n全部完成。")


if __name__ == "__main__":
    main()
