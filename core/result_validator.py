# -*- coding: utf-8 -*-
"""确定性 ResultValidator（Phase 7-5，借鉴 BossHunter 评分闸门/简历反幻觉审计）。

核心原则：**不让 LLM 自己证明自己没胡说**。
LLM 负责判断，程序负责校验/归一/决定是否接受：

  Agent → Raw LLM Output → Parser(已有启发式) → ResultValidator
       → Validated AgentResult（信号程序归一写回）→ Persistence → 下一个 Agent

校验结论分两级：
- error  ：结构不合格，整次结果不接受（执行器带 issue 清单返工，最多 1 次，仍败则该 Agent failed）；
- warning：接受但留痕（如"数字无来源"），写入 metadata.validation_warnings。

另有 signals：程序从文本中确定性提取的信号（blocking / redline_triggered /
conclusion / pierced_count / unsourced_numbers），**写回后覆盖 Agent 自报**，
把"红线一票否决"从 Prompt 规则变成系统规则。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from schemas.agent_result import AgentResult


SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"

# Phase 7-9：行动项编号识别必须与 commander_v1.md 输出模板对齐。
# 真实样本 4/4 使用圆圈数字①②③（模板即如此规定），旧正则只认阿拉伯数字，
# 导致"3 条行动项稳定输出、validator 稳定误判、Repair 无信息可改"。
_ACTION_BULLET_RE = re.compile(
    r"^\s*(?:"
    r"\d+[\.、\)]"                        # 1. / 1、/ 1)
    r"|[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮]"            # 圆圈数字（prompt 模板格式）
    r"|[（(]\d+[）)]"                      # (1) / （1）
    r"|[一二三四五六七八九十]+[、\.）)]"     # 一、 / 二. / 三）
    r")"
)

# Phase 7-9：指挥官项目阶段以 commander_v1.md 模板为权威
# （旧集合"产品验证/市场验证/规模扩张"与模板"方案修正/路演准备/可进入路演"冲突）。
_COMMANDER_STAGES = ("想法验证", "方案修正", "路演准备", "可进入路演")


# ── Phase 7-8 Critic/Repair 工程化 ──
# error 一律触发返工；warning 中属于"结构性缺失/输出格式不规范"的，
# 也应消耗一次返工机会修复（如 COMMANDER_ACTIONS_LT_3 行动项不足）。
# 纯信息类 warning（数字无来源、证据分级意识等）不触发返工，仅留痕。
REPAIRABLE_WARNING_CODES = {
    # 指挥官：阶段判断与行动项格式
    "COMMANDER_NO_STAGE", "COMMANDER_ACTIONS_LT_3",
    # 路演：结论与评委追问
    "PITCH_NO_CONCLUSION", "PITCH_NO_JUDGE_QUESTIONS",
    # 产品：MVP 与核心闭环
    "PRODUCT_NO_MVP", "PRODUCT_NO_CORE_LOOP",
    # 商业：付费方/收入/成本骨架
    "BUSINESS_NO_PAYER", "BUSINESS_NO_REVENUE", "BUSINESS_NO_COST",
    # 用户洞察：痛点与付费者
    "USER_NO_PAINPOINT", "USER_PAYER_MISSING",
    # 竞品：三分法与差异化
    "COMPETITOR_MISSING_TIERS", "COMPETITOR_NO_DIFFERENTIATION",
    # 增长：框架要素
    "GROWTH_MISSING_FRAMEWORK",
    # 风险：覆盖面与致命锚点
    "RISK_DOMAIN_INCOMPLETE", "RISK_FATAL_WITHOUT_ANCHOR",
    # 红队：证据锚点 + 单维缺失（Phase 7-9：4/5 时点名缺哪维，触发一次返工补齐）
    "REDTEAM_NO_EVIDENCE_ANCHOR", "REDTEAM_DIM_MISSING_ONE",
    # 财务：假设声明
    "FINANCE_NO_EXPLICIT_ASSUMPTION",
}


@dataclass
class ValidationIssue:
    severity: str   # error / warning
    code: str
    message: str


@dataclass
class ValidationResult:
    agent_name: str
    issues: List[ValidationIssue] = field(default_factory=list)
    # 程序确定性提取的信号，执行器负责写回 AgentResult
    signals: Dict[str, object] = field(default_factory=dict)

    @property
    def errors(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == SEVERITY_ERROR]

    @property
    def warnings(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == SEVERITY_WARNING]

    @property
    def accepted(self) -> bool:
        return not self.errors

    @property
    def repairable_issues(self) -> List[ValidationIssue]:
        """可消耗一次返工的问题：全部 error + 结构性 warning。"""
        return [i for i in self.issues
                if i.severity == SEVERITY_ERROR
                or (i.severity == SEVERITY_WARNING and i.code in REPAIRABLE_WARNING_CODES)]

    @property
    def needs_repair(self) -> bool:
        """Critic 是否判定需要返工。error 必返；可修 warning 也返。"""
        return bool(self.repairable_issues)

    def to_dict(self) -> dict:
        return {
            "agent_name": self.agent_name,
            "accepted": self.accepted,
            "issues": [{"severity": i.severity, "code": i.code, "message": i.message}
                       for i in self.issues],
            "signals": self.signals,
        }


# ───────────────────────── 通用工具 ─────────────────────────

# 明确的 AI 拒答套话（"无法可靠计算"是财务官的正常结论，不在其列）
_REFUSAL_MARKERS = (
    "作为一个人工智能", "作为ai语言模型", "我是一个ai", "我无法访问互联网",
    "无法浏览网页", "无法访问实时", "我不能提供实时", "sorry, i cannot",
    "i cannot assist", "作为语言模型",
)

# 数字 + 单位（市场规模/用户量/金额），刻意避开纯编号与日期
_NUMBER_RE = re.compile(
    r"\d+(?:\.\d+)?\s*(?:万亿|亿元|亿|万|百万|千万元|千元|元)"
    r"|\d+(?:\.\d+)?\s*%"
    r"|\d{4,}\s*(?:用户|人|家|个|条|次|台|套|所|名)"
)
# 数字行里出现这些词，视为已标注来源/假设性质
_NUMBER_SOURCE_MARKERS = (
    "来源", "出处", "待验证", "假设", "估算", "示例", "约", "预计", "预测",
    "测算", "推算", "目标", "规划", "报告", "统计", "年鉴", "数据显示",
    "如果", "理论", "潜在", "上限", "保守", "乐观", "中性",
)

# 红线强信号（程序判定，不信任 LLM 自述）
_REDLINE_MARKERS = ("一票否决", "不得直接准入", "红线未清", "红线触发", "命中红线", "触发红线")
_FATAL_MARKERS = (
    "致命风险", "致命红线", "一票否决", "阻断上线", "阻断路演",
    "不得直接上线", "不得路演", "做了即违法",
)
# 致命信号必须锚定具体风险域，防止模型滥用"致命"
_FATAL_ANCHORS = (
    "备案", "授权", "许可", "资质", "合规", "违法", "法律", "监管",
    "未成年人", "二清", "支付牌照", "隐私", "个人信息", "数据安全",
    "伦理", "学历", "进校园", "准入", "内容审核", "知识产权",
)


def _lines(raw: str) -> List[str]:
    return [l.strip() for l in (raw or "").split("\n") if l.strip()]


def _has_any(text: str, markers) -> bool:
    return any(m in text for m in markers)


# 否定语境："未发现致命风险/不触发一票否决/无红线问题"不得被判定为命中。
# 先剔除"否定词（≤12字间隔）+ 致命/红线信号"片段，再做信号匹配。
_NEGATED_SIGNAL_RE = re.compile(
    r"(?:未发现|未识别|未触发|未命中|不存在|没有|未见|并无|无|不触发|不构成)"
    r"[^。；;\n]{0,12}"
    r"(?:致命风险|致命红线|一票否决|阻断上线|阻断路演|不得直接上线|不得路演|做了即违法|命中红线|触发红线|红线)"
)


def _positive_signals_only(raw: str) -> str:
    """剔除否定语境后的文本，用于致命/红线信号的肯定性判定。"""
    return _NEGATED_SIGNAL_RE.sub("", raw or "")


def _count_any(text: str, markers) -> int:
    return sum(text.count(m) for m in markers)


# 数字前后多少字内出现来源标记词，才算"该数字已标注"（避免长段里远处有个"来源"遮蔽裸数字）
_SOURCE_WINDOW = 16


def _unsourced_number_lines(raw: str, limit: int = 5) -> List[str]:
    hits = []
    for line in _lines(raw):
        unsourced_spans = []
        for m in _NUMBER_RE.finditer(line):
            window = line[max(0, m.start() - _SOURCE_WINDOW):m.end() + _SOURCE_WINDOW]
            if not _has_any(window, _NUMBER_SOURCE_MARKERS):
                unsourced_spans.append(m)
        if unsourced_spans:
            first = unsourced_spans[0]
            snippet = line[max(0, first.start() - 24):first.end() + 24]
            hits.append(snippet[:80])
            if len(hits) >= limit:
                break
    return hits


def _common_checks(vr: ValidationResult, raw: str, min_chars: int = 200):
    """所有 Agent 共用的闸门：空/过短/拒答。"""
    if not raw or not raw.strip():
        vr.issues.append(ValidationIssue(SEVERITY_ERROR, "EMPTY_OUTPUT", "报告为空，LLM 未返回有效内容"))
        return
    if len(raw.strip()) < min_chars:
        vr.issues.append(ValidationIssue(
            SEVERITY_ERROR, "OUTPUT_TOO_SHORT",
            f"报告仅 {len(raw.strip())} 字（下限 {min_chars} 字），疑似空响应或敷衍输出"))
    if _has_any(raw.lower(), _REFUSAL_MARKERS):
        vr.issues.append(ValidationIssue(
            SEVERITY_ERROR, "REFUSAL_DETECTED", "报告包含 AI 拒答套话，未完成分析任务"))


# ───────────────────────── 12 个领域规则 ─────────────────────────

def _check_user_insight(vr: ValidationResult, raw: str):
    if not _has_any(raw, ("痛点", "需求")):
        vr.issues.append(ValidationIssue(SEVERITY_WARNING, "USER_NO_PAINPOINT",
                                         "未出现'痛点/需求'核心概念，用户洞察可能跑题"))
    if not _has_any(raw, ("证据", "访谈", "观察", "待验证", "问卷", "行为")):
        vr.issues.append(ValidationIssue(SEVERITY_WARNING, "USER_NO_EVIDENCE_LEVEL",
                                         "缺少证据分级意识（证据/访谈/观察/待验证均未出现）"))
    if not _has_any(raw, ("付费", "购买", "买单", "收费")):
        vr.issues.append(ValidationIssue(SEVERITY_WARNING, "USER_PAYER_MISSING",
                                         "未区分使用者与付费者"))


def _check_market(vr: ValidationResult, raw: str):
    # TAM/SAM/SOM 是市场报告骨架，缺一不可（error → 返工）
    missing = [k for k in ("TAM", "SAM", "SOM") if k not in raw]
    if missing:
        vr.issues.append(ValidationIssue(
            SEVERITY_ERROR, "MARKET_MISSING_TIERS",
            f"市场分层不完整，缺少：{', '.join(missing)}（必须给出 TAM/SAM/SOM 三层）"))
    if not _has_any(raw, ("待验证", "假设", "估算", "来源", "测算", "示例")):
        vr.issues.append(ValidationIssue(SEVERITY_WARNING, "MARKET_NO_EVIDENCE_STATE",
                                         "市场数据未标注证据状态（来源/待验证/假设/估算）"))
    unsourced = _unsourced_number_lines(raw)
    if unsourced:
        vr.signals["unsourced_numbers"] = unsourced
        vr.issues.append(ValidationIssue(
            SEVERITY_WARNING, "MARKET_UNSOURCED_NUMBERS",
            f"发现 {len(unsourced)} 处规模数字未标注来源/假设性质"))


def _check_competitor(vr: ValidationResult, raw: str):
    groups = (
        ("直接竞品", ("直接竞品", "直接竞争", "直接对手")),
        ("间接竞品", ("间接竞品", "间接竞争")),
        ("替代方案", ("替代", "免费替代")),
    )
    missing = [name for name, ms in groups if not _has_any(raw, ms)]
    if missing:
        vr.issues.append(ValidationIssue(SEVERITY_WARNING, "COMPETITOR_MISSING_TIERS",
                                         f"竞品三分法不完整，缺少：{', '.join(missing)}"))
    if not _has_any(raw, ("差异", "壁垒", "护城河")):
        vr.issues.append(ValidationIssue(SEVERITY_WARNING, "COMPETITOR_NO_DIFFERENTIATION",
                                         "未给出差异化或壁垒判断"))


def _check_product(vr: ValidationResult, raw: str):
    if "MVP" not in raw and "mvp" not in raw:
        vr.issues.append(ValidationIssue(SEVERITY_WARNING, "PRODUCT_NO_MVP", "未出现 MVP 判断"))
    if not _has_any(raw, ("闭环", "核心任务", "核心功能")):
        vr.issues.append(ValidationIssue(SEVERITY_WARNING, "PRODUCT_NO_CORE_LOOP",
                                         "未明确核心任务/产品闭环"))


def _check_business(vr: ValidationResult, raw: str):
    if not _has_any(raw, ("付费方", "付费", "买单", "购买方")):
        vr.issues.append(ValidationIssue(SEVERITY_WARNING, "BUSINESS_NO_PAYER",
                                         "未识别付费方（谁掏钱）"))
    if not _has_any(raw, ("收入", "营收")):
        vr.issues.append(ValidationIssue(SEVERITY_WARNING, "BUSINESS_NO_REVENUE", "未出现收入来源分析"))
    if not _has_any(raw, ("成本", "费用结构")):
        vr.issues.append(ValidationIssue(SEVERITY_WARNING, "BUSINESS_NO_COST", "未出现成本结构分析"))


def _check_finance(vr: ValidationResult, raw: str):
    variables = ("LTV", "CAC", "收入", "成本", "利润", "客单价", "毛利", "单价")
    hit = [v for v in variables if v in raw]
    if len(hit) < 3:
        vr.issues.append(ValidationIssue(
            SEVERITY_ERROR, "FINANCE_MISSING_VARIABLES",
            f"关键财务变量不齐全（仅出现 {hit or '无'}，至少需要收入/成本/利润、LTV/CAC 等 3 项）"))
    if not _has_any(raw, ("假设", "若", "参数")):
        vr.issues.append(ValidationIssue(SEVERITY_WARNING, "FINANCE_NO_EXPLICIT_ASSUMPTION",
                                         "测算假设未显式声明"))
    # 结论程序归一
    if _has_any(raw, ("无法可靠计算", "无法计算", "不可靠", "无法测算")):
        vr.signals["conclusion"] = "无法可靠计算"
    elif hit:
        vr.signals["conclusion"] = "可计算"


def _check_growth(vr: ValidationResult, raw: str):
    concepts = ("飞轮", "AARRR", "冷启动", "渠道", "获客", "留存", "激活")
    hit = [c for c in concepts if c in raw]
    if len(hit) < 3:
        vr.issues.append(ValidationIssue(
            SEVERITY_WARNING, "GROWTH_MISSING_FRAMEWORK",
            f"增长框架要素不足（仅 {hit or '无'}，应覆盖飞轮/AARRR/冷启动/渠道等）"))


def _check_risk(vr: ValidationResult, raw: str):
    # 六类风险：合规法律 / 数据隐私 / 内容安全 / 系统运营 / 伦理社会 / 落地资质
    domains = (
        ("合规与法律", ("合规", "法律", "违法", "监管", "备案")),
        ("数据与隐私", ("数据", "隐私", "个人信息")),
        ("内容与安全", ("内容审核", "不良内容", "违规内容", "人身安全")),
        ("系统与运营", ("支付", "二清", "单点", "履约", "运营风险", "供应链")),
        ("伦理与社会", ("伦理", "未成年人", "歧视", "舆论", "社会")),
        ("落地与资质", ("资质", "许可", "ICP", "EDI", "经营主体", "进校园", "准入")),
    )
    covered = [name for name, ms in domains if _has_any(raw, ms)]
    if len(covered) < 4:
        vr.issues.append(ValidationIssue(
            SEVERITY_WARNING, "RISK_DOMAIN_INCOMPLETE",
            f"六类风险仅覆盖 {len(covered)} 类（{', '.join(covered) or '无'}），排查不充分"))
    vr.signals["risk_domains_covered"] = covered

    # ★ 系统规则：blocking 由程序判定，不信任 Agent 自述（先剔除"未发现致命风险"类否定语境）
    positive = _positive_signals_only(raw)
    blocking = _has_any(positive, _FATAL_MARKERS)
    vr.signals["blocking"] = blocking
    if blocking and not _has_any(raw, _FATAL_ANCHORS):
        vr.issues.append(ValidationIssue(
            SEVERITY_WARNING, "RISK_FATAL_WITHOUT_ANCHOR",
            "报告宣称致命/阻断风险，但未锚定具体风险域（备案/授权/合规/数据等），疑似泛化"))


def _check_red_team(vr: ValidationResult, raw: str):
    # 五维假设攻击：需求 / 付费 / 竞争 / 增长 / 壁垒
    # Phase 7-9：基于 5 份真实红队报告取证重订词根——
    # 付费维真实措辞是"付费者/采购/预算/客单价/单位经济"（旧表一个不识）；
    # 增长维去掉裸"渠道"（3 份样本的"渠道"全在壁垒段，属旧规则假阳性），
    # 改用获客/冷启动/转化率等增长语境词，覆盖后另以单维 warning 防漏。
    dims = (
        ("需求假设", ("需求假设", "需求不成立", "伪需求", "痛点", "真需求", "用户画像", "种子用户", "刚需")),
        ("付费假设", ("付费", "掏钱", "买单", "收费", "采购", "预算", "客单价", "定价",
                  "订阅", "收入来源", "单位经济", "LTV", "CAC")),
        ("竞争假设", ("竞争假设", "替代品", "现成", "竞品", "替代方案", "迁移成本", "迁移到")),
        ("增长假设", ("增长假设", "增长目标", "增长路径", "用户增长", "获客", "引流", "拉新",
                  "冷启动", "流量", "推广", "地推", "触达", "转化率", "用户留存", "留存率",
                  "复购", "渠道从哪", "获客渠道", "推广渠道")),
        ("壁垒假设", ("壁垒", "护城河", "巨头", "垄断")),
    )
    covered = [name for name, ms in dims if _has_any(raw, ms)]
    missing = [name for name, _ in dims if name not in covered]
    vr.signals["attack_dimensions"] = covered
    vr.signals["missing_dimensions"] = missing
    if len(covered) < 4:
        vr.issues.append(ValidationIssue(
            SEVERITY_ERROR, "REDTEAM_MISSING_DIMENSIONS",
            f"五维假设攻击仅覆盖 {len(covered)} 维（{', '.join(covered) or '无'}），"
            f"至少 4 维；缺失：{', '.join(missing)}"))
    elif missing:
        # 4/5：放行但点名缺哪一维——可修 warning，驱动一次返工补齐，
        # 防止"措辞放宽后真实缺口被静默放过"。
        vr.issues.append(ValidationIssue(
            SEVERITY_WARNING, "REDTEAM_DIM_MISSING_ONE",
            f"五维攻击覆盖 4 维，缺少对「{missing[0]}」的专门攻击"
            f"（需引用项目原文，给出待验证证据）"))
    # 无证据攻击防护：攻击必须带证伪/证据/假设锚点
    if not _has_any(raw, ("证据", "证伪", "假设", "如果", "什么情况下", "依据")):
        vr.issues.append(ValidationIssue(
            SEVERITY_WARNING, "REDTEAM_NO_EVIDENCE_ANCHOR",
            "攻击点缺少证据/证伪条件锚点，存在'无证据攻击'风险"))
    vr.signals["fatal_or_high_count"] = _count_any(raw, ("致命", "高风险"))


def _check_commander(vr: ValidationResult, raw: str):
    # 阶段判断四选一（以 commander_v1.md 模板为权威），程序归一
    conclusion = ""
    for line in _lines(raw):
        if _has_any(line, _COMMANDER_STAGES):
            conclusion = line[:60]
            break
    if not conclusion:
        vr.issues.append(ValidationIssue(
            SEVERITY_WARNING, "COMMANDER_NO_STAGE",
            "未给出项目阶段判断（想法验证/方案修正/路演准备/可进入路演）"))
    vr.signals["conclusion"] = conclusion

    # 行动项：只数字号化编号的行动行（"下一步行动："这类栏目标题不计入条数，
    # 否则"2 条行动 + 标题"会虚高为 3）。Phase 7-9：编号格式对齐 prompt 模板。
    action_lines = [l for l in _lines(raw) if _ACTION_BULLET_RE.match(l)]
    if len(action_lines) < 3:
        vr.issues.append(ValidationIssue(
            SEVERITY_WARNING, "COMMANDER_ACTIONS_LT_3",
            "下一步行动不足 3 条编号行动项：请在'下一步行动'下逐条列出至少 3 条，"
            "每条独占一行并以编号开头（支持 1. 2. 3. / ①②③ / 一、二、三、）"))


def _check_review(vr: ValidationResult, raw: str):
    # 五维成熟度评分缺一不可（error）
    dims = (
        ("用户与需求", ("用户", "需求")),
        ("市场与竞争", ("市场", "竞争")),
        ("产品与方案", ("产品", "方案")),
        ("商业与财务", ("商业", "财务")),
        ("风险与合规", ("风险", "合规")),
    )
    missing = [name for name, ms in dims if not _has_any(raw, ms)]
    if missing:
        vr.issues.append(ValidationIssue(
            SEVERITY_ERROR, "REVIEW_MISSING_DIMENSIONS",
            f"五维终审评分缺少：{', '.join(missing)}"))

    # 终审结论程序归一（四档）
    conclusion = ""
    lines = _lines(raw)
    for i, line in enumerate(lines):
        if "终审结论" in line:
            window = " ".join(lines[i:i + 3])
            conclusion = _classify_review_conclusion(window) or conclusion
    if not conclusion:
        conclusion = _classify_review_conclusion(raw)
    vr.signals["conclusion"] = conclusion

    # ★★ 红线系统规则：红线由程序判定（剔除否定语境）；红线与"准入"冲突时整次不接受
    positive = _positive_signals_only(raw)
    redline = _has_any(positive, _REDLINE_MARKERS)
    vr.signals["redline_triggered"] = redline
    if redline:
        admitted = _has_any(raw, ("准入路演", "同意路演", "可以路演"))
        safe_override = _has_any(raw, ("有条件", "暂缓", "不予", "不得", "暂不", "先不", "修订"))
        if admitted and not safe_override:
            vr.issues.append(ValidationIssue(
                SEVERITY_ERROR, "REDLINE_CONFLICT",
                "报告同时命中红线一票否决与'准入路演'，结论自相矛盾；红线未清不得准入"))


def _classify_review_conclusion(text: str) -> str:
    """把评审文本归一到四档结论；返回 '' 表示无法识别。"""
    if "材料不齐" in text or "不予终审" in text or "无法终审" in text:
        return "材料不齐，不予终审"
    if _has_any(text, ("暂缓", "暂不准入", "修订周期", "不予准入")):
        return "暂缓进入修订周期"
    if "有条件准入" in text:
        return "有条件准入路演"
    if "准入路演" in text or "同意准入" in text:
        return "准入路演"
    return ""


_PITCH_VERDICTS = ("有条件路演", "暂不建议", "无法评估", "可以路演")  # 顺序敏感：先匹配限定性结论


def _check_pitch(vr: ValidationResult, raw: str):
    # 路演结论四选一，程序归一（在结论行内定位判定词截取，避免长行开头截断丢失结论）
    conclusion = ""
    for line in _lines(raw):
        hit_pos, hit_word = -1, None
        for w in _PITCH_VERDICTS:
            p = line.find(w)
            if p >= 0:
                hit_pos, hit_word = p, w
                break
        if hit_pos >= 0:
            label_pos = line.find("结论")
            start = label_pos if 0 <= label_pos <= hit_pos else max(0, hit_pos - 8)
            conclusion = line[start:hit_pos + len(hit_word) + 16][:60]
            break
    if not conclusion:
        if "暂不建议" in raw:
            conclusion = "暂不建议路演"
        else:
            vr.issues.append(ValidationIssue(
                SEVERITY_WARNING, "PITCH_NO_CONCLUSION",
                "未给出路演结论（可以路演/有条件路演/暂不建议/无法评估）"))
    vr.signals["conclusion"] = conclusion
    # 击穿数系统统一口径
    vr.signals["pierced_count"] = raw.count("被击穿") + raw.count("击穿")
    if not _has_any(raw, ("追问", "评委", "问题")):
        vr.issues.append(ValidationIssue(SEVERITY_WARNING, "PITCH_NO_JUDGE_QUESTIONS",
                                         "缺少评委追问模拟"))


# ───────────────────────── 注册表与入口 ─────────────────────────

_RULES: Dict[str, Callable[[ValidationResult, str], None]] = {
    "user_insight": _check_user_insight,
    "market_analysis": _check_market,
    "competitor_analysis": _check_competitor,
    "product_design": _check_product,
    "business_model": _check_business,
    "finance": _check_finance,
    "growth_ops": _check_growth,
    "risk_review": _check_risk,
    "red_team": _check_red_team,
    "commander": _check_commander,
    "project_review": _check_review,
    "pitch_defense": _check_pitch,
}

# 红线被触发且结论冲突、返工仍不达标时，系统强制改判的兜底结论
REDLINE_FORCED_CONCLUSION = "暂缓进入修订周期（红线未清，系统强制）"


def validate_result(result: AgentResult) -> ValidationResult:
    """校验单个 AgentResult。未知 Agent 只跑通用闸门。"""
    vr = ValidationResult(agent_name=result.agent_name)
    raw = result.raw_output or ""
    _common_checks(vr, raw)
    rule = _RULES.get(result.agent_name)
    if rule is not None:
        rule(vr, raw)
    return vr


def apply_signals(result: AgentResult, vr: ValidationResult, *, force_redline: bool = False) -> AgentResult:
    """把程序提取的信号写回 AgentResult（系统规则覆盖 Agent 自报）。

    force_redline=True 用于返工后仍 REDLINE_CONFLICT 的终审：
    程序直接强制 redline_triggered=True 并改判结论。
    """
    signals = dict(vr.signals)
    if force_redline and result.agent_name == "project_review":
        signals["redline_triggered"] = True
        signals["conclusion"] = REDLINE_FORCED_CONCLUSION
        signals["redline_forced_by_system"] = True

    conclusion = signals.get("conclusion")
    if isinstance(conclusion, str) and conclusion:
        result.conclusion = conclusion
    for key, value in signals.items():
        if key == "conclusion":
            continue
        result.metadata[key] = value

    result.metadata["validation_accepted"] = vr.accepted
    if vr.warnings:
        result.metadata["validation_warnings"] = [
            f"[{i.code}] {i.message}" for i in vr.warnings]
    else:
        result.metadata.pop("validation_warnings", None)
    return result


def format_issues_for_repair(vr: ValidationResult) -> str:
    """把不接受原因格式化为返工指令片段（喂给 LLM）。"""
    lines = ["上一版报告未通过系统校验，必须修正以下问题后重新输出**完整报告**："]
    for i in vr.issues:
        tag = "【不合格】" if i.severity == SEVERITY_ERROR else "【建议】"
        lines.append(f"- {tag}{i.message}")
    lines.append("要求：只输出修正后的完整报告正文，不要解释你改了什么，不要输出道歉或过程性话术。")
    return "\n".join(lines)


# ─────────────── 跨 Agent 决策链一致性（Phase 7-6，程序级制衡证据） ───────────────
#
# 单棒校验只能保证"每份报告自身合格"；委员会的核心卖点是棒次之间的制衡，
# 因此在所有报告就绪后再做一次跨层一致性检查（只依赖程序信号，不看 LLM 自述）：
#
#   risk.blocking ──→ review.redline_triggered / 准入结论 ──→ pitch 路演结论
#
# 致命风险被程序判定后，评审不得给出无条件准入；红线被触发后，答辩不得给出任何路演放行。

def _classify_pitch_verdict(text: str) -> str:
    """路演结论归一为四档（返回 '' 表示无法识别）。"""
    if not text:
        return ""
    if "暂不建议" in text:
        return "暂不建议路演"
    if "无法评估" in text:
        return "无法评估"
    if "有条件路演" in text:
        return "有条件路演"
    if "可以路演" in text:
        return "可以路演"
    return ""


# 总指挥文本中明确的"放行"锚点（阶段判断/访谈通过等正常用词不在其列，防止误伤）
_COMMANDER_PASS_MARKERS = ("评审通过", "允许进入路演", "同意进入路演", "建议直接路演",
                           "可以直接进入路演", "无条件通过")
# "不允许进入路演/不建议直接路演"等否定放行，不得误判为放行
# 长否定词在前，"不"兜底放在最后（靠正则分支顺序优先匹配长词）
_COMMANDER_NEGATED_RE = re.compile(
    r"(?:不得|不准|不允许|不能|不予|不建议|不会|没有|无法|暂缓|禁止|未|不)[^。；;\n]{0,4}"
    r"(?:" + "|".join(_COMMANDER_PASS_MARKERS) + r")"
)


def cross_check_decisions(reports) -> List[ValidationIssue]:
    """对已完成的决策链（risk→commander→review→pitch）做跨层一致性检查。

    入参为 AgentResult 列表（成功/失败均可，失败棒不参与判定）；
    返回的 issue 全部挂在虚拟 agent_name='decision_chain' 上。
    """
    by_name = {r.agent_name: r for r in reports
               if getattr(r, "status", "") == "success"}
    issues: List[ValidationIssue] = []

    def add(severity, code, message):
        issues.append(ValidationIssue(severity, code, message))

    risk = by_name.get("risk_review")
    commander = by_name.get("commander")
    review = by_name.get("project_review")
    pitch = by_name.get("pitch_defense")

    risk_blocking = bool(risk and risk.metadata.get("blocking") is True)
    review_redline = bool(review and review.metadata.get("redline_triggered") is True)
    review_concl = (review.conclusion if review else "") or ""
    pitch_verdict = _classify_pitch_verdict((pitch.conclusion if pitch else "") or "")

    # 规则 1（error）：风险程序判定阻断级风险，评审既未触发红线、又给出无条件准入
    if risk_blocking and review and not review_redline and review_concl.strip() == "准入路演":
        add(SEVERITY_ERROR, "DECISION_RISK_REVIEW_CONFLICT",
            "风险审查官程序判定存在阻断级风险（blocking=True），但项目评审官未触发红线且给出"
            "「准入路演」——风险结论与终审结论冲突，红线应由系统兜底")
    # 规则 1b（warning）：阻断风险下仅给"有条件准入"，需确认条件即风险整改
    elif risk_blocking and review and not review_redline and "有条件准入" in review_concl:
        add(SEVERITY_WARNING, "DECISION_RISK_REVIEW_CONDITIONAL",
            "存在阻断级风险但评审给出「有条件准入路演」，准入条件必须显式绑定风险整改完成")

    # 规则 2（error）：红线触发/被系统强制后，路演答辩仍给出任何形式的放行
    if review_redline and pitch and pitch_verdict in ("可以路演", "有条件路演"):
        forced = "（评审结论为系统强制改判）" if review.metadata.get("redline_forced_by_system") else ""
        add(SEVERITY_ERROR, "DECISION_REDLINE_PITCH_CONFLICT",
            f"项目评审官已触发红线一票否决{forced}，但路演答辩官结论为「{pitch_verdict}」"
            "——红线未清不得路演，答辩结论不得推翻红线")

    # 规则 3（error）：阻断风险下，总指挥给出明确放行指令
    if risk_blocking and commander:
        craw = _positive_signals_only(commander.raw_output or "")
        craw = _COMMANDER_NEGATED_RE.sub("", craw)
        if _has_any(craw, _COMMANDER_PASS_MARKERS):
            add(SEVERITY_ERROR, "DECISION_RISK_COMMANDER_CONFLICT",
                "风险审查官程序判定存在阻断级风险，但创业总指挥给出明确放行指令"
                "（评审通过/允许进入路演等）——总指挥不得绕过风险结论")

    # 规则 4（warning）：终审与答辩结论方向性背离（答辩更保守时留痕，不阻断）
    if review and pitch and pitch_verdict in ("暂不建议路演", "无法评估") \
            and ("准入路演" in review_concl or "有条件准入" in review_concl):
        add(SEVERITY_WARNING, "DECISION_REVIEW_PITCH_DIVERGENCE",
            f"评审结论「{review_concl}」与路演答辩结论「{pitch_verdict}」方向背离，需人工复核分歧点")

    return issues
