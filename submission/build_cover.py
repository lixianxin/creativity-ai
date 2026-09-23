# -*- coding: utf-8 -*-
"""封面图 v2（16:9，1920x1080）：浅色主题 · 创想∞ AI创业委员会
风格：现代 AI SaaS + 创业委员会 + 产品化工作台。暖白底 + 白卡 + 委员会语义色。"""
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H = 1920, 1080
BG = (247, 248, 250)         # #F7F8FA
SURFACE = (255, 255, 255)
BORDER = (233, 231, 227)
PRIMARY = (91, 99, 232)       # #5B63E8
EXPERT = (79, 125, 255)       # #4F7DFF
RED = (232, 91, 91)           # #E85B5B
DECISION = (122, 101, 216)    # #7A65D8
FG = (26, 26, 46)
MUTED = (107, 114, 128)
FB = "C:/Windows/Fonts/msyhbd.ttc"
FR = "C:/Windows/Fonts/msyh.ttc"


def font(s, b=True):
    return ImageFont.truetype(FB if b else FR, s)


img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img, "RGBA")

# 顶部主色细线
d.rectangle([0, 0, W, 8], fill=PRIMARY)

# 背景装饰：右侧柔和主色光晕（不刺眼）
glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
gd = ImageDraw.Draw(glow)
gd.ellipse([W - 520, -180, W + 200, 540], fill=(91, 99, 232, 26))
gd.ellipse([W - 300, 400, W + 100, 800], fill=(122, 101, 216, 18))
glow = glow.filter(ImageFilter.GaussianBlur(40))
img.paste(glow, (0, 0), glow)
d = ImageDraw.Draw(img, "RGBA")

# 中央"会议桌"椭圆（浅色描边）
d.ellipse([420, 640, W - 420, 900], outline=(217, 220, 229), width=2)

# 12 个委员面板沿椭圆前半弧排布，红队位抬起
N = 12
for i in range(N):
    ang = math.pi * (0.06 + 0.88 * i / (N - 1))
    cx = W / 2 + 720 * math.cos(math.pi - ang)
    cy = 770 + 230 * math.sin(math.pi - ang) * 0.62
    is_red = (i == 8)
    is_decision = i in (9, 10, 11)
    pw, ph = 104, 74
    raise_y = -52 if is_red else 0
    if is_red:
        accent = RED
        soft = (253, 236, 236)
    elif is_decision:
        accent = DECISION
        soft = (242, 238, 251)
    else:
        accent = EXPERT
        soft = (238, 243, 255)
    # 阴影
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle(
        [cx - pw / 2 + 3, cy - ph / 2 + raise_y + 5, cx + pw / 2 + 3, cy + ph / 2 + raise_y + 5],
        14, fill=(16, 24, 40, 18))
    sh = sh.filter(ImageFilter.GaussianBlur(6))
    img.paste(sh, (0, 0), sh)
    d = ImageDraw.Draw(img, "RGBA")
    # 面板
    d.rounded_rectangle([cx - pw / 2, cy - ph / 2 + raise_y, cx + pw / 2, cy + ph / 2 + raise_y],
                        14, fill=SURFACE, outline=BORDER, width=1)
    # 顶部色条
    d.rounded_rectangle([cx - pw / 2, cy - ph / 2 + raise_y, cx + pw / 2, cy - ph / 2 + raise_y + 8],
                        14, fill=accent)
    d.rectangle([cx - pw / 2, cy - ph / 2 + raise_y + 4, cx + pw / 2, cy - ph / 2 + raise_y + 8], fill=accent)
    # 内容横线
    line_c = accent if is_red else (180, 188, 200)
    for k in range(3):
        ww = pw - 34 - (k * 10)
        d.rounded_rectangle([cx - pw / 2 + 18, cy - 14 + k * 15 + raise_y,
                             cx - pw / 2 + 18 + ww, cy - 8 + k * 15 + raise_y], 3, fill=line_c)
    if is_red:
        # 红队"举手"圆点
        d.ellipse([cx - 8, cy - ph / 2 + raise_y - 30, cx + 8, cy - ph / 2 + raise_y - 14], fill=RED)

# 标题区
title = "创想∞ AI创业委员会"
tf = font(104)
tw = tf.getlength(title)
d.text(((W - tw) / 2, 150), title, font=tf, fill=FG)

# 主色强调条
bar_w = 120
d.rounded_rectangle([(W - bar_w) / 2, 300, (W + bar_w) / 2, 308], 4, fill=PRIMARY)

sub = "让 AI 先质疑你的创业想法"
sf = font(40, False)
sw = sf.getlength(sub)
d.text(((W - sw) / 2, 350), sub, font=sf, fill=PRIMARY)

tagline = "不是帮你把商业计划写得更漂亮，而是先让它经受一场委员会的挑战"
tgf = font(26, False)
tw2 = tgf.getlength(tagline)
d.text(((W - tw2) / 2, 420), tagline, font=tgf, fill=MUTED)

# 底部标签
labels = ["12 Agent", "专家 · 对抗 · 决策三委员会", "5 层 DAG · 真实全链路运行"]
lf = font(28)
gap = 48
widths = [lf.getlength(t) + 56 for t in labels]
total_w = sum(widths) + gap * (len(labels) - 1)
xx = (W - total_w) / 2
colors = [EXPERT, RED, DECISION]
for t, ww, c in zip(labels, widths, colors):
    d.rounded_rectangle([xx, 980, xx + ww, 1036], 28, fill=SURFACE, outline=BORDER, width=1)
    d.ellipse([xx + 22, 999, xx + 36, 1013], fill=c)
    d.text((xx + 48, 988), t, font=lf, fill=FG)
    xx += ww + gap

out = str(Path(__file__).resolve().parent / "06_封面图_16x9.png")
img.save(out)
print("saved", out)
