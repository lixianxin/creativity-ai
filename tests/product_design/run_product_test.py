# -*- coding: utf-8 -*-
"""
产品设计官 V1.0 实测脚本
- 加载 agents/prompts/product_design_v1.md
- 5 案例：二手书最小闭环 / 学习助手8大功能堆砌 / 树洞信息不足 / 自习室短路径 / AI平台10大功能大全
输出：tests/product_design/outputs/case_N.md
用法: python run_product_test.py [case编号 ...]
"""
import sys
import time
import json
from pathlib import Path

from openai import OpenAI

ROOT = Path(__file__).resolve().parents[2]
PROMPT_FILE = ROOT / "agents" / "prompts" / "product_design_v1.md"
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
    {"id": 1, "name": "二手书-最小交易闭环",
     "input": "项目名称：校园二手书交易平台\n项目描述：我要做一个校园二手书交易平台，目标用户是全国大学生，平台从每笔订单抽取5%服务费，我预计第一年做到10万用户。我觉得平台需要：物流系统、智能推荐、社区论坛、信用评价、在线支付、晒单分享、会员体系、新人优惠券。\n目标用户：全国大学生\n核心痛点：未提供\n解决方案：校园二手书交易撮合平台\n商业模式：每笔订单抽5%服务费\n当前阶段：想法阶段"},
    {"id": 2, "name": "AI学习助手-8大功能堆砌压力测试",
     "input": "项目名称：AI学习助手\n项目描述：我要做一个AI学习助手，面向所有学生，完全免费，靠广告盈利，第一年100万用户。功能方面我们规划了：拍照搜题、知识点讲解、AI错题本、智能学习计划、AI聊天陪伴、学习社区、积分商城、排行榜，这些全部都要在第一版做，一个都不能少，这样用户才会觉得我们功能全、有竞争力。\n目标用户：所有学生\n核心痛点：未提供\n解决方案：AI学习助手\n商业模式：免费+广告\n当前阶段：想法阶段"},
    {"id": 3, "name": "树洞-信息严重不足",
     "input": "项目名称：校园树洞\n项目描述：我们希望让学生有一个匿名表达的空间。\n目标用户：学生\n核心痛点：想匿名表达\n解决方案：未提供\n商业模式：未提供\n当前阶段：想法阶段"},
    {"id": 4, "name": "自习室-查找预约短路径",
     "input": "项目名称：本校考研自习室预约小程序\n项目描述：我只做本校考研学生的自习室预约，学校周边有3家自习室，目前空位靠微信群登记、经常抢不到。已访谈120名备考学生，68人表示愿意每月付300元买固定座位。用户的核心需求是快速知道哪里有空座位并能锁定座位：查找可预约座位→预约→到店使用。我打算先做微信小程序。\n目标用户：本校考研学生\n核心痛点：空位靠微信群登记、经常抢不到\n解决方案：微信小程序预约\n商业模式：向自习室抽佣10%\n当前阶段：想法阶段（有120人访谈，未上线）"},
    {"id": 5, "name": "AI平台10大功能大全-砍功能压力测试",
     "input": "项目名称：AI创业超级平台\n项目描述：我们的AI创业平台要做：AI问答、AI写作、AI绘图、AI视频、AI社区、AI商城、AI课程、AI招聘、AI社交、AI游戏。我们认为AI是未来趋势，功能越全用户越多，十大功能形成生态闭环，竞争壁垒极高，目标用户是所有有需求的人。\n目标用户：所有有需求的人\n核心痛点：未提供\n解决方案：十大AI功能生态平台\n商业模式：未提供\n当前阶段：想法阶段"},
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
            f"# 产品设计官案例{case['id']}：{case['name']}\n\n"
            f"- 平台：{meta.get('platform')} / {meta.get('model')}\n"
            f"- 耗时：{meta.get('seconds')}s，tokens：{meta.get('prompt_tokens')}+{meta.get('completion_tokens')}\n\n"
            f"## 输入\n\n{case['input']}\n\n"
            f"## 产品设计输出\n\n{content}\n", encoding="utf-8")
        print(f"[已保存] {out_file}")
        results.append({"case": case["id"], **meta})
    (OUT_DIR / "run_meta.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n全部完成。")


if __name__ == "__main__":
    main()
