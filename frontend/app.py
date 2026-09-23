# -*- coding: utf-8 -*-
"""创想∞ AI创业委员会 —— Streamlit 工作台（页面编排层 · Design System v2）

本文件只做三件事：取真实数据 → 交给组件渲染 → 接住用户动作。

业务边界（本次 UI 重构零改动）：
    Agent / Prompt / Agent 数量与顺序 / Registry / DAG / Execution Graph /
    Orchestrator / Validator / Repair / RunStore / Checkpoint / Resume / LLM / 数据库
所有展示数据均来自 session_state 中的真实结果或磁盘上的真实报告，
前端不修改任何结论、状态、数字，也不硬编码「成功」。

结构：
    frontend/app.py            页面编排（本文件）
    frontend/ui_components.py  展示组件（纯 HTML）
    frontend/ui_helpers.py     状态映射 / 文本清洗 / 真实报告解析
    frontend/design_tokens.py  设计令牌 + 全局 CSS
"""
import os
import sys
from pathlib import Path
from typing import Optional

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

from pipeline.orchestrator import CommitteePipeline
from core.context import ProjectContext
from core.config import PLATFORMS
from core.run_store import RunStore
from core.run import RUN_PAUSED, RUN_FAILED, RUN_COMPLETED_WITH_ERRORS
from schemas.agent_result import (
    AgentResult,
    STATUS_SUCCESS, STATUS_FAILED, STATUS_BLOCKED, STATUS_SKIPPED,
)
from auth import get_auth_client, UserInfo

from frontend import design_tokens as T
from frontend import ui_helpers as H
from frontend import ui_components as UI

# ── 页面配置 ──
st.set_page_config(
    page_title="创想∞ AI创业委员会",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(T.build_css(), unsafe_allow_html=True)

# ── 导航项 ──
NAV_NEW = "＋ 新建审议"
NAV_RUN = "◉ 本次审议"
NAV_RECENT = "▣ 最近项目"
NAV_COMMITTEE = "◈ 委员会"
NAV_SETTINGS = "⚙ 设置"
NAV_ITEMS = [NAV_NEW, NAV_RUN, NAV_RECENT, NAV_COMMITTEE, NAV_SETTINGS]

# ── 认证状态键 ──
AUTH_USER_KEY = "cx_current_user"              # UserInfo or None
SIGNUP_PENDING_EMAIL_KEY = "cx_signup_pending_email"  # 注册第二步：待验证邮箱

# ── 演示用的默认创业想法（仅作为输入框初始值，不参与任何结论） ──
DEFAULT_IDEA = {
    "name": "创想∞ AI创业委员会",
    "desc": "面向高校创新创业场景的 AI 评审系统。学生提交创业想法后，12 个 AI 委员模拟真实创业委员会进行全链路审查。",
    "users": "高校创新创业学生（免费），学校创业学院/教务处（机构版采购）",
    "biz": "学生免费，学校机构版按年采购。基于大模型 API 直接上线对外服务。",
    "valid": "目前 2 所学校创业学院老师口头表示感兴趣。",
}
IDEA_LIMIT = 2000
DEMO_REPORT_DIR = ROOT / "reports"

# 红队角色定义（逐字取自 agents/prompts/red_team_v1.md，用于红队区块的角色自述）
RED_TEAM_ROLE = "你不是顾问、不是导师、不是啦啦队。你不夸项目、不哄用户、不替用户设计方案、不做最终裁决。"


# ═══════════════════════════════════════════════════════════
# 会话状态
# ═══════════════════════════════════════════════════════════
ss = st.session_state
if "nav" not in ss:
    ss.nav = NAV_NEW
if "stage" not in ss:
    ss.stage = -1          # -1=未开始, 0-11=运行中, 12=完成
    ss.ctx = None
    ss.project_input = ""
    ss.results = {}        # {stage_idx: AgentResult}
    ss.error = None
if "_nav_next" not in ss:
    ss._nav_next = None
if "source" not in ss:
    ss.source = ""         # 当前结果来源（真实运行 / 磁盘报告）
if AUTH_USER_KEY not in ss:
    ss[AUTH_USER_KEY] = None    # 未登录 → None；登录后 → UserInfo
if SIGNUP_PENDING_EMAIL_KEY not in ss:
    ss[SIGNUP_PENDING_EMAIL_KEY] = ""    # 注册第二步：待验证邮箱

# 导航切换必须发生在 sidebar 控件实例化之前
if ss._nav_next:
    ss.nav = ss._nav_next
    ss._nav_next = None


def goto(page: str):
    ss._nav_next = page
    st.rerun()


def reset_run():
    ss.stage = -1
    ss.ctx = None
    ss.results = {}
    ss.error = None
    ss.source = ""


# ═══════════════════════════════════════════════════════════
# 认证辅助
# ═══════════════════════════════════════════════════════════

def current_user() -> Optional[UserInfo]:
    """返回当前登录用户，未登录返回 None。"""
    return ss.get(AUTH_USER_KEY)


def current_user_id() -> str:
    """返回当前登录用户的 ID，未登录返回空串。"""
    u = current_user()
    return u.id if u else ""


# ═══════════════════════════════════════════════════════════
# 数据读取（全部来自真实来源，只读不改）
# ═══════════════════════════════════════════════════════════

def report_paths(report_dir: Path) -> list:
    """按 registry 的棒次与 stage_key 定位磁盘上的真实报告文件。"""
    out = []
    for row in H.STAGE_ROWS:
        out.append((row, Path(report_dir) / f"{row['seq']}_{row['key']}.md"))
    return out


def available_reports(report_dir) -> int:
    try:
        d = Path(report_dir)
        if not d.exists():
            return 0
        return sum(1 for _, f in report_paths(d) if f.exists())
    except Exception:
        return 0


def _derive_summary(raw: str) -> str:
    """从报告原文取一句摘要（跳过标题行），不改写任何结论。"""
    lines = [l.strip() for l in (raw or "").splitlines() if l.strip()]
    for line in lines[1:8]:
        if line.startswith(("#", "【", "一、", "二、", "-", "▪", "|", "▶", "→")):
            continue
        return H.truncate(line, 92)
    return H.truncate(lines[0] if lines else "", 92)


def hydrate_result(res: AgentResult):
    """从报告原文解析展示字段（结论 / 系统留痕）。

    只影响展示层字段，不改状态、不改分数、不改结论档位；
    解析不到就留空，绝不编造。
    """
    raw = res.raw_output or ""
    res.conclusion = ""
    res.metadata = {}
    name = res.agent_name
    if name == "commander":
        d = H.parse_commander(raw)
        res.conclusion = d["conclusion"] or d["stage"]
    elif name == "project_review":
        d = H.parse_review(raw)
        res.conclusion = d["verdict"]
        if d["veto"]:
            res.metadata["redline_triggered"] = (d["veto"] == "是")
        else:
            res.metadata["redline_triggered"] = ("一票否决" in raw and "不得直接" in raw)
    elif name == "pitch_defense":
        d = H.parse_pitch(raw)
        res.conclusion = d["conclusion"]
        res.metadata["pierced_count"] = d["ratings_pierced"]
        res.metadata["ratings_total"] = d["ratings_total"]
    elif name == "risk_review":
        res.metadata["blocking"] = "存在致命风险" in raw
    elif name == "finance":
        res.conclusion = H.parse_finance(raw)["conclusion"]


def load_reports_from_dir(report_dir, project_input: str = "") -> bool:
    """把磁盘上的真实报告读入展示层（Demo / 历史项目）。不做任何业务计算。"""
    files = report_paths(report_dir)
    existing = [(row, f) for row, f in files if f.exists()]
    if not existing:
        return False
    ss.ctx = ProjectContext(project_info=project_input or _compose_project_input(DEFAULT_IDEA))
    ss.results = {}
    for i, (row, f) in enumerate(files):
        if not f.exists():
            continue
        content = f.read_text(encoding="utf-8")
        res = AgentResult(
            agent_name=row["name"],
            status=STATUS_SUCCESS,
            raw_output=content,
            summary=_derive_summary(content),
        )
        hydrate_result(res)
        ss.ctx.add_report(res)
        ss.results[i] = ss.ctx.reports[-1]
    ss.stage = 12
    ss.source = str(report_dir)
    return True


def _compose_project_input(idea: dict) -> str:
    """与既有约定完全一致的输入拼接格式（Agent 消费的文本不变）。"""
    return (
        f"{idea['name']}：{idea['desc']}\n"
        f"目标用户：{idea['users']}\n"
        f"商业模式：{idea['biz']}\n"
        f"已有验证：{idea['valid']}"
    )


def current_status() -> tuple:
    """Header 右侧只放一个真实状态。"""
    if ss.stage < 0:
        return "系统就绪", "success"
    if ss.stage < len(H.STAGE_ROWS):
        return f"审议进行中 {ss.stage}/{len(H.STAGE_ROWS)}", "primary"
    return "审议已完成", "success"


# ═══════════════════════════════════════════════════════════
# 侧边栏
# ═══════════════════════════════════════════════════════════

def render_sidebar():
    with st.sidebar:
        st.markdown(UI.sidebar_brand(), unsafe_allow_html=True)
        # ── 用户信息 + 退出 ──
        user = current_user()
        if user:
            st.markdown(
                f'<div class="cx-root" style="display:flex;align-items:center;gap:8px;padding:6px 0 10px 0;">'
                f'<span style="width:28px;height:28px;border-radius:50%;background:{T.PRIMARY_SOFT};'
                f'color:{T.PRIMARY};display:flex;align-items:center;justify-content:center;'
                f'font-size:14px;font-weight:700;">{H.esc(user.email[0].upper())}</span>'
                f'<span style="flex:1;min-width:0;font-size:12.5px;font-weight:600;color:{T.FOREGROUND};'
                f'overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{H.esc(user.email)}</span>'
                f'</div>', unsafe_allow_html=True)
            if st.button("退出登录", use_container_width=True):
                try:
                    get_auth_client().sign_out()
                except Exception:
                    pass
                ss[AUTH_USER_KEY] = None
                ss[SIGNUP_PENDING_EMAIL_KEY] = ""
                reset_run()
                st.rerun()
            st.markdown('<div class="cx-side-rule" style="margin-top:10px;"></div>',
                        unsafe_allow_html=True)
        st.radio("导航", NAV_ITEMS, key="nav", label_visibility="collapsed")
        st.markdown('<div class="cx-side-rule" style="margin-top:14px;"></div>',
                    unsafe_allow_html=True)
        agent_n = len(H.STAGE_ROWS)
        st.markdown(UI.sidebar_label("当前审议"), unsafe_allow_html=True)
        if ss.stage < 0:
            st.markdown(
                UI.sidebar_foot("尚未开始<br>提交创业想法后开始 12 棒审议"),
                unsafe_allow_html=True)
        else:
            done = min(ss.stage, agent_n)
            src = "磁盘报告" if ss.source else "实时运行"
            st.markdown(
                UI.sidebar_foot(f"进度 · {done} / {agent_n} 棒<br>来源 · {src}"),
                unsafe_allow_html=True)
        st.markdown('<div class="cx-side-rule" style="margin-top:14px;"></div>',
                    unsafe_allow_html=True)
        st.markdown(UI.sidebar_label("委员会"), unsafe_allow_html=True)
        st.markdown(
            UI.sidebar_foot(
                f"{agent_n} 位 AI 委员 · {len(H.GROUP_ORDER)} 大委员会<br>"
                "红队对抗 · 红线一票否决"),
            unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════
# 页面：登录 / 注册
# ═══════════════════════════════════════════════════════════

def page_auth():
    """登录 / 注册页面 —— 未登录时的唯一入口。

    注册流程（邮箱验证码回填版，方案 A）：
      第一步：邮箱 + 密码 + 确认密码 → 点击「注册并获取验证码」
              → Supabase sign_up 创建用户并发送邮箱验证码
              → 页面切换到第二步
      第二步：显示「验证码已发送至 xxx」，回填验证码
              → 点击「验证并注册」→ Supabase verify_otp(type=email)
              → 验证成功 → 进入主应用
    """
    st.markdown('<div class="cx-root">', unsafe_allow_html=True)
    st.markdown(
        f'<div style="text-align:center;padding:40px 0 20px 0;">'
        f'<div style="font-size:28px;font-weight:700;color:{T.FOREGROUND};">创想∞ AI创业委员会</div>'
        f'<div style="font-size:14px;color:{T.MUTED};margin-top:8px;">让 AI 先质疑你的创业想法</div>'
        f'</div>', unsafe_allow_html=True)

    auth = get_auth_client()

    pending_email = ss.get(SIGNUP_PENDING_EMAIL_KEY) or ""

    tab_login, tab_signup = st.tabs(["登录", "注册"])

    # ── 登录 Tab ──
    with tab_login:
        with st.form("cx_login_form"):
            login_email = st.text_input("邮箱", key="login_email", placeholder="your@email.com")
            login_pwd = st.text_input("密码", type="password", key="login_pwd", placeholder="至少 6 位")
            login_submit = st.form_submit_button("登录", type="primary", use_container_width=True)
        if login_submit:
            try:
                user = auth.sign_in(login_email, login_pwd)
                ss[AUTH_USER_KEY] = user
                ss[SIGNUP_PENDING_EMAIL_KEY] = ""
                st.rerun()
            except Exception as e:
                st.error(f"登录失败：{str(e)[:120]}")

    # ── 注册 Tab（两步切换） ──
    with tab_signup:
        if pending_email:
            # 第二步：输入邮箱验证码
            st.markdown(
                f'<div style="text-align:center;padding:10px 0 18px 0;">'
                f'<div style="font-size:16px;font-weight:600;color:{T.FOREGROUND};">验证你的邮箱</div>'
                f'<div style="font-size:12.5px;color:{T.MUTED};margin-top:6px;">'
                f'验证码已发送至 <span style="font-weight:600;color:{T.FOREGROUND};">{H.esc(pending_email)}</span>'
                f'</div></div>', unsafe_allow_html=True)
            with st.form("cx_signup_otp_form"):
                otp = st.text_input(
                    "邮箱验证码",
                    key="signup_otp",
                    placeholder="请输入邮件中的 6 位验证码",
                )
                otp_submit = st.form_submit_button("验证并注册", type="primary", use_container_width=True)
            col_back, _, _ = st.columns([1, 2, 2])
            with col_back:
                if st.button("← 重新填写邮箱", use_container_width=True):
                    ss[SIGNUP_PENDING_EMAIL_KEY] = ""
                    ss["signup_otp"] = ""
                    st.rerun()
            if otp_submit:
                try:
                    user = auth.verify_signup_otp(pending_email, otp)
                    ss[AUTH_USER_KEY] = user
                    ss[SIGNUP_PENDING_EMAIL_KEY] = ""
                    st.rerun()
                except Exception as e:
                    st.error(f"验证失败：{str(e)[:120]}")
        else:
            # 第一步：邮箱 + 密码 + 确认密码
            with st.form("cx_signup_form"):
                signup_email = st.text_input("邮箱", key="signup_email", placeholder="your@email.com")
                signup_pwd = st.text_input("密码", type="password", key="signup_pwd", placeholder="至少 6 位")
                signup_pwd2 = st.text_input("确认密码", type="password", key="signup_pwd2")
                signup_submit = st.form_submit_button(
                    "注册并获取验证码", type="primary", use_container_width=True)
            if signup_submit:
                if signup_pwd != signup_pwd2:
                    st.error("两次输入的密码不一致")
                else:
                    try:
                        auth.signup_send_otp(signup_email, signup_pwd)
                        ss[SIGNUP_PENDING_EMAIL_KEY] = signup_email.strip().lower()
                        ss["signup_otp"] = ""
                        st.success("验证码已发送，请查收邮件（含垃圾箱）")
                        st.rerun()
                    except Exception as e:
                        st.error(f"注册失败：{str(e)[:120]}")

    st.markdown(
        f'<div style="text-align:center;padding:16px 0;color:{T.MUTED_SOFT};font-size:11px;">'
        f'认证服务：Supabase Auth · 邮箱验证码注册'
        f'</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════
# 页面：新建审议
# ═══════════════════════════════════════════════════════════

def committee_rows() -> list:
    rows = []
    for group in H.GROUP_ORDER:
        names = H.group_agent_names(group)
        hard, soft = set(), set()
        for n in names:
            hd, sd = H.dependency_names(n)
            hard |= set(hd)
            soft |= set(sd)
        if hard:
            foot = "硬依赖 " + " / ".join(sorted(hard))
        elif soft:
            foot = f"软依赖 {len(soft)} 份专家报告"
        else:
            foot = "并行独立分析"
        rows.append({
            "group": group,
            "count": len(names),
            "members": [H.agent_label(n) for n in names],
            "foot": foot,
        })
    return rows


def pipeline_nodes(states: dict = None) -> list:
    """首页与运行页共用的审议流程（真实分组与依赖形成的 5 步闭环）。"""
    states = states or {}
    expert_n = len(H.group_agent_names("专家委员会"))
    red_soft = len(H.dependency_names("red_team")[1])
    nodes = [
        {"key": "expert", "title": "专家委员会", "sub": f"{expert_n} 位委员并行独立分析"},
        {"key": "red_team", "title": "红队质疑", "sub": f"对 {red_soft} 份专家报告发起对抗攻击"},
        {"key": "commander", "title": "创业总指挥", "sub": "综合结论、核心矛盾与阶段判断"},
        {"key": "review", "title": "项目评审", "sub": "五维评估 + 红线一票否决终审"},
        {"key": "pitch", "title": "路演答辩", "sub": "模拟评委追问与路演诊断"},
    ]
    marks = {"expert": "◆", "red_team": "▲", "commander": "●", "review": "■", "pitch": "★"}
    tones = {"red_team": "red", "commander": "purple", "review": "purple", "pitch": "purple"}
    for n in nodes:
        n["mark"] = marks[n["key"]]
        n["tone"] = tones.get(n["key"], "expert")
        st_key = states.get(n["key"])
        n["state"] = {"done": "done", "running": "running", "blocked": "blocked"}.get(st_key, "pending")
        if st_key:
            n["state_badge"] = st_key
    return nodes


def page_new():
    title, tone = current_status()
    st.markdown(UI.page_header("创业项目审议", "让 AI 创业委员会先质疑它", title, tone),
                unsafe_allow_html=True)
    st.markdown(UI.hero(len(H.STAGE_ROWS), len(H.GROUP_ORDER), 5), unsafe_allow_html=True)

    st.markdown(UI.section("Committees", "三大委员会",
                           "专家负责把想法拆开看，红队负责找它可能失败的地方，决策委员会负责给出结论。"),
                unsafe_allow_html=True)
    st.markdown(UI.committee_cards(committee_rows()), unsafe_allow_html=True)

    st.markdown(UI.section("New Review", "提交创业想法",
                           "描述越具体，红队攻击越精准。目标用户、痛点、产品、商业模式缺一项都会被追问。"),
                unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown('<div class="cx-root cx-card-head">'
                    '<span class="cx-mark" style="background:%s;color:%s;">📝</span>'
                    '<span class="cx-card-title">介绍你的创业想法</span></div>' % (T.PRIMARY_SOFT, T.PRIMARY),
                    unsafe_allow_html=True)
        idea = st.text_area(
            "创业想法",
            value=DEFAULT_IDEA["desc"],
            height=190,
            max_chars=IDEA_LIMIT,
            label_visibility="collapsed",
        )
        st.markdown(
            UI.input_hint(len(idea or ""), IDEA_LIMIT,
                          "建议覆盖：目标用户 · 痛点 · 产品 · 商业模式 · 已有验证"),
            unsafe_allow_html=True)
        extra = {}
        with st.expander("补充信息（可选 · 会一并交给委员会）"):
            extra["name"] = st.text_input("项目名称", value=DEFAULT_IDEA["name"])
            extra["users"] = st.text_input("目标用户", value=DEFAULT_IDEA["users"])
            extra["biz"] = st.text_input("商业模式", value=DEFAULT_IDEA["biz"])
            extra["valid"] = st.text_area("已有验证 / 数据", value=DEFAULT_IDEA["valid"], height=80)
        col_a, col_b = st.columns([1.2, 2.6])
        with col_a:
            start = st.button("🚀 开始委员会审议", type="primary", use_container_width=True)
        with col_b:
            st.caption("12 位委员将逐棒审议，任一棒失败不影响其余委员，结果可追溯、可续跑。")

    idea_payload = {
        "name": extra.get("name") or DEFAULT_IDEA["name"],
        "desc": (idea or "").strip() or DEFAULT_IDEA["desc"],
        "users": extra.get("users") or DEFAULT_IDEA["users"],
        "biz": extra.get("biz") or DEFAULT_IDEA["biz"],
        "valid": extra.get("valid") or DEFAULT_IDEA["valid"],
    }

    if start:
        ss.project_input = _compose_project_input(idea_payload)
        ss.stage = 0
        ss.ctx = ProjectContext(project_info=ss.project_input)
        ss.results = {}
        ss.error = None
        ss.source = ""
        goto(NAV_RUN)

    # 次要动作：磁盘报告 / 委员会架构
    c1, c2, _sp = st.columns([1.4, 1.2, 2.4])
    with c1:
        n_reports = available_reports(DEMO_REPORT_DIR)
        if st.button(f"📂 加载已有报告（{n_reports}/12）", use_container_width=True):
            if load_reports_from_dir(DEMO_REPORT_DIR, _compose_project_input(idea_payload)):
                goto(NAV_RUN)
            else:
                st.error("未找到可读取的报告文件。")
    with c2:
        if st.button("◈ 查看委员会架构", use_container_width=True):
            goto(NAV_COMMITTEE)

    st.markdown(UI.section("Pipeline", "审议闭环"), unsafe_allow_html=True)
    st.markdown(UI.dag(pipeline_nodes()), unsafe_allow_html=True)

    st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
    st.markdown(UI.footnote(
        "审议结论全部来自委员会真实输出：结论档位、红线触发、五维评分均由报告原文解析或系统规则结算，"
        "前端不做任何美化性修改。"), unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════
# 页面：本次审议（空态 / 运行态 / 结果态）
# ═══════════════════════════════════════════════════════════

def group_states(current_stage: int) -> dict:
    """按真实棒次计算每个委员会的进度与状态键。"""
    out = {}
    for group in H.GROUP_ORDER:
        idxs = [r["idx"] for r in H.STAGE_ROWS if r["group"] == group]
        done = sum(1 for i in idxs if i < current_stage)
        if done >= len(idxs):
            key = "success"
        elif any(i == current_stage for i in idxs):
            key = "running"
        else:
            key = "pending"
        out[group] = {"done": done, "total": len(idxs), "state_key": key}
    return out


def stage_node_states(current_stage: int) -> dict:
    """把 12 棒映射到 5 个流程节点的状态（真实棒次区间）。"""
    out = {}
    out["expert"] = "running" if current_stage <= 7 else "done"
    out["red_team"] = ("running" if current_stage == 8
                       else "done" if current_stage > 8 else None)
    out["commander"] = ("running" if current_stage == 9
                        else "done" if current_stage > 9 else None)
    out["review"] = ("running" if current_stage == 10
                     else "done" if current_stage > 10 else None)
    out["pitch"] = ("running" if current_stage == 11
                    else "done" if current_stage > 11 else None)
    return {k: v for k, v in out.items() if v}


def agent_rows(current_stage: int) -> list:
    rows = []
    for r in H.STAGE_ROWS:
        res = ss.results.get(r["idx"])
        key = H.status_key_for(res, r["idx"], current_stage)
        rows.append({
            "label": r["label"],
            "seq": r["seq"],
            "group": r["group"],
            "status_key": key,
            "conclusion": getattr(res, "conclusion", "") if res is not None else "",
        })
    return rows


def page_run():
    if ss.stage < 0 or ss.ctx is None:
        title, tone = current_status()
        st.markdown(UI.page_header("本次审议", "", title, tone), unsafe_allow_html=True)
        st.markdown(UI.empty_state(
            "∞", "还没有进行中的审议",
            "提交一个创业想法，12 位 AI 委员将逐棒审议：专家并行分析 → 红队质疑 → 总指挥 → 项目评审 → 路演答辩。"),
            unsafe_allow_html=True)
        c1, c2, _ = st.columns([1.2, 1.2, 3])
        with c1:
            if st.button("＋ 新建审议", type="primary", use_container_width=True):
                goto(NAV_NEW)
        with c2:
            if st.button("▣ 最近项目", use_container_width=True):
                goto(NAV_RECENT)
        return

    if ss.stage >= len(H.STAGE_ROWS):
        page_result()
        return

    # ══════════ 运行态 ══════════
    current_idx = ss.stage
    info = H.STAGE_ROWS[current_idx]
    total = len(H.STAGE_ROWS)
    project_head = H.truncate((ss.project_input or "").split("\n")[0], 46)

    st.markdown(UI.page_header("本次审议", "委员会正在审议", f"进行中 {ss.stage + 1}/{total}", "primary"),
                unsafe_allow_html=True)
    st.markdown(UI.section("Live Review", "委员会正在审议",
                           f"你的创业想法正在接受 {total} 位 AI 委员的联合分析 · 当前第 {ss.stage + 1} 棒：{info['label']}"),
                unsafe_allow_html=True)
    st.markdown(UI.footnote(H.esc(project_head)), unsafe_allow_html=True)
    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)

    st.progress(min(current_idx + 1, total) / total)
    st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)
    st.markdown(UI.group_progress([
        {"group": g, **v} for g, v in group_states(current_idx).items()
    ]), unsafe_allow_html=True)

    st.markdown(UI.section("Pipeline", "审议流程"), unsafe_allow_html=True)
    st.markdown(UI.dag(pipeline_nodes(stage_node_states(current_idx))), unsafe_allow_html=True)

    st.markdown(UI.section("Agents", "Agent 状态墙",
                           "每一步都来自系统真实执行状态：等待 / 分析中 / 已完成 / 降级 / 异常 / 阻断。"),
                unsafe_allow_html=True)
    st.markdown(UI.agent_wall(agent_rows(current_idx)), unsafe_allow_html=True)

    # ── 执行当前棒（业务逻辑与重构前完全一致） ──
    pipe = CommitteePipeline()
    try:
        with st.spinner(f"{info['label']} 正在分析..."):
            result = pipe.run_stage(current_idx, ss.project_input, ss.ctx)
            ss.results[current_idx] = result
            ss.stage += 1

            if ss.stage < total:
                st.rerun()
            else:
                pipe.save_final_report(ss.ctx)
                ss.stage = total
                st.rerun()
    except Exception as e:
        st.error(f"第 {current_idx + 1} 棒执行失败：{str(e)[:200]}")
        st.markdown(UI.note_box(
            "可能是 LLM 推理链占满 token，或模型服务暂不可用。",
            "已成功棒次的结论仍在，可直接重试当前棒；也可稍后从「最近项目」断点续跑。",
            "warning"), unsafe_allow_html=True)
        if st.button("🔄 重试当前棒"):
            st.rerun()


# ═══════════════════════════════════════════════════════════
# 页面：终审结果
# ═══════════════════════════════════════════════════════════

def _verdict_tone(text: str) -> str:
    t = text or ""
    if any(k in t for k in ("暂缓", "不予", "材料不齐", "否决")):
        return "danger"
    if any(k in t for k in ("准入", "通过", "可进入")):
        return "success"
    return "primary"


def render_agent_report(res: AgentResult, row: dict):
    """单个 Agent 的完整报告（首屏只给摘要，展开后是原文与留痕）。"""
    label = row["label"]
    status_key = H.status_key_for(res, row["idx"], ss.stage)
    head = f"{row['seq']} · {label} · {H.status_ui(status_key)['label']}"
    with st.expander(head, expanded=False):
        if res.status == STATUS_FAILED:
            st.markdown(UI.note_box(
                "本棒未通过系统确定性校验（返工后仍不合格）",
                f"该棒失败但不连坐其他委员。原因：{H.truncate(res.summary, 160)}", "danger"),
                unsafe_allow_html=True)
        if res.status == STATUS_BLOCKED:
            st.markdown(UI.note_box("本棒被硬依赖阻断、未调用 AI", H.truncate(res.summary, 200), "danger"),
                        unsafe_allow_html=True)
        if res.status == STATUS_SKIPPED:
            st.markdown(UI.note_box("本棒因上游链路阻断被跳过、未调用 AI", H.truncate(res.summary, 200), "warning"),
                        unsafe_allow_html=True)
        if res.metadata.get("degraded_inputs"):
            missing = "、".join(H.agent_label(n) for n in res.metadata["degraded_inputs"])
            st.markdown(UI.note_box("本棒在上游输入缺失的情况下降级完成",
                                    f"缺失：{missing}。结论请注意输入不完整。", "warning"),
                        unsafe_allow_html=True)
        if res.metadata.get("redline_forced_by_system"):
            st.markdown(UI.note_box(
                "系统强制改判",
                "该终审意见命中红线却给出准入结论，与系统红线规则冲突；"
                "系统已强制改判为「暂缓进入修订周期（红线未清，系统强制）」。", "danger"),
                unsafe_allow_html=True)
        if res.metadata.get("repaired"):
            st.markdown(UI.note_box("本报告已返工", "首次输出未通过系统确定性校验，已附带校验意见返工重写 1 次后通过。",
                                    "warning"), unsafe_allow_html=True)
        warns = res.metadata.get("validation_warnings") or []
        if warns:
            st.markdown(UI.note_box(f"系统校验警告（{len(warns)} 条，接受但留痕）",
                                    "；".join(H.truncate(w, 70) for w in warns[:4]), "warning"),
                        unsafe_allow_html=True)
        if res.conclusion:
            st.markdown(f"**结论：{res.conclusion}**")
        if res.risks:
            st.markdown("**关键风险：**")
            for risk_item in res.risks[:5]:
                st.markdown(f"- {H.truncate(risk_item, 90)}")
        hard, soft = H.dependency_names(row["name"])
        st.markdown(UI.kv_rows([
            ("委员会", row["group"]),
            ("状态", H.status_ui(status_key)["label"]),
            ("硬依赖", " / ".join(hard) or "无（DAG 第 0 层）"),
            ("软依赖", " / ".join(soft) or "无"),
        ]), unsafe_allow_html=True)
        st.markdown("---")
        st.markdown(res.raw_output or "_（本棒无原文输出）_")


def page_result():
    ctx = ss.ctx
    commander = ctx.get_report("commander")
    reviewer = ctx.get_report("project_review")
    pitch = ctx.get_report("pitch_defense")
    red_team = ctx.get_report("red_team")
    stage_text = H.truncate((ss.project_input or "").split("\n")[0], 46)

    st.markdown(UI.page_header("创业项目终审", stage_text or "委员会审议已完成",
                               "审议已完成", "success"), unsafe_allow_html=True)

    # ── 1. 终审结论 ──
    rv = H.parse_review(reviewer.raw_output) if (reviewer is not None and reviewer.raw_output) else {}
    cm = H.parse_commander(commander.raw_output) if (commander is not None and commander.raw_output) else {}
    pt = H.parse_pitch(pitch.raw_output) if (pitch is not None and pitch.raw_output) else {}

    verdict_text = rv.get("verdict") or (reviewer.conclusion if reviewer is not None else "") or "结论缺失"
    if reviewer is None or reviewer.status in (STATUS_BLOCKED, STATUS_SKIPPED, STATUS_FAILED):
        verdict_text = "终审未产出"
    tone = _verdict_tone(verdict_text)
    redline = bool(reviewer is not None and reviewer.metadata.get("redline_triggered"))
    note_parts = []
    if rv.get("veto") == "是":
        note_parts.append("一票否决已触发")
    elif rv.get("veto") == "否":
        note_parts.append("一票否决未触发")
    if rv.get("compliance"):
        note_parts.append(H.truncate(rv["compliance"], 120))
    if reviewer is not None and reviewer.metadata.get("redline_forced_by_system"):
        note_parts.append("系统强制改判：Agent 曾给出与红线冲突的准入结论，已被系统改判为暂缓（红线是系统规则，不是 Prompt 建议）。")

    metrics = [
        ("当前阶段", cm.get("stage") or (commander.conclusion if commander is not None else "") or "未判断",
         "总指挥阶段判定"),
        ("红线一票否决", "触发" if redline else "未触发", "系统规则结算"),
        ("路演建议", pt.get("conclusion") or (pitch.conclusion if pitch is not None else "") or "未判断",
         (f"答辩评级击穿 {pt.get('ratings_pierced')}/{pt.get('ratings_total')}"
          if pt.get("ratings_total") else "路演答辩官判定")),
    ]
    st.markdown(UI.section("Final Review", "创业项目终审", "委员会结论、红线状态与路演建议——全部来自真实报告。"),
                unsafe_allow_html=True)
    st.markdown(UI.verdict_card("Final Verdict", verdict_text, tone,
                                " · ".join(note_parts), metrics), unsafe_allow_html=True)

    # ── 2. 五维评估 ──
    if rv.get("dims"):
        st.markdown(UI.section("Dimensions", "五维评估", "评分与证据强度来自项目评审官报告原文。"),
                    unsafe_allow_html=True)
        st.markdown(UI.dim_rows(rv["dims"]), unsafe_allow_html=True)

    # ── 3. 冲突链 ──
    red_items = (H.parse_red_team_assumptions(red_team.raw_output)
                 if (red_team is not None and red_team.raw_output) else [])
    conflicts = H.build_conflict_chain(red_items, limit=4)
    if conflicts:
        st.markdown(UI.section("Conflicts", "委员会发现的关键矛盾",
                               "红队报告中对项目方主张的引用，以及委员会要求补上的证据。"),
                    unsafe_allow_html=True)
        st.markdown(UI.conflict_list(conflicts), unsafe_allow_html=True)

    # ── 4. 红队 ──
    if red_team is not None:
        counts = H.parse_red_team_counts(red_team.raw_output or "")
        st.markdown(UI.section("Adversarial", "红队质疑官", "全程只说这个想法可能怎么失败。"),
                    unsafe_allow_html=True)
        st.markdown(UI.redteam_block(RED_TEAM_ROLE, counts, red_items), unsafe_allow_html=True)

    # ── 5. 创业总指挥 ──
    if commander is not None:
        st.markdown(UI.section("Chair", "创业总指挥", "把 12 棒结论收拢成一句结论和三步行动。"),
                    unsafe_allow_html=True)
        st.markdown(UI.commander_block(
            cm.get("conclusion") or commander.conclusion,
            cm.get("stage", ""),
            cm.get("core_conflict", ""),
            cm.get("actions", []),
        ), unsafe_allow_html=True)

    # ── 6. 12 位委员详细报告 ──
    st.markdown(UI.section("Reports", "委员会完整报告",
                           "首屏只给状态与结论，完整原文与系统留痕在展开项里。"),
                unsafe_allow_html=True)
    st.markdown(UI.agent_wall(agent_rows(ss.stage)), unsafe_allow_html=True)
    st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)

    rows_by_name = {r["name"]: r for r in H.STAGE_ROWS}
    report_map = {r.agent_name: r for r in ctx.reports}
    for group in H.GROUP_ORDER:
        names = H.group_agent_names(group)
        present = [n for n in names if n in report_map]
        if not present:
            continue
        meta = H.committee_meta(group)
        st.markdown(
            '<div class="cx-root cx-card-head" style="margin:6px 0 8px 0;">'
            f'<span class="cx-mark" style="background:{meta["soft"]};color:{meta["text"]};">{meta["mark"]}</span>'
            f'<span class="cx-card-title">{H.esc(group)}</span>'
            f'<span class="cx-kv" style="margin-left:6px;">{len(present)} / {len(names)} 份报告</span></div>',
            unsafe_allow_html=True)
        for n in present:
            render_agent_report(report_map[n], rows_by_name[n])

    st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
    c1, c2, c3, _ = st.columns([1.5, 1.2, 1.2, 2.1])
    with c1:
        if st.button("🔄 重新审查另一个项目", type="primary", use_container_width=True):
            reset_run()
            goto(NAV_NEW)
    with c2:
        if st.button("▣ 最近项目", use_container_width=True):
            goto(NAV_RECENT)
    with c3:
        if st.button("◈ 委员会", use_container_width=True):
            goto(NAV_COMMITTEE)


# ═══════════════════════════════════════════════════════════
# 页面：最近项目
# ═══════════════════════════════════════════════════════════

def page_recent():
    title, tone = current_status()
    st.markdown(UI.page_header("最近项目", "运行记录与报告来源", title, tone), unsafe_allow_html=True)

    try:
        uid = current_user_id()
        store = RunStore()
        if uid:
            runs = store.list_user_runs(uid, limit=20)
        else:
            runs = store.list_recent_runs(limit=10)
        err = ""
    except Exception as e:
        runs, err = [], str(e)[:120]

    if err:
        st.markdown(UI.note_box("运行记录不可用", err, "warning"), unsafe_allow_html=True)
    if not runs:
        st.markdown(UI.empty_state("▣", "还没有历史运行记录",
                                   "完成一次委员会审议后，这里会显示每一次运行的真实状态、棒次与报告目录。"),
                    unsafe_allow_html=True)
        return

    recoverable = (RUN_PAUSED, RUN_FAILED, RUN_COMPLETED_WITH_ERRORS)
    for run in runs:
        status_key = H.run_status_key(run.status)
        n_reports = available_reports(run.report_dir)
        meta = H.committee_meta("决策委员会")
        with st.container(border=True):
            st.markdown(
                '<div class="cx-root" style="display:flex;align-items:flex-start;gap:12px;">'
                '<div style="flex:1 1 auto;min-width:0;">'
                f'<div class="cx-card-head">{UI.dot(meta["solid"])}'
                f'<span class="cx-card-title">{H.esc(H.truncate((run.project_input or "未记录项目描述").splitlines()[0], 40))}</span>'
                f'<span style="margin-left:auto;">{UI.status_badge(status_key)}</span></div>'
                f'<div class="cx-agent-meta" style="margin-top:6px;">{H.esc(run.run_id)} · 当前棒次 {H.esc(run.current_stage or "-")}'
                f' · 报告 {n_reports}/12 份</div>'
                f'<div class="cx-kv" style="margin-top:4px;">更新于 {H.esc(run.updated_at or "-")}'
                + (f" · 暂停原因：{H.esc(H.truncate(run.pause_reason, 40))}" if run.pause_reason else "")
                + (" · 错误：" + H.esc(H.truncate(run.error, 40)) if run.error else "")
                + '</div></div></div>',
                unsafe_allow_html=True)
            b1, b2, _ = st.columns([1.1, 1.3, 3.6])
            if run.status in recoverable:
                with b1:
                    if st.button("▶ 恢复审议", key=f"resume_{run.run_id}", use_container_width=True):
                        try:
                            with st.spinner("正在从断点恢复：已成功的棒次本地回读，不重复调用 LLM..."):
                                pipe = CommitteePipeline()
                                ss.ctx = pipe.resume(run.run_id)
                                ss.project_input = run.project_input
                                ss.results = {}
                                pipe.save_final_report(ss.ctx)
                                ss.stage = len(H.STAGE_ROWS)
                                ss.source = getattr(ss.ctx, "report_dir", "") or ""
                            goto(NAV_RUN)
                        except Exception as e:
                            st.error(f"恢复失败：{str(e)[:200]}")
            with b2:
                if n_reports > 0 and st.button("📂 加载这些报告", key=f"load_{run.run_id}",
                                               use_container_width=True):
                    if load_reports_from_dir(run.report_dir, run.project_input):
                        goto(NAV_RUN)
                    else:
                        st.error("该运行的报告目录不可读。")
            if n_reports == 0 and run.status not in recoverable:
                with b1:
                    st.caption("无报告文件")


# ═══════════════════════════════════════════════════════════
# 页面：委员会
# ═══════════════════════════════════════════════════════════

def page_committee():
    title, tone = current_status()
    st.markdown(UI.page_header("委员会", f"{len(H.STAGE_ROWS)} 位 AI 委员 · {len(H.GROUP_ORDER)} 大委员会",
                               title, tone), unsafe_allow_html=True)
    st.markdown(UI.section("Committees", "三大委员会",
                           "委员名称、数量、顺序与依赖关系均来自 Agent Registry（DAG 单一事实源）。"),
                unsafe_allow_html=True)
    st.markdown(UI.committee_cards(committee_rows()), unsafe_allow_html=True)

    st.markdown(UI.section("Roster", "委员名册", "硬依赖缺失会阻断本棒，软依赖缺失则降级继续。"),
                unsafe_allow_html=True)
    for group in H.GROUP_ORDER:
        meta = H.committee_meta(group)
        names = H.group_agent_names(group)
        st.markdown(
            '<div class="cx-root cx-card-head" style="margin:8px 0 10px 0;">'
            f'<span class="cx-mark" style="background:{meta["soft"]};color:{meta["text"]};">{meta["mark"]}</span>'
            f'<span class="cx-card-title">{H.esc(group)}</span>'
            f'<span class="cx-kv" style="margin-left:6px;">{len(names)} Agent{"" if len(names) == 1 else "s"}</span></div>',
            unsafe_allow_html=True)
        rows = []
        for n in names:
            hard, soft = H.dependency_names(n)
            dep = " / ".join(H.truncate(x, 6) for x in hard) or ("软依赖 " + str(len(soft)) + " 份专家报告" if soft else "无前置依赖")
            rows.append({
                "label": H.agent_label(n),
                "seq": H.agent_seq(n),
                "group": group,
                "status_key": "pending",
                "conclusion": f"依赖：{dep}",
            })
        st.markdown(UI.agent_wall(rows), unsafe_allow_html=True)

    st.markdown(UI.section("Pipeline", "审议闭环"), unsafe_allow_html=True)
    st.markdown(UI.dag(pipeline_nodes()), unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════
# 页面：设置
# ═══════════════════════════════════════════════════════════

def page_settings():
    title, tone = current_status()
    st.markdown(UI.page_header("设置", "系统状态与设计规范", title, tone), unsafe_allow_html=True)

    st.markdown(UI.section("System", "系统状态", "只展示是否已注入密钥，绝不显示密钥内容。"),
                unsafe_allow_html=True)
    platforms = []
    for p in PLATFORMS:
        platforms.append((p.name, f"{p.model} · 密钥{'已注入' if p.api_key else '未注入'}"))
    st.markdown(UI.kv_rows([
        ("前端框架", f"Streamlit {st.__version__}"),
        ("Python", sys.version.split()[0]),
        ("报告目录", str(DEMO_REPORT_DIR.relative_to(ROOT)) + f"（{available_reports(DEMO_REPORT_DIR)}/12 份）"),
        ("运行记录库", str((ROOT / "data" / "creativity_runs.db").relative_to(ROOT))),
        ("委员数量", f"{len(H.STAGE_ROWS)} 位 · 顺序与依赖由 Registry 派生"),
    ] + platforms), unsafe_allow_html=True)

    st.markdown(UI.section("Session", "当前会话", "仅重置前端展示状态，不影响磁盘上的报告与运行记录。"),
                unsafe_allow_html=True)
    c1, _sp = st.columns([1.4, 4.6])
    with c1:
        if st.button("清空当前会话", use_container_width=True):
            reset_run()
            ss.nav = NAV_NEW
            st.rerun()

    st.markdown(UI.section("Design", "设计规范", "界面只使用 Design Token，不散写色值。"),
                unsafe_allow_html=True)
    st.markdown(UI.swatches([
        ("background", T.BACKGROUND), ("surface", T.SURFACE), ("border", T.BORDER),
        ("primary", T.PRIMARY), ("主色软底", T.PRIMARY_SOFT),
        ("专家委员会", T.EXPERT), ("对抗委员会", T.REDTEAM), ("决策委员会", T.DECISION),
        ("success", T.SUCCESS), ("warning", T.WARNING), ("danger", T.DANGER),
    ]), unsafe_allow_html=True)
    st.markdown(UI.footnote(
        f"圆角只允许三档：{T.RADIUS_SM} / {T.RADIUS_MD} / {T.RADIUS_LG}　·　"
        f"阴影只保留两级：{T.SHADOW_DEFAULT} / {T.SHADOW_HOVER}"), unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════
# 路由（带认证门禁）
# ═══════════════════════════════════════════════════════════
if not current_user():
    # 未登录 → 只显示登录/注册页（不渲染侧边栏与业务页面）
    page_auth()
else:
    render_sidebar()

    if ss.nav == NAV_NEW:
        page_new()
    elif ss.nav == NAV_RUN:
        page_run()
    elif ss.nav == NAV_RECENT:
        page_recent()
    elif ss.nav == NAV_COMMITTEE:
        page_committee()
    else:
        page_settings()
