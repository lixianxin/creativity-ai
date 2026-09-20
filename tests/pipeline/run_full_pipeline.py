# -*- coding: utf-8 -*-
"""
12 Agent 全链路联调（真实串联，非模拟）：
  项目 -> 用户洞察 -> 市场分析 -> 竞品分析 -> 产品设计 -> 商业模式
       -> 财务分析 -> 增长运营 -> 风险审查 -> 红队质疑
       -> 创业总指挥 -> 项目评审 -> 路演答辩 -> 最终诊断结果
- 所有 Prompt 均来自 agents/prompts/
- 前9棒各自独立看项目描述（保持独立知识边界）
- 后3棒汇总所有前置报告做阶段/终审/答辩诊断
- 每棒真实输出落盘到 tests/pipeline/outputs/full_run_<id>/<序号>_<agent>.md
用法: python run_full_pipeline.py
"""
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

# 全链路测试项目库
PROJECTS = [
    {
        "id": 1, "name": "校园二手书交易平台",
        "project": {
            "name": "校园二手书交易平台",
            "desc": "我要做一个校园二手书交易平台，目标用户是全国大学生，学生可以在上面买卖二手教材和资料，平台撮合后学生线下见面交易，钱先付给平台、确认收货后平台再打给卖家，平台从每笔订单抽5%服务费。第一年目标10万用户。",
            "users": "全国大学生",
            "pain": "未提供",
            "solution": "校园二手书交易撮合平台，平台代收货款",
            "model": "平台代收代付货款，抽5%服务费",
            "stage": "想法阶段（未提供团队、进展、资源信息）",
        },
        "pitch": (
            "我们做校园二手书交易平台，市场巨大，全国3000万大学生都是我们的用户。"
            "平台轻资产运营，通过校园社群裂变快速获客，第一年10万用户完全没问题。"
            "我们有先发优势，团队执行力强，闲鱼做不了校园这种熟人场景。"
        ),
    },
    {
        "id": 2, "name": "创想∞ AI创业委员会",
        "project": {
            "name": "创想∞ AI创业委员会",
            "desc": "面向大学生创新创业教育的多智能体创业项目审查与模拟路演空间。学生把创业想法输入后，12个AI专家委员给出结构化审查报告和修改建议，学生免费；学校购买机构版用于创业课程教学、大创项目筛选、创业大赛初赛评审，项目方会收集学生提交的创业项目内容和报告数据，并考虑把脱敏后的项目数据做成数据服务对外提供。产品基于大模型API开发，计划直接上线对外服务。目前产品原型已完成，2所学校创业学院老师口头表示感兴趣。",
            "users": "有创业想法的大学生；高校创业学院",
            "pain": "学生创业想法缺乏专业质疑；学校指导师资不足",
            "solution": "多智能体AI审查SaaS",
            "model": "学生免费；学校机构版按年采购；脱敏数据服务",
            "stage": "产品原型阶段（原型已完成，2所学校老师口头感兴趣）",
        },
        "pitch": (
            "我们是AI时代的创业教育基础设施。学生输入创业想法，12个AI专家委员给出结构化审查和模拟路演反馈。"
            "学生端免费形成流量，学校按年采购机构版用于课程教学和项目筛选。"
            "目前已有2所学校明确表达合作意向，预计明年进入20所学校。"
        ),
    },
]


def get_project(proj_id):
    for p in PROJECTS:
        if p["id"] == proj_id:
            return p
    return PROJECTS[0]


def build_project_text(project):
    return (
        f"项目名称：{project['name']}\n项目描述：{project['desc']}\n"
        f"目标用户：{project['users']}\n核心痛点：{project['pain']}\n"
        f"解决方案：{project['solution']}\n商业模式：{project['model']}\n当前阶段：{project['stage']}"
    )

# 12 棒定义：(序号, agent名, prompt文件名, 是否汇总前置报告)
STAGES = [
    (1, "user_insight", "user_insight_v1.md", False),
    (2, "market_analysis", "market_analysis_v1.md", False),
    (3, "competitor_analysis", "competitor_analysis_v1.md", False),
    (4, "product_design", "product_design_v1.md", False),
    (5, "business_model", "business_model_v1.md", False),
    (6, "finance", "finance_v1.md", False),
    (7, "growth_ops", "growth_ops_v1.md", False),
    (8, "risk_review", "risk_review_v1.md", False),
    (9, "red_team", "red_team_v1.md", False),
    (10, "commander", "commander_v1.md", True),
    (11, "project_review", "project_review_v1.md", True),
    (12, "pitch_defense", "pitch_defense_v1.md", True),
]

AGENT_LABEL = {
    "user_insight": "用户洞察官", "market_analysis": "市场分析官",
    "competitor_analysis": "竞品分析官", "product_design": "产品设计官",
    "business_model": "商业模式官", "finance": "财务分析官",
    "growth_ops": "增长运营官", "risk_review": "风险审查官",
    "red_team": "红队质疑官", "commander": "创业总指挥",
    "project_review": "项目评审官", "pitch_defense": "路演答辩官",
}


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


def call(client, plat, system_prompt, user_content, label):
    t0 = time.time()
    resp = client.chat.completions.create(
        model=plat["model"],
        messages=[{"role": "system", "content": system_prompt},
                  {"role": "user", "content": user_content}],
        temperature=0.3, max_tokens=20000)
    dt = time.time() - t0
    content = resp.choices[0].message.content
    if not content:
        rc = getattr(resp.choices[0].message, "reasoning_content", None)
        raise RuntimeError(f"[{label}] 正文为空。reasoning: {(rc or '')[:200]}")
    u = resp.usage
    print(f"[{label}] {dt:.0f}s, tokens {u.prompt_tokens}+{u.completion_tokens}, {len(content)}字")
    return content, {"seconds": round(dt, 1), "prompt_tokens": u.prompt_tokens,
                     "completion_tokens": u.completion_tokens}


def build_aggregate_input(agent, reports, project_text, pitch):
    """汇总型 Agent 的输入：项目 + 前置报告"""
    parts = [project_text]
    # 路演答辩官需要路演陈述
    if agent == "pitch_defense":
        parts.append(f"\n【路演陈述/BP口径】{pitch}\n")
    parts.append("\n==== 委员会各Agent报告 ====")
    for a, r in reports.items():
        parts.append(f"\n【{AGENT_LABEL[a]}报告】\n{r}")
    return "\n".join(parts)


def main():
    import sys
    proj_id = 1
    if len(sys.argv) > 1:
        try:
            proj_id = int(sys.argv[1])
        except ValueError:
            print(f"用法: python run_full_pipeline.py [项目编号]")
            print("项目列表：")
            for p in PROJECTS:
                print(f"  {p['id']}. {p['name']}")
            return
    proj = get_project(proj_id)
    project = proj["project"]
    project_text = build_project_text(project)
    pitch = proj["pitch"]

    prompts = {}
    for _, agent, fname, _ in STAGES:
        prompts[agent] = (PROMPT_DIR / fname).read_text(encoding="utf-8")

    client, plat = pick_client()
    run_id = int(time.time())
    out_dir = OUT_ROOT / f"full_run_{run_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n########## 12 Agent 全链路联调 Run {run_id}：{project['name']} ##########")
    print(f"输出目录：{out_dir}")

    reports = {}  # agent -> 输出内容
    summary = []

    for seq, agent, fname, aggregate in STAGES:
        label = f"{seq}_{AGENT_LABEL[agent]}"
        print(f"\n--- 第{seq}棒：{AGENT_LABEL[agent]} ---")
        if aggregate:
            user_input = build_aggregate_input(agent, reports, project_text, pitch)
        else:
            user_input = project_text

        try:
            content, meta = call(client, plat, prompts[agent], user_input, label)
            reports[agent] = content
            out_file = out_dir / f"{seq:02d}_{agent}.md"
            out_file.write_text(
                f"# Run{run_id} 第{seq}棒 {AGENT_LABEL[agent]}\n\n"
                f"- 平台：{plat['name']} / {plat['model']}\n"
                f"- 耗时：{meta['seconds']}s，tokens：{meta['prompt_tokens']}+{meta['completion_tokens']}\n\n"
                f"## 输入\n\n{user_input}\n\n## 输出\n\n{content}\n",
                encoding="utf-8")
            summary.append({"seq": seq, "agent": agent, "label": AGENT_LABEL[agent],
                            "status": "ok", "tokens": meta["completion_tokens"]})
        except Exception as e:
            print(f"[错误] {e}")
            reports[agent] = f"[API错误] {e}"
            summary.append({"seq": seq, "agent": agent, "label": AGENT_LABEL[agent],
                            "status": "error", "error": str(e)[:200]})

    (out_dir / "pipeline_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n########## 全链路联调完成。共 {len(reports)} 棒，输出目录：{out_dir} ##########")


if __name__ == "__main__":
    main()
