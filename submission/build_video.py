# -*- coding: utf-8 -*-
"""合成 5 分钟内无配音字幕版演示视频（画面均为真实 UI 截图 + 真实 Run 引用）。
输出：submission/09_Demo演示_v1.mp4
"""
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import imageio

W, H, FPS = 1920, 1080, 25
FADE = 12  # 交叉淡化帧数
NAVY = (11, 31, 58)
NAVY2 = (16, 42, 74)
TEAL = (18, 181, 163)
ORANGE = (255, 138, 61)
RED = (229, 75, 75)
WHITE = (240, 246, 252)
GREY = (150, 170, 190)

FB = "C:/Windows/Fonts/msyhbd.ttc"
FR = "C:/Windows/Fonts/msyh.ttc"
ASSET = os.path.join(os.path.dirname(__file__), "video_assets")
OUT = os.path.join(os.path.dirname(__file__), "09_Demo演示_v1.mp4")


def f(size, bold=True):
    return ImageFont.truetype(FB if bold else FR, size)


def wrap(text, font, max_w):
    lines, cur = [], ""
    for ch in text:
        if ch == "\n":
            lines.append(cur); cur = ""; continue
        if font.getlength(cur + ch) > max_w and cur:
            lines.append(cur); cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    return lines


def base():
    img = Image.new("RGB", (W, H), NAVY)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 8], fill=TEAL)
    return img


def text_card(overline, title, subtitle="", title_size=88):
    img = base(); d = ImageDraw.Draw(img)
    x = 160
    d.rounded_rectangle([x, 250, x + 16, 300], 3, fill=TEAL)
    d.text((x + 36, 246), overline, font=f(30), fill=TEAL)
    y = 330
    for ln in wrap(title, f(title_size), W - 2 * x):
        d.text((x, y), ln, font=f(title_size), fill=WHITE)
        y += int(title_size * 1.35)
    if subtitle:
        y += 30
        for ln in wrap(subtitle, f(36, False), W - 2 * x):
            d.text((x, y), ln, font=f(36, False), fill=GREY)
            y += 56
    return img


def shot_card(png, caption):
    img = base()
    shot = Image.open(os.path.join(ASSET, png)).convert("RGB")
    # 暗色放大衬底
    bs = max(W / shot.width, H / shot.height)
    bg = shot.resize((int(shot.width * bs), int(shot.height * bs)))
    bg = bg.crop(((bg.width - W) // 2, (bg.height - H) // 2,
                  (bg.width - W) // 2 + W, (bg.height - H) // 2 + H))
    bg = Image.blend(bg, Image.new("RGB", (W, H), NAVY), 0.9)
    img.paste(bg, (0, 0))
    d0 = ImageDraw.Draw(img)
    d0.rectangle([0, 0, W, 8], fill=TEAL)
    box_w, box_h, top = 1620, 900, 30
    s = min(box_w / shot.width, box_h / shot.height)
    shot = shot.resize((int(shot.width * s), int(shot.height * s)))
    x = (W - shot.width) // 2
    img.paste(shot, (x, top))
    d0.rectangle([x - 2, top - 2, x + shot.width + 1, top + shot.height + 1],
                 outline=(64, 86, 112), width=2)
    d = ImageDraw.Draw(img, "RGBA")
    bar = Image.new("RGBA", (W, 120), (5, 14, 28, 225))
    img.paste(bar, (0, H - 120), bar)
    d.rectangle([0, H - 120, 10, H], fill=TEAL)
    lines = wrap(caption, f(34, False), W - 200)
    yy = H - 120 + (120 - len(lines) * 46) // 2
    for ln in lines:
        d.text((100, yy), ln, font=f(34, False), fill=WHITE)
        yy += 46
    return img


def quote_card(tag, quote, extra=""):
    img = base(); d = ImageDraw.Draw(img)
    x, y, w, hh = 170, 250, W - 340, 560
    d.rounded_rectangle([x, y, x + w, y + hh], 18, fill=NAVY2, outline=RED, width=3)
    chip_w = int(f(32).getlength(tag)) + 44
    d.rounded_rectangle([x + 40, y + 40, x + 40 + chip_w, y + 96], 10, fill=RED)
    d.text((x + 62, y + 48), tag, font=f(32), fill=WHITE)
    qf = f(52)
    lines = wrap("“" + quote + "”", qf, w - 140)
    yy = y + 140
    for ln in lines:
        d.text((x + 60, yy), ln, font=qf, fill=WHITE)
        yy += 82
    if extra:
        yy += 20
        for ln in wrap(extra, f(32, False), w - 140):
            d.text((x + 60, yy), ln, font=f(32, False), fill=GREY)
            yy += 50
    d.text((x + 40, y + hh - 56), "摘自真实运行 run_ecf846e4ff50 · 2026-09-19 · 红队审查报告原文",
           font=f(26, False), fill=GREY)
    return img


def evidence_card():
    img = base(); d = ImageDraw.Draw(img)
    d.text((160, 120), "工程侧事实", font=f(30), fill=TEAL)
    d.text((160, 170), "每一条都可复查", font=f(72), fill=WHITE)
    rows = [
        "12 位 AI 委员：8 位专家并行 → 红队对抗 → 总指挥 → 评审 → 路演答辩",
        "真实大模型 API 全链路：最近一次完整运行 12/12 成功，零返工",
        "DAG 编排：失败可断点续跑，降级 / 跳过 / 阻断状态全程留痕",
        "270 项离线验证全部通过，每次“通过”均绑定可复查证据",
    ]
    y = 360
    for r in rows:
        d.ellipse([166, y + 14, 190, y + 38], fill=TEAL)
        for ln in wrap(r, f(38, False), W - 420):
            d.text((214, y), ln, font=f(38, False), fill=WHITE)
            y += 58
        y += 24
    d.text((160, H - 110), "演示画面与引文均来自真实运行 run_ecf846e4ff50（2026-09-19）",
           font=f(28, False), fill=GREY)
    return img


SCENES = [
    (6.0, lambda: text_card("DEMO · 真实运行演示", "创想∞ AI创业委员会",
                            "不是帮你把创业故事讲得更漂亮，而是先让它经受一次委员会的挑战")),
    (14.0, lambda: shot_card("v2_01_home.png",
                             "提交一段创业想法，12 位 AI 委员自动组成专家、对抗、决策三个委员会")),
    (18.0, lambda: shot_card("v2_03_chain.png",
                             "一次真实大模型 API 全链路运行的终审结果：想法验证阶段，红线一票否决触发，暂不建议路演")),
    (18.0, lambda: quote_card("红队质疑官 · 付费假设（致命）",
                              "口头兴趣 ≠ 立项意向 ≠ 预算落实 ≠ 采购流程启动。",
                              "2 所学校老师的口头兴趣，不构成任何一条付费证据链。")),
    (18.0, lambda: quote_card("红队质疑官 · 增长假设（致命）",
                              "所谓“上线即服务”，实为“上线即静默”。",
                              "没有渠道入口、没有触发场景、没有种子用户获取动作——未提出任何冷启动路径。")),
    (24.0, lambda: shot_card("v2_04_redteam.png",
                             "真实 Run 的红队报告原文：五维假设逐一攻击，并列出待验证项与证据缺口")),
    (26.0, lambda: shot_card("v2_05_commander.png",
                             "创业总指挥不重新分析，只输出阶段结论与 3 条下一步行动——每一条都可验证")),
    (20.0, lambda: shot_card("v2_02_final.png",
                             "冲突链全程留痕：风险审查判定无致命风险，红队同时指出 3 个致命——矛盾被带进终审，而非被抹平")),
    (22.0, evidence_card),
    (12.0, lambda: text_card("创想∞", "AI 不只是回答，而是先质疑。",
                             "创想∞ AI创业委员会 · 让每一个创业想法先经受委员会的挑战", 80)),
]


def main():
    frames_bases = [build() for _, build in SCENES]
    black = Image.new("RGB", (W, H), (0, 0, 0))
    total = sum(int(d * FPS) for d, _ in SCENES)
    print("total seconds:", sum(d for d, _ in SCENES), "frames:", total)
    with imageio.get_writer(OUT, fps=FPS, codec="libx264", quality=8,
                            macro_block_size=None,
                            output_params=["-pix_fmt", "yuv420p", "-movflags", "+faststart"]) as w:
        # 开场黑场淡入（计入第 1 个场景时长）
        for i in range(FADE):
            w.append_data(np.asarray(Image.blend(black, frames_bases[0], i / FADE)))
        for si, ((dur, _), base_img) in enumerate(zip(SCENES, frames_bases)):
            n = int(dur * FPS)
            if si < len(SCENES) - 1:
                # 本场景静态帧 = 总帧 - 开场淡入（仅首个） - 结尾交叉淡化
                static_n = n - FADE - (FADE if si == 0 else 0)
                for _ in range(static_n):
                    w.append_data(np.asarray(base_img))
                nxt = frames_bases[si + 1]
                for i in range(FADE):
                    w.append_data(np.asarray(Image.blend(base_img, nxt, i / FADE)))
            else:
                # 末场景：全部静态后淡出黑场（淡出额外附加）
                for _ in range(n):
                    w.append_data(np.asarray(base_img))
                for i in range(FADE):
                    w.append_data(np.asarray(Image.blend(base_img, black, i / FADE)))
    print("written:", OUT, os.path.getsize(OUT), "bytes")


if __name__ == "__main__":
    main()
