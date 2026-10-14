"""生成应用图标 assets/icon.ico（多尺寸）。

设计语言与托盘图标一致：深色底 + 蓝色高亮块，
用三个方块表示「多个桌面」，中间那块高亮表示「当前所在桌面」。

用法：python tools/make_icon.py
"""

from __future__ import annotations

import os

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets", "icon.ico")

BASE = 512  # 先按大尺寸绘制再降采样，边缘更干净
BG = (28, 28, 30, 255)        # #1C1C1E
CHIP = (72, 74, 78, 255)      # 未选中的方块
ACCENT = (10, 132, 255, 255)  # #0A84FF 当前桌面
SIZES = [16, 24, 32, 48, 64, 128, 256]


def rounded(draw: ImageDraw.ImageDraw, box, radius, fill) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def render() -> Image.Image:
    img = Image.new("RGBA", (BASE, BASE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    pad = int(BASE * 0.055)
    rounded(d, (pad, pad, BASE - pad, BASE - pad), radius=int(BASE * 0.22), fill=BG)

    # 三个方块：等宽等高，间距一致；中间为高亮（当前桌面）
    margin = int(BASE * 0.175)
    gap = int(BASE * 0.075)
    inner = BASE - margin * 2
    chip_w = (inner - gap * 2) // 3
    top = margin + int(BASE * 0.045)
    bottom = BASE - margin - int(BASE * 0.045)
    radius = max(2, int(chip_w * 0.22))

    for i in range(3):
        x0 = margin + i * (chip_w + gap)
        color = ACCENT if i == 1 else CHIP
        rounded(d, (x0, top, x0 + chip_w, bottom), radius=radius, fill=color)

    return img


def main() -> None:
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    big = render()
    frames = [big.resize((s, s), Image.LANCZOS) for s in SIZES]
    frames[-1].save(OUT, format="ICO", sizes=[(s, s) for s in SIZES])
    print(f"已生成 {OUT}（{', '.join(str(s) for s in SIZES)} px）")


if __name__ == "__main__":
    main()
