# -*- coding: utf-8 -*-
"""路演 PPT 构建器（Phase 7-10）：python submission/build_pptx.py
内容与 05_路演PPT_初稿.md 一致，证据只用真实验证过的数字。"""
from pathlib import Path

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.oxml.ns import qn

NAVY = RGBColor(0x0B, 0x1F, 0x3A)
NAVY2 = RGBColor(0x14, 0x2E, 0x52)
TEAL = RGBColor(0x12, 0xB5, 0xA3)
ORANGE = RGBColor(0xFF, 0x8A, 0x3D)
RED = RGBColor(0xE5, 0x4B, 0x4B)
WHITE = RGBColor(0xF2, 0xF6, 0xFA)
GRAY = RGBColor(0xA9, 0xB8, 0xCC)
FONT = "微软雅黑"

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
BLANK = prs.slide_layouts[6]


def slide(bg=NAVY):
    s = prs.slides.add_slide(BLANK)
    s.background.fill.solid()
    s.background.fill.fore_color.rgb = bg
    return s


def box(s, x, y, w, h, fill=None, line=None, line_w=1.0, round_=False):
    shp = s.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE if round_ else MSO_SHAPE.RECTANGLE,
        Inches(x), Inches(y), Inches(w), Inches(h))
    if fill is None:
        shp.fill.background()
    else:
        shp.fill.solid()
        shp.fill.fore_color.rgb = fill
    if line is None:
        shp.line.fill.background()
    else:
        shp.line.color.rgb = line
        shp.line.width = Pt(line_w)
    shp.shadow.inherit = False
    return shp


def text(s, x, y, w, h, runs, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, sp_after=6):
    """runs: list of paragraphs; each paragraph = list of (txt, size, color, bold)."""
    tb = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    for i, para in enumerate(runs):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(sp_after)
        for (txt, size, color, bold) in para:
            r = p.add_run()
            r.text = txt
            r.font.size = Pt(size)
            r.font.color.rgb = color
            r.font.bold = bold
            r.font.name = FONT
            r.font._rPr.set(qn("w:eastAsia"), FONT)
    return tb


def tag(s, txt, x=0.55, y=0.55, color=TEAL):
    box(s, x, y, 0.12, 0.42, fill=color)
    text(s, x + 0.25, y - 0.06, 11.5, 0.6, [[(txt, 26, WHITE, True)]])


def footer(s, n):
    text(s, 0.55, 7.02, 9, 0.35,
         [[("创想∞ AI创业委员会", 10, GRAY, False)]])
    text(s, 12.2, 7.02, 0.8, 0.35, [[(str(n), 10, GRAY, False)]], align=PP_ALIGN.RIGHT)


# ── P1 封面 ──
s = slide()
box(s, 0, 0, 13.333, 0.14, fill=TEAL)
text(s, 0.9, 2.05, 11.5, 1.4, [[("创想∞ AI创业委员会", 48, WHITE, True)]])
text(s, 0.9, 3.35, 11.5, 0.8,
     [[("先质疑，后肯定 —— 12 位 AI 委员的创业评审系统", 22, TEAL, False)]])
text(s, 0.9, 4.45, 11.5, 1.2,
     [[("输入：高校创新创业场景的 AI 评审系统 · 学生免费、学校机构版采购 · 2 位老师口头感兴趣", 14, GRAY, False)],
      [("输出：三委员会接力审查 → 暂缓通过 + 3 条可验证行动", 14, GRAY, False)]], sp_after=8)
text(s, 0.9, 6.5, 11.5, 0.5, [[("路演汇报 · 2026.09", 13, ORANGE, True)]])

# ── P2 痛点 ──
s = slide()
tag(s, "为什么需要一个“反方委员会”", 0.55, 0.55)
for i, (h, b, c) in enumerate([
    ("反馈来得太晚", "学生往往路演当天才第一次被问“谁付钱、为什么是你”，致命问题发现即终局。", RED),
    ("评审资源稀缺", "一位老师面对几十上百份项目，口头鼓励多、结构化质疑少，初筛负荷重。", ORANGE),
    ("想法止步于自嗨", "需求未验证、付费方不清、壁垒缺失，却没有人专业、即时且敢说“不”。", TEAL),
]):
    x = 0.55 + i * 4.25
    box(s, x, 1.7, 3.9, 4.4, fill=NAVY2, round_=True)
    box(s, x, 1.7, 3.9, 0.12, fill=c)
    text(s, x + 0.3, 2.1, 3.3, 0.6, [[(h, 20, WHITE, True)]])
    text(s, x + 0.3, 2.95, 3.35, 2.8, [[(b, 15, GRAY, False)]])
text(s, 0.55, 6.35, 12.2, 0.6,
     [[("我们的答案：在见投资人之前，先让 AI 委员会把不靠谱的假设杀死。", 16, ORANGE, True)]])
footer(s, 2)

# ── P3 三委员会 12 Agent ──
s = slide()
tag(s, "三委员会 · 12 个分工冲突的智能体", 0.55, 0.55)
groups = [
    ("专家委员会 · 8 官并行尽调", TEAL,
     ["用户洞察", "市场分析", "竞品分析", "产品设计", "商业模式", "财务分析", "增长运营", "风险审查"]),
    ("对抗委员会 · 只攻击不安慰", RED, ["红队质疑官"]),
    ("决策委员会 · 分权裁决", ORANGE, ["创业总指挥", "项目评审官", "路演答辩官"]),
]
x = 0.55
for h, c, agents in groups:
    n = len(agents)
    h_box = max(2.4, 0.75 + n * 0.52)
    box(s, x, 1.65, 3.9, h_box + 0.5, fill=NAVY2, round_=True)
    box(s, x, 1.65, 3.9, 0.12, fill=c)
    text(s, x + 0.25, 1.9, 3.4, 0.6, [[(h, 15, WHITE, True)]])
    text(s, x + 0.25, 2.6, 3.45, h_box,
         [[("• " + a, 14, WHITE if a != "红队质疑官" else RED, a == "红队质疑官")] for a in agents],
         sp_after=7)
    x += 4.25
# 箭头
for ax in (4.62, 8.87):
    ar = box(s, ax, 3.05, 0.42, 0.42, fill=TEAL)
    ar.rotation = 0
text(s, 0.55, 6.35, 12.2, 0.6,
     [[("角色冲突是被设计出来的：专家分析、红队攻击、风险否决、指挥官与评审官分权。", 15, GRAY, False)]])
footer(s, 3)

# ── P4 核心闭环 ──
s = slide()
tag(s, "核心业务闭环：用户只提交一次想法", 0.55, 0.55)
steps = ["输入\n创业想法", "8 专家\n并行尽调", "红队\n五维质疑", "风险\n红线把关",
         "总指挥\n阶段结论", "评审官\n终审裁决", "路演官\n模拟问答", "12 份\n可追溯报告"]
for i, st_ in enumerate(steps):
    x = 0.45 + i * 1.62
    c = TEAL if i in (1, 7) else (RED if i in (2, 3) else ORANGE)
    box(s, x, 2.3, 1.42, 1.5, fill=NAVY2, line=c, line_w=1.5, round_=True)
    parts = st_.split("\n")
    text(s, x + 0.08, 2.45, 1.26, 1.25,
         [[(p, 13 if j == 0 else 11, WHITE if j == 0 else GRAY, j == 0)] for j, p in enumerate(parts)],
         align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, sp_after=2)
box(s, 0.45, 4.35, 11.1, 0.55, fill=NAVY2, round_=True)
text(s, 0.65, 4.43, 10.8, 0.45,
     [[("第一层 8 个 Agent 由依赖图自动调度、同时开工；后四层严格等待前置层完成。", 14, TEAL, True)]])
text(s, 0.55, 5.4, 12.2, 1.0,
     [[("并行不是人为开线程，而是执行器根据依赖图自动识别“当前谁可以跑”。", 15, WHITE, False)],
      [("真实运行：L0 八棒同秒启动，最大并发 8。", 14, GRAY, False)]], sp_after=8)
footer(s, 4)

# ── P5 红队案例 ──
s = slide()
tag(s, "红队质疑案例（真实 Run 原文节选）", 0.55, 0.55, RED)
box(s, 0.55, 1.55, 6.0, 4.7, fill=NAVY2, line=RED, line_w=1.5, round_=True)
text(s, 0.85, 1.78, 5.5, 0.5, [[("【付费假设｜致命】", 17, RED, True)]])
text(s, 0.85, 2.4, 5.45, 3.7,
     [[("“仅凭 2 所学校老师口头表示感兴趣，不构成任何付费证据——口头兴趣 ≠ 立项意向 ≠ 预算落实 ≠ 采购流程启动。”", 15, WHITE, False)],
      [("采购主体、预算科目、审批链条、历史同类采购案例、客单价、决策者角色——全部为零，采购即不存在。", 13, GRAY, False)]], sp_after=10)
box(s, 6.78, 1.55, 6.0, 4.7, fill=NAVY2, line=RED, line_w=1.5, round_=True)
text(s, 7.08, 1.78, 5.5, 0.5, [[("【增长假设｜致命】", 17, RED, True)]])
text(s, 7.08, 2.4, 5.45, 3.7,
     [[("“没有渠道入口、没有触发场景、没有种子用户获取动作。所谓‘上线即服务’实为‘上线即静默’。”", 15, WHITE, False)],
      [("增长目标缺乏 渠道 × 流量 × 转化率 × 时间 四要素推导，连最基础的地推成本都未测算。", 13, GRAY, False)]], sp_after=10)
text(s, 0.55, 6.45, 12.2, 0.5,
     [[("五维攻击：需求 / 付费 / 竞争 / 增长 / 壁垒，每一维都必须引用项目原文并给出“待验证证据”。", 14, TEAL, True)]])
footer(s, 5)

# ── P6 风险红线 ──
s = slide()
tag(s, "风险红线：一票否决由程序执行")
for i, t in enumerate(["备案与资质", "数据授权与隐私", "内容安全", "误导性建议", "伦理公平", "落地合规"]):
    x = 0.55 + (i % 3) * 4.25
    y = 1.7 + (i // 3) * 1.35
    box(s, x, y, 3.9, 1.05, fill=NAVY2, line=RED, line_w=1.2, round_=True)
    text(s, x + 0.3, y + 0.22, 3.4, 0.6, [[(t, 16, WHITE, True)]])
box(s, 0.55, 4.55, 12.23, 1.5, fill=NAVY2, line=ORANGE, line_w=1.5, round_=True)
text(s, 0.9, 4.78, 11.6, 1.1,
     [[("即使其他委员结论乐观，只要存在未处置的致命风险，程序会强制改判为“不予终审”，", 15, WHITE, False)],
      [("并在终审页留下“系统规则强制”留痕——否决权是系统规则，不是提示词里的一句请求。", 15, ORANGE, True)]], sp_after=6)
footer(s, 6)

# ── P7 技术架构 ──
s = slide()
tag(s, "为什么它“跑得稳、判得准”")
for i, (h, b, c) in enumerate([
    ("依赖图调度", "12 个 Agent 按 hard/soft 依赖自动分层并行；单棒失败按策略阻断或降级，不拖垮全流程。", TEAL),
    ("程序校验 + 自动返工", "每份输出先过确定性校验器；error 或结构性 warning 自动返工一次并留存证据，问题输出不进下游。", ORANGE),
    ("断点续跑", "Checkpoint 记录完整图状态；中断后重算可执行节点，已完成的棒本地回读、不重复花钱调用。", RED),
]):
    x = 0.55 + i * 4.25
    box(s, x, 1.7, 3.9, 3.9, fill=NAVY2, round_=True)
    box(s, x, 1.7, 3.9, 0.12, fill=c)
    text(s, x + 0.3, 2.1, 3.35, 0.6, [[(h, 19, WHITE, True)]])
    text(s, x + 0.3, 2.9, 3.35, 2.5, [[(b, 14, GRAY, False)]])
text(s, 0.55, 5.9, 12.2, 0.8,
     [[("工程观：LLM 是不受信任的执行者，程序负责最终约束。", 18, TEAL, True)]])
footer(s, 7)

# ── P8 真实验收数据 ──
s = slide()
tag(s, "验收数据：只展示有证据的")
cards = [
    ("12/12", "真实 API 全链路成功\nRun 可复查", TEAL),
    ("8", "委员真实并行\n两次真实运行 363.8s→267.8s*", ORANGE),
    ("270", "项离线自动化验收\n全部通过", RED),
    ("1", "条真实故障链验证\n失败→阻断/降级→续跑", TEAL),
]
for i, (big, small, c) in enumerate(cards):
    x = 0.55 + i * 3.18
    box(s, x, 1.8, 2.9, 3.2, fill=NAVY2, round_=True)
    box(s, x, 1.8, 2.9, 0.12, fill=c)
    text(s, x + 0.2, 2.25, 2.5, 1.0, [[(big, 44, c, True)]], align=PP_ALIGN.CENTER)
    text(s, x + 0.2, 3.45, 2.5, 1.2,
         [[(p, 13, WHITE if j == 0 else GRAY, j == 0)] for j, p in enumerate(small.split("\n"))],
         align=PP_ALIGN.CENTER, sp_after=3)
text(s, 0.55, 5.35, 12.2, 0.9,
     [[("* 267.8s 与 363.8s 是 2026 年 9 月两次真实运行的耗时对比，不是固定性能承诺。", 13, GRAY, False)],
      [("我们不包装未经统计验证的“准确率/性能指标”——诚实本身就是工程严谨性。", 13, GRAY, False)]], sp_after=6)
footer(s, 8)

# ── P9 Demo 引导 ──
s = slide()
tag(s, "现场演示：请盯三个瞬间")
for i, (n, t, b_, c) in enumerate([
    ("01", "看 8 位专家同秒开跑", "首页粘贴想法、点击开始，第一层 8 个 Agent 同时进入运行。", TEAL),
    ("02", "看红队的攻击原文", "针对这份项目原文逐维质疑，不是模板话术；可现场换一个想法再跑。", RED),
    ("03", "看冷静的终审结论", "“暂缓通过 + 3 条可验证行动”，以及 12 份可追溯报告与冲突链。", ORANGE),
]):
    y = 1.75 + i * 1.6
    box(s, 0.55, y, 1.35, 1.3, fill=c, round_=True)
    text(s, 0.55, y + 0.32, 1.35, 0.7, [[(n, 30, NAVY, True)]], align=PP_ALIGN.CENTER)
    box(s, 2.1, y, 10.68, 1.3, fill=NAVY2, round_=True)
    text(s, 2.45, y + 0.18, 10.1, 1.05,
         [[(t, 18, WHITE, True)], [(b_, 13, GRAY, False)]], sp_after=4)
text(s, 0.55, 6.6, 12.2, 0.5,
     [[("系统诚实比系统乐观更有价值：它真的可能对你说“不通过”。", 15, ORANGE, True)]])
footer(s, 9)

# ── P10 价值与收尾 ──
s = slide()
box(s, 0, 0, 13.333, 0.14, fill=ORANGE)
for i, (h, b) in enumerate([
    ("对学生", "在投入时间与金钱前，提前经历一次严苛、诚实的委员会拷问。"),
    ("对教师", "12 维结构化初筛与可追溯报告，大幅降低人工评审负荷。"),
    ("对高校", "双创课程的可复盘教学工具：每个想法都留下完整审查证据链。"),
]):
    x = 0.55 + i * 4.25
    box(s, x, 1.6, 3.9, 2.9, fill=NAVY2, round_=True)
    text(s, x + 0.3, 1.95, 3.35, 0.6, [[(h, 22, TEAL, True)]])
    text(s, x + 0.3, 2.85, 3.35, 1.5, [[(b, 15, WHITE, False)]])
text(s, 0.9, 5.1, 11.5, 1.2,
     [[("在见投资人之前，先见你的 AI 委员会。", 30, WHITE, True)]], align=PP_ALIGN.CENTER)
text(s, 0.9, 6.35, 11.5, 0.6,
     [[("创想∞ AI创业委员会", 16, ORANGE, True)]], align=PP_ALIGN.CENTER)

out = Path(__file__).resolve().parent / "07_路演PPT_v1.pptx"
prs.save(str(out))
print("saved:", out, out.stat().st_size, "bytes,", len(list(prs.slides)), "slides")
