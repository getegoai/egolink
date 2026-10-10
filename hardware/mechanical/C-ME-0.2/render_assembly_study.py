"""Render a qualitative assembly relationship diagram, never a dimensional model."""

from __future__ import annotations

import argparse
from html import escape
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font", default="C:/Windows/Fonts/msyh.ttc")
    args = parser.parse_args()
    out = Path(__file__).resolve().parent
    width, height = 1800, 1370
    bg, ink, muted = "#F4F2ED", "#253A40", "#64767A"
    green, gold, blue = "#C3DED1", "#F3D79A", "#C9DDEE"
    img = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(img)
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<title>Ego Link 现板装配关系研究</title>',
        '<desc>不按比例的 A/B 装配关系示意，不表示实际器件位置、尺寸或装配通过。</desc>',
        f'<rect width="{width}" height="{height}" fill="{bg}"/>',
    ]

    def box(x, y, w, h, fill, stroke=None, radius=12):
        draw.rounded_rectangle((x, y, x+w, y+h), radius=radius, fill=fill, outline=stroke, width=2)
        svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{stroke or "none"}" stroke-width="2"/>')

    def line(x1, y1, x2, y2, color=muted, weight=2):
        draw.line((x1, y1, x2, y2), fill=color, width=weight)
        svg.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{weight}"/>')

    def text(x, y, value, size=25, color=ink):
        font = ImageFont.truetype(args.font, size)
        draw.text((x, y), value, font=font, fill=color, anchor="lt")
        svg.append(f'<text x="{x}" y="{y}" font-family="Microsoft YaHei,Noto Sans CJK SC,sans-serif" font-size="{size}" fill="{color}" dominant-baseline="text-before-edge">{escape(value)}</text>')

    def lines(x, y, values, size=24, color=ink, step=38):
        for i, value in enumerate(values):
            text(x, y+i*step, value, size, color)

    text(55, 40, "EGO LINK · 现板装配布局研究", 43)
    text(58, 105, "C-ME-0.2  /  2026-10-10     关系示意，不按比例；不代表实际元件位置或已通过装配。", 25, muted)

    for x, label, subtitle, variant in [
        (50, "A  主板与电池背叠", "首台样机优先评审：少改现板，接受厚度代价", "A"),
        (925, "B  电池局部错位", "减薄候选：增加平面面积，先验证低器件区", "B"),
    ]:
        box(x, 170, 825, 690, "#FFFFFF")
        text(x+28, 197, label, 34)
        text(x+28, 252, subtitle, 25, muted)
        text(x+35, 306, "外侧 / 前功能壳（镜头、声学件另行分区）", 22, muted)
        box(x+35, 349, 750, 18, "#9AA7A5", radius=5)
        box(x+55, 393, 174, 124, blue, "#7893AB")
        lines(x+76, 414, ["GNSS 分仓", "整体高度待测"], 22, step=37)
        line(x+247, 381, x+247, 609, "#C0C7C6")
        # The PCB occupies the same qualitative horizontal span in both diagrams.
        box(x+270, 417, 495, 16, "#3B8C74", radius=2)
        box(x+295, 385, 100, 32, green, "#7BA994", radius=3)
        box(x+562, 393, 125, 24, green, "#7BA994", radius=3)
        box(x+285, 433, 190, 70, "#C9CECD", "#82918E", radius=4)
        text(x+302, 452, "高器件区域", 22)
        box(x+530, 433, 175, 25, green, "#7BA994", radius=3)
        if variant == "A":
            line(x+270, 527, x+565, 527, "#BE9850", 4)
            box(x+270, 548, 295, 65, gold, "#BE9850", radius=8)
            text(x+288, 566, "电池 Pack ＋托盘", 23)
            box(x+35, 640, 750, 18, "#9AA7A5", radius=5)
            lines(x+30, 702, ["电池跨过高器件投影，离板间距由其制约。", "分仓使 GNSS 不再叠加到电池厚度上。", "实装壳外形允许大于既有概念参考尺寸。"], 25, step=43)
        else:
            # A qualitative extension beyond the PCB is deliberate, not measured.
            line(x+505, 485, x+800, 485, "#BE9850", 4)
            box(x+505, 506, 295, 65, gold, "#BE9850", radius=8)
            text(x+540, 525, "错位电池 Pack", 23)
            box(x+35, 602, 765, 18, "#9AA7A5", radius=5)
            text(x+45, 649, "示意：电池向板外延伸，壳体平面尺寸增加", 22, muted)
            lines(x+30, 702, ["仅在真实低器件区、线束与电池尺寸允许时成立。", "板外延伸也可能沿长度方向，图中方向未冻结。", "没有高度地图与碰撞检查，不能承诺减薄。"], 25, step=43)

    text(58, 889, "共同装配原则", 32)
    cards = [
        (50, "01  定位与承力", ["内托架支承 PCB；电池独立固定。", "板边压片需避开器件与走线。", "不把排孔、插座或软排线当固定件。"]),
        (640, "02  连接与维修", ["接插件配合高度、FPC 转弯都计入。", "先接被遮挡的线，再装电池托盘。", "GNSS、天线、镜头各有固定与应力释放。"]),
        (1230, "03  壳体与密封", ["后盖密封、声腔、窗口分别设计。", "USB 沿用现板位置；湿区方案待评审。", "腕带／背夹载荷传给承力壳与载体。"]),
    ]
    for x, title, body in cards:
        box(x, 948, 520, 208, "#E6EBE7")
        text(x+22, 972, title, 28)
        lines(x+22, 1022, body, 23, step=36)

    box(50, 1190, 1700, 122, "#E8DCC9")
    text(78, 1210, "尺寸输入仍缺：去工艺边 PCB 外形与双面高度 / GNSS 整体包络 / 电池 Pack 最大包络。", 26)
    text(78, 1258, "下一步：实测 → A/B 三维占位与干涉检查 → 干态装配样壳 → 带壳专项验证。", 25)
    text(58, 1331, "两版外观均保留；60×44×22 mm 外壳、48×34 mm 主板均非现板实测或已确认装配尺寸。", 21, muted)
    svg.append("</svg>")
    (out / "assembly-layout-study.svg").write_text("\n".join(svg)+"\n", encoding="utf-8")
    img.save(out / "assembly-layout-study.png", optimize=True)
    print("Created qualitative assembly SVG and PNG; no hardware dimensions were inferred.")


if __name__ == "__main__":
    main()
