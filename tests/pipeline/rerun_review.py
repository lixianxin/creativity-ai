# -*- coding: utf-8 -*-
"""
单棒重跑：项目评审官（修复 max_tokens 截断）
- 读取指定 full_run 目录下前10棒的真实输出
- 重新调用项目评审官 Prompt，max_tokens=20000
- 覆盖原 11_project_review.md
用法: python rerun_review.py <full_run目录名>
示例: python rerun_review.py full_run_1788706135
"""
import sys
import time
import json
import re
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

AGENT_LABEL = {
    "user_insight": "用户洞察官", "market_analysis": "市场分析官",
    "competitor_analysis": "竞品分析官", "product_design": "产品设计官",
    "business_model": "商业模式官", "finance": "财务分析官",
    "growth_ops": "增长运营官", "risk_review": "风险审查官",
    "red_team": "红队质疑官", "commander": "创业总指挥",
}

STAGE_ORDER = [
    "01_user_insight", "02_market_analysis", "03_competitor_analysis",
    "04_product_design", "05_business_model", "06_finance",
    "07_growth_ops", "08_risk_review", "09_red_team", "10_commander",
]


def extract_output(filepath):
    """从联调输出文件中提取'## 输出'之后的真实 Agent 输出"""
    text = filepath.read_text(encoding="utf-8")
    # 取最后一个 "## 输出" 之后的内容
    parts = text.split("## 输出")
    if len(parts) < 2:
        return text
    return parts[-1].strip()


def pick_client():
    for p in PLATFORMS:
        try:
            client = OpenAI(api_key=p["api_key"], base_url=p["base_url"], timeout=120)
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


def main():
    if len(sys.argv) < 2:
        print("用法: python rerun_review.py <full_run目录名>")
        print("示例: python rerun_review.py full_run_1788706135")
        return

    run_dir = OUT_ROOT / sys.argv[1]
    if not run_dir.exists():
        print(f"目录不存在: {run_dir}")
        return

    # 读取前10棒输出
    reports = {}
    project_text = None
    for stage in STAGE_ORDER:
        f = run_dir / f"{stage}.md"
        if not f.exists():
            print(f"[跳过] 缺少 {f.name}")
            continue
        agent = stage.split("_", 1)[1]
        out = extract_output(f)
        reports[agent] = out
        # 从第一棒提取项目原文（输入部分）
        if project_text is None:
            text = f.read_text(encoding="utf-8")
            m = re.search(r"## 输入\n\n(.*?)\n\n## 输出", text, re.S)
            if m:
                project_text = m.group(1).strip()

    if project_text is None:
        print("[错误] 无法从第一棒提取项目原文")
        return

    print(f"已加载 {len(reports)} 份前置报告")

    # 构造评审官输入
    parts = [project_text, "\n==== 委员会各Agent报告 ===="]
    for stage in STAGE_ORDER:
        agent = stage.split("_", 1)[1]
        if agent in reports:
            parts.append(f"\n【{AGENT_LABEL[agent]}报告】\n{reports[agent]}")
    user_input = "\n".join(parts)

    # 调用评审官
    prompt = (PROMPT_DIR / "project_review_v1.md").read_text(encoding="utf-8")
    client, plat = pick_client()

    print("\n--- 重跑第11棒：项目评审官（max_tokens=20000）---")
    t0 = time.time()
    resp = client.chat.completions.create(
        model=plat["model"],
        messages=[{"role": "system", "content": prompt},
                  {"role": "user", "content": user_input}],
        temperature=0.3, max_tokens=20000)
    dt = time.time() - t0
    content = resp.choices[0].message.content
    if not content:
        rc = getattr(resp.choices[0].message, "reasoning_content", None)
        raise RuntimeError(f"正文为空。reasoning: {(rc or '')[:200]}")
    u = resp.usage
    print(f"[项目评审官] {dt:.0f}s, tokens {u.prompt_tokens}+{u.completion_tokens}, {len(content)}字")

    # 覆盖原文件
    out_file = run_dir / "11_project_review.md"
    out_file.write_text(
        f"# 第11棒 项目评审官（重跑修复版）\n\n"
        f"- 平台：{plat['name']} / {plat['model']}\n"
        f"- 耗时：{round(dt,1)}s，tokens：{u.prompt_tokens}+{u.completion_tokens}\n"
        f"- 修复说明：max_tokens 从 16000 提升至 20000，确保完整九栏目输出\n\n"
        f"## 输入\n\n{user_input}\n\n## 输出\n\n{content}\n",
        encoding="utf-8")
    print(f"[已覆盖] {out_file}")

    # 验收检查
    has_verdict = "终审结论" in content
    has_redline = "一票否决" in content and "不得直接准入路演" in content
    print(f"\n===== 验收 =====")
    print(f"1. 报告完整落盘：{'✅' if out_file.exists() else '❌'}")
    print(f"2. 终审结论栏目存在：{'✅' if has_verdict else '❌'}")
    print(f"3. 致命红线→不得直接准入路演：{'✅' if has_redline else '❌'}")


if __name__ == "__main__":
    main()
