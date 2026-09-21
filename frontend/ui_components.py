# -*- coding: utf-8 -*-
"""创想∞ 前端展示组件（纯展示层 · 灵动 AI SaaS 风格）。

原则：
- 本文件只产出 HTML/CSS，不调用任何后端逻辑、不伪造任何数据；
- 所有动态文本必须经 esc() 转义；
- 红队五维 / 总指挥行动项等摘要均从真实报告原文解析，解析不到就不展示。
"""
import html as _html
import re

import streamlit as st

# ═══════════════════════════════════════════════════════════
# 品牌设计令牌（灵动 AI SaaS · 参考 Linear / Vercel / Stripe / Claude）
# ═══════════════════════════════════════════════════════════

PAGE_BG = "#F7F9FC"
CARD_BG = "#FFFFFF"
TEXT = "#172033"
MUTED = "#667085"
BORDER = "#E4E7EC"
BORDER_STRONG = "#D0D5DD"
SUBTLE_BG = "#F9FAFB"

BRAND = "#5B6CFF"
BRAND_2 = "#7C6CFF"          # 渐变副色
BRAND_LIGHT = "#EEF5FF"
TEAL = "#20BFA9"
TEAL_LIGHT = "#EAFBF7"
RED = "#F05A5A"
RED_LIGHT = "#FFF0F0"
PURPLE = "#7C6CFF"
PURPLE_LIGHT = "#F1EEFF"
ORANGE = "#F26B1D"
ORANGE_LIGHT = "#FFF6E8"
GRAY = "#98A2B3"

STATUS_META = {
    "done":     (TEAL, "已完成"),
    "running":  (BRAND, "分析中"),
    "pending":  (GRAY, "等待中"),
    "failed":   (RED, "校验未通过"),
    "blocked":  ("#D92D2D", "已阻断"),
    "degraded": (ORANGE, "降级完成"),
    "skipped":  (GRAY, "已跳过"),
}

COMMITTEE_META = {
    "expert":      (BRAND, BRAND_LIGHT, "专家委员会"),
    "adversarial": (RED,   RED_LIGHT,   "对抗委员会"),
    "decision":    (PURPLE, PURPLE_LIGHT, "决策委员会"),
}


def esc(text) -> str:
    return _html.escape(str(text if text is not None else ""))


def clean(text) -> str:
    s = str(text if text is not None else "")
    return s.replace("**", "").replace("__", "").strip()


def mc(text) -> str:
    return esc(clean(text))


# ═══════════════════════════════════════════════════════════
# CSS（灵动 · gradient mesh · 流动光效 · 入场动画 · 克制微交互）
# ═══════════════════════════════════════════════════════════

CSS = r"""
<style>
:root {
  --cx-brand: %BRAND%; --cx-brand2: %BRAND_2%; --cx-teal: %TEAL%; --cx-red: %RED%; --cx-purple: %PURPLE%;
  --cx-orange: %ORANGE%; --cx-gray: %GRAY%;
  --cx-text: %TEXT%; --cx-muted: %MUTED%; --cx-border: %BORDER%;
  --cx-card: %CARD_BG%; --cx-page: %PAGE_BG%; --cx-subtle: %SUBTLE_BG%;
  --cx-brand-l: %BRAND_LIGHT%; --cx-teal-l: %TEAL_LIGHT%; --cx-red-l: %RED_LIGHT%;
  --cx-purple-l: %PURPLE_LIGHT%; --cx-orange-l: %ORANGE_LIGHT%;
}

/* ════════════ 框架收敛 ════════════ */
.block-container { padding-top: 2rem; padding-bottom: 3rem; max-width: 1180px; position: relative; z-index: 1; }
header[data-testid="stHeader"] { background: transparent; }
#MainMenu, footer { visibility: hidden; }
.stApp {
  background: var(--cx-page);
  font-family: 'Inter', system-ui, -apple-system, sans-serif;
  position: relative; overflow-x: hidden;
}
.stApp, section, .stMarkdown { color: var(--cx-text); }

/* ════════════ 灵动 gradient mesh 背景（缓慢流动，不喧宾夺主） ════════════ */
.cx-bg-mesh {
  position: fixed; inset: 0; z-index: 0; pointer-events: none; overflow: hidden;
}
.cx-bg-mesh .orb {
  position: absolute; border-radius: 50%; filter: blur(60px); opacity: .35;
  animation: cx-float-orb 24s ease-in-out infinite;
}
.cx-bg-mesh .orb1 { width: 420px; height: 420px; top: -80px; left: -60px;
  background: radial-gradient(circle, rgba(91,108,255,.55), transparent 65%); }
.cx-bg-mesh .orb2 { width: 360px; height: 360px; top: -40px; right: -80px;
  background: radial-gradient(circle, rgba(124,108,255,.5), transparent 65%); animation-delay: -8s; }
.cx-bg-mesh .orb3 { width: 300px; height: 300px; top: 40%; left: 50%;
  background: radial-gradient(circle, rgba(32,191,169,.35), transparent 65%); animation-delay: -16s; }
@keyframes cx-float-orb {
  0%,100% { transform: translate(0,0) scale(1); }
  33% { transform: translate(30px, 40px) scale(1.08); }
  66% { transform: translate(-25px, 20px) scale(.95); }
}
/* 极淡网格纹理 */
.cx-bg-mesh .grid {
  position: absolute; inset: 0;
  background-image:
    linear-gradient(rgba(91,108,255,.04) 1px, transparent 1px),
    linear-gradient(90deg, rgba(91,108,255,.04) 1px, transparent 1px);
  background-size: 48px 48px;
  mask-image: radial-gradient(ellipse at center, black 30%, transparent 75%);
}

/* ════════════ 标题节奏 ════════════ */
h1, h2, h3 { letter-spacing: -.01em; font-weight: 700; }
hr { border-color: var(--cx-border); margin: 1.6rem 0; }

/* ════════════ 输入控件：白底圆角 + focus 渐变光晕 ════════════ */
.stTextInput input, .stTextArea textarea {
  background: var(--cx-card) !important; border: 1px solid var(--cx-border) !important;
  border-radius: 10px !important; color: var(--cx-text) !important;
  transition: border-color .18s ease, box-shadow .18s ease;
}
.stTextInput input:focus, .stTextArea textarea:focus {
  border-color: var(--cx-brand) !important;
  box-shadow: 0 0 0 3px rgba(91,108,255,.14), 0 4px 16px rgba(91,108,255,.08) !important;
}
.stTextArea textarea { min-height: 110px; }
.stTextArea textarea::placeholder, .stTextInput input::placeholder { color: var(--cx-muted); }

/* ════════════ 按钮：主按钮渐变 + hover 上浮光晕 ════════════ */
.stButton > button {
  border-radius: 10px; border: 1px solid var(--cx-border);
  background: var(--cx-card); color: var(--cx-text); font-weight: 600;
  padding: .5rem 1.1rem; font-size: 14px;
  transition: background .18s ease, border-color .18s ease, transform .18s ease, box-shadow .18s ease;
}
.stButton > button:hover {
  background: var(--cx-subtle); border-color: var(--cx-border-strong); transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(16,24,40,.06);
}
.stButton > button[kind="primary"], button[data-testid="baseButton-primary"] {
  background: linear-gradient(135deg, var(--cx-brand), var(--cx-brand2));
  border-color: transparent; color: #FFFFFF; font-weight: 700;
  background-size: 180% 180%; background-position: 0% 0%;
  transition: background-position .4s ease, transform .18s ease, box-shadow .18s ease;
}
.stButton > button[kind="primary"]:hover {
  background-position: 100% 100%; transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(91,108,255,.35), 0 0 0 3px rgba(91,108,255,.1);
}

/* ════════════ Tabs：渐变 active 底色 ════════════ */
.stTabs [data-baseweb="tab-list"] { gap: 4px; border-bottom: 1px solid var(--cx-border); background: transparent; }
.stTabs [data-baseweb="tab"] {
  border-radius: 8px; padding: 8px 14px; font-weight: 600; font-size: 14px;
  color: var(--cx-muted); background: transparent; border: 1px solid transparent;
  transition: background .18s ease, color .18s ease;
}
.stTabs [data-baseweb="tab"]:hover { background: var(--cx-subtle); color: var(--cx-text); }
.stTabs [aria-selected="true"] {
  color: var(--cx-brand); background: linear-gradient(135deg, var(--cx-brand-l), var(--cx-purple-l));
  border-color: rgba(91,108,255,.2);
}
.stTabs [data-baseweb="tab-highlight"] { background-color: transparent !important; height: 0 !important; }
.stTabs [data-baseweb="tab-border"] { background: transparent !important; }

/* ════════════ Expander 卡片化 ════════════ */
[data-testid="stExpander"] {
  background: var(--cx-card); border: 1px solid var(--cx-border); border-radius: 10px;
  padding: 2px 14px; margin-bottom: 8px;
  box-shadow: 0 1px 3px rgba(16,24,40,.04);
  transition: box-shadow .18s ease;
}
[data-testid="stExpander"]:hover { box-shadow: 0 4px 16px rgba(16,24,40,.06); }
[data-testid="stExpander"] summary { font-weight: 600; color: var(--cx-text); }
[data-testid="stAlert"] { border-radius: 10px; border: 1px solid var(--cx-border); }
.stContainer > div, [data-testid="stVerticalBlock"] { border-color: var(--cx-border) !important; }

/* ═══════════════════════════════════════════════════════════
   自定义组件
   ═══════════════════════════════════════════════════════════ */

/* ── Hero 区：渐变标题 + 浮动光球 + 入场动画 ── */
.cx-hero {
  text-align: center; padding: 2.4rem 0 1.4rem 0; position: relative;
  animation: cx-fade-up .6s ease both;
}
.cx-hero .eyebrow {
  color: var(--cx-brand); font-size: 11px; font-weight: 700;
  letter-spacing: 3px; margin-bottom: 14px; text-transform: uppercase;
  animation: cx-fade-up .6s ease .1s both;
}
.cx-hero h1 {
  font-size: 42px; font-weight: 800; margin: 0 0 12px 0; letter-spacing: -.02em;
  background: linear-gradient(120deg, var(--cx-brand) 0%, var(--cx-brand2) 40%, var(--cx-teal) 100%);
  background-size: 200% auto;
  -webkit-background-clip: text; background-clip: text;
  -webkit-text-fill-color: transparent; color: transparent;
  animation: cx-gradient-flow 6s ease infinite, cx-fade-up .6s ease .15s both;
}
.cx-hero .tagline {
  color: var(--cx-muted); font-size: 16px; margin: 0 auto; max-width: 560px; line-height: 1.6;
  animation: cx-fade-up .6s ease .25s both;
}
.cx-hero .meta-row {
  display: flex; justify-content: center; gap: 24px; margin-top: 18px;
  font-size: 13px; color: var(--cx-muted); font-weight: 600;
  animation: cx-fade-up .6s ease .35s both;
}
.cx-hero .meta-row span { display: inline-flex; align-items: center; gap: 6px; }
.cx-hero .meta-dot {
  width: 8px; height: 8px; border-radius: 50%;
  box-shadow: 0 0 8px currentColor; animation: cx-pulse-dot 2s ease-in-out infinite;
}

/* ── Section 标题 ── */
.cx-section { margin: 28px 0 12px 0; animation: cx-fade-up .5s ease both; }
.cx-section .eyebrow {
  color: var(--cx-brand); font-size: 11px; font-weight: 700; letter-spacing: 2px; text-transform: uppercase;
}
.cx-section h2 { font-size: 22px; font-weight: 700; margin: 4px 0 0 0; color: var(--cx-text); }

/* ── 委员会卡片：渐变边 + hover 光晕 + 图标脉冲 ── */
.cx-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
.cx-card {
  position: relative; background: var(--cx-card); border: 1px solid var(--cx-border); border-radius: 12px;
  padding: 20px; box-shadow: 0 1px 3px rgba(16,24,40,.04);
  transition: transform .22s ease, box-shadow .22s ease, border-color .22s ease;
  animation: cx-fade-up .5s ease both;
}
.cx-card::before {
  content: ''; position: absolute; inset: 0; border-radius: 12px; padding: 1px;
  background: linear-gradient(135deg, var(--c-accent, var(--cx-brand)), transparent 60%);
  -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
  -webkit-mask-composite: xor; mask-composite: exclude; opacity: 0;
  transition: opacity .22s ease; pointer-events: none;
}
.cx-card:hover { transform: translateY(-3px); box-shadow: 0 12px 32px rgba(16,24,40,.1), 0 0 24px var(--c-glow, rgba(91,108,255,.12)); border-color: transparent; }
.cx-card:hover::before { opacity: 1; }
.cx-card .c-head { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.cx-card .c-dot {
  width: 12px; height: 12px; border-radius: 50%; flex: 0 0 auto;
  box-shadow: 0 0 10px currentColor; animation: cx-pulse-dot 2.4s ease-in-out infinite;
}
.cx-card .c-badge {
  margin-left: auto; font-size: 11px; font-weight: 700; padding: 3px 10px; border-radius: 999px;
}
.cx-card h3 { font-size: 17px; margin: 0; color: var(--cx-text); font-weight: 700; }
.cx-card .c-sub { font-size: 13px; color: var(--cx-muted); margin: 2px 0 12px 0; }
.cx-card ul { margin: 6px 0 0 0; padding-left: 0; list-style: none; }
.cx-card li { font-size: 13.5px; color: var(--cx-text); padding: 3px 0; line-height: 1.5; opacity: .85; }
.cx-card:nth-child(1) { animation-delay: .05s; }
.cx-card:nth-child(2) { animation-delay: .12s; }
.cx-card:nth-child(3) { animation-delay: .19s; }

/* ── DAG 审议路径：流动连线 + 脉冲光环 ── */
.cx-dag {
  display: flex; align-items: stretch; gap: 0; margin: 10px 0 6px 0;
  background: var(--cx-card); border: 1px solid var(--cx-border); border-radius: 12px;
  padding: 18px 12px; box-shadow: 0 1px 3px rgba(16,24,40,.04);
  animation: cx-fade-up .5s ease .15s both;
}
.cx-dag-node { flex: 1 1 0; text-align: center; padding: 6px 8px; position: relative; }
.cx-dag-node .n-dot {
  width: 32px; height: 32px; border-radius: 50%; margin: 0 auto 8px auto;
  display: flex; align-items: center; justify-content: center;
  background: var(--cx-subtle); border: 2px solid var(--cx-border);
  transition: all .22s ease; position: relative;
}
.cx-dag-node .n-dot .n-icon { font-size: 13px; font-weight: 800; color: var(--cx-muted); }
.cx-dag-node .n-name { font-size: 14px; font-weight: 700; color: var(--cx-text); }
.cx-dag-node .n-sub { font-size: 11px; color: var(--cx-muted); margin-top: 2px; }
.cx-dag-node.done .n-dot { background: var(--cx-teal-l); border-color: var(--cx-teal); box-shadow: 0 0 12px rgba(32,191,169,.3); }
.cx-dag-node.done .n-dot .n-icon { color: var(--cx-teal); }
.cx-dag-node.active .n-dot {
  background: linear-gradient(135deg, var(--cx-brand-l), var(--cx-purple-l));
  border-color: var(--cx-brand);
  box-shadow: 0 0 0 4px rgba(91,108,255,.12), 0 0 20px rgba(91,108,255,.25);
  animation: cx-pulse-ring 1.8s ease-in-out infinite;
}
.cx-dag-node.active .n-dot .n-icon { color: var(--cx-brand); }
.cx-dag-arrow {
  display: flex; align-items: center; color: var(--cx-border-strong); font-size: 16px; padding: 0 4px;
  margin-top: -22px; position: relative;
}
.cx-dag-arrow::after {
  content: ''; position: absolute; left: 0; right: 0; top: 50%; height: 2px;
  background: linear-gradient(90deg, transparent, var(--cx-brand), transparent);
  background-size: 200% 100%; animation: cx-flow 2.5s linear infinite; opacity: .5;
}

/* ── Agent 成员名片：扫光 + 涟漪 + 渐变状态条 ── */
.cx-agent-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 10px; }
.cx-agent {
  position: relative; overflow: hidden;
  background: var(--cx-card); border: 1px solid var(--cx-border); border-radius: 10px;
  padding: 14px 16px;
  transition: transform .2s ease, box-shadow .2s ease, border-color .2s ease;
  animation: cx-fade-up .4s ease both;
}
.cx-agent::before {
  content: ''; position: absolute; top: 0; left: -100%; width: 60%; height: 100%;
  background: linear-gradient(90deg, transparent, rgba(91,108,255,.08), transparent);
  transition: left .6s ease; pointer-events: none;
}
.cx-agent:hover::before { left: 120%; }
.cx-agent:hover { transform: translateY(-2px); box-shadow: 0 6px 20px rgba(16,24,40,.08); }
.cx-agent .a-head { display: flex; align-items: center; gap: 8px; font-weight: 700; font-size: 14.5px; color: var(--cx-text); }
.cx-agent .a-group { font-size: 11px; color: var(--cx-muted); letter-spacing: .5px; margin: 3px 0 0 20px; }
.cx-agent .a-state { font-size: 12.5px; color: var(--cx-muted); margin: 6px 0 0 20px; line-height: 1.5; }
.cx-dot {
  width: 10px; height: 10px; border-radius: 50%; background: var(--cx-gray);
  display: inline-block; flex: 0 0 auto; position: relative;
}
.cx-dot.done { background: var(--cx-teal); box-shadow: 0 0 8px var(--cx-teal); }
.cx-dot.running { background: var(--cx-brand); box-shadow: 0 0 8px var(--cx-brand); }
.cx-dot.running::after {
  content: ''; position: absolute; inset: -4px; border-radius: 50%; border: 2px solid var(--cx-brand);
  animation: cx-ripple 1.4s ease-out infinite;
}
.cx-dot.failed, .cx-dot.blocked { background: var(--cx-red); box-shadow: 0 0 8px var(--cx-red); }
.cx-dot.degraded { background: var(--cx-orange); box-shadow: 0 0 8px var(--cx-orange); }
.cx-dot.skipped { background: var(--cx-gray); }
.cx-agent.done { border-left: 3px solid var(--cx-teal); }
.cx-agent.running { border-left: 3px solid var(--cx-brand); }
.cx-agent.failed { border-left: 3px solid var(--cx-red); }
.cx-agent.blocked { border-left: 3px solid #D92D2D; }
.cx-agent.degraded { border-left: 3px solid var(--cx-orange); }
.cx-agent.skipped { border-left: 3px solid var(--cx-gray); opacity: .7; }

/* ── 终审横幅：渐变背景 mesh + Badge 光晕 + 标题渐变 ── */
.cx-verdict {
  position: relative; overflow: hidden;
  background: var(--cx-card); border: 1px solid var(--cx-border); border-left: 5px solid var(--cx-red);
  border-radius: 12px; padding: 24px 28px; margin: 8px 0 18px 0;
  box-shadow: 0 1px 3px rgba(16,24,40,.05);
  animation: cx-fade-up .5s ease both;
}
.cx-verdict::after {
  content: ''; position: absolute; top: -60px; right: -60px; width: 240px; height: 240px;
  background: radial-gradient(circle, rgba(240,90,90,.1), transparent 70%); pointer-events: none;
}
.cx-verdict.safe { border-left-color: var(--cx-teal); }
.cx-verdict.safe::after { background: radial-gradient(circle, rgba(32,191,169,.12), transparent 70%); }
.cx-verdict .eyebrow { color: var(--cx-muted); font-size: 11px; letter-spacing: 2px; font-weight: 700; text-transform: uppercase; }
.cx-verdict .v-main {
  font-size: 30px; font-weight: 800; margin: 6px 0 16px 0; letter-spacing: -.01em;
  background: linear-gradient(120deg, var(--cx-red), var(--cx-orange));
  -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent;
}
.cx-verdict.safe .v-main { background: linear-gradient(120deg, var(--cx-brand), var(--cx-teal)); -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; }
.cx-verdict .v-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; padding-top: 14px; border-top: 1px solid var(--cx-border); position: relative; }
.cx-verdict .v-item .v-k { font-size: 12px; color: var(--cx-muted); font-weight: 600; }
.cx-verdict .v-item .v-v { font-size: 16px; font-weight: 700; margin-top: 4px; color: var(--cx-text); }
.cx-verdict .v-badge {
  display: inline-flex; align-items: center; gap: 4px; font-size: 12px; font-weight: 700;
  padding: 3px 10px; border-radius: 999px; margin-top: 4px;
  animation: cx-badge-glow 2.5s ease-in-out infinite;
}
.cx-verdict .v-badge.red { background: var(--cx-red-l); color: var(--cx-red); box-shadow: 0 0 12px rgba(240,90,90,.25); }
.cx-verdict .v-badge.teal { background: var(--cx-teal-l); color: var(--cx-teal); box-shadow: 0 0 12px rgba(32,191,169,.25); }
.cx-verdict .v-forced-note { font-size: 12px; color: var(--cx-orange); margin-top: 6px; }

/* ── 冲突链：渐变编号 + hover 提升 ── */
.cx-chain { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.cx-chain .step {
  background: var(--cx-subtle); border: 1px solid var(--cx-border); border-radius: 10px;
  padding: 16px 18px; position: relative; overflow: hidden;
  transition: transform .2s ease, box-shadow .2s ease, border-color .2s ease;
  animation: cx-fade-up .45s ease both;
}
.cx-chain .step::before {
  content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px;
  background: linear-gradient(90deg, var(--c-step, var(--cx-brand)), transparent);
  opacity: .6;
}
.cx-chain .step:hover { transform: translateY(-2px); box-shadow: 0 8px 24px rgba(16,24,40,.08); border-color: var(--c-step, var(--cx-brand)); }
.cx-chain .step .s-no {
  font-size: 14px; font-weight: 800; letter-spacing: 1px; margin-bottom: 6px;
  background: linear-gradient(120deg, var(--c-step, var(--cx-brand)), var(--cx-brand2));
  -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent;
}
.cx-chain .step .s-k { font-size: 12px; color: var(--cx-muted); font-weight: 600; letter-spacing: .5px; }
.cx-chain .step .s-v { font-size: 13.5px; color: var(--cx-text); margin-top: 8px; line-height: 1.6; }
.cx-chain .step .s-vs {
  display: inline-block; font-size: 11px; font-weight: 700; color: var(--cx-muted);
  background: var(--cx-card); padding: 2px 8px; border-radius: 4px; margin: 6px 0; border: 1px solid var(--cx-border);
}
.cx-chain .step.redteam { --c-step: var(--cx-red); }
.cx-chain .step.risk { --c-step: var(--cx-red); }
.cx-chain .step.review { --c-step: var(--cx-purple); }
.cx-chain .step:nth-child(1) { animation-delay: .05s; }
.cx-chain .step:nth-child(2) { animation-delay: .12s; }
.cx-chain .step:nth-child(3) { animation-delay: .19s; }
.cx-chain .step:nth-child(4) { animation-delay: .26s; }

/* ── 红队 / 总指挥 callout：渐变左色条 + 背景装饰 ── */
.cx-callout {
  position: relative; overflow: hidden;
  background: var(--cx-card); border: 1px solid var(--cx-border); border-left: 4px solid var(--cx-red);
  border-radius: 12px; padding: 18px 22px; margin-bottom: 14px;
  box-shadow: 0 1px 3px rgba(16,24,40,.04);
  animation: cx-fade-up .5s ease both;
}
.cx-callout::after {
  content: ''; position: absolute; top: -40px; right: -40px; width: 180px; height: 180px;
  background: radial-gradient(circle, rgba(240,90,90,.08), transparent 70%); pointer-events: none;
}
.cx-callout .c-title { font-weight: 800; color: var(--cx-red); font-size: 16px; margin-bottom: 6px; }
.cx-callout .c-body { color: var(--cx-muted); font-size: 14px; line-height: 1.7; position: relative; }
.cx-callout.commander { border-left: 4px solid var(--cx-purple); position: relative; }
.cx-callout.commander::before {
  content: ''; position: absolute; top: 0; left: 0; bottom: 0; width: 4px;
  background: linear-gradient(180deg, var(--cx-purple), var(--cx-brand));
  border-radius: 2px 0 0 2px;
}
.cx-callout.commander::after { background: radial-gradient(circle, rgba(124,108,255,.1), transparent 70%); }
.cx-callout.commander .c-title { color: var(--cx-purple); }
.cx-callout .c-conclusion { font-size: 14px; color: var(--cx-purple); margin: 8px 0 4px 0; font-weight: 600; }

/* ── 五维 chips：渐变底 + 光晕 ── */
.cx-chips { display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0 4px 0; }
.cx-chip {
  font-size: 13px; font-weight: 600; border-radius: 999px; padding: 5px 14px;
  border: 1px solid var(--cx-border); background: var(--cx-subtle); color: var(--cx-text);
  transition: transform .18s ease, box-shadow .18s ease;
}
.cx-chip:hover { transform: translateY(-1px); }
.cx-chip.fatal { border-color: rgba(240,90,90,.35); color: var(--cx-red); background: linear-gradient(135deg, var(--cx-red-l), #FFE8E8); box-shadow: 0 0 10px rgba(240,90,90,.15); }
.cx-chip.high { border-color: rgba(242,107,29,.35); color: var(--cx-orange); background: linear-gradient(135deg, var(--cx-orange-l), #FFEFDA); box-shadow: 0 0 10px rgba(242,107,29,.15); }

/* ── 总指挥行动卡：渐变编号 + hover 提升 ── */
.cx-actions { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin: 12px 0; }
.cx-action {
  position: relative; overflow: hidden;
  background: var(--cx-card); border: 1px solid var(--cx-border); border-radius: 10px; padding: 14px 16px;
  transition: transform .2s ease, box-shadow .2s ease;
  animation: cx-fade-up .45s ease both;
}
.cx-action::before {
  content: ''; position: absolute; top: 0; left: 0; bottom: 0; width: 3px;
  background: linear-gradient(180deg, var(--cx-purple), var(--cx-brand));
}
.cx-action:hover { transform: translateY(-2px); box-shadow: 0 8px 24px rgba(16,24,40,.08); }
.cx-action .a-no {
  font-size: 15px; font-weight: 800; letter-spacing: 1px;
  background: linear-gradient(120deg, var(--cx-purple), var(--cx-brand));
  -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent;
}
.cx-action .a-label { font-size: 11px; color: var(--cx-muted); font-weight: 600; text-transform: uppercase; letter-spacing: .5px; margin-top: 2px; }
.cx-action .a-t { font-size: 13.5px; color: var(--cx-text); line-height: 1.65; margin-top: 8px; }
.cx-action:nth-child(1) { animation-delay: .1s; }
.cx-action:nth-child(2) { animation-delay: .18s; }
.cx-action:nth-child(3) { animation-delay: .26s; }

/* ── Sidebar 品牌化 ── */
.cx-sidebar-brand { padding: 4px 4px 12px 4px; border-bottom: 1px solid var(--cx-border); margin-bottom: 12px; }
.cx-sidebar-brand .t1 {
  font-size: 20px; font-weight: 800;
  background: linear-gradient(120deg, var(--cx-brand), var(--cx-brand2));
  -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent;
}
.cx-sidebar-brand .t2 { font-size: 12px; color: var(--cx-muted); letter-spacing: .5px; margin-top: 2px; }
.cx-sb-k { font-size: 11px; color: var(--cx-muted); font-weight: 700; letter-spacing: 1px; margin: 14px 0 6px 0; text-transform: uppercase; }
.cx-sb-row { font-size: 13px; color: var(--cx-text); padding: 2px 0; display: flex; align-items: center; gap: 6px; }
.cx-sb-row .sb-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--cx-teal); flex: 0 0 auto; box-shadow: 0 0 6px var(--cx-teal); animation: cx-pulse-dot 2.4s ease-in-out infinite; }

/* ════════════ 关键帧 ════════════ */
@keyframes cx-fade-up { from { opacity: 0; transform: translateY(14px); } to { opacity: 1; transform: translateY(0); } }
@keyframes cx-gradient-flow { 0%,100% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } }
@keyframes cx-pulse-dot { 0%,100% { opacity: 1; transform: scale(1); } 50% { opacity: .5; transform: scale(.85); } }
@keyframes cx-pulse-ring { 0%,100% { box-shadow: 0 0 0 4px rgba(91,108,255,.12), 0 0 20px rgba(91,108,255,.25); } 50% { box-shadow: 0 0 0 8px rgba(91,108,255,.06), 0 0 30px rgba(91,108,255,.35); } }
@keyframes cx-ripple { 0% { transform: scale(1); opacity: .6; } 100% { transform: scale(1.8); opacity: 0; } }
@keyframes cx-flow { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
@keyframes cx-badge-glow { 0%,100% { box-shadow: 0 0 12px rgba(240,90,90,.25); } 50% { box-shadow: 0 0 20px rgba(240,90,90,.4); } }

@media (max-width: 1100px) {
  .cx-grid { grid-template-columns: 1fr; }
  .cx-chain, .cx-verdict .v-grid, .cx-actions { grid-template-columns: 1fr; }
  .cx-dag { flex-direction: column; gap: 4px; }
  .cx-dag-arrow { display: none; }
}
</style>
<div class="cx-bg-mesh">
  <div class="grid"></div>
  <div class="orb orb1"></div>
  <div class="orb orb2"></div>
  <div class="orb orb3"></div>
</div>
""".replace("%BRAND%", BRAND).replace("%BRAND_2%", BRAND_2).replace("%TEAL%", TEAL) \
   .replace("%RED%", RED).replace("%PURPLE%", PURPLE).replace("%ORANGE%", ORANGE).replace("%GRAY%", GRAY) \
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
    """三大委员会卡片。白底 + 渐变边 hover + 图标脉冲。内容为静态组织事实。"""
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
            f'<div class="cx-card" style="--c-accent:{color};--c-glow:{color}22;">'
            f'<div class="c-head">'
            f'<span class="c-dot" style="background:{color};color:{color}"></span>'
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
    """五节点 DAG 审议路径。流动连线 + 脉冲光环。"""
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
    """真实状态计数：专家 0-7 / 对抗 8 / 决策 9-11。"""
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
    """12 Agent 成员名片墙。扫光 + 涟漪 + 渐变状态条。"""
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
            f"""<div class="cx-agent {state}" style="animation-delay:{idx * .04}s">
              <div class="a-head"><span class="cx-dot {state}"></span>{mc(si['label'])}</div>
              <div class="a-group">{esc(group_cn.get(si.get('group'), ''))}</div>
              <div class="a-state">{mc(detail)}</div>
            </div>"""
        )
    st.markdown(f'<div class="cx-agent-grid">{"".join(cards)}</div>', unsafe_allow_html=True)


def verdict_banner(stage_text: str, redline: bool, redline_forced: bool, pitch_text: str,
                   review_conclusion: str):
    """终审横幅。渐变背景 mesh + Badge 光晕 + 标题渐变。"""
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
    """冲突链证据卡。渐变编号 + hover 提升。"""
    risk_body = mc("；".join(risk_items[:2])[:90]) if risk_items else mc((risk_summary or "无致命风险")[:90])
    st.markdown(
        f"""
        <div class="cx-chain">
          <div class="step expert" style="--c-step:var(--cx-brand)">
            <div class="s-no">01</div>
            <div class="s-k">风险审查 · 专家意见</div>
            <div class="s-v">{risk_body or '无致命风险'}</div>
          </div>
          <div class="step redteam" style="--c-step:var(--cx-red)">
            <div class="s-no">02</div>
            <div class="s-k">红队质疑 · 致命假设</div>
            <div class="s-v">{mc((redteam_summary or '')[:90])}</div>
          </div>
          <div class="step risk" style="--c-step:var(--cx-red)">
            <div class="s-no">03</div>
            <div class="s-k">分歧进入终审</div>
            <div class="s-v">风险与红队结论不一致时，矛盾不被抹平，全部留痕带进终审。</div>
          </div>
          <div class="step review" style="--c-step:var(--cx-purple)">
            <div class="s-no">04</div>
            <div class="s-k">项目评审 · 终审裁决</div>
            <div class="s-v">{mc((review_text or '')[:90])}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ── 真实报告解析 ──

def parse_redteam_findings(raw: str):
    """解析『①【需求假设｜致命】』式五维标题。"""
    out = []
    for m in re.finditer(r"[①②③④⑤]\s*[【\[]\s*([^】\]｜|]+)\s*(?:[｜|]\s*([^】\]]+?))?\s*[】\]]", raw or ""):
        dim = m.group(1).strip()
        sev = (m.group(2) or "").strip()
        if dim:
            out.append((dim, sev))
    return out[:5]


def redteam_block(raw: str):
    """红队 callout：渐变左色条 + 五维 chips。"""
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
