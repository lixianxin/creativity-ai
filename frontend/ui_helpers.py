# -*- coding: utf-8 -*-
"""UI 辅助层 —— 状态映射 / 文本清洗 / 真实报告解析。

三条硬规则：
1. **纯函数**：无 IO、无网络、无副作用，不修改任何业务数据（AgentResult 只读）；
2. **解析不到就留空**：前端绝不编造数字、状态或结论，宁可不展示；
3. **单一事实源**：Agent 名称 / 委员会归属从 agents.registry 读取，不另抄一份。

本模块只被展示层调用，不参与任何业务判断，也不写回任何结果对象。
"""
import html as _html
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agents.registry import registry  # noqa: E402  （纯 dataclass 注册表，无 IO）
from schemas.agent_result import (  # noqa: E402
    STATUS_PENDING, STATUS_RUNNING, STATUS_SUCCESS, STATUS_FAILED,
    STATUS_BLOCKED, STATUS_DEGRADED, STATUS_SKIPPED,
)
from frontend import design_tokens as T  # noqa: E402

# ═══════════════════════════════════════════════════════════
# 一、Agent / 委员会 元信息（唯一事实源：registry）
# ═══════════════════════════════════════════════════════════

_SPECS = registry.all()
_SPEC_BY_NAME = {s.name: s for s in _SPECS}


def stage_info() -> list:
    """12 棒的展示元信息（顺序与 registry 完全一致）。"""
    return [
        {
            "idx": i,
            "seq": s.seq,
            "key": s.stage_key,
            "name": s.name,
            "label": s.label,
            "group": s.group,
            "dependencies": list(s.dependencies),
            "soft_dependencies": list(s.soft_dependencies),
        }
        for i, s in enumerate(_SPECS)
    ]


STAGE_ROWS = stage_info()
AGENT_LABEL = {r["name"]: r["label"] for r in STAGE_ROWS}
AGENT_GROUP = {r["name"]: r["group"] for r in STAGE_ROWS}
AGENT_SEQ = {r["name"]: r["seq"] for r in STAGE_ROWS}
LABEL_BY_IDX = {r["idx"]: r["label"] for r in STAGE_ROWS}

GROUP_ORDER = ["专家委员会", "对抗委员会", "决策委员会"]


def committee_meta(group: str) -> dict:
    """委员会语义色（专家蓝 / 红队红 / 决策紫）。未知分组退回中性色。"""
    return T.COMMITTEE_UI.get(group, {
        "key": "neutral", "soft": T.NEUTRAL_SOFT, "border": T.NEUTRAL_BORDER,
        "text": T.NEUTRAL_TEXT, "solid": T.NEUTRAL, "short": "委员会", "mark": "◇",
    })


def agent_label(name: str) -> str:
    return AGENT_LABEL.get(name, name)


def agent_group(name: str) -> str:
    return AGENT_GROUP.get(name, "")


def agent_seq(name: str) -> str:
    return AGENT_SEQ.get(name, "")


def group_agent_names(group: str) -> list:
    return [r["name"] for r in STAGE_ROWS if r["group"] == group]


def dependency_names(spec_name: str) -> tuple:
    """返回 (硬依赖标签, 软依赖标签)，用于「委员会」页展示真实 DAG 依赖。"""
    row = next((r for r in STAGE_ROWS if r["name"] == spec_name), None)
    if not row:
        return [], []
    return ([agent_label(n) for n in row["dependencies"]],
            [agent_label(n) for n in row["soft_dependencies"]])


# ═══════════════════════════════════════════════════════════
# 二、状态映射（所有 Agent 状态只走这张表）
# ═══════════════════════════════════════════════════════════

_RUN_STATUS_UI = {
    "queued": "pending",
    "running": "running",
    "success": "success",
    "degraded": "degraded",
    "failed": "failed",
    "blocked": "blocked",
    "skipped": "skipped",
    "paused": "degraded",
    "completed_with_errors": "degraded",
}

_RUN_STATUS_LABEL = {
    "queued": "排队中",
    "running": "执行中",
    "success": "全部成功",
    "degraded": "降级完成",
    "failed": "已失败",
    "blocked": "已阻断",
    "skipped": "已跳过",
    "paused": "已暂停",
    "completed_with_errors": "部分成功",
}


def status_ui(key: str) -> dict:
    return T.STATUS_UI.get(key, T.STATUS_UI["pending"])


def status_key_for(result, idx: int, current_stage: int) -> str:
    """把真实结果 + 当前棒次映射到状态键。不改变任何结果本身。"""
    if result is not None:
        st = getattr(result, "status", STATUS_PENDING)
        meta = getattr(result, "metadata", {}) or {}
        if st == STATUS_FAILED:
            return "failed"
        if st == STATUS_BLOCKED:
            return "blocked"
        if st == STATUS_SKIPPED:
            return "skipped"
        if st == STATUS_DEGRADED or meta.get("degraded_inputs"):
            return "degraded"
        if st == STATUS_SUCCESS:
            return "success"
        if st == STATUS_RUNNING:
            return "running"
    if idx == current_stage:
        return "running"
    return "pending"


def run_status_key(run_status: str) -> str:
    return _RUN_STATUS_UI.get(run_status, "pending")


def run_status_label(run_status: str) -> str:
    return _RUN_STATUS_LABEL.get(run_status, run_status)


def level_ui(level: str) -> dict:
    """问题等级（致命/高/中/低）→ 语义色。"""
    level = (level or "").strip()
    if level in ("致命", "高", "中", "低", "一般"):
        return T.LEVEL_UI[level]
    return T.LEVEL_UI["一般"]


# ═══════════════════════════════════════════════════════════
# 三、文本清洗
# ═══════════════════════════════════════════════════════════

def esc(text) -> str:
    """HTML 转义（所有动态文本必须经过它）。"""
    return _html.escape(str(text if text is not None else ""))


_MD_DROP = re.compile(r"[*`#]+")
_WS = re.compile(r"\s+")


def clean_text(text) -> str:
    """去掉 Markdown 强调符号与多余空白，保留内容原义。"""
    if text is None:
        return ""
    s = str(text).replace("\u200b", "")
    s = _MD_DROP.sub("", s)
    return _WS.sub(" ", s).strip(" -—▪·；;")


def truncate(text, limit: int = 60) -> str:
    s = clean_text(text)
    return s if len(s) <= limit else s[: max(limit - 1, 1)] + "…"


def first_sentence(text, limit: int = 90) -> str:
    s = clean_text(text)
    if not s:
        return ""
    m = re.split(r"[。；;!?！？]", s, maxsplit=1)
    return truncate(m[0] if m else s, limit)


def split_title_desc(text, title_limit: int = 18):
    """把一句行动项拆成 (标题, 说明)：优先按「，/：」切分。"""
    s = clean_text(text)
    if not s:
        return "", ""
    parts = re.split(r"[，。：；]", s, maxsplit=1)
    head = truncate(parts[0], title_limit)
    rest = s[len(parts[0]):].lstrip("，。：；") if len(parts) > 1 else ""
    return head, rest


def _lines(raw: str) -> list:
    return [l.strip() for l in (raw or "").splitlines() if l.strip()]


def _value_after_line(lines: list, key: str) -> str:
    """找到包含 key 的行，返回其后第一条非空行的清洗值。"""
    for i, line in enumerate(lines):
        if key in line:
            tail = line.split(key, 1)[1].strip(" ：:*")
            if tail:
                return clean_text(tail)
            for nxt in lines[i + 1:i + 3]:
                if nxt and not nxt.startswith(("#", "|")):
                    return clean_text(nxt)
    return ""


def _after_colon(line: str) -> str:
    for ch in ("：", ":"):
        if ch in line:
            return clean_text(line.split(ch, 1)[1])
    return clean_text(line)


_CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩"
_CIRCLED_RE = re.compile(r"^([①②③④⑤⑥⑦⑧⑨⑩])\s*(.*)$")


# ═══════════════════════════════════════════════════════════
# 四、真实报告解析（解析不到一律返回空，绝不编造）
# ═══════════════════════════════════════════════════════════

_ITEM_HEAD_RE = re.compile(r"^[①②③④⑤⑥⑦⑧⑨⑩]\s*【(.+?)】")
# 只采信「你声称“…”」这种报告原文引用作为项目方主张；引用不到就留空，
# 由组件退回展示假设名称——绝不替 Agent 编造主张。
_CLAIM_RE = re.compile(r"你(?:声称|称|说|提到|表示)[“\"']([^”\"']{4,60})[”\"']")


def parse_red_team_assumptions(raw: str, limit: int = 8) -> list:
    """红队五维假设：①【需求假设｜致命】- 攻击：… - 待验证：…"""
    items, cur = [], None
    for line in _lines(raw):
        m = _ITEM_HEAD_RE.match(line)
        if m:
            head = m.group(1)
            name, _, level = head.replace("|", "｜").partition("｜")
            cur = {"name": clean_text(name) or "假设",
                   "level": clean_text(level) or "一般",
                   "attack": "", "verify": ""}
            items.append(cur)
            continue
        if cur is None:
            continue
        if "- 攻击" in line or line.startswith("攻击"):
            cur["attack"] = _after_colon(line)
        elif "- 待验证" in line or line.startswith("待验证"):
            cur["verify"] = _after_colon(line)
    out = []
    for it in items[:limit]:
        claim = ""
        q = _CLAIM_RE.search(it["attack"])
        if q:
            claim = clean_text(q.group(1))
        out.append({
            "name": it["name"],
            "level": it["level"],
            "claim": truncate(claim, 52),
            "gap": truncate(it["verify"], 96),
        })
    return out


def parse_red_team_counts(raw: str) -> dict:
    """致命问题：3个 / 高风险问题：2个 / 一般问题：0个"""
    out = {}
    for line in _lines(raw):
        m = re.match(r"^(致命|高风险|一般|高|中|低)问题[：:]\s*(\d+)", line)
        if m:
            key = m.group(1).replace("高风险", "高")
            out[key] = int(m.group(2))
    return out


_RISK_HEAD_RE = re.compile(r"^[▶►]\s*风险点")
_RISK_LEVEL_RE = re.compile(r"^[→>-]\s*等级[：:]\s*(\S+)")
_RISK_ACTION_RE = re.compile(r"^[→>-]\s*上线前必须完成的动作[：:]\s*(.*)$")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")


def parse_risk_items(raw: str, limit: int = 12) -> list:
    """风险审查报告条目：▶ 风险点… → 等级：致命 → 上线前必须完成的动作：…"""
    items, cur = [], None
    for line in _lines(raw):
        if _RISK_HEAD_RE.match(line):
            body = _after_colon(line)
            m = _BOLD_RE.search(body)
            title = clean_text(m.group(1) if m else body)
            cur = {"title": title, "level": "", "action": ""}
            items.append(cur)
            continue
        if cur is None:
            continue
        m = _RISK_LEVEL_RE.match(line)
        if m and not cur["level"]:
            cur["level"] = clean_text(m.group(1))
            continue
        m = _RISK_ACTION_RE.match(line)
        if m:
            cur["action"] = truncate(m.group(1), 110)
    return items[:limit]


def parse_risk_counts(raw: str) -> dict:
    """风险计数：致命 3 个 / 高 4 个 / 中 1 个 / 低 0 个"""
    out = {}
    for line in _lines(raw):
        if "风险计数" not in line:
            continue
        for level, num in re.findall(r"(致命|高|中|低)\s*(\d+)\s*个", line):
            out[level] = int(num)
    return out


def parse_commander(raw: str) -> dict:
    """创业总指挥：委员会结论 / 项目阶段 / 核心矛盾 / 下一步行动 ①②③"""
    lines = _lines(raw)
    core = _value_after_line(lines, "核心矛盾")
    if core.startswith("核心矛盾"):
        core = core.split("核心矛盾", 1)[1].strip(" ：:")
    core = core.strip(" ：:")
    return {
        "conclusion": _value_after_line(lines, "委员会结论"),
        "stage": _value_after_line(lines, "项目阶段"),
        "core_conflict": truncate(core, 240),
        "actions": _slice_actions(lines),
    }


def _slice_actions(lines: list, limit: int = 4) -> list:
    """从「下一步行动」之后提取 ①②③ 行动项（含跨行续写）。"""
    start = None
    for i, line in enumerate(lines):
        if "下一步行动" in line:
            start = i
            break
    if start is None:
        return []
    out = []
    for line in lines[start + 1:]:
        m = _CIRCLED_RE.match(line)
        if m:
            if len(out) >= limit:
                break
            out.append({
                "no": f"{_CIRCLED.index(m.group(1)) + 1:02d}",
                "text": clean_text(m.group(2)),
            })
        elif out:
            if line.endswith("：") or line.endswith(":"):
                break          # 进入下一个段落标题，停止续写
            out[-1]["text"] = clean_text(out[-1]["text"] + " " + line)
    return out


def parse_review(raw: str) -> dict:
    """项目评审官：终审结论 / 一票否决 / 五维评估 / 红线与报告完整性。"""
    lines = _lines(raw)
    dims = []
    for line in lines:
        if not line.startswith("|"):
            continue
        cells = [clean_text(c) for c in line.strip("|").split("|")]
        if len(cells) < 3 or "维度" in cells[0] or set(cells[0]) <= set("-: "):
            continue
        score = 0
        m = re.search(r"(\d)\s*分", cells[1]) or re.search(r"^(\d)$", cells[1])
        if m:
            score = int(m.group(1))
        dims.append({
            "name": cells[0],
            "score": score,
            "summary": truncate(cells[3] if len(cells) > 3 else "", 70),
            "strength": truncate(cells[4] if len(cells) > 4 else "", 24),
        })
    veto = ""
    m = re.search(r"一票否决是否触发[：:]\s*\**\s*(是|否)", raw)
    if m:
        veto = m.group(1)
    return {
        "verdict": _value_after_line(lines, "终审结论"),
        "veto": veto,
        "dims": dims[:6],
        "compliance": _value_after_line(lines, "合规致命风险"),
        "completeness": _value_after_line(lines, "关键报告完整性"),
    }


def parse_pitch(raw: str) -> dict:
    """路演答辩官：路演表现结论 / 答辩评级击穿计数。"""
    lines = _lines(raw)
    concluded = _value_after_line(lines, "路演表现结论")
    if not concluded:
        for line in lines:
            if any(k in line for k in ["可以路演", "有条件路演", "暂不建议", "无法评估"]):
                concluded = clean_text(line)
                break
    total = sum(1 for line in lines if "答辩评级" in line)
    pierced = sum(1 for line in lines if "答辩评级" in line and "击穿" in line)
    return {"conclusion": concluded, "ratings_total": total, "ratings_pierced": pierced}


def parse_finance(raw: str) -> dict:
    lines = _lines(raw)
    return {
        "conclusion": _value_after_line(lines, "分析结论"),
        "basis": truncate(_value_after_line(lines, "一句话依据"), 120),
    }


def build_conflict_chain(red_items: list, limit: int = 4) -> list:
    """冲突链 = 项目方主张（报告引用原话） VS 委员会要求验证的缺口。

    只保留「有真实待验证缺口」的条目：缺口为空说明报告未给出可展示矛盾，
    此时不生成卡片，也不补默认文案。
    """
    out = []
    for it in (red_items or []):
        if not it.get("gap"):
            continue
        out.append({
            "no": f"{len(out) + 1:02d}",
            "name": it.get("name", ""),
            "level": it.get("level", ""),
            "claim": it.get("claim", ""),
            "gap": it.get("gap", ""),
        })
        if len(out) >= limit:
            break
    return out
