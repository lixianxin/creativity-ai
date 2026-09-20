# -*- coding: utf-8 -*-
"""
三Agent最小闭环联调（真实串联，非模拟）：
  用户项目 -> 财务分析官 -> 红队质疑官 -> 创业总指挥 -> 最终阶段结论
- 三个 Agent 的 Prompt 均来自 agents/prompts/
- 每个 Agent 的真实输出落盘到 tests/pipeline/outputs/run_<N>/
- 后一个 Agent 的输入 = 项目信息 + 前一个 Agent 的真实输出文件内容
用法: python run_pipeline.py [run编号 ...]   例如 python run_pipeline.py 1 2
"""
import sys
import time
import json
from pathlib import Path

from openai import OpenAI

ROOT = Path(__file__).resolve().parents[2]
PROMPT_DIR = ROOT / "agents" / "prompts"
OUT_ROOT = Path(__file__).resolve().parent / "outputs"

PLATFORMS = [
    {"name": "deepseek", "base_url": "https://api.deepseek.com",
     "api_key": "", "model": "deepseek-v4-flash"},
    {"name": "bailian",
     "base_url": "https://llm-969nmsfu6bcf8ozc.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
     "api_key": "", "model": "qwen-plus"},
    {"name": "zhipu", "base_url": "https://open.bigmodel.cn/api/paas/v4",
     "api_key": "", "model": "glm-5.1"},
]

# ---- 联调项目（固定3个）----
RUNS = [
    {
        "id": 1, "name": "校园二手书交易平台",
        "project": {
            "name": "校园二手书交易平台",
            "desc": "我要做一个校园二手书交易平台，目标用户是全国大学生，平台从每笔订单抽取5%服务费，我预计第一年做到10万用户。",
            "users": "全国大学生（项目方原文，未进一步细分）",
            "pain": "未提供",
            "solution": "校园二手书交易撮合平台",
            "model": "每笔订单抽取5%服务费；其余未提供",
            "stage": "想法阶段（未提供团队、进展、资源信息）",
        },
    },
    {
        "id": 2, "name": "校园AI产品-信息缺失",
        "project": {
            "name": "未命名校园AI产品",
            "desc": "我要做一个校园AI产品，具体功能还没想好，但我觉得市场很大。",
            "users": "未提供",
            "pain": "未提供",
            "solution": "未提供（功能还没想好）",
            "model": "未提供",
            "stage": "想法阶段",
        },
    },
    {
        "id": 3, "name": "考研自习室预约-双报告不同侧重",
        "project": {
            "name": "本校考研寄宿自习室预约与拼团平台",
            "desc": "我要做一个面向本校考研学生的寄宿自习室预约与拼团平台，已访谈120名备考学生，68人表示愿意每月付300元买固定座位，目前学校周边3家自习室空位靠微信群登记、经常抢不到，我打算先做微信小程序，向自习室抽佣10%。",
            "users": "本校考研学生（项目方原文）",
            "pain": "学校周边自习室空位靠微信群登记、经常抢不到",
            "solution": "微信小程序：自习室预约与拼团",
            "model": "向自习室抽佣10%；学生付自习室约300元/月",
            "stage": "想法阶段（有120人访谈，无真实付费/试点数据）",
        },
    },
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


def call(client, plat, system_prompt, user_content, label):
    t0 = time.time()
    resp = client.chat.completions.create(
        model=plat["model"],
        messages=[{"role": "system", "content": system_prompt},
                  {"role": "user", "content": user_content}],
        temperature=0.3, max_tokens=16000)
    dt = time.time() - t0
    content = resp.choices[0].message.content
    if not content:
        rc = getattr(resp.choices[0].message, "reasoning_content", None)
        raise RuntimeError(f"[{label}] 正文为空。reasoning: {(rc or '')[:200]}")
    u = resp.usage
    print(f"[{label}] {dt:.0f}s, tokens {u.prompt_tokens}+{u.completion_tokens}, {len(content)}字")
    return content


def finance_input(project):
    # 财务Agent直接面向项目描述
    return (f"项目名称：{project['name']}\n项目描述：{project['desc']}\n"
            f"目标用户：{project['users']}\n商业模式：{project['model']}\n当前阶段：{project['stage']}")


def redteam_input(project):
    return project["desc"]


def commander_input(project, finance_report, redteam_report):
    return (
        f"项目名称：\n{project['name']}\n\n项目描述：\n{project['desc']}\n\n"
        f"目标用户：\n{project['users']}\n\n核心痛点：\n{project['pain']}\n\n"
        f"解决方案：\n{project['solution']}\n\n商业模式：\n{project['model']}\n\n"
        f"当前阶段：\n{project['stage']}\n\n"
        f"===== 财务分析报告 =====\n{finance_report}\n\n"
        f"===== 红队审查报告 =====\n{redteam_report}\n"
    )


def main():
    only = [int(x) for x in sys.argv[1:]] if len(sys.argv) > 1 else None
    fin_prompt = (PROMPT_DIR / "finance_v1.md").read_text(encoding="utf-8")
    rt_prompt = (PROMPT_DIR / "red_team_v1.md").read_text(encoding="utf-8")
    cmd_prompt = (PROMPT_DIR / "commander_v1.md").read_text(encoding="utf-8")

    client, plat = pick_client()
    summary = []
    for run in RUNS:
        if only and run["id"] not in only:
            continue
        proj = run["project"]
        out_dir = OUT_ROOT / f"run_{run['id']}"
        out_dir.mkdir(parents=True, exist_ok=True)
        print(f"\n########## 联调 Run {run['id']}：{run['name']} ##########")

        print("--- 第1棒：财务分析官 ---")
        fin = call(client, plat, fin_prompt, finance_input(proj), "财务")
        (out_dir / "1_finance.md").write_text(
            f"# Run{run['id']} 财务分析输出\n\n## 输入\n{finance_input(proj)}\n\n## 输出\n\n{fin}\n",
            encoding="utf-8")

        print("--- 第2棒：红队质疑官 ---")
        rt = call(client, plat, rt_prompt, redteam_input(proj), "红队")
        (out_dir / "2_redteam.md").write_text(
            f"# Run{run['id']} 红队审查输出\n\n## 输入\n{redteam_input(proj)}\n\n## 输出\n\n{rt}\n",
            encoding="utf-8")

        print("--- 第3棒：创业总指挥（输入=项目+财务真实输出+红队真实输出）---")
        cmd = call(client, plat, cmd_prompt, commander_input(proj, fin, rt), "总指挥")
        (out_dir / "3_commander.md").write_text(
            f"# Run{run['id']} 总指挥最终结论\n\n## 输出\n\n{cmd}\n", encoding="utf-8")

        # 提取最终结论行便于验收
        verdict = "未识别"
        for line in cmd.splitlines():
            if "暂缓通过" in line:
                verdict = "暂缓通过"; break
            if "有条件通过" in line:
                verdict = "有条件通过"; break
            if line.strip() == "通过" or "结论：通过" in line:
                verdict = "通过"; break
        print(f"=== Run{run['id']} 最终结论：{verdict} ===")
        summary.append({"run": run["id"], "name": run["name"], "verdict": verdict})

    (OUT_ROOT / "pipeline_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n联调全部完成。")


if __name__ == "__main__":
    main()
