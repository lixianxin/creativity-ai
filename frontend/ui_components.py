# -*- coding: utf-8 -*-
"""创想∞ 前端展示组件（纯展示层 · 轻量 AI SaaS 风格）。

原则：
- 本文件只产出 HTML/CSS，不调用任何后端逻辑、不伪造任何数据；
- 所有动态文本必须经 esc() 转义；
- 红队五维 / 总指挥行动项等摘要均从真实报告原文解析，解析不到就不展示。
"""
import html as _html
import re

import streamlit as st

# ═══════════════════════════════════════════════════════════
# 品牌设计令牌（轻量 AI SaaS · 参考 Linear / Notion / Vercel）
# ═══════════════════════════════════════════════════════════

# ── 基础色板 ──
PAGE_BG = "#F7F9FC"        # 页面背景
CARD_BG = "#FFFFFF"         # 卡片背景
TEXT = "#172033"            # 主文字
MUTED = "#667085"           # 次文字
BORDER = "#E4E7EC"          # 细边框
BORDER_STRONG = "#D0D5DD"   # 略强边框
SUBTLE_BG = "#F9FAFB"       # 浅灰底

# ── 语义色 ──
BRAND = "#5B6CFF"           # 主品牌蓝紫
BRAND_LIGHT = "#EEF5FF"     # 浅蓝底
TEAL = "#20BFA9"            # AI 青绿（正向 / 已完成）
TEAL_LIGHT = "#EAFBF7"      # 浅青底
RED = "#F05A5A"             # 红队 / 致命 / 风险
RED_LIGHT = "#FFF0F0"       # 浅红底
PURPLE = "#7C6CFF"          # 决策委员会紫
PURPLE_LIGHT = "#F1EEFF"    # 浅紫底
ORANGE = "#F26B1D"          # 降级 / 高风险
ORANGE_LIGHT = "#FFF6E8"    # 浅橙底
GRAY = "#98A2B3"            # 等待 / 跳过

STATUS_META = {
    "done":     (TEAL, "已完成"),
    "running":  (BRAND, "分析中"),
    "pending":  (GRAY, "等待中"),
    "failed":   (RED, "校验未通过"),
    "blocked":  ("#D92D2D", "已阻断"),
    "degraded": (ORANGE, "降级完成"),
    "skipped":  (GRAY, "已跳过"),
}

# 三大委员会配色（白底 + 小面积强调）
COMMITTEE_META = {
    "expert":      (BRAND, BRAND_LIGHT, "专家委员会"),
    "adversarial": (RED,   RED_LIGHT,   "对抗委员会"),
    "decision":    (PURPLE, PURPLE_LIGHT, "决策委员会"),
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


# ═══════════════════════════════════════════════════════════
# CSS（轻量 · 空气感 · 克制阴影 · 微交互）
# ═══════════════════════════════════════════════════════════

CSS = """
<style>
:root {
  --cx-brand: %BRAND%; --cx-teal: %TEAL%; --cx-red: %RED%; --cx-purple: %PURPLE%;
  --cx-orange: %ORANGE%; --cx-gray: %GRAY%;
  --cx-text: %TEXT%; --cx-muted: %MUTED%; --cx-border: %BORDER%;
  --cx-card: %CARD_BG%; --cx-page: %PAGE_BG%; --cx-subtle: %SUBTLE_BG%;
  --cx-brand-l: %BRAND_LIGHT%; --cx-teal-l: %TEAL_LIGHT%; --cx-red-l: %RED_LIGHT%;
  --cx-purple-l: %PURPLE_LIGHT%; --cx-orange-l: %ORANGE_LIGHT%;
}

/* ── 框架收敛 ── */
.block-container { padding-top: 2rem; padding-bottom: 3rem; max-width: 1180px; }
header[data-testid="stHeader"] { background: transparent; }
#MainMenu, footer { visibility: hidden; }
.stApp { background: var(--cx-page); }
.stApp, section, .stMarkdown { color: var(--cx-text); font-family: 'Inter', system-ui, -apple-system, sans-serif; }

/* 空气感：极浅柔光装饰（无渐变、无赛博） */
.stApp::before {
  content: ''; position: fixed; top: -120px; left: -80px; width: 360px; height: 360px;
  background: radial-gradient(circle, rgba(91,108,255,.045) 0%, transparent 70%);
  pointer-events: none; z-index: 0;
}
.stApp::after {
  content: ''; position: fixed; top: -60px; right: -100px; width: 320px; height: 320px;
  background: radial-gradient(circle, rgba(124,108,255,.04) 0%, transparent 70%);
  pointer-events: none; z-index: 0;
}

/* ── 标题节奏 ── */
h1, h2, h3 { letter-spacing: -.01em; font-weight: 700; }
hr { border-color: var(--cx-border); margin: 1.6rem 0; }

/* ── 输入控件：白底圆角、focus 蓝紫光晕 ── */
.stTextInput input, .stTextArea textarea {
  background: var(--cx-card) !important; border: 1px solid var(--cx-border) !important;
  border-radius: 10px !important; color: var(--cx-text) !important;
  transition: border-color .15s ease, box-shadow .15s ease;
}
.stTextInput input:focus, .stTextArea textarea:focus {
  border-color: var(--cx-brand) !important;
  box-shadow: 0 0 0 3px rgba(91,108,255,.12) !important;
}
.stTextArea textarea { min-height: 110px; }
.stTextArea textarea::placeholder, .stTextInput input::placeholder { color: var(--cx-muted); }

/* ── 按钮：主按钮蓝紫，二级白底灰边 ── */
.stButton > button {
  border-radius: 10px; border: 1px solid var(--cx-border);
  background: var(--cx-card); color: var(--cx-text); font-weight: 600;
  padding: .5rem 1.1rem; font-size: 14px;
  transition: background .15s ease, border-color .15s ease, transform .15s ease, box-shadow .15s ease;
}
.stButton > button:hover {
  background: var(--cx-subtle); border-color: var(--cx-border-strong); transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(16,24,40,.06);
}
.stButton > button[kind="primary"], button[data-testid="baseButton-primary"] {
  background: var(--cx-brand); border-color: var(--cx-brand); color: #FFFFFF; font-weight: 700;
}
.stButton > button[kind="primary"]:hover {
  background: #6B7AFF; border-color: #6B7AFF; transform: translateY(-1px);
  box-shadow: 0 6px 20px rgba(91,108,255,.25);
}

/* ── Tabs：去掉粗下划线，active 浅蓝底 + 品牌色文字 ── */
.stTabs [data-baseweb="tab-list"] { gap: 4px; border-bottom: 1px solid var(--cx-border); background: transparent; }
.stTabs [data-baseweb="tab"] {
  border-radius: 8px; padding: 8px 14px; font-weight: 600; font-size: 14px;
  color: var(--cx-muted); background: transparent; border: 1px solid transparent;
  transition: background .15s ease, color .15s ease;
}
.stTabs [data-baseweb="tab"]:hover { background: var(--cx-subtle); color: var(--cx-text); }
.stTabs [aria-selected="true"] { color: var(--cx-brand); background: var(--cx-brand-l); border-color: var(--cx-brand-l); }
.stTabs [data-baseweb="tab-highlight"] { background-color: transparent !important; height: 0 !important; }
.stTabs [data-baseweb="tab-border"] { background: transparent !important; }

/* ── Expander 卡片化（白底细边） ── */
[data-testid="stExpander"] {
  background: var(--cx-card); border: 1px solid var(--cx-border); border-radius: 10px;
  padding: 2px 14px; margin-bottom: 8px;
  box-shadow: 0 1px 3px rgba(16,24,40,.04);
}
[data-testid="stExpander"] summary { font-weight: 600; color: var(--cx-text); }

/* ── alert 收敛 ── */
[data-testid="stAlert"] { border-radius: 10px; border: 1px solid var(--cx-border); }

/* ── Streamlit container(border) 浅化 ── */
.stContainer > div, [data-testid="stVerticalBlock"] {
  border-color: var(--cx-border) !important;
}

/* ═══════════════════════════════════════════════════════════
   自定义组件
   ═══════════════════════════════════════════════════════════ */

/* ── Hero 区：白底、极浅装饰、深色标题、充足留白 ── */
.cx-hero {
  text-align: center; padding: 2.2rem 0 1.2rem 0; position: relative;
}
.cx-hero .eyebrow {
  color: var(--cx-brand); font-size: 11px; font-weight: 700;
  letter-spacing: 3px; margin-bottom: 14px; text-transform: uppercase;
}
.cx-hero h1 {
  font-size: 38px; font-weight: 800; margin: 0 0 12px 0; color: var(--cx-text);
  letter-spacing: -.02em;
}
.cx-hero .tagline {
  color: var(--cx-muted); font-size: 16px; margin: 0 auto; max-width: 560px; line-height: 1.6;
}
.cx-hero .meta-row {
  display: flex; justify-content: center; gap: 24px; margin-top: 18px;
  font-size: 13px; color: var(--cx-muted); font-weight: 600;
}
.cx-hero .meta-row span { display: inline-flex; align-items: center; gap: 6px; }
.cx-hero .meta-dot { width: 6px; height: 6px; border-radius: 50%; }

/* ── Section 标题 ── */
.cx-section { margin: 28px 0 12px 0; }
.cx-section .eyebrow {
  color: var(--cx-brand); font-size: 11px; font-weight: 700; letter-spacing: 2px; text-transform: uppercase;
}
.cx-section h2 { font-size: 22px; font-weight: 700; margin: 4px 0 0 0; color: var(--cx-text); }

/* ── 委员会卡片：白底、细边、小圆点、Badge ── */
.cx-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
.cx-card {
  background: var(--cx-card); border: 1px solid var(--cx-border); border-radius: 12px;
  padding: 20px; transition: transform .18s ease, box-shadow .18s ease;
  box-shadow: 0 1px 3px rgba(16,24,40,.04);
}
.cx-card:hover { transform: translateY(-2px); box-shadow: 0 8px 24px rgba(16,24,40,.08); }
.cx-card .c-head { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.cx-card .c-dot { width: 10px; height: 10px; border-radius: 50%; flex: 0 0 auto; }
.cx-card .c-badge {
  margin-left: auto; font-size: 11px; font-weight: 700; padding: 3px 10px; border-radius: 999px;
}
.cx-card h3 { font-size: 17px; margin: 0; color: var(--cx-text); font-weight: 700; }
.cx-card .c-sub { font-size: 13px; color: var(--cx-muted); margin: 2px 0 12px 0; }
.cx-card ul { margin: 6px 0 0 0; padding-left: 0; list-style: none; }
.cx-card li { font-size: 13.5px; color: var(--cx-text); padding: 3px 0; line-height: 1.5; opacity: .85; }

/* ── DAG 审议路径：细连线 + 节点点 ── */
.cx-dag {
  display: flex; align-items: stretch; gap: 0; margin: 10px 0 6px 0;
  background: var(--cx-card); border: 1px solid var(--cx-border); border-radius: 12px;
  padding: 18px 12px; box-shadow: 0 1px 3px rgba(16,24,40,.04);
}
.cx-dag-node {
  flex: 1 1 0; text-align: center; padding: 6px 8px; position: relative;
}
.cx-dag-node .n-dot {
  width: 28px; height: 28px; border-radius: 50%; margin: 0 auto 8px auto;
  display: flex; align-items: center; justify-content: center;
  background: var(--cx-subtle); border: 2px solid var(--cx-border); transition: all .18s ease;
}
.cx-dag-node .n-dot .n-icon { font-size: 13px; font-weight: 800; color: var(--cx-muted); }
.cx-dag-node .n-name { font-size: 14px; font-weight: 700; color: var(--cx-text); }
.cx-dag-node .n-sub { font-size: 11px; color: var(--cx-muted); margin-top: 2px; }
.cx-dag-node.done .n-dot { background: var(--cx-teal-l); border-color: var(--cx-teal); }
.cx-dag-node.done .n-dot .n-icon { color: var(--cx-teal); }
.cx-dag-node.active .n-dot {
  background: var(--cx-brand-l); border-color: var(--cx-brand);
  box-shadow: 0 0 0 4px rgba(91,108,255,.1);
}
.cx-dag-node.active .n-dot .n-icon { color: var(--cx-brand); }
.cx-dag-arrow {
  display: flex; align-items: center; color: var(--cx-border-strong); font-size: 16px; padding: 0 4px;
  margin-top: -20px;
}

/* ── Agent 成员名片：白底 + 小圆点 + 名称/委员会/状态 ── */
.cx-agent-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 10px; }
.cx-agent {
  background: var(--cx-card); border: 1px solid var(--cx-border); border-radius: 10px;
  padding: 14px 16px; transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease;
}
.cx-agent:hover { transform: translateY(-1px); box-shadow: 0 4px 16px rgba(16,24,40,.06); }
.cx-agent .a-head { display: flex; align-items: center; gap: 8px; font-weight: 700; font-size: 14.5px; color: var(--cx-text); }
.cx-agent .a-group { font-size: 11px; color: var(--cx-muted); letter-spacing: .5px; margin: 3px 0 0 20px; }
.cx-agent .a-state { font-size: 12.5px; color: var(--cx-muted); margin: 6px 0 0 20px; line-height: 1.5; }
.cx-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--cx-gray); display: inline-block; flex: 0 0 auto; }
.cx-dot.done { background: var(--cx-teal); }
.cx-dot.running { background: var(--cx-brand); animation: cx-pulse 1.2s ease-in-out infinite; }
.cx-dot.failed, .cx-dot.blocked { background: var(--cx-red); }
.cx-dot.degraded { background: var(--cx-orange); }
.cx-dot.skipped { background: var(--cx-gray); }
@keyframes cx-pulse { 0%,100% { opacity: 1; } 50% { opacity: .35; } }
/* Agent 左侧细色条（状态指示） */
.cx-agent.done { border-left: 3px solid var(--cx-teal); }
.cx-agent.running { border-left: 3px solid var(--cx-brand); }
.cx-agent.failed { border-left: 3px solid var(--cx-red); }
.cx-agent.blocked { border-left: 3px solid #D92D2D; }
.cx-agent.degraded { border-left: 3px solid var(--cx-orange); }
.cx-agent.skipped { border-left: 3px solid var(--cx-gray); opacity: .7; }

/* ── 终审横幅：决策报告风（白底 + 左色条 + Badge） ── */
.cx-verdict {
  background: var(--cx-card); border: 1px solid var(--cx-border); border-left: 5px solid var(--cx-red);
  border-radius: 12px; padding: 24px 28px; margin: 8px 0 18px 0;
  box-shadow: 0 1px 3px rgba(16,24,40,.05);
}
.cx-verdict.safe { border-left-color: var(--cx-teal); }
.cx-verdict .eyebrow { color: var(--cx-muted); font-size: 11px; letter-spacing: 2px; font-weight: 700; text-transform: uppercase; }
.cx-verdict .v-main { font-size: 28px; font-weight: 800; margin: 6px 0 16px 0; color: var(--cx-text); letter-spacing: -.01em; }
.cx-verdict.safe .v-main { color: var(--cx-teal); }
.cx-verdict .v-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; padding-top: 14px; border-top: 1px solid var(--cx-border); }
.cx-verdict .v-item .v-k { font-size: 12px; color: var(--cx-muted); font-weight: 600; }
.cx-verdict .v-item .v-v { font-size: 16px; font-weight: 700; margin-top: 4px; color: var(--cx-text); }
.cx-verdict .v-badge {
  display: inline-flex; align-items: center; gap: 4px; font-size: 12px; font-weight: 700;
  padding: 3px 10px; border-radius: 999px; margin-top: 4px;
}
.cx-verdict .v-badge.red { background: var(--cx-red-l); color: var(--cx-red); }
.cx-verdict .v-badge.teal { background: var(--cx-teal-l); color: var(--cx-teal); }
.cx-verdict .v-forced-note { font-size: 12px; color: var(--cx-orange); margin-top: 6px; }

/* ── 冲突链：证据卡（01-04 编号 + 浅灰底 + 少量强调色） ── */
.cx-chain { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.cx-chain .step {
  background: var(--cx-subtle); border: 1px solid var(--cx-border); border-radius: 10px;
  padding: 16px 18px; position: relative;
}
.cx-chain .step .s-no {
  font-size: 13px; font-weight: 800; color: var(--cx-brand); letter-spacing: 1px; margin-bottom: 6px;
}
.cx-chain .step .s-k { font-size: 12px; color: var(--cx-muted); font-weight: 600; letter-spacing: .5px; }
.cx-chain .step .s-v { font-size: 13.5px; color: var(--cx-text); margin-top: 8px; line-height: 1.6; }
.cx-chain .step .s-vs {
  display: inline-block; font-size: 11px; font-weight: 700; color: var(--cx-muted);
  background: var(--cx-card); padding: 2px 8px; border-radius: 4px; margin: 6px 0; border: 1px solid var(--cx-border);
}
.cx-chain .step.redteam .s-no { color: var(--cx-red); }
.cx-chain .step.risk .s-no { color: var(--cx-red); }
.cx-chain .step.review .s-no { color: var(--cx-purple); }

/* ── 红队 / 总指挥 callout：白底 + 左色条 ── */
.cx-callout {
  background: var(--cx-card); border: 1px solid var(--cx-border); border-left: 4px solid var(--cx-red);
  border-radius: 12px; padding: 18px 22px; margin-bottom: 14px;
  box-shadow: 0 1px 3px rgba(16,24,40,.04);
}
.cx-callout .c-title { font-weight: 800; color: var(--cx-red); font-size: 16px; margin-bottom: 6px; }
.cx-callout .c-body { color: var(--cx-muted); font-size: 14px; line-height: 1.7; }
.cx-callout.commander { border-left-color: var(--cx-purple); }
.cx-callout.commander .c-title { color: var(--cx-purple); }
.cx-callout .c-conclusion { font-size: 14px; color: var(--cx-purple); margin: 8px 0 4px 0; font-weight: 600; }

/* ── 五维 chips（浅底 + 语义色） ── */
.cx-chips { display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0 4px 0; }
.cx-chip {
  font-size: 13px; font-weight: 600; border-radius: 999px; padding: 5px 14px;
  border: 1px solid var(--cx-border); background: var(--cx-subtle); color: var(--cx-text);
}
.cx-chip.fatal { border-color: rgba(240,90,90,.35); color: var(--cx-red); background: var(--cx-red-l); }
.cx-chip.high { border-color: rgba(242,107,29,.35); color: var(--cx-orange); background: var(--cx-orange-l); }

/* ── 总指挥行动卡（白底 + 编号 01-03） ── */
.cx-actions { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin: 12px 0; }
.cx-action {
  background: var(--cx-card); border: 1px solid var(--cx-border); border-radius: 10px; padding: 14px 16px;
  transition: transform .18s ease, box-shadow .18s ease;
}
.cx-action:hover { transform: translateY(-1px); box-shadow: 0 4px 16px rgba(16,24,40,.06); }
.cx-action .a-no { color: var(--cx-purple); font-weight: 800; font-size: 15px; letter-spacing: 1px; }
.cx-action .a-label { font-size: 11px; color: var(--cx-muted); font-weight: 600; text-transform: uppercase; letter-spacing: .5px; margin-top: 2px; }
.cx-action .a-t { font-size: 13.5px; color: var(--cx-text); line-height: 1.65; margin-top: 8px; }

/* ── Sidebar 品牌化（浅色） ── */
.cx-sidebar-brand { padding: 4px 4px 12px 4px; border-bottom: 1px solid var(--cx-border); margin-bottom: 12px; }
.cx-sidebar-brand .t1 { font-size: 18px; font-weight: 800; color: var(--cx-text); }
.cx-sidebar-brand .t2 { font-size: 12px; color: var(--cx-muted); letter-spacing: .5px; margin-top: 2px; }
.cx-sb-k { font-size: 11px; color: var(--cx-muted); font-weight: 700; letter-spacing: 1px; margin: 14px 0 6px 0; text-transform: uppercase; }
.cx-sb-row { font-size: 13px; color: var(--cx-text); padding: 2px 0; display: flex; align-items: center; gap: 6px; }
.cx-sb-row .sb-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--cx-teal); flex: 0 0 auto; }

@media (max-width: 1100px) {
  .cx-grid { grid-template-columns: 1fr; }
  .cx-chain, .cx-verdict .v-grid, .cx-actions { grid-template-columns: 1fr; }
  .cx-dag { flex-direction: column; gap: 4px; }
  .cx-dag-arrow { display: none; }
}
</style>
""".replace("%BRAND%", BRAND).replace("%TEAL%", TEAL).replace("%RED%", RED) \
   .replace("%PURPLE%", PURPLE).replace("%ORANGE%", ORANGE).replace("%GRAY%", GRAY) \
   .replace("%TEXT%", TEXT).replace("%MUTED%", MUTED).replace("%BORDER%", BORDER) \
   .replace("%CARD_BG%", CARD_BG).replace("%PAGE_BG%", PAGE_BG).replace("%SUBTLE_BG%", SUBTLE_BG) \
   .replace("%BRAND_LIGHT%", BRAND_LIGHT).replace("%TEAL_LIGHT%", TEAL_LIGHT) \
   .replace("%RED_LIGHT%", RED_LIGHT).replace("%PURPLE_LIGHT%", PURPLE_LIGHT) \
   .replace("%ORANGE_LIGHT%", ORANGE_LIGHT)


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════
# 结构组件
# ═══════════════════════════════════════════════════════════

def hero():
    st.markdown(
        """
        <div class="cx-hero">
          <div class="eyebrow">AI ENTREPRENEURSHIP REVIEW COMMITTEE</div>
          <h1>创想∞ AI创业委员会</h1>
          <p class="tagline">别人帮你完善创业想法，我们让 AI 创业委员会先质疑它。</p>
          <div class="meta-row">
            <span><span class="meta-dot" style="background:#5B6CFF"></span>12 AI 委员</span>
            <span><span class="meta-dot" style="background:#20BFA9"></span>3 大委员会</span>
            <span><span class="meta-dot" style="background:#7C6CFF"></span>1 条审议闭环</span>
          </div>
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
    """三大委员会卡片（内容为静态组织事实：8/1/3）。白底 + 蓝/红/紫小圆点 + Badge。"""
    cards = [
        ("expert", "EXPERT", "专家委员会", "8 位 AI 专家 · 首轮并行分析", "8",
         ["用户洞察 · 市场分析 · 竞品分析", "产品设计 · 商业模式 · 财务分析", "增长运营 · 风险审查"]),
        ("adversarial", "ADVERSARIAL", "对抗委员会", "1 位 AI 委员 · 专门唱反调", "1",
         ["红队质疑官", "五维攻击：需求 / 付费 / 竞争 / 增长 / 壁垒", "不辩护、不补台、只找致命假设"]),
        ("decision", "DECISION", "决策委员会", "3 位 AI 委员 · 逐层终审", "3",
         ["创业总指挥 —— 阶段判断与行动项", "项目评审官 —— 红线一票否决", "路演答辩官 —— 路演压力测试"]),
    ]
    parts = ['<div class="cx-grid">']
    for key, kicker, title, sub, count, items in cards:
        color, light_bg, _ = COMMITTEE_META[key]
        items_html = "".join(f"<li>{esc(it)}</li>" for it in items)
        parts.append(
            f'<div class="cx-card">'
            f'<div class="c-head">'
            f'<span class="c-dot" style="background:{color}"></span>'
            f'<span style="font-size:11px;font-weight:700;letter-spacing:1.5px;color:{color}">{esc(kicker)}</span>'
            f'<span class="c-badge" style="background:{light_bg};color:{color}">{count} Agents</span>'
            f'</div>'
            f'<h3>{esc(title)}</h3>'
            f'<div class="c-sub">{esc(sub)}</div>'
            f'<ul>{items_html}</ul>'
            f'</div>'
        )
    parts.append('</div>')
    st.markdown("".join(parts), unsafe_allow_html=True)


def dag_flow(states=None):
    """五节点 DAG 审议路径。states: list[5]，每项 ∈ done/active/pending。"""
    states = states or ["pending"] * 5
    nodes = [
        ("专家委员会", "8 位并行", "E"),
        ("红队质疑", "五维攻击", "R"),
        ("创业总指挥", "阶段决策", "C"),
        ("项目评审", "红线终审", "V"),
        ("路演答辩", "压力测试", "P"),
    ]
    parts = ['<div class="cx-dag">']
    for i, (name, sub, icon) in enumerate(nodes):
        state = states[i] if states[i] in ("done", "active") else ""
        cls = f' {state}' if state else ''
        parts.append(
            f'<div class="cx-dag-node{cls}">'
            f'<div class="n-dot"><span class="n-icon">{esc(icon)}</span></div>'
            f'<div class="n-name">{esc(name)}</div>'
            f'<div class="n-sub">{esc(sub)}</div>'
            f'</div>'
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
    """12 Agent 成员名片墙。results/current_idx 来自真实运行状态。"""
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
    """终审横幅（决策报告风）。全部字段来自真实 AgentResult。白底 + 左色条 + Badge。"""
    safe = not redline
    cls = " safe" if safe else ""
    main = mc(review_conclusion) if review_conclusion else ("终审通过" if safe else "终审暂缓")
    redline_badge = (
        '<span class="v-badge red">⚠ 红线触发</span>' if redline
        else '<span class="v-badge teal">✓ 红线未触发</span>'
    )
    forced_note = (
        '<div class="v-forced-note">系统红线规则强制改判（Agent 曾给出冲突结论）</div>'
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
              {redline_badge}{forced_note}
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
    """冲突链证据卡（01-04 编号）。文本全部来自真实报告。"""
    risk_body = mc("；".join(risk_items[:2])[:90]) if risk_items else mc((risk_summary or "无致命风险")[:90])
    st.markdown(
        f"""
        <div class="cx-chain">
          <div class="step expert">
            <div class="s-no">01</div>
            <div class="s-k">风险审查 · 专家意见</div>
            <div class="s-v">{risk_body or '无致命风险'}</div>
          </div>
          <div class="step redteam">
            <div class="s-no">02</div>
            <div class="s-k">红队质疑 · 致命假设</div>
            <div class="s-v">{mc((redteam_summary or '')[:90])}</div>
          </div>
          <div class="step risk">
            <div class="s-no">03</div>
            <div class="s-k">分歧进入终审</div>
            <div class="s-v">风险与红队结论不一致时，矛盾不被抹平，全部留痕带进终审。</div>
          </div>
          <div class="step review">
            <div class="s-no">04</div>
            <div class="s-k">项目评审 · 终审裁决</div>
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
      <div class="c-title">🔴 红队质疑官 · 我不是来完善你的创业想法的</div>
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
            f'<div class="cx-action"><div class="a-no">0{i+1}</div>'
            f'<div class="a-label">下一步行动</div>'
            f'<div class="a-t">{mc(t[:130])}{"…" if len(t) > 130 else ""}</div></div>'
            for i, (_, t) in enumerate(actions)
        )
        action_html = f'<div class="cx-actions">{cards}</div>'
    conclusion_html = (
        f'<div class="c-conclusion">当前判断：{mc(conclusion)}</div>'
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
            <div class="cx-sb-row"><span class="sb-dot"></span>委员会运行时就绪</div>
            <div class="cx-sb-row"><span class="sb-dot"></span>12 位 AI 委员已加载</div>
            <div class="cx-sb-row"><span class="sb-dot"></span>DAG 编排 · 断点续跑</div>
            <div class="cx-sb-k">版本</div>
            <div class="cx-sb-row">v1.0 · 12 Agents</div>
            """,
            unsafe_allow_html=True,
        )
