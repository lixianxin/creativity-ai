# -*- coding: utf-8 -*-
"""创想∞ AI创业委员会 —— Streamlit 工作台
输入创业想法 → 12 Agent 委员会审查 → 成熟度诊断报告
"""
import os
import sys
import time
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Phase 7-10 部署：Streamlit Cloud 等平台通过 .streamlit/secrets.toml 管理密钥，
# 在导入 core.config 前把 secrets 注入环境变量（core 保持不依赖 streamlit）。
try:
    for _k, _v in (st.secrets or {}).items():
        if isinstance(_v, str):
            os.environ.setdefault(_k, _v)
except Exception:
    pass

from pipeline.orchestrator import CommitteePipeline, STAGES
from core.context import ProjectContext
from core.run_store import RunStore
from core.run import RUN_PAUSED, RUN_FAILED, RUN_COMPLETED_WITH_ERRORS
from schemas.agent_result import (
    STATUS_PENDING, STATUS_RUNNING, STATUS_SUCCESS, STATUS_FAILED,
    STATUS_BLOCKED, STATUS_DEGRADED, STATUS_SKIPPED,
)

# ── 页面配置 ──
st.set_page_config(
    page_title="创想∞ AI创业委员会",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── 初始化 session_state ──
ss = st.session_state
if "stage" not in ss:
    ss.stage = -1          # -1=未开始, 0-11=运行中, 12=完成
    ss.ctx = None
    ss.project_input = ""
    ss.results = {}        # {stage_idx: AgentResult}
    ss.error = None


def render_status_icon(status):
    if status == STATUS_SUCCESS:
        return "✅"
    elif status == STATUS_FAILED:
        return "❌"
    elif status == STATUS_DEGRADED:
        return "🟡"
    elif status == STATUS_BLOCKED:
        return "🚫"
    elif status == STATUS_SKIPPED:
        return "⏭️"
    elif status == STATUS_RUNNING:
        return "⚡"
    else:
        return "⏳"


def render_agent_status(stage_idx):
    """渲染单个 Agent 状态行。"""
    info = CommitteePipeline.STAGE_INFO[stage_idx]
    if stage_idx in ss.results:
        result = ss.results[stage_idx]
        icon = render_status_icon(result.status)
        if result.status == STATUS_FAILED:
            return f"{icon} **{info['label']}** — 校验未通过（该棒失败，不连坐其余委员）"
        conclusion = f" → {result.conclusion}" if result.conclusion else ""
        return f"{icon} **{info['label']}**{conclusion}"
    elif stage_idx == ss.stage:
        return f"⚡ **{info['label']}** — 分析中..."
    elif stage_idx < ss.stage or (ss.stage == -1 and ss.stage > stage_idx):
        return f"⏳ **{info['label']}**"
    else:
        return f"⏳ **{info['label']}**"


# ── 顶部标题栏 ──
st.markdown("""
<style>
.main-header {
    text-align: center;
    padding: 20px 0 10px 0;
}
.sub-header {
    text-align: center;
    color: #888;
    font-size: 16px;
    margin-bottom: 30px;
}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-header"><h1>🏛️ 创想∞ AI创业委员会</h1></div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">不是帮你把创业故事讲得更漂亮，而是先让它经受一次委员会的挑战。</div>', unsafe_allow_html=True)

st.divider()

# ── 阶段判断 ──
if ss.stage == -1:
    # ══════════ 输入页 ══════════
    with st.container():
        col1, col2 = st.columns([1, 1])
        with col1:
            st.subheader("📝 提交创业项目")
            project_name = st.text_input("项目名称", value="创想∞ AI创业委员会")
            project_desc = st.text_area("项目简介", value="面向高校创新创业场景的 AI 评审系统。学生提交创业想法后，12个AI委员模拟真实创业委员会进行全链路审查。")
            target_users = st.text_input("目标用户", value="高校创新创业学生（免费），学校创业学院/教务处（机构版采购）")
            biz_model = st.text_input("商业模式", value="学生免费，学校机构版按年采购。基于大模型API直接上线对外服务。")
            validation = st.text_area("已有验证/数据", value="目前2所学校创业学院老师口头表示感兴趣。")

            if st.button("🚀 开始委员会审查", type="primary", use_container_width=True):
                # 拼装项目输入
                ss.project_input = f"""{project_name}：{project_desc}
目标用户：{target_users}
商业模式：{biz_model}
已有验证：{validation}"""
                ss.stage = 0
                ss.ctx = ProjectContext(project_info=ss.project_input)
                ss.results = {}
                ss.error = None
                st.rerun()

            # 加载已有结果（Demo 模式，不重新跑 LLM）
            st.markdown("---")
            st.markdown("**或加载已有审查结果（Demo 模式）**")
            report_dir = ROOT / "reports"
            existing = sorted(report_dir.glob("*.md")) if report_dir.exists() else []
            if len(existing) >= 12 and st.button("📂 加载已有报告", use_container_width=True):
                ss.project_input = f"""{project_name}：{project_desc}
目标用户：{target_users}
商业模式：{biz_model}
已有验证：{validation}"""
                ss.ctx = ProjectContext(project_info=ss.project_input)
                ss.results = {}
                # STAGE_INFO key → 实际 prompt_name（agent_name）
                agent_names = ["user_insight","market_analysis","competitor_analysis","product_design",
                               "business_model","finance","growth_ops","risk_review",
                               "red_team","commander","project_review","pitch_defense"]
                for i, (seq, key, _, _) in enumerate(STAGES):
                    f = report_dir / f"{seq}_{key}.md"
                    if f.exists():
                        from schemas.agent_result import AgentResult
                        content = f.read_text(encoding="utf-8")
                        ss.ctx.add_report(AgentResult(
                            agent_name=agent_names[i],
                            status=STATUS_SUCCESS,
                            raw_output=content,
                            summary=content[:100],
                        ))
                        ss.results[i] = ss.ctx.reports[-1]
                # 提取结论和元数据
                for r in ss.ctx.reports:
                    lines = [l.strip() for l in r.raw_output.split("\n") if l.strip()]
                    r.conclusion = ""
                    r.metadata = {}
                    # 总指挥：阶段判断
                    if r.agent_name == "commander":
                        for line in lines:
                            if any(k in line for k in ["想法验证", "方案修正", "路演准备", "可进入路演"]):
                                r.conclusion = line
                                break
                    # 评审官：终审结论
                    elif r.agent_name == "project_review":
                        for i, line in enumerate(lines):
                            if "终审结论" in line and i + 1 < len(lines):
                                r.conclusion = lines[i + 1]
                                break
                        if not r.conclusion:
                            for line in lines:
                                if any(k in line for k in ["暂缓", "准入", "材料不齐"]) and "报告" not in line:
                                    r.conclusion = line
                                    break
                        r.metadata = {"redline_triggered": "一票否决" in r.raw_output or "不得直接" in r.raw_output}
                    # 答辩官：路演结论
                    elif r.agent_name == "pitch_defense":
                        for line in lines:
                            if any(k in line for k in ["可以路演", "有条件路演", "暂不建议", "无法评估"]):
                                r.conclusion = line
                                break
                        r.metadata = {"pierced_count": r.raw_output.count("击穿")}
                    # 风险官
                    elif r.agent_name == "risk_review":
                        r.metadata = {"blocking": "致命" in r.raw_output or "一票否决" in r.raw_output}
                    # 财务官
                    elif r.agent_name == "finance":
                        r.conclusion = "无法可靠计算" if "无法可靠计算" in r.raw_output else "可计算"
                ss.stage = 12
                st.rerun()

            # 恢复 V2 Runtime 中断的 Run（暂停/失败/部分成功；成功棒不重复花 API）
            st.markdown("---")
            with st.expander("⏸️ 恢复上次中断的委员会审查（断点续跑）"):
                try:
                    recoverable = [
                        r for r in RunStore().list_recent_runs(limit=10)
                        if r.status in (RUN_PAUSED, RUN_FAILED, RUN_COMPLETED_WITH_ERRORS)
                    ]
                except Exception as _e:
                    recoverable = []
                    st.caption(f"运行记录不可用：{str(_e)[:80]}")
                if not recoverable:
                    st.caption("暂无可以恢复的审查（仅暂停 / 失败 / 部分成功的 Run 可恢复）。")
                _STATUS_CN = {
                    RUN_PAUSED: "已暂停", RUN_FAILED: "已失败",
                    RUN_COMPLETED_WITH_ERRORS: "部分成功",
                }
                for run in recoverable[:5]:
                    rc1, rc2 = st.columns([4, 1])
                    reason = f"，原因：{run.pause_reason}" if run.pause_reason else ""
                    rc1.caption(f"`{run.run_id}` · {_STATUS_CN[run.status]}{reason}")
                    rc1.caption(f"项目：{(run.project_input or '')[:50]}")
                    if rc2.button("▶️ 恢复", key=f"resume_{run.run_id}", use_container_width=True):
                        try:
                            with st.spinner("正在从断点恢复：已成功的棒次本地回读，不重复调用 LLM..."):
                                pipe = CommitteePipeline()
                                ss.ctx = pipe.resume(run.run_id)
                                ss.project_input = run.project_input
                                ss.results = {}
                                pipe.save_final_report(ss.ctx)
                                ss.stage = 12
                            st.rerun()
                        except Exception as e:
                            st.error(f"恢复失败：{str(e)[:200]}")

        with col2:
            st.subheader("📋 委员会架构")
            st.markdown("""
**专家委员会**（8 员）
- 用户洞察官 · 市场分析官 · 竞品分析官
- 产品设计官 · 商业模式官 · 财务分析官
- 增长运营官 · 风险审查官

**对抗委员会**（1 员）
- 红队质疑官

**决策委员会**（3 员）
- 创业总指挥 · 项目评审官 · 路演答辩官
""")
            st.info("委员会将逐层分析你的创业想法，主动质疑核心假设，识别致命风险，最终决定项目是否可以进入路演。")

elif 0 <= ss.stage < 12:
    # ══════════ 运行页：逐棒执行 ══════════
    pipe = CommitteePipeline()
    current_idx = ss.stage
    info = CommitteePipeline.STAGE_INFO[current_idx]

    # 显示 12 Agent 状态面板
    st.subheader("🔍 委员会审查进行中")
    progress = ss.stage / 12
    st.progress(progress, text=f"第 {ss.stage + 1}/12 棒 — {info['label']} 分析中...")

    # 三组状态
    groups = {}
    for i, si in enumerate(CommitteePipeline.STAGE_INFO):
        g = si["group"]
        if g not in groups:
            groups[g] = []
        groups[g].append((i, si))

    for group_name, stages in groups.items():
        st.markdown(f"**{group_name}**")
        for idx, si in stages:
            st.markdown(render_agent_status(idx))
        st.markdown("")

    # 运行当前棒
    try:
        with st.spinner(f"{info['label']} 正在分析..."):
            result = pipe.run_stage(current_idx, ss.project_input, ss.ctx)
            ss.results[current_idx] = result
            ss.stage += 1

            if ss.stage < 12:
                st.rerun()
            else:
                # 全部完成，生成最终报告
                pipe.save_final_report(ss.ctx)
                ss.stage = 12
                st.rerun()
    except Exception as e:
        st.error(f"第{current_idx + 1}棒执行失败: {str(e)[:200]}")
        st.info("可能是 LLM 推理链占满 token，点击重试。")
        if st.button("🔄 重试当前棒"):
            st.rerun()

elif ss.stage == 12:
    # ══════════ 结果页 ══════════
    ctx = ss.ctx
    pipe = CommitteePipeline()

    # ── 最终诊断面板 ──
    commander = ctx.get_report("commander")
    reviewer = ctx.get_report("project_review")
    pitch = ctx.get_report("pitch_defense")
    risk = ctx.get_report("risk_review")

    st.subheader("🎯 创业项目终审结果")
    st.markdown("---")

    # 第一行：阶段 + 红线 + 路演结论
    col1, col2, col3 = st.columns(3)
    with col1:
        stage_text = commander.conclusion if commander and commander.conclusion else "未判断"
        st.metric("项目阶段", stage_text)
    with col2:
        redline = reviewer and reviewer.metadata.get("redline_triggered", False)
        st.metric("红线一票否决", "⛔ 触发" if redline else "✅ 未触发")
        if reviewer and reviewer.metadata.get("redline_forced_by_system"):
            st.caption("⚖️ 系统规则强制：Agent 曾给出与红线冲突的准入结论，"
                       "已被系统强制改判为「暂缓（红线未清）」——红线是系统规则，不是 Prompt 建议。")
    with col3:
        pitch_conclusion = pitch.conclusion if pitch and pitch.conclusion else "未判断"
        st.metric("路演建议", pitch_conclusion)

    st.markdown("---")

    # ── 冲突感展示：专家→红队→风险→评审 ──
    st.subheader("⚡ 委员会冲突链")
    col_a, col_b, col_c, col_d = st.columns(4)
    with col_a:
        st.markdown("**专家意见**")
        if risk:
            st.info(risk.summary[:80])
    with col_b:
        st.markdown("**红队质疑**")
        red_team = ctx.get_report("red_team")
        if red_team:
            st.warning(red_team.summary[:80])
    with col_c:
        st.markdown("**风险审查**")
        if risk:
            risks_text = "\n".join(r[:60] for r in risk.risks[:3]) if risk.risks else "无致命风险"
            st.error(risks_text)
    with col_d:
        st.markdown("**项目评审**")
        if reviewer:
            st.error(reviewer.conclusion or reviewer.summary[:80])

    st.markdown("---")

    # ── 12 Agent 报告卡片 ──
    st.subheader("📄 委员会完整报告")
    labels = {
        "user_insight": "用户洞察官", "market_analysis": "市场分析官",
        "competitor_analysis": "竞品分析官", "product_design": "产品设计官",
        "business_model": "商业模式官", "finance": "财务分析官",
        "growth_ops": "增长运营官", "risk_review": "风险审查官",
        "red_team": "红队质疑官", "commander": "创业总指挥",
        "project_review": "项目评审官", "pitch_defense": "路演答辩官",
    }

    # 用 tab 展示（❌=校验失败；🟡=输入降级；🚫=硬依赖阻断；⏭️=断链跳过；🔧=返工后通过）
    def _tab_badge(r):
        if r.status == STATUS_FAILED:
            return "❌ "
        if r.status == STATUS_BLOCKED:
            return "🚫 "
        if r.status == STATUS_SKIPPED:
            return "⏭️ "
        if r.metadata.get("degraded_inputs"):
            return "🟡 "
        if r.metadata.get("repaired"):
            return "🔧 "
        return ""

    report_tabs = st.tabs([_tab_badge(r) + labels.get(r.agent_name, r.agent_name)
                           for r in ctx.reports])
    for i, (tab, r) in enumerate(zip(report_tabs, ctx.reports)):
        with tab:
            # V2 Runtime 系统留痕：失败原因 / 红线强制改判 / 返工 / 校验警告
            if r.status == STATUS_FAILED:
                st.error(f"本棒未通过系统确定性校验（返工后仍不合格），该棒失败但不连坐其他委员。\n\n"
                         f"原因：{r.summary[:160]}")
            if r.status == STATUS_BLOCKED:
                st.error(f"🚫 本棒因硬依赖失败被系统阻断，未调用 AI。\n\n{r.summary[:200]}")
            if r.status == STATUS_SKIPPED:
                st.warning(f"⏭️ 本棒因上游链路阻断被跳过，未调用 AI。\n\n{r.summary[:200]}")
            if r.metadata.get("degraded_inputs"):
                missing_labels = "、".join(labels.get(n, n) for n in r.metadata["degraded_inputs"])
                st.warning("🟡 本棒在部分上游输入缺失的情况下降级完成"
                           f"（缺失：{missing_labels}），结论请注意输入不完整。")
            if r.metadata.get("redline_forced_by_system"):
                st.error("⛔ **系统强制改判**：该终审意见命中红线却给出准入结论，与系统红线规则冲突；"
                         "系统已强制改判为「暂缓进入修订周期（红线未清，系统强制）」。")
            if r.metadata.get("repaired"):
                st.warning("🔧 本报告首次输出未通过系统确定性校验，已附带具体校验意见返工重写 1 次后通过。")
            warns = r.metadata.get("validation_warnings") or []
            if warns:
                with st.expander(f"⚠️ 系统校验警告（{len(warns)} 条，接受但留痕）"):
                    for w in warns:
                        st.markdown(f"- {w}")
            if r.conclusion:
                st.markdown(f"**结论：{r.conclusion}**")
            if r.risks:
                st.markdown("**关键风险：**")
                for risk_item in r.risks[:5]:
                    st.markdown(f"- {risk_item[:80]}")
            with st.expander("查看完整报告", expanded=False):
                st.markdown(r.raw_output)

    st.markdown("---")

    # ── 重置 ──
    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("🔄 重新审查另一个项目"):
            ss.stage = -1
            ss.ctx = None
            ss.results = {}
            st.rerun()
