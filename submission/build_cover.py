# -*- coding: utf-8 -*-
"""封面图（16:9，1920x1080）：品牌色 + 12 委员面板主视觉（1 个红色面板"举手质疑"）。"""
import math
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H = 1920, 1080
NAVY = (11, 31, 58)
NAVY_D = (7, 19, 38)
TEAL = (18, 181, 163)
ORANGE = (255, 138, 61)
RED = (229, 75, 75)
WHITE = (240, 246, 252)
GREY = (152, 172, 192)
FB, FR = "C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/msyh.ttc"


def font(s, b=True):
    return ImageFont.truetype(FB if b else FR, s)


img = Image.new("RGB", (W, H), NAVY_D)
# 纵向渐变
top = Image.new("RGB", (1, H))
for y in range(H):
    t = y / H
    top.putpixel((0, y), tuple(int(NAVY_D[i] + (NAVY[i] - NAVY_D[i]) * t) for i in range(3)))
img.paste(top.resize((W, H)), (0, 0))
d = ImageDraw.Draw(img, "RGBA")

# 长桌椭圆（透视感扁椭圆）
glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
gd = ImageDraw.Draw(glow)
gd.ellipse([360, 610, W - 360, 900], fill=(18, 181, 163, 46), outline=(18, 181, 163, 130), width=3)
glow = glow.filter(ImageFilter.GaussianBlur(14))
img.paste(glow, (0, 0), glow)
d = ImageDraw.Draw(img, "RGBA")
d.ellipse([360, 610, W - 360, 900], outline=(18, 181, 163, 160), width=3)

# 12 个面板沿椭圆排布，红色"质疑官"抬起
N = 12
for i in range(N):
    ang = math.pi * (0.06 + 0.88 * i / (N - 1))  # 沿前半弧
    cx = W / 2 + 760 * math.cos(math.pi - ang)
    cy = 755 + 250 * math.sin(math.pi - ang) * 0.62
    red = (i == 8)  # 红队质疑官位
    pw, ph = 96, 70
    raise_y = -46 if red else 0
    fill = RED if red else (18, 44, 76)
    outline_c = RED if red else (90, 120, 150)
    if red:
        g2 = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(g2).rounded_rectangle(
            [cx - pw / 2 - 10, cy - ph / 2 + raise_y - 10, cx + pw / 2 + 10, cy + ph / 2 + raise_y + 10],
            14, fill=(229, 75, 75, 150))
        g2 = g2.filter(ImageFilter.GaussianBlur(18))
        img.paste(g2, (0, 0), g2)
        d = ImageDraw.Draw(img, "RGBA")
    d.rounded_rectangle([cx - pw / 2, cy - ph / 2 + raise_y, cx + pw / 2, cy + ph / 2 + raise_y],
                        12, fill=fill, outline=outline_c, width=2)
    # 面板上的横线（拟屏幕内容）
    line_c = (255, 255, 255, 220) if red else (140, 168, 196, 200)
    for k in range(3):
        ww = pw - 34 - (k * 12 if not red else 0)
        d.rounded_rectangle([cx - pw / 2 + 17, cy - 16 + k * 15 + raise_y,
                             cx - pw / 2 + 17 + ww, cy - 10 + k * 15 + raise_y], 3, fill=line_c)
    if red:
        d.ellipse([cx - 7, cy - ph / 2 + raise_y - 26, cx + 7, cy - ph / 2 + raise_y - 12], fill=RED)

# 顶部细条
d.rectangle([0, 0, W, 8], fill=TEAL)

# 标题区
title = "创想∞ AI创业委员会"
tf = font(108)
tw = tf.getlength(title)
d.text(((W - tw) / 2, 150), title, font=tf, fill=WHITE)
sub = "不是帮你把创业故事讲得更漂亮，而是先让它经受一次委员会的挑战"
sf = font(38, False)
d.text(((W - sf.getlength(sub)) / 2, 310), sub, font=sf, fill=GREY)

# 底部标签
labels = ["12 位 AI 委员", "专家 · 对抗 · 决策三委员会", "真实大模型全链路评审"]
lf = font(30)
gap = 56
widths = [lf.getlength(t) + 48 for t in labels]
total_w = sum(widths) + gap * (len(labels) - 1)
xx = (W - total_w) / 2
for t, ww in zip(labels, widths):
    d.rounded_rectangle([xx, 970, xx + ww, 1026], 28, outline=(90, 120, 150), width=2)
    d.text((xx + 24, 980), t, font=lf, fill=(190, 208, 226))
    xx += ww + gap

out = "submission/06_封面图_16x9.png"
img.save(out)
print("saved", out)
