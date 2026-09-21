# -*- coding: utf-8 -*-
"""Design Token —— 创想∞ AI创业委员会 · 统一设计令牌 + 全局样式

职责边界（重要）：
- 本模块是**纯展示层**：只做「常量定义 + 字符串拼装」；
- import 期不读文件、不连数据库、不起线程、不调 LLM、不访问网络；
- 所有组件只允许引用此处 Token，不得在组件里散写十六进制颜色值。

视觉方向：温暖浅色 AI SaaS（Notion / Linear / Vercel 气质）
- 暖白背景 + 白色卡片 + 1px 浅边框（不靠厚重阴影分层）
- 主品牌蓝紫稀缺使用；委员会语义色：专家蓝 / 红队红 / 决策紫
"""

# ═══════════════════════════════════════════════════════════
# 一、颜色 Token
# ═══════════════════════════════════════════════════════════

# ── 底层背景与卡片 ──
BACKGROUND = "#F7F8FA"        # 页面背景（极浅暖灰，让白卡浮出来）
SURFACE = "#FFFFFF"           # 主卡片
SURFACE_SOFT = "#FCFCFB"      # 子卡片 / 内嵌区块

# ── 边框 ──
BORDER = "#E9E7E3"            # 全站默认 1px 边框
BORDER_SOFT = "#F0EEEA"       # 更弱的分隔
BORDER_STRONG = "#D9DCE5"     # 连接线 / 强分隔

# ── 文字 ──
FOREGROUND = "#1A1A2E"        # 主文字
MUTED = "#6B7280"             # 次要文字
MUTED_SOFT = "#9CA3AF"        # 辅助文字 / 占位

# ── 品牌主色（蓝紫 · 稀缺使用） ──
PRIMARY = "#5B63E8"
PRIMARY_HOVER = "#4B53DD"
PRIMARY_SOFT = "#EEF0FF"      # 激活底色 / 浅主色背景
PRIMARY_BORDER = "#C9CDF9"
PRIMARY_TEXT = "#4B4FD8"      # 主色文字（保证对比度）

# ── 委员会语义色：专家（蓝） ──
EXPERT = "#4F7DFF"
EXPERT_SOFT = "#EEF3FF"
EXPERT_BORDER = "#C6D6FB"
EXPERT_TEXT = "#3D6AE0"

# ── 委员会语义色：对抗 / 红队（红） ──
REDTEAM = "#E85B5B"
REDTEAM_SOFT = "#FDECEC"
REDTEAM_BORDER = "#F5C4C4"
REDTEAM_TEXT = "#CE4646"

# ── 委员会语义色：决策（紫） ──
DECISION = "#7A65D8"
DECISION_SOFT = "#F2EEFB"
DECISION_BORDER = "#D8CDF3"
DECISION_TEXT = "#6852C5"

# ── 状态语义色 ──
SUCCESS = "#16A34A"
SUCCESS_SOFT = "#EAFBEF"
SUCCESS_BORDER = "#BBE5C5"
SUCCESS_TEXT = "#15803D"

WARNING = "#E8870D"
WARNING_SOFT = "#FEF5E7"
WARNING_BORDER = "#F5D9A8"
WARNING_TEXT = "#A96A08"

DANGER = "#DC2626"
DANGER_SOFT = "#FDECEC"
DANGER_BORDER = "#F4B8B8"
DANGER_TEXT = "#B91C1C"

INFO = "#4F7DFF"
INFO_SOFT = "#EEF3FF"
INFO_BORDER = "#C6D6FB"
INFO_TEXT = "#3D6AE0"

NEUTRAL = "#6B7280"
NEUTRAL_SOFT = "#F3F4F6"
NEUTRAL_BORDER = "#D9DCE5"
NEUTRAL_TEXT = "#4B5563"

# ═══════════════════════════════════════════════════════════
# 二、Agent 状态 → UI 三件套（浅色背景 + 20% 透明边框 + 深色文字）
#     所有 Agent 状态只能走这张表，禁止在页面里散写状态 CSS。
# ═══════════════════════════════════════════════════════════
STATUS_UI = {
    "pending":  {"icon": "○", "label": "等待",   "bg": NEUTRAL_SOFT, "border": NEUTRAL_BORDER, "text": NEUTRAL_TEXT, "dot": MUTED_SOFT},
    "running":  {"icon": "●", "label": "分析中", "bg": PRIMARY_SOFT, "border": PRIMARY_BORDER, "text": PRIMARY_TEXT, "dot": PRIMARY},
    "success":  {"icon": "✓", "label": "已完成", "bg": SUCCESS_SOFT, "border": SUCCESS_BORDER, "text": SUCCESS_TEXT, "dot": SUCCESS},
    "failed":   {"icon": "!", "label": "异常",   "bg": DANGER_SOFT,  "border": DANGER_BORDER,  "text": DANGER_TEXT,  "dot": DANGER},
    "blocked":  {"icon": "⊘", "label": "阻断",   "bg": DANGER_SOFT,  "border": DANGER_BORDER,  "text": DANGER_TEXT,  "dot": DANGER},
    "degraded": {"icon": "△", "label": "降级",   "bg": WARNING_SOFT, "border": WARNING_BORDER, "text": WARNING_TEXT, "dot": WARNING},
    "skipped":  {"icon": "▽", "label": "跳过",   "bg": NEUTRAL_SOFT, "border": NEUTRAL_BORDER, "text": "#6B5790",    "dot": "#9C8BB8"},
}

# 委员会语义色表（按 registry 的 group 名索引）
COMMITTEE_UI = {
    "专家委员会": {"key": "expert",      "soft": EXPERT_SOFT,   "border": EXPERT_BORDER,   "text": EXPERT_TEXT,   "solid": EXPERT,   "short": "专家组", "mark": "◆"},
    "对抗委员会": {"key": "adversarial", "soft": REDTEAM_SOFT,  "border": REDTEAM_BORDER,  "text": REDTEAM_TEXT,  "solid": REDTEAM,  "short": "红队",   "mark": "▲"},
    "决策委员会": {"key": "decision",    "soft": DECISION_SOFT, "border": DECISION_BORDER, "text": DECISION_TEXT, "solid": DECISION, "short": "决策组", "mark": "●"},
}

# 问题等级 → 语义色（红队 / 风险报告的 致命・高・中・低）
LEVEL_UI = {
    "致命": {"bg": DANGER_SOFT,  "border": DANGER_BORDER,  "text": DANGER_TEXT},
    "高":   {"bg": WARNING_SOFT, "border": WARNING_BORDER, "text": WARNING_TEXT},
    "中":   {"bg": INFO_SOFT,    "border": INFO_BORDER,    "text": INFO_TEXT},
    "低":   {"bg": NEUTRAL_SOFT, "border": NEUTRAL_BORDER, "text": NEUTRAL_TEXT},
    "一般": {"bg": NEUTRAL_SOFT, "border": NEUTRAL_BORDER, "text": NEUTRAL_TEXT},
}

# ═══════════════════════════════════════════════════════════
# 三、圆角（只允许三档）
# ═══════════════════════════════════════════════════════════
RADIUS_SM = "6px"     # 输入框 / Badge / 小按钮
RADIUS_MD = "10px"    # 普通 Card / Agent Card
RADIUS_LG = "14px"    # 大型区块 / Hero / 主容器

# ═══════════════════════════════════════════════════════════
# 四、阴影（只保留两级，不用黑色重阴影 / 发光）
# ═══════════════════════════════════════════════════════════
SHADOW_DEFAULT = "0 1px 2px rgba(16,24,40,.04)"
SHADOW_HOVER = "0 8px 24px rgba(16,24,40,.07)"

# ═══════════════════════════════════════════════════════════
# 五、间距 / 字号 / 字重
# ═══════════════════════════════════════════════════════════
SPACE_XS = "4px"
SPACE_SM = "8px"
SPACE_MD = "12px"
SPACE_LG = "16px"
SPACE_XL = "24px"
SPACE_2XL = "32px"

FS_HERO = "34px"      # Hero 主标题
FS_H1 = "24px"        # 页面标题
FS_H2 = "18px"        # 区块标题
FS_TITLE = "14px"     # 卡片标题
FS_BODY = "13px"      # 正文
FS_SMALL = "12px"     # 辅助 / helper
FS_MICRO = "11px"     # Badge / eyebrow

FW_BOLD = "700"
FW_SEMIBOLD = "600"
FW_NORMAL = "400"

FONT_FAMILY = (
    'Inter, -apple-system, BlinkMacSystemFont, '
    '"Segoe UI", "Microsoft YaHei", "PingFang SC", sans-serif'
)


# ═══════════════════════════════════════════════════════════
# 六、CSS 变量 + 全局样式
# ═══════════════════════════════════════════════════════════

CSS_VARS = {
    "cx-bg": BACKGROUND,
    "cx-surface": SURFACE,
    "cx-surface-soft": SURFACE_SOFT,
    "cx-border": BORDER,
    "cx-border-soft": BORDER_SOFT,
    "cx-border-strong": BORDER_STRONG,
    "cx-fg": FOREGROUND,
    "cx-muted": MUTED,
    "cx-muted-soft": MUTED_SOFT,
    "cx-primary": PRIMARY,
    "cx-primary-hover": PRIMARY_HOVER,
    "cx-primary-soft": PRIMARY_SOFT,
    "cx-primary-border": PRIMARY_BORDER,
    "cx-primary-text": PRIMARY_TEXT,
    "cx-expert": EXPERT,
    "cx-expert-soft": EXPERT_SOFT,
    "cx-expert-border": EXPERT_BORDER,
    "cx-expert-text": EXPERT_TEXT,
    "cx-red": REDTEAM,
    "cx-red-soft": REDTEAM_SOFT,
    "cx-red-border": REDTEAM_BORDER,
    "cx-red-text": REDTEAM_TEXT,
    "cx-purple": DECISION,
    "cx-purple-soft": DECISION_SOFT,
    "cx-purple-border": DECISION_BORDER,
    "cx-purple-text": DECISION_TEXT,
    "cx-success": SUCCESS,
    "cx-success-soft": SUCCESS_SOFT,
    "cx-success-border": SUCCESS_BORDER,
    "cx-warning": WARNING,
    "cx-warning-soft": WARNING_SOFT,
    "cx-warning-border": WARNING_BORDER,
    "cx-danger": DANGER,
    "cx-danger-soft": DANGER_SOFT,
    "cx-danger-border": DANGER_BORDER,
    "cx-neutral-soft": NEUTRAL_SOFT,
    "cx-neutral-border": NEUTRAL_BORDER,
    "cx-radius-sm": RADIUS_SM,
    "cx-radius-md": RADIUS_MD,
    "cx-radius-lg": RADIUS_LG,
    "cx-shadow": SHADOW_DEFAULT,
    "cx-shadow-hover": SHADOW_HOVER,
    "cx-font": FONT_FAMILY,
}

# 全局样式：只使用 .cx-* 自有类；Streamlit 自身的覆盖集中在最后一节，
# 且全部是**单层选择器**（不写 `[data-testid] div div div` 这类深层覆盖）。
_CSS_BODY = """
/* ── 基础排版 ───────────────────────────────────── */
html, body, [class*="css"] { font-family: var(--cx-font); }
.cx-root, .cx-root * { box-sizing: border-box; }
.cx-root {
  font-family: var(--cx-font);
  color: var(--cx-fg);
  font-size: 13px;
  line-height: 1.62;
}

/* ── 滚动条（精致感的组成部分） ─────────────────── */
html ::-webkit-scrollbar, body ::-webkit-scrollbar { width: 6px; height: 6px; }
html ::-webkit-scrollbar-track, body ::-webkit-scrollbar-track { background: var(--cx-bg); }
html ::-webkit-scrollbar-thumb, body ::-webkit-scrollbar-thumb {
  background: #D8DAE3; border-radius: 3px;
}
html ::-webkit-scrollbar-thumb:hover, body ::-webkit-scrollbar-thumb:hover { background: var(--cx-primary); }

/* ── Sidebar 品牌区与导航 ───────────────────────── */
.cx-brand { display: flex; align-items: center; gap: 10px; padding: 2px 2px 14px 2px; }
.cx-brand-mark {
  width: 30px; height: 30px; border-radius: var(--cx-radius-sm);
  background: var(--cx-primary-soft); color: var(--cx-primary);
  display: flex; align-items: center; justify-content: center;
  font-size: 17px; font-weight: 700; line-height: 1;
}
.cx-brand-name { font-size: 14px; font-weight: 700; letter-spacing: .2px; }
.cx-brand-sub { font-size: 11px; color: var(--cx-muted); }
.cx-side-rule { height: 1px; background: var(--cx-border); margin: 2px 0 12px 0; }
.cx-side-label {
  font-size: 10.5px; letter-spacing: .12em; color: var(--cx-muted-soft);
  text-transform: uppercase; margin: 14px 0 6px 2px;
}
.cx-side-foot { font-size: 11px; color: var(--cx-muted-soft); line-height: 1.7; }

/* ── Header（极简：页面名 + 一个真实状态） ──────── */
.cx-header {
  display: flex; align-items: center; justify-content: space-between;
  gap: 16px; padding: 4px 0 14px 0; border-bottom: 1px solid var(--cx-border);
  margin-bottom: 22px;
}
.cx-header-title { font-size: 15px; font-weight: 700; letter-spacing: .2px; }
.cx-header-sub { font-size: 11.5px; color: var(--cx-muted); font-weight: 400; margin-top: 1px; }
.cx-header-status {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 11.5px; padding: 4px 10px; border-radius: 999px;
  border: 1px solid var(--cx-neutral-border); background: var(--cx-surface);
  color: var(--cx-muted); white-space: nowrap;
}
.cx-header-status .cx-dot { width: 6px; height: 6px; border-radius: 50%; }

/* ── Hero ───────────────────────────────────────── */
.cx-hero {
  position: relative; overflow: hidden;
  background: var(--cx-surface);
  border: 1px solid var(--cx-border);
  border-radius: var(--cx-radius-lg);
  box-shadow: var(--cx-shadow);
  padding: 30px 32px 26px 32px;
}
.cx-hero::after {
  content: ""; position: absolute; right: -90px; top: -110px;
  width: 260px; height: 260px; border-radius: 50%;
  background: radial-gradient(circle at center, rgba(91,99,232,.09), rgba(91,99,232,0) 68%);
}
.cx-hero::before {
  content: ""; position: absolute; right: 60px; bottom: -120px;
  width: 200px; height: 200px; border-radius: 50%;
  background: radial-gradient(circle at center, rgba(122,101,216,.07), rgba(122,101,216,0) 70%);
}
.cx-eyebrow {
  font-size: 10.5px; letter-spacing: .16em; text-transform: uppercase;
  color: var(--cx-primary); font-weight: 700; margin-bottom: 10px;
}
.cx-hero-title { font-size: var(--cx-fs-hero, 34px); font-weight: 700; letter-spacing: -.4px; line-height: 1.24; }
.cx-hero-sub { font-size: 15px; color: #40465A; margin-top: 10px; line-height: 1.7; max-width: 620px; }
.cx-hero-meta {
  display: flex; flex-wrap: wrap; gap: 18px; margin-top: 16px;
  font-size: 11.5px; color: var(--cx-muted);
}
.cx-hero-meta b { color: var(--cx-fg); font-weight: 600; }

/* ── 区块标题 ───────────────────────────────────── */
.cx-section { margin: 30px 0 14px 0; }
.cx-section-eyebrow {
  font-size: 10.5px; letter-spacing: .14em; text-transform: uppercase;
  color: var(--cx-muted-soft); font-weight: 600; margin-bottom: 5px;
}
.cx-section-title { font-size: 18px; font-weight: 700; letter-spacing: -.1px; }
.cx-section-sub { font-size: 12.5px; color: var(--cx-muted); margin-top: 5px; line-height: 1.65; }

/* ── 卡片 ───────────────────────────────────────── */
.cx-card {
  background: var(--cx-surface); border: 1px solid var(--cx-border);
  border-radius: var(--cx-radius-md); box-shadow: var(--cx-shadow);
  padding: 16px 18px; transition: all .18s ease;
}
.cx-card:hover { transform: translateY(-1px); box-shadow: var(--cx-shadow-hover); border-color: #DEDCD7; }
.cx-card-pad-lg { padding: 22px 24px; }
.cx-card-soft { background: var(--cx-surface-soft); }
.cx-card-title { font-size: 14px; font-weight: 700; }
.cx-card-desc { font-size: 12.5px; color: var(--cx-muted); line-height: 1.65; margin-top: 6px; }
.cx-card-head { display: flex; align-items: center; gap: 9px; }
.cx-card-foot {
  margin-top: 14px; padding-top: 10px; border-top: 1px solid var(--cx-border-soft);
  font-size: 11.5px; color: var(--cx-muted-soft);
}
.cx-mark {
  width: 24px; height: 24px; border-radius: var(--cx-radius-sm); flex: 0 0 auto;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 12px; font-weight: 700; line-height: 1;
}

/* ── 网格 ───────────────────────────────────────── */
.cx-grid { display: grid; gap: 14px; }
.cx-grid-2 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.cx-grid-3 { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.cx-grid-4 { grid-template-columns: repeat(4, minmax(0, 1fr)); }
.cx-grid-agents { grid-template-columns: repeat(auto-fill, minmax(196px, 1fr)); }
@media (max-width: 1100px) {
  .cx-grid-3, .cx-grid-4, .cx-grid-2 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 720px) {
  .cx-grid-3, .cx-grid-4, .cx-grid-2 { grid-template-columns: 1fr; }
  .cx-hero { padding: 22px 20px; }
}

/* ── Badge（10% 浅底 + 透明边框 + 700 字重） ────── */
.cx-badge {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 2px 8px; border-radius: var(--cx-radius-sm);
  font-size: 11px; font-weight: 700; line-height: 1.7;
  border: 1px solid transparent; white-space: nowrap;
}
.cx-chip {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 3px 9px; border-radius: 999px; font-size: 11px;
  border: 1px solid var(--cx-border); background: var(--cx-surface);
  color: var(--cx-muted);
}
.cx-kv { font-size: 11.5px; color: var(--cx-muted); }
.cx-strong { font-weight: 700; color: var(--cx-fg); }
.cx-quiet { color: var(--cx-muted); }

/* ── DAG（轻量流程：白卡节点 + 1px 连接线） ─────── */
.cx-dag { display: flex; flex-direction: column; gap: 0; }
.cx-dag-node {
  display: flex; align-items: center; gap: 12px;
  background: var(--cx-surface); border: 1px solid var(--cx-border);
  border-radius: var(--cx-radius-md); padding: 11px 14px;
  box-shadow: var(--cx-shadow); transition: all .18s ease;
}
.cx-dag-node:hover { transform: translateY(-1px); box-shadow: var(--cx-shadow-hover); }
.cx-dag-node.is-active { border-color: var(--cx-primary-border); background: var(--cx-primary-soft); }
.cx-dag-node.is-active .cx-dag-title { color: var(--cx-primary-text); }
.cx-dag-node.is-done { border-color: var(--cx-border); }
.cx-dag-node.is-blocked { border-color: var(--cx-red-border); background: var(--cx-red-soft); }
.cx-dag-icon {
  width: 26px; height: 26px; border-radius: 50%; flex: 0 0 auto;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 11px; font-weight: 700; line-height: 1;
  border: 1px solid var(--cx-neutral-border); background: var(--cx-neutral-soft); color: var(--cx-muted);
}
.cx-dag-title { font-size: 13px; font-weight: 600; }
.cx-dag-sub { display: block; font-size: 11.5px; color: var(--cx-muted); margin-top: 1px; }
.cx-dag-side { margin-left: auto; }
.cx-dag-conn { width: 1px; height: 16px; background: var(--cx-border-strong); margin-left: 27px; }

/* ── Agent 状态墙 ───────────────────────────────── */
.cx-agent {
  background: var(--cx-surface); border: 1px solid var(--cx-border);
  border-radius: var(--cx-radius-md); padding: 12px 13px;
  box-shadow: var(--cx-shadow); transition: all .18s ease; position: relative;
}
.cx-agent:hover { transform: translateY(-1px); box-shadow: var(--cx-shadow-hover); }
.cx-agent-top { display: flex; align-items: center; gap: 7px; }
.cx-agent-name { font-size: 12.5px; font-weight: 600; }
.cx-agent-meta { font-size: 11px; color: var(--cx-muted-soft); margin-top: 3px; }
.cx-agent-status { margin-top: 9px; }
.cx-agent-concl {
  font-size: 11.5px; color: var(--cx-muted); margin-top: 7px;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.cx-agent.is-dim { opacity: .72; }
.cx-dot { width: 7px; height: 7px; border-radius: 50%; flex: 0 0 auto; }

/* ── 指标卡（label → value → helper） ───────────── */
.cx-metric { background: var(--cx-surface-soft); border: 1px solid var(--cx-border-soft); border-radius: var(--cx-radius-sm); padding: 11px 13px; height: 100%; }
.cx-metric-label { font-size: 11px; color: var(--cx-muted); letter-spacing: .02em; }
.cx-metric-value { font-size: 15px; font-weight: 700; margin-top: 5px; line-height: 1.45; }
.cx-metric-helper { font-size: 11px; color: var(--cx-muted-soft); margin-top: 4px; }

/* ── 终审结果卡（左侧 4px 语义线，整卡永不变色） ── */
.cx-verdict {
  background: var(--cx-surface); border: 1px solid var(--cx-border);
  border-left: 4px solid var(--cx-primary);
  border-radius: var(--cx-radius-lg); box-shadow: var(--cx-shadow);
  padding: 24px 26px;
}
.cx-verdict.cx-tone-danger { border-left-color: var(--cx-danger); }
.cx-verdict.cx-tone-success { border-left-color: var(--cx-success); }
.cx-verdict.cx-tone-warning { border-left-color: var(--cx-warning); }
.cx-verdict-label { font-size: 11px; letter-spacing: .12em; text-transform: uppercase; color: var(--cx-muted-soft); font-weight: 600; }
.cx-verdict-value { font-size: 26px; font-weight: 700; letter-spacing: -.3px; margin-top: 8px; line-height: 1.3; }
.cx-verdict-note { font-size: 12.5px; color: var(--cx-muted); margin-top: 8px; line-height: 1.7; }
.cx-verdict-grid { display: grid; grid-template-columns: repeat(3, minmax(0,1fr)); gap: 12px; margin-top: 20px; }
@media (max-width: 900px) { .cx-verdict-grid { grid-template-columns: 1fr; } }

/* ── 冲突链（编号 + 一句话） ────────────────────── */
.cx-conflict { display: flex; gap: 14px; align-items: flex-start; }
.cx-conflict-no {
  font-size: 12px; font-weight: 700; color: var(--cx-muted-soft);
  font-variant-numeric: tabular-nums; width: 22px; flex: 0 0 auto; padding-top: 1px;
}
.cx-conflict-body { flex: 1 1 auto; min-width: 0; }
.cx-conflict-claim { font-size: 13px; font-weight: 600; }
.cx-conflict-vs {
  font-size: 10px; font-weight: 700; letter-spacing: .12em; color: var(--cx-red);
  margin: 6px 0 6px 0;
}
.cx-conflict-gap { font-size: 12px; color: var(--cx-muted); line-height: 1.65; }

/* ── 红队区块（品牌识别度：左侧红线 + 浅红标题区） ── */
.cx-redteam {
  background: var(--cx-surface); border: 1px solid var(--cx-border);
  border-left: 4px solid var(--cx-red); border-radius: var(--cx-radius-lg);
  box-shadow: var(--cx-shadow); overflow: hidden;
}
.cx-redteam-head {
  background: var(--cx-red-soft); border-bottom: 1px solid var(--cx-red-border);
  padding: 18px 24px;
}
.cx-redteam-title { font-size: 16px; font-weight: 700; color: var(--cx-red-text); display: flex; align-items: center; gap: 8px; }
.cx-redteam-quote { font-size: 13px; color: #7A4747; margin-top: 8px; line-height: 1.7; }
.cx-redteam-body { padding: 18px 24px 20px 24px; }
.cx-assumption {
  border: 1px solid var(--cx-border); border-radius: var(--cx-radius-md);
  padding: 13px 15px; background: var(--cx-surface-soft);
}
.cx-assumption-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.cx-assumption-name { font-size: 13px; font-weight: 700; }
.cx-assumption-text { font-size: 12px; color: var(--cx-muted); line-height: 1.66; margin-top: 8px; }

/* ── 总指挥区块（决策紫） ───────────────────────── */
.cx-commander {
  background: var(--cx-surface); border: 1px solid var(--cx-border);
  border-left: 4px solid var(--cx-purple); border-radius: var(--cx-radius-lg);
  box-shadow: var(--cx-shadow); overflow: hidden;
}
.cx-commander-head {
  background: var(--cx-purple-soft); border-bottom: 1px solid var(--cx-purple-border);
  padding: 18px 24px;
}
.cx-commander-title { font-size: 16px; font-weight: 700; color: var(--cx-purple-text); display: flex; align-items: center; gap: 8px; }
.cx-commander-body { padding: 18px 24px 20px 24px; }
.cx-action { display: flex; gap: 12px; align-items: flex-start; }
.cx-action-no {
  font-size: 11px; font-weight: 700; color: var(--cx-purple-text); background: var(--cx-purple-soft);
  border: 1px solid var(--cx-purple-border); border-radius: var(--cx-radius-sm);
  padding: 2px 7px; flex: 0 0 auto; font-variant-numeric: tabular-nums;
}
.cx-action-title { font-size: 13px; font-weight: 600; }
.cx-action-desc { font-size: 12px; color: var(--cx-muted); line-height: 1.68; margin-top: 4px; }
.cx-list { margin: 8px 0 0 0; padding: 0; list-style: none; }
.cx-list li { font-size: 12.5px; color: var(--cx-muted); line-height: 1.7; padding-left: 13px; position: relative; }
.cx-list li::before {
  content: ""; position: absolute; left: 0; top: 9px;
  width: 4px; height: 4px; border-radius: 50%; background: var(--cx-border-strong);
}

/* ── 五维评估条 ─────────────────────────────────── */
.cx-dim-row { display: flex; align-items: center; gap: 12px; }
.cx-dim-name { font-size: 12.5px; font-weight: 600; width: 92px; flex: 0 0 auto; }
.cx-dim-track { flex: 1 1 auto; height: 6px; border-radius: 3px; background: var(--cx-neutral-soft); overflow: hidden; }
.cx-dim-fill { height: 100%; border-radius: 3px; }
.cx-dim-note { font-size: 11.5px; color: var(--cx-muted); }

/* ── 空态 ───────────────────────────────────────── */
.cx-empty {
  background: var(--cx-surface-soft); border: 1px dashed var(--cx-border-strong);
  border-radius: var(--cx-radius-lg); padding: 34px 26px; text-align: center;
}
.cx-empty-mark {
  width: 38px; height: 38px; border-radius: var(--cx-radius-md); margin: 0 auto 12px auto;
  background: var(--cx-primary-soft); color: var(--cx-primary);
  display: flex; align-items: center; justify-content: center; font-size: 17px; font-weight: 700;
}
.cx-empty-title { font-size: 14px; font-weight: 700; }
.cx-empty-desc { font-size: 12.5px; color: var(--cx-muted); margin-top: 7px; line-height: 1.7; }

/* ── 输入区提示 ─────────────────────────────────── */
.cx-hint-row {
  display: flex; align-items: center; justify-content: space-between;
  gap: 12px; margin-top: 8px;
}
.cx-hint { font-size: 11.5px; color: var(--cx-muted-soft); }
.cx-counter { font-size: 11.5px; color: var(--cx-muted-soft); font-variant-numeric: tabular-nums; }
.cx-field-label { font-size: 12px; font-weight: 600; margin: 4px 0 4px 1px; }
.cx-footnote { font-size: 11px; color: var(--cx-muted-soft); line-height: 1.75; }

/* ── 按钮（只做单层按钮样式，主按钮稀缺） ───────── */
button[kind="primary"], button[kind="primaryFormSubmit"] {
  border-radius: var(--cx-radius-sm) !important;
  font-weight: 600 !important; box-shadow: none !important;
  transition: all .16s ease !important;
}
button[kind="primary"]:hover, button[kind="primaryFormSubmit"]:hover {
  transform: translateY(-1px); box-shadow: 0 6px 16px rgba(91,99,232,.18) !important;
}
button[kind="secondary"], button[kind="secondaryFormSubmit"] {
  border-radius: var(--cx-radius-sm) !important;
  border: 1px solid var(--cx-border) !important;
  background: var(--cx-surface) !important; color: #3A3F52 !important;
  font-weight: 500 !important; transition: all .16s ease !important;
}
button[kind="secondary"]:hover, button[kind="secondaryFormSubmit"]:hover {
  transform: translateY(-1px); border-color: var(--cx-border-strong) !important;
  background: var(--cx-surface-soft) !important;
}

/* ── Sidebar 导航（激活态 = 浅蓝紫底 + 主色文字，不用粗左条） ── */
[data-testid="stRadioGroup"] { gap: 3px !important; }
[data-testid="stRadioOption"] { padding: 4px 8px; border-radius: var(--cx-radius-sm); transition: background .16s ease; }
[data-testid="stRadioOption"]:hover { background: var(--cx-neutral-soft); }
[data-testid="stRadioOption"][data-selected="true"] { background: var(--cx-primary-soft); }
[data-testid="stRadioOption"][data-selected="true"] p {
  color: var(--cx-primary-text) !important; font-weight: 600;
}

/* ── Streamlit 自身的少量覆盖（全部单层，不做深层后代覆盖） ──
   1) 主内容区留白与最大宽度，让信息不贴边；
   2) 侧边栏宽度固定 232px（折叠时由 Streamlit 自行处理）；
   3) 顶部栏透明化，保留折叠按钮与菜单可用。
   注意：这些样式只影响外观，不阻塞任何 Python 执行。 */
.block-container { padding-top: 3.4rem !important; padding-bottom: 3rem !important; max-width: 1180px; }
.stSidebar { min-width: 232px !important; max-width: 232px !important; }
.stSidebar .block-container, .stSidebar [data-testid="stSidebarUserContent"] { padding-top: 1.4rem; }
[data-testid="stHeader"] { background: transparent; }
[data-testid="stToolbar"] { display: none; }
[data-testid="stVerticalBlockBorderWrapper"] {
  border-radius: var(--cx-radius-md) !important;
  border-color: var(--cx-border) !important;
  box-shadow: var(--cx-shadow) !important;
}
"""


def build_css() -> str:
    """返回全局 CSS（含 :root 变量）。纯字符串拼装，无副作用。"""
    root = "\n".join(f"  --{k}: {v};" for k, v in CSS_VARS.items())
    return (
        "<style>\n"
        f":root {{\n{root}\n}}\n"
        f".cx-root {{ --cx-fs-hero: {FS_HERO}; }}\n"
        f"{_CSS_BODY}\n"
        "</style>"
    )
