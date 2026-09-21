# -*- coding: utf-8 -*-
"""UI 组件层 —— 创想∞ AI创业委员会 展示组件

规则：
- 每个函数只**返回 HTML 字符串**，由 app.py 决定渲染位置（组件不做编排）；
- 颜色/圆角/阴影一律引用 design_tokens，不散写色值；
- 所有动态文本经 ui_helpers.esc() 转义；
- 生成的 HTML **不缩进**（行首不留 4 空格），避免被 Markdown 当作代码块；
- 本模块无 IO / 无网络 / 无副作用，import 期只做常量准备。
"""
from frontend import design_tokens as T
from frontend import ui_helpers as H

# 语义色调表：(浅底, 边框, 文字)
_TONES = {
    "neutral": (T.NEUTRAL_SOFT, T.NEUTRAL_BORDER, T.NEUTRAL_TEXT),
    "primary": (T.PRIMARY_SOFT, T.PRIMARY_BORDER, T.PRIMARY_TEXT),
    "expert": (T.EXPERT_SOFT, T.EXPERT_BORDER, T.EXPERT_TEXT),
    "red": (T.REDTEAM_SOFT, T.REDTEAM_BORDER, T.REDTEAM_TEXT),
    "purple": (T.DECISION_SOFT, T.DECISION_BORDER, T.DECISION_TEXT),
    "success": (T.SUCCESS_SOFT, T.SUCCESS_BORDER, T.SUCCESS_TEXT),
    "warning": (T.WARNING_SOFT, T.WARNING_BORDER, T.WARNING_TEXT),
    "danger": (T.DANGER_SOFT, T.DANGER_BORDER, T.DANGER_TEXT),
    "info": (T.INFO_SOFT, T.INFO_BORDER, T.INFO_TEXT),
}


def _badge_style(tone: str) -> str:
    bg, bd, tx = _TONES.get(tone, _TONES["neutral"])
    return f"background:{bg};border-color:{bd};color:{tx};"


def badge(text: str, tone: str = "neutral", mark: str = "") -> str:
    """状态 / 等级 Badge：浅底 + 半透明边框 + 深色文字（不用高饱和铺底）。"""
    label = f"{mark} {text}".strip() if mark else text
    return f'<span class="cx-badge" style="{_badge_style(tone)}">{H.esc(label)}</span>'


def status_badge(key: str) -> str:
    meta = H.status_ui(key)
    tone = {"pending": "neutral", "running": "primary", "success": "success",
            "failed": "danger", "blocked": "danger", "degraded": "warning",
            "skipped": "neutral"}.get(key, "neutral")
    return badge(meta["label"], tone, meta["icon"])


def dot(color: str, size: int = 7) -> str:
    return f'<span class="cx-dot" style="width:{size}px;height:{size}px;background:{color};"></span>'


# ═══════════════════════════════════════════════════════════
# 页面骨架：Header / Sidebar
# ═══════════════════════════════════════════════════════════

def page_header(title: str, sub: str = "", status_text: str = "", status_tone: str = "neutral") -> str:
    """极简 Header：只在左侧放页面名、右侧放一个真实状态。"""
    right = ""
    if status_text:
        _, _, tx = _TONES.get(status_tone, _TONES["neutral"])
        right = (
            '<span class="cx-header-status">'
            + dot(tx)
            + f'<span>{H.esc(status_text)}</span></span>'
        )
    sub_html = f'<div class="cx-header-sub">{H.esc(sub)}</div>' if sub else ""
    return (
        '<div class="cx-root cx-header">'
        f'<div><div class="cx-header-title">{H.esc(title)}</div>{sub_html}</div>'
        f'{right}</div>'
    )


def sidebar_brand() -> str:
    return (
        '<div class="cx-root cx-brand">'
        '<div class="cx-brand-mark">∞</div>'
        '<div><div class="cx-brand-name">创想</div>'
        '<div class="cx-brand-sub">AI 创业委员会</div></div></div>'
        '<div class="cx-side-rule"></div>'
    )


def sidebar_label(text: str) -> str:
    return f'<div class="cx-root cx-side-label">{H.esc(text)}</div>'


def sidebar_foot(html_text: str) -> str:
    return f'<div class="cx-root cx-side-foot">{html_text}</div>'


# ═══════════════════════════════════════════════════════════
# 首页：Hero / 委员会卡片 / 输入区 / 流程
# ═══════════════════════════════════════════════════════════

def hero(agent_count: int, committee_count: int, chain_steps: int) -> str:
    return (
        '<div class="cx-root cx-hero">'
        '<div class="cx-eyebrow">AI Entrepreneurship Review</div>'
        '<div class="cx-hero-title">创想∞ AI创业委员会</div>'
        '<div class="cx-hero-sub">别人帮你完善创业想法，<br>我们让 AI 创业委员会先质疑它。</div>'
        '<div class="cx-hero-meta">'
        f'<span><b>{agent_count}</b> 位 AI 委员</span>'
        f'<span><b>{committee_count}</b> 大委员会</span>'
        f'<span><b>{chain_steps}</b> 步审议闭环</span>'
        '<span>红队对抗 · 红线一票否决 · 可断点续跑</span>'
        '</div></div>'
    )


def section(eyebrow: str, title: str, sub: str = "") -> str:
    sub_html = f'<div class="cx-section-sub">{H.esc(sub)}</div>' if sub else ""
    eyebrow_html = f'<div class="cx-section-eyebrow">{H.esc(eyebrow)}</div>' if eyebrow else ""
    return (
        '<div class="cx-root cx-section">'
        f'{eyebrow_html}<div class="cx-section-title">{H.esc(title)}</div>{sub_html}</div>'
    )


def committee_cards(rows: list) -> str:
    """rows: [{group, count, members:[label], foot}]"""
    cards = []
    for r in rows:
        meta = H.committee_meta(r["group"])
        members = " · ".join(r.get("members", [])[:6])
        desc = H.truncate(members, 58)
        cards.append(
            '<div class="cx-card" style="padding:18px 18px 14px 18px;">'
            '<div class="cx-card-head">'
            f'<span class="cx-mark" style="background:{meta["soft"]};color:{meta["text"]};">{meta["mark"]}</span>'
            f'<span class="cx-card-title">{H.esc(r["group"])}</span></div>'
            f'<div class="cx-card-desc">{H.esc(desc)}</div>'
            '<div class="cx-card-foot">'
            f'<span style="color:{meta["text"]};font-weight:700;">{r["count"]} Agent{"" if r["count"] == 1 else "s"}</span>'
            + (f' · {H.esc(r["foot"])}' if r.get("foot") else "")
            + '</div></div>'
        )
    return '<div class="cx-root"><div class="cx-grid cx-grid-3">' + "".join(cards) + "</div></div>"


def input_hint(used: int, limit: int, hint: str) -> str:
    return (
        '<div class="cx-root cx-hint-row">'
        f'<span class="cx-hint">{H.esc(hint)}</span>'
        f'<span class="cx-counter">{used} / {limit}</span></div>'
    )


def field_label(text: str) -> str:
    return f'<div class="cx-root cx-field-label">{H.esc(text)}</div>'


def footnote(text_html: str) -> str:
    return f'<div class="cx-root cx-footnote">{text_html}</div>'


def dag(nodes: list) -> str:
    """nodes: [{title, sub, state(pending/running/done/blocked), mark, tone}]"""
    parts = []
    for i, n in enumerate(nodes):
        if n.get("state") == "running":
            cls, tone = "cx-dag-node is-active", "primary"
        elif n.get("state") == "blocked":
            cls, tone = "cx-dag-node is-blocked", "red"
        else:
            cls, tone = "cx-dag-node", "neutral"
        bg, bd, tx = _TONES.get(n.get("tone") or tone, _TONES["neutral"])
        right = f'<span class="cx-dag-side">{status_badge(n["state_badge"])}</span>' if n.get("state_badge") else ""
        parts.append(
            f'<div class="{cls}">'
            f'<span class="cx-dag-icon" style="background:{bg};border-color:{bd};color:{tx};">{H.esc(n.get("mark", "•"))}</span>'
            '<span><span class="cx-dag-title">' + H.esc(n["title"]) + '</span>'
            f'<span class="cx-dag-sub">{H.esc(n.get("sub", ""))}</span></span>'
            f'{right}</div>'
        )
        if i < len(nodes) - 1:
            parts.append('<div class="cx-dag-conn"></div>')
    return '<div class="cx-root"><div class="cx-dag">' + "".join(parts) + "</div></div>"


# ═══════════════════════════════════════════════════════════
# 运行页：分组进度 + Agent 状态墙
# ═══════════════════════════════════════════════════════════

def group_progress(rows: list) -> str:
    """rows: [{group, done, total, state_key}]"""
    cards = []
    for r in rows:
        meta = H.committee_meta(r["group"])
        key = r["state_key"]
        st_meta = H.status_ui(key)
        cards.append(
            '<div class="cx-card" style="padding:14px 16px;">'
            '<div class="cx-card-head">'
            f'<span class="cx-mark" style="background:{meta["soft"]};color:{meta["text"]};">{meta["mark"]}</span>'
            f'<span class="cx-card-title">{H.esc(r["group"])}</span>'
            f'<span style="margin-left:auto;">{status_badge(key)}</span></div>'
            '<div class="cx-card-foot" style="margin-top:10px;">'
            f'{r["done"]} / {r["total"]} 棒</div></div>'
        )
    return '<div class="cx-root"><div class="cx-grid cx-grid-3">' + "".join(cards) + "</div></div>"


def agent_card(row: dict) -> str:
    """row: {label, seq, group, status_key, conclusion}"""
    meta = H.committee_meta(row.get("group", ""))
    key = row.get("status_key", "pending")
    dim = " is-dim" if key == "pending" else ""
    concl = row.get("conclusion") or ""
    concl_html = f'<div class="cx-agent-concl">{H.esc(H.truncate(concl, 54))}</div>' if concl else ""
    return (
        f'<div class="cx-agent{dim}">'
        '<div class="cx-agent-top">'
        f'{dot(meta["solid"])}'
        f'<span class="cx-agent-name">{H.esc(row.get("label", ""))}</span>'
        f'<span style="margin-left:auto;">{status_badge(key)}</span></div>'
        f'<div class="cx-agent-meta">{H.esc(row.get("seq", ""))} · {H.esc(row.get("group", ""))}</div>'
        f'{concl_html}</div>'
    )


def agent_wall(rows: list) -> str:
    return ('<div class="cx-root"><div class="cx-grid cx-grid-agents">'
            + "".join(agent_card(r) for r in rows) + "</div></div>")


# ═══════════════════════════════════════════════════════════
# 结果页：终审卡 / 指标 / 五维 / 冲突链 / 红队 / 总指挥
# ═══════════════════════════════════════════════════════════

def metric_cell(label: str, value: str, helper: str = "", tone: str = "") -> str:
    _, _, tx = _TONES.get(tone, ("", "", T.FOREGROUND))
    helper_html = f'<div class="cx-metric-helper">{H.esc(helper)}</div>' if helper else ""
    return (
        '<div class="cx-metric">'
        f'<div class="cx-metric-label">{H.esc(label)}</div>'
        f'<div class="cx-metric-value" style="color:{tx if tone else T.FOREGROUND};">{H.esc(value)}</div>'
        f'{helper_html}</div>'
    )


def metric_grid(cells: list) -> str:
    cols = min(max(len(cells), 1), 4)
    return (f'<div class="cx-root"><div class="cx-grid cx-grid-{cols}">'
            + "".join(cells) + "</div></div>")


def verdict_card(label: str, value: str, tone: str = "primary",
                 note: str = "", metrics: list = None) -> str:
    cells = "".join(metric_cell(*m) for m in (metrics or []))
    grid = f'<div class="cx-verdict-grid">{cells}</div>' if cells else ""
    note_html = f'<div class="cx-verdict-note">{H.esc(note)}</div>' if note else ""
    return (
        f'<div class="cx-root cx-verdict cx-tone-{tone}">'
        f'<div class="cx-verdict-label">{H.esc(label)}</div>'
        f'<div class="cx-verdict-value">{H.esc(value)}</div>'
        f'{note_html}{grid}</div>'
    )


def dim_rows(dims: list) -> str:
    """五维评估：真实评分（1-5）→ 进度条 + 证据强度。"""
    rows = []
    for d in dims:
        score = max(0, min(int(d.get("score") or 0), 5))
        if score <= 1:
            fill = T.DANGER
        elif score == 2:
            fill = T.WARNING
        elif score == 3:
            fill = T.INFO
        else:
            fill = T.SUCCESS
        pct = int(score / 5 * 100)
        note = H.truncate(d.get("summary", ""), 64)
        strength = d.get("strength", "")
        rows.append(
            '<div class="cx-card" style="padding:12px 15px;">'
            '<div class="cx-dim-row">'
            f'<span class="cx-dim-name">{H.esc(d.get("name", ""))}</span>'
            '<span class="cx-dim-track">'
            f'<span class="cx-dim-fill" style="width:{pct}%;background:{fill};"></span></span>'
            f'<span class="cx-badge" style="background:{T.NEUTRAL_SOFT};border-color:{T.NEUTRAL_BORDER};color:{T.FOREGROUND};">{score} / 5</span>'
            '<span style="margin-left:6px;">'
            + badge(strength or "未标注", "neutral") + "</span></div>"
            f'<div class="cx-dim-note" style="margin-top:7px;">{H.esc(note)}</div></div>'
        )
    return '<div class="cx-root"><div class="cx-grid" style="gap:10px;">' + "".join(rows) + "</div></div>"


def kv_rows(items: list) -> str:
    """items: [(k, v)] —— 只用于展示真实字段。"""
    rows = "".join(
        '<div style="display:flex;gap:10px;padding:6px 0;">'
        f'<span class="cx-kv" style="flex:0 0 92px;">{H.esc(k)}</span>'
        f'<span class="cx-value" style="flex:1 1 auto;font-size:12.5px;">{H.esc(v)}</span></div>'
        for k, v in items
    )
    return f'<div class="cx-root">{rows}</div>'


def bullet_list(items: list, limit: int = 6, cut: int = 88) -> str:
    lis = "".join(f"<li>{H.esc(H.truncate(t, cut))}</li>" for t in items[:limit])
    return f'<div class="cx-root"><ul class="cx-list">{lis}</ul></div>'


def conflict_list(items: list) -> str:
    """委员会发现的关键矛盾：项目方主张 VS 委员会要求。"""
    rows = []
    for it in items:
        level = it.get("level", "")
        tone = {"致命": "danger", "高": "warning", "中": "info"}.get(level, "neutral")
        claim = it.get("claim") or ""
        claim_html = (f'<div class="cx-conflict-gap">报告引用项目方主张：「{H.esc(claim)}」</div>'
                      if claim else "")
        rows.append(
            '<div class="cx-card" style="padding:15px 17px;">'
            '<div class="cx-conflict">'
            f'<span class="cx-conflict-no">{H.esc(it.get("no", ""))}</span>'
            '<span class="cx-conflict-body">'
            '<span style="display:flex;align-items:center;justify-content:space-between;gap:10px;">'
            f'<span class="cx-conflict-claim">{H.esc(it.get("name", ""))}</span>'
            + badge(level or "待定", tone) + "</span>"
            f'<span class="cx-conflict-vs">项目主张 &nbsp;VS&nbsp; 委员会要求</span>'
            f'{claim_html}'
            f'<div class="cx-conflict-gap" style="margin-top:5px;color:{T.FOREGROUND};">{H.esc(it.get("gap", ""))}</div>'
            "</span></div></div>"
        )
    return '<div class="cx-root"><div class="cx-grid cx-grid-2">' + "".join(rows) + "</div></div>"


def redteam_block(quote: str, counts: dict, items: list) -> str:
    """红队质疑官：浅红标题区 + 左侧红线 + 假设 Badge（最有品牌识别度的区块）。"""
    count_html = "".join(
        badge(f"{lv} {counts[lv]}", {"致命": "danger", "高": "warning", "一般": "neutral"}.get(lv, "neutral"))
        + "&nbsp;"
        for lv in ("致命", "高", "一般") if lv in counts
    )
    cards = []
    for it in items:
        level = it.get("level", "")
        tone = {"致命": "danger", "高": "warning", "中": "info"}.get(level, "neutral")
        claim = it.get("claim") or ""
        claim_html = (f'<div class="cx-assumption-text">报告引用项目方主张：「{H.esc(claim)}」</div>'
                      if claim else "")
        gap = it.get("gap") or ""
        gap_html = (f'<div class="cx-assumption-text">待验证：{H.esc(H.truncate(gap, 120))}</div>'
                    if gap else "")
        cards.append(
            '<div class="cx-assumption">'
            '<div class="cx-assumption-head">'
            f'<span class="cx-assumption-name">{H.esc(it.get("name", ""))}</span>'
            + badge(level or "待定", tone) + "</div>"
            f"{claim_html}{gap_html}</div>"
        )
    return (
        '<div class="cx-root cx-redteam">'
        '<div class="cx-redteam-head">'
        f'<div class="cx-redteam-title">🔴 红队质疑官 &nbsp; {count_html}</div>'
        f'<div class="cx-redteam-quote">{H.esc(quote)}</div></div>'
        '<div class="cx-redteam-body"><div class="cx-grid cx-grid-2">'
        + "".join(cards) + "</div></div></div>"
    )


def commander_block(conclusion: str, stage: str, core_conflict: str, actions: list) -> str:
    """创业总指挥：浅紫标题区 + 结论 + 下一步行动 01/02/03。"""
    head_right = ""
    if stage:
        head_right = badge(f"阶段 · {stage}", "purple")
    core_html = ""
    if core_conflict:
        core_html = (
            '<div style="margin-bottom:16px;">'
            '<div class="cx-side-label" style="margin:0 0 6px 0;color:' + T.MUTED + ';">核心矛盾</div>'
            f'<div style="font-size:12.5px;line-height:1.75;color:#3A3F52;">{H.esc(core_conflict)}</div></div>'
        )
    cards = []
    for a in actions:
        title, desc = H.split_title_desc(a.get("text", ""), 20)
        cards.append(
            '<div class="cx-action" style="padding:13px 15px;border:1px solid '
            + T.BORDER + ';border-radius:' + T.RADIUS_MD + ';background:' + T.SURFACE_SOFT + ';">'
            f'<span class="cx-action-no">{H.esc(a.get("no", ""))}</span>'
            '<span><span class="cx-action-title">' + H.esc(title) + '</span>'
            f'<div class="cx-action-desc">{H.esc(desc)}</div></span></div>'
        )
    actions_html = ""
    if cards:
        actions_html = (
            '<div class="cx-side-label" style="margin:4px 0 10px 0;color:' + T.MUTED + ';">下一步行动</div>'
            '<div class="cx-grid" style="gap:10px;">' + "".join(cards) + "</div>"
        )
    if not core_html and not actions_html:
        actions_html = (f'<div class="cx-footnote">本棒未产出可用结论'
                        f'（核心矛盾与行动项为空，详见「委员会完整报告」原文）。</div>')
    return (
        '<div class="cx-root cx-commander">'
        '<div class="cx-commander-head">'
        '<div class="cx-commander-title" style="justify-content:space-between;">'
        '<span>创业总指挥 &nbsp;' + badge(conclusion or "未判断", "purple") + "</span>"
        f'<span>{head_right}</span></div></div>'
        f'<div class="cx-commander-body">{core_html}{actions_html}</div></div>'
    )


def empty_state(mark: str, title: str, desc: str) -> str:
    return (
        '<div class="cx-root cx-empty">'
        f'<div class="cx-empty-mark">{H.esc(mark)}</div>'
        f'<div class="cx-empty-title">{H.esc(title)}</div>'
        f'<div class="cx-empty-desc">{H.esc(desc)}</div></div>'
    )


def note_box(title: str, text: str, tone: str = "neutral") -> str:
    """系统留痕条（降级 / 返工 / 阻断 / 校验警告）——不用默认警告色块铺满。"""
    bg, bd, tx = _TONES.get(tone, _TONES["neutral"])
    title_html = f'<span style="font-weight:700;color:{tx};">{H.esc(title)}</span>' if title else ""
    sep = " &nbsp; " if title else ""
    return (
        f'<div class="cx-root cx-card" style="background:{bg};border-color:{bd};'
        f'box-shadow:none;padding:12px 14px;margin-bottom:10px;font-size:12.5px;line-height:1.7;">'
        f'{title_html}{sep}{H.esc(text)}</div>'
    )


def swatches(items: list) -> str:
    """设计令牌色卡（items: [(label, hex)]），用于「设计规范」展示。"""
    cells = []
    for label, color in items:
        cells.append(
            '<div style="display:flex;align-items:center;gap:9px;">'
            f'<span style="width:16px;height:16px;border-radius:{T.RADIUS_SM};'
            f'background:{color};border:1px solid rgba(0,0,0,.06);flex:0 0 auto;"></span>'
            f'<span style="font-size:11.5px;color:{T.MUTED};">{H.esc(label)}</span>'
            f'<span style="font-size:11px;color:{T.MUTED_SOFT};margin-left:auto;">{H.esc(color)}</span>'
            '</div>'
        )
    return ('<div class="cx-root cx-grid" style="grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:8px;">'
            + "".join(cells) + "</div>")
