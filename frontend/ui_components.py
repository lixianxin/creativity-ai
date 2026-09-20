# -*- coding: utf-8 -*-
"""创想∞ 前端展示组件（纯展示层）。

原则：
- 本文件只产出 HTML/CSS，不调用任何后端逻辑、不伪造任何数据；
- 所有动态文本必须经 esc() 转义；
- 红队五维 / 总指挥行动项等摘要均从真实报告原文解析，解析不到就不展示。
"""
import html as _html
import re

import streamlit as st

# ── 品牌设计令牌（与 config.toml 深色主题、PPT/视频/封面一致） ──
NAVY = "#0B1F3A"
CARD = "#132B4D"
CARD_HOVER = "#17345A"
BORDER = "#24415F"
TEXT = "#F2F6FA"
MUTED = "#8FA3BC"
TEAL = "#12B5A3"
RED = "#E54B4B"
RED_DARK = "#B4353F"
ORANGE = "#FF8A3D"
BLUE = "#4F8DFF"
SKIP = "#6B7F99"

STATUS_META = {
    "done":     (TEAL, "已完成"),
    "running":  (BLUE, "分析中"),
    "pending":  ("#5B7189", "等待中"),
    "failed":   (RED, "校验未通过"),
    "blocked":  (RED_DARK, "已阻断"),
    "degraded": (ORANGE, "降级完成"),
    "skipped":  (SKIP, "已跳过"),
}


def esc(text) -> str:
    return _html.escape(str(text if text is not None else ""))


def clean(text) -> str:
    """清洗报告原文里的 markdown 粗体符号（HTML 卡片不渲染 markdown），不改写数据本身。"""
    s = str(text if text is not None else "")
    return s.replace("**", "").replace("__", "").strip()


def mc(text) -> str:
    """业务文本入卡片：先清洗 markdown 符号再转义。"""
    return esc(clean(text))


# ════════════════════════ CSS ════════════════════════

CSS = """
<style>
:root {
  --cx-teal: %TEAL%; --cx-red: %RED%; --cx-orange: %ORANGE%;
  --cx-border: %BORDER%; --cx-card: %CARD%; --cx-muted: %MUTED%;
}
/* 框架收敛 */
.block-container { padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1240px; }
header[data-testid="stHeader"] { background: transparent; }
#MainMenu, footer { visibility: hidden; }
.stApp { border-top: 4px solid %TEAL%; }
.stApp, section, .stMarkdown { color: %TEXT%; }

/* 标题节奏 */
h1, h2, h3 { letter-spacing: .5px; }
hr, .stHorizontalBlock + hr { border-color: %BORDER%; margin: 1.4rem 0; }

/* 输入控件：深色、圆角、克制 */
.stTextInput input, .stTextArea textarea {
  background: #0E2543 !important; border: 1px solid %BORDER% !important;
  border-radius: 10px !important; color: %TEXT% !important;
}
.stTextInput input:focus, .stTextArea textarea:focus {
  border-color: %TEAL% !important; box-shadow: none !important;
}
.stTextArea textarea { min-height: 110px; }

/* 按钮：一个主按钮，其余低权重 */
.stButton > button {
  border-radius: 10px; border: 1px solid %BORDER%;
  background: #10294A; color: %TEXT%; font-weight: 600;
  padding: .55rem 1rem; transition: background .15s ease, border-color .15s ease;
}
.stButton > button:hover { background: %CARD%; border-color: #35597F; color: %TEXT%; }
.stButton > button[kind="primary"], button[data-testid="baseButton-primary"] {
  background: %TEAL%; border-color: %TEAL%; color: #06202B; font-weight: 700;
}
.stButton > button[kind="primary"]:hover { background: #18C9B5; border-color: #18C9B5; color: #06202A; }

/* Tabs：激活态青色下划线 */
.stTabs [data-baseweb="tab-list"] { gap: 6px; border-bottom: 1px solid %BORDER%; }
.stTabs [data-baseweb="tab"] {
  border-radius: 8px 8px 0 0; padding: 10px 16px; font-weight: 600;
  color: %MUTED%; background: transparent;
}
.stTabs [aria-selected="true"] { color: %TEXT%; background: #10294A; }
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] { background-color: %TEAL% !important; }
.stTabs [data-baseweb="tab-border"] { background: %BORDER%; }

/* Expander 卡片化 */
[data-testid="stExpander"] {
  background: #0F2745; border: 1px solid %BORDER%; border-radius: 12px;
  padding: 2px 14px; margin-bottom: 10px;
}
[data-testid="stExpander"] summary { font-weight: 600; color: %TEXT%; }

/* alert/info 收敛为卡片 */
[data-testid="stAlert"] { border-radius: 10px; }

/* ── 自定义组件 ── */
.cx-hero { text-align: center; padding: 26px 0 8px 0; }
.cx-hero .eyebrow {
  color: var(--cx-teal); font-size: 12px; font-weight: 700;
  letter-spacing: 3px; margin-bottom: 14px;
}
.cx-hero h1 { font-size: 40px; font-weight: 800; margin: 0 0 12px 0; color: %TEXT%; }
.cx-hero .tagline { color: var(--cx-muted); font-size: 17px; margin: 0; }

.cx-section { margin: 26px 0 10px 0; }
.cx-section .eyebrow {
  color: var(--cx-teal); font-size: 12px; font-weight: 700; letter-spacing: 2px;
}
.cx-section h2 { font-size: 23px; font-weight: 700; margin: 4px 0 0 0; }

.cx-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 14px; }
.cx-card {
  background: linear-gradient(0deg, rgba(255,255,255,.015), rgba(255,255,255,.015)), var(--cx-card);
  border: 1px solid var(--cx-border); border-radius: 12px; padding: 18px 18px 16px 18px;
}
.cx-card .kicker { font-size: 12px; font-weight: 700; letter-spacing: 1.5px; color: var(--cx-muted); }
.cx-card h3 { font-size: 18px; margin: 6px 0 4px 0; }
.cx-card .count { font-size: 13px; color: var(--cx-muted); margin-bottom: 10px; }
.cx-card ul { margin: 6px 0 0 0; padding-left: 0; list-style: none; }
.cx-card li { font-size: 14px; color: #C7D5E6; padding: 3px 0; }
.cx-card.comittee-adversarial { border-color: rgba(229,75,75,.55); }
.cx-card.comittee-adversarial h3 { color: #FF8A8A; }

/* DAG 流程条 */
.cx-dag { display: flex; align-items: stretch; gap: 0; flex-wrap: wrap; margin: 6px 0 4px 0; }
.cx-dag-node {
  flex: 1 1 150px; min-width: 150px; background: #0F2745;
  border: 1px solid var(--cx-border); border-radius: 12px; padding: 14px 16px; text-align: center;
}
.cx-dag-node .n-name { font-size: 15px; font-weight: 700; }
.cx-dag-node .n-sub { font-size: 12px; color: var(--cx-muted); margin-top: 3px; }
.cx-dag-node.done { border-color: rgba(18,181,163,.6); }
.cx-dag-node.active { border-color: var(--cx-teal); background: #102F4C; }
.cx-dag-arrow { display: flex; align-items: center; padding: 0 10px; color: var(--cx-muted); font-size: 20px; }

/* Agent 状态墙 */
.cx-agent-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(235px, 1fr)); gap: 12px; }
.cx-agent {
  background: #0F2745; border: 1px solid var(--cx-border); border-left: 3px solid #5B7189;
  border-radius: 10px; padding: 12px 14px;
}
.cx-agent.done { border-left-color: var(--cx-teal); }
.cx-agent.running { border-left-color: var(--cx-blue, #4F8DFF); }
.cx-agent.failed { border-left-color: var(--cx-red); }
.cx-agent.blocked { border-left-color: #B4353F; }
.cx-agent.degraded { border-left-color: var(--cx-orange); }
.cx-agent.skipped { border-left-color: #6B7F99; opacity: .82; }
.cx-agent .a-head { display: flex; align-items: center; gap: 8px; font-weight: 700; font-size: 15px; }
.cx-agent .a-group { font-size: 11px; color: var(--cx-muted); letter-spacing: 1px; margin: 3px 0 0 18px; }
.cx-agent .a-state { font-size: 12.5px; color: #C7D5E6; margin: 6px 0 0 18px; line-height: 1.5; }
.cx-dot { width: 9px; height: 9px; border-radius: 50%; background: #5B7189; display: inline-block; flex: 0 0 auto; }
.cx-dot.done { background: var(--cx-teal); }
.cx-dot.running { background: #4F8DFF; animation: cx-pulse 1.1s ease-in-out infinite; }
.cx-dot.failed, .cx-dot.blocked { background: var(--cx-red); }
.cx-dot.degraded { background: var(--cx-orange); }
.cx-dot.skipped { background: #6B7F99; }
@keyframes cx-pulse { 0%,100% { opacity: 1; } 50% { opacity: .25; } }

/* 终审横幅 */
.cx-verdict {
  border: 1px solid var(--cx-border); border-left: 5px solid var(--cx-red);
  background: #13284A; border-radius: 14px; padding: 24px 28px; margin: 8px 0 18px 0;
}
.cx-verdict.safe { border-left-color: var(--cx-teal); }
.cx-verdict .eyebrow { color: var(--cx-muted); font-size: 12px; letter-spacing: 2px; font-weight: 700; }
.cx-verdict .v-main { font-size: 30px; font-weight: 800; margin: 6px 0 14px 0; color: %TEXT%; }
.cx-verdict.safe .v-main { color: #8FE3D8; }
.cx-verdict .v-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.cx-verdict .v-item .v-k { font-size: 12px; color: var(--cx-muted); }
.cx-verdict .v-item .v-v { font-size: 17px; font-weight: 700; margin-top: 2px; }
.cx-verdict .v-v.red { color: #FF8A8A; }
.cx-verdict .v-v.teal { color: #8FE3D8; }

/* 冲突链 */
.cx-chain { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.cx-chain .step {
  background: #0F2745; border: 1px solid var(--cx-border); border-radius: 12px; padding: 14px 16px;
  position: relative;
}
.cx-chain .step .s-k { font-size: 12px; color: var(--cx-muted); font-weight: 700; letter-spacing: 1px; }
.cx-chain .step .s-v { font-size: 13.5px; color: #D5E1EF; margin-top: 8px; line-height: 1.6; }
.cx-chain .step.expert { border-top: 3px solid var(--cx-teal); }
.cx-chain .step.redteam { border-top: 3px solid var(--cx-orange); }
.cx-chain .step.risk { border-top: 3px solid var(--cx-red); }
.cx-chain .step.review { border-top: 3px solid var(--cx-red); }

/* 红队/总指挥提示条 */
.cx-callout {
  border-radius: 12px; padding: 16px 20px; margin-bottom: 14px;
  background: #1D2236; border: 1px solid rgba(229,75,75,.5); border-left: 4px solid var(--cx-red);
}
.cx-callout .c-title { font-weight: 800; color: #FF8A8A; font-size: 16px; margin-bottom: 4px; }
.cx-callout .c-body { color: #D5E1EF; font-size: 14px; line-height: 1.7; }
.cx-callout.commander { background: #10293C; border-color: rgba(18,181,163,.45); border-left-color: var(--cx-teal); }
.cx-callout.commander .c-title { color: #8FE3D8; }

.cx-chips { display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0 4px 0; }
.cx-chip {
  font-size: 13px; font-weight: 600; border-radius: 999px; padding: 4px 13px;
  border: 1px solid var(--cx-border); background: #0F2745; color: #C7D5E6;
}
.cx-chip.fatal { border-color: rgba(229,75,75,.6); color: #FF9A9A; background: rgba(229,75,75,.12); }
.cx-chip.high { border-color: rgba(255,138,61,.6); color: #FFB37A; background: rgba(255,138,61,.1); }

.cx-actions { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin: 12px 0; }
.cx-action { background: #0F2745; border: 1px solid var(--cx-border); border-radius: 12px; padding: 14px 16px; }
.cx-action .a-no { color: var(--cx-teal); font-weight: 800; font-size: 14px; }
.cx-action .a-t { font-size: 13px; color: #C7D5E6; line-height: 1.65; margin-top: 6px; }

.cx-sidebar-brand { padding: 6px 4px 14px 4px; border-bottom: 1px solid var(--cx-border); margin-bottom: 12px; }
.cx-sidebar-brand .t1 { font-size: 19px; font-weight: 800; }
.cx-sidebar-brand .t2 { font-size: 12px; color: var(--cx-muted); letter-spacing: 1px; margin-top: 2px; }
.cx-sb-k { font-size: 12px; color: var(--cx-muted); font-weight: 700; letter-spacing: 1px; margin: 14px 0 6px 0; }
.cx-sb-row { font-size: 13.5px; color: #C7D5E6; padding: 2px 0; }

@media (max-width: 1100px) {
  .cx-chain, .cx-verdict .v-grid, .cx-actions { grid-template-columns: 1fr; }
}
</style>
""".replace("%TEAL%", TEAL).replace("%RED%", RED).replace("%ORANGE%", ORANGE) \
   .replace("%BORDER%", BORDER).replace("%CARD%", CARD).replace("%MUTED%", MUTED) \
   .replace("%TEXT%", TEXT)


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


# ════════════════════════ 结构组件 ════════════════════════

def hero():
    st.markdown(
        f"""
        <div class="cx-hero">
          <div class="eyebrow">AI ENTREPRENEURSHIP REVIEW COMMITTEE</div>
          <h1>创想∞ AI创业委员会</h1>
          <p class="tagline">不是帮你把创业故事讲得更漂亮，而是先让它经受一次委员会的挑战。</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def section_heading(eyebrow: str, title: str):
    st.markdown(
        f"""<div class="cx-section">
          <div class="eyebrow">{esc(eyebrow)}</div>
          <h2>{esc(title)}</h2>
        </div>""",
        unsafe_allow_html=True,
    )


def committee_cards():
    """三大委员会卡片（内容为静态组织事实：8/1/3）。"""
    st.markdown(
        """
        <div class="cx-grid">
          <div class="cx-card">
            <div class="kicker">EXPERT COMMITTEE</div>
            <h3>专家委员会</h3>
            <div class="count">8 位 AI 委员 · 首轮并行分析</div>
            <ul>
              <li>用户洞察官 · 市场分析官 · 竞品分析官</li>
              <li>产品设计官 · 商业模式官 · 财务分析官</li>
              <li>增长运营官 · 风险审查官</li>
            </ul>
          </div>
          <div class="cx-card comittee-adversarial">
            <div class="kicker">ADVERSARIAL</div>
            <h3>对抗委员会</h3>
            <div class="count">1 位 AI 委员 · 专门唱反调</div>
            <ul>
              <li>红队质疑官</li>
              <li>五维攻击：需求 / 付费 / 竞争 / 增长 / 壁垒</li>
              <li>不辩护、不补台、只找致命假设</li>
            </ul>
          </div>
          <div class="cx-card">
            <div class="kicker">DECISION COMMITTEE</div>
            <h3>决策委员会</h3>
            <div class="count">3 位 AI 委员 · 逐层终审</div>
            <ul>
              <li>创业总指挥 —— 阶段判断与行动项</li>
              <li>项目评审官 —— 红线一票否决</li>
              <li>路演答辩官 —— 路演压力测试</li>
            </ul>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def dag_flow(states=None):
    """五节点 DAG 流程条。states: list[5]，每项 ∈ done/active/pending。"""
    states = states or ["pending"] * 5
    nodes = [
        ("专家委员会", "8 位并行"),
        ("红队质疑", "五维攻击"),
        ("创业总指挥", "阶段决策"),
        ("项目评审", "红线终审"),
        ("路演答辩", "压力测试"),
    ]
    parts = ['<div class="cx-dag">']
    for i, (name, sub) in enumerate(nodes):
        cls = states[i] if states[i] in ("done", "active") else ""
        parts.append(
            f'<div class="cx-dag-node {cls}"><div class="n-name">{esc(name)}</div>'
            f'<div class="n-sub">{esc(sub)}</div></div>'
        )
        if i < len(nodes) - 1:
            parts.append('<div class="cx-dag-arrow">→</div>')
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)


def group_progress(results: dict, current_idx: int):
    """真实状态计数：专家 0-7 / 对抗 8 / 决策 9-11。返回 [(done,total,state), ...]。"""
    out = []
    for lo, hi in ((0, 8), (8, 9), (9, 12)):
        total = hi - lo
        done = sum(
            1 for i in range(lo, hi)
            if i in results and getattr(results[i], "status", "") in ("success", "degraded")
        )
        if current_idx >= hi:
            state = "done"
        elif lo <= current_idx < hi:
            state = "active"
        else:
            state = "pending"
        out.append((done, total, state))
    return out


def dag_states(current_idx: int):
    """当前棒次 → 五节点 DAG 状态（真实执行位置）。"""
    if current_idx < 0:
        return ["pending"] * 5
    if current_idx < 8:
        return ["active", "pending", "pending", "pending", "pending"]
    if current_idx == 8:
        return ["done", "active", "pending", "pending", "pending"]
    if current_idx == 9:
        return ["done", "done", "active", "pending", "pending"]
    if current_idx == 10:
        return ["done", "done", "done", "active", "pending"]
    if current_idx == 11:
        return ["done", "done", "done", "done", "active"]
    return ["done"] * 5


def _result_state(result, idx, current_idx):
    if result is not None:
        if result.status == "failed":
            return "failed"
        if result.status == "blocked":
            return "blocked"
        if result.status == "skipped":
            return "skipped"
        if result.status == "degraded" or (result.metadata or {}).get("degraded_inputs"):
            return "degraded"
        return "done"
    if idx == current_idx:
        return "running"
    return "pending"


def agent_wall(stage_info, results: dict, current_idx: int):
    """12 Agent 状态墙。results/current_idx 来自真实运行状态。"""
    group_cn = {"expert": "专家委员会", "adversarial": "对抗委员会", "decision": "决策委员会"}
    cards = []
    for idx, si in enumerate(stage_info):
        result = results.get(idx)
        state = _result_state(result, idx, current_idx)
        color, default_text = STATUS_META[state]
        if result is not None and state == "done" and getattr(result, "conclusion", ""):
            detail = result.conclusion[:24]
        elif result is not None and state in ("failed", "blocked", "skipped", "degraded"):
            detail = (getattr(result, "summary", "") or default_text)[:24]
        else:
            detail = default_text
        cards.append(
            f"""<div class="cx-agent {state}">
              <div class="a-head"><span class="cx-dot {state}"></span>{mc(si['label'])}</div>
              <div class="a-group">{esc(group_cn.get(si.get('group'), ''))}</div>
              <div class="a-state">{mc(detail)}</div>
            </div>"""
        )
    st.markdown(f'<div class="cx-agent-grid">{"".join(cards)}</div>', unsafe_allow_html=True)


def verdict_banner(stage_text: str, redline: bool, redline_forced: bool, pitch_text: str,
                   review_conclusion: str):
    """终审横幅。全部字段来自真实 AgentResult。"""
    safe = not redline
    cls = " safe" if safe else ""
    main = mc(review_conclusion) if review_conclusion else ("终审通过" if safe else "终审暂缓")
    redline_html = (
        '<div class="v-v red">触发</div>' if redline else '<div class="v-v teal">未触发</div>'
    )
    forced_note = (
        '<div style="font-size:12px;color:#FFB37A;margin-top:4px;">系统红线规则强制改判</div>'
        if redline_forced else ""
    )
    st.markdown(
        f"""
        <div class="cx-verdict{cls}">
          <div class="eyebrow">FINAL VERDICT · 创业项目终审结果</div>
          <div class="v-main">{main}</div>
          <div class="v-grid">
            <div class="v-item">
              <div class="v-k">项目阶段（创业总指挥）</div>
              <div class="v-v">{mc(stage_text) or '—'}</div>
            </div>
            <div class="v-item">
              <div class="v-k">红线一票否决（项目评审官）</div>
              {redline_html}{forced_note}
            </div>
            <div class="v-item">
              <div class="v-k">路演建议（路演答辩官）</div>
              <div class="v-v">{mc(pitch_text) or '—'}</div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def conflict_chain(risk_summary: str, redteam_summary: str, risk_items: list, review_text: str):
    """冲突链四卡，文本全部来自真实报告。"""
    risk_body = mc("；".join(risk_items[:2])[:90]) if risk_items else mc((risk_summary or "无致命风险")[:90])
    st.markdown(
        f"""
        <div class="cx-chain">
          <div class="step expert">
            <div class="s-k">① 风险审查 · 专家意见</div>
            <div class="s-v">{risk_body or '无致命风险'}</div>
          </div>
          <div class="step redteam">
            <div class="s-k">② 红队质疑 · 致命假设</div>
            <div class="s-v">{mc((redteam_summary or '')[:90])}</div>
          </div>
          <div class="step risk">
            <div class="s-k">③ 分歧进入终审</div>
            <div class="s-v">风险与红队结论不一致时，矛盾不被抹平，全部留痕带进终审。</div>
          </div>
          <div class="step review">
            <div class="s-k">④ 项目评审 · 终审裁决</div>
            <div class="s-v">{mc((review_text or '')[:90])}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ── 真实报告解析（解析不到返回 None / 空，绝不编造） ──

def parse_redteam_findings(raw: str):
    """解析『①【需求假设｜致命】』式五维标题。返回 [(维度, 严重度), ...]。"""
    out = []
    for m in re.finditer(r"[①②③④⑤]\s*[【\[]\s*([^】\]｜|]+)\s*(?:[｜|]\s*([^】\]]+?))?\s*[】\]]", raw or ""):
        dim = m.group(1).strip()
        sev = (m.group(2) or "").strip()
        if dim:
            out.append((dim, sev))
    return out[:5]


def redteam_block(raw: str):
    """红队 tab 顶部：宣言条 + 真实五维严重度 chips。无内容返回 None。"""
    findings = parse_redteam_findings(raw)
    chips = []
    for dim, sev in findings:
        cls = "fatal" if "致命" in sev else ("high" if sev in ("高", "高风险") else "")
        suffix = f"｜{mc(sev)}" if sev else ""
        chips.append(f'<span class="cx-chip {cls}">{mc(dim)}{suffix}</span>')
    chips_html = f'<div class="cx-chips">{"".join(chips)}</div>' if chips else ""
    return f"""
    <div class="cx-callout">
      <div class="c-title">红队质疑官 · 我不是来完善你的创业想法的</div>
      <div class="c-body">我负责找出它为什么可能失败：对需求、付费、竞争、增长、壁垒五类核心假设逐一攻击，
      并给出待验证项与证据缺口。以下五维判定来自本次真实审查报告。</div>
      {chips_html}
    </div>
    """


def parse_commander_actions(raw: str):
    """从『下一步行动』段解析 ①②③ 行动项原文。"""
    anchor = re.search(r"下一步行动[：:]?\s*(.*)", raw or "", re.S)
    if not anchor:
        return []
    tail = anchor.group(1)
    tail = re.split(r"\n\s*[#\-\*]{2,}|$", tail)[0]
    marks = list(re.finditer(r"[①②③④⑤]", tail))
    actions = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(tail)
        text = tail[m.end():end].strip(" ：:\n\r\t。；")
        text = re.sub(r"\s+", " ", text)
        if text:
            actions.append((m.group(0), text))
    return actions[:3]


def commander_block(raw: str, conclusion: str):
    actions = parse_commander_actions(raw)
    action_html = ""
    if actions:
        cards = "".join(
            f'<div class="cx-action"><div class="a-no">行动 {mc(no)}</div>'
            f'<div class="a-t">{mc(t[:130])}{"…" if len(t) > 130 else ""}</div></div>'
            for no, t in actions
        )
        action_html = f'<div class="cx-actions">{cards}</div>'
    conclusion_html = (
        f'<div style="font-size:14px;color:#8FE3D8;margin-bottom:4px;">当前判断：{mc(conclusion)}</div>'
        if conclusion else ""
    )
    return f"""
    <div class="cx-callout commander">
      <div class="c-title">创业总指挥 · 阶段决策与行动项</div>
      <div class="c-body">不重新分析，只基于全部委员意见给出项目阶段判断与可验证的下一步行动。</div>
      {conclusion_html}{action_html}
    </div>
    """


def sidebar_brand():
    with st.sidebar:
        st.markdown(
            """
            <div class="cx-sidebar-brand">
              <div class="t1">创想∞</div>
              <div class="t2">AI 创业委员会</div>
            </div>
            <div class="cx-sb-k">系统状态</div>
            <div class="cx-sb-row">● 委员会运行时就绪</div>
            <div class="cx-sb-row">● 12 位 AI 委员已加载</div>
            <div class="cx-sb-row">● DAG 编排 · 断点续跑</div>
            <div class="cx-sb-k">版本</div>
            <div class="cx-sb-row">v1.0 · 12 Agents</div>
            """,
            unsafe_allow_html=True,
        )
