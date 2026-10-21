#!/usr/bin/env python3
"""从品牌源图生成 UnionFlow 前端 logo / favicon 资源。

源图为 `dify/images/new/*.png`（纯图形 mark，无文字），本脚本：
  1. 按 alpha 边界自动裁切，再居中补白成正方形；
  2. 输出方形图标（嵌入对话页头像/头部，1x/2x/3x）与多尺寸 favicon.ico；
  3. 输出横版 lockup（图形 + "UnionFlow" 文字）的浅色/深色两版，以及内嵌栅格的 logo.svg。

依赖 Pillow（`dify-api` 镜像自带，无需联网安装）。

用法（仓库根目录）：
    docker run --rm --user "$(id -u):$(id -g)" --entrypoint /bin/bash \
      -v "$PWD":/repo -v /usr/share/fonts/truetype/dejavu:/fonts:ro \
      -w /repo dify-api:1.17.1-custom \
      -c "python3 scripts/brand/generate_brand_assets.py"

输出全部落在 web/public/ 下，覆盖同名旧资源。
"""

from __future__ import annotations

import base64
import io
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont  # type: ignore[import-not-found]  # 仅存在于 dify-api 镜像内

BRAND_NAME = "UnionFlow"
SRC_DIR = Path("images/new")
SITE_DIR = Path("web/public")
LOGO_DIR = SITE_DIR / "logo"
FONT_BOLD = Path("/fonts/DejaVuSans-Bold.ttf")

# 视觉参数
ALPHA_THRESHOLD = 8
SQUARE_MARGIN = 0.06  # 方形画布四周留白比例
LOCKUP_TEXT_HEIGHT = 0.46  # 文字高度相对图形高度
LOCKUP_GAP = 0.16  # 图形与文字间距，相对图形高度
COLOR_LIGHT = (16, 24, 40, 255)  # 浅色背景下的文字色
COLOR_DARK = (255, 255, 255, 255)  # 深色背景下的文字色


def load_source() -> Image.Image:
    candidates = sorted(SRC_DIR.glob("*.png"))
    if len(candidates) != 1:
        raise SystemExit(f"期望 {SRC_DIR} 下有且只有一张源图，实际: {candidates}")
    return Image.open(candidates[0]).convert("RGBA")


def square_master(src: Image.Image) -> Image.Image:
    # 源图边缘有 alpha≤8 的淡噪声，先清零再取 bbox，否则裁切会包住整张画布
    alpha = src.getchannel("A").point(lambda v: 0 if v <= ALPHA_THRESHOLD else v)
    src.putalpha(alpha)
    bbox = src.getbbox()
    if bbox is None:
        raise SystemExit("源图完全透明")
    mark = src.crop(bbox)
    side = int(max(mark.size) * (1 + SQUARE_MARGIN * 2))
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(mark, ((side - mark.width) // 2, (side - mark.height) // 2), mark)
    print(f"源图 {src.size} → alpha bbox {bbox} → mark {mark.size} → 方形 {canvas.size}")
    return canvas


def build_lockup(mark: Image.Image, color: tuple[int, int, int, int], emblem_height: int) -> Image.Image:
    font_size = max(8, int(emblem_height * LOCKUP_TEXT_HEIGHT))
    font = ImageFont.truetype(str(FONT_BOLD), font_size)
    gap = int(emblem_height * LOCKUP_GAP)

    emblem = mark.resize((emblem_height, emblem_height), Image.LANCZOS)
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    text_box = probe.textbbox((0, 0), BRAND_NAME, font=font)
    text_w = text_box[2] - text_box[0]

    width = emblem_height + gap + text_w
    canvas = Image.new("RGBA", (width, emblem_height), (0, 0, 0, 0))
    canvas.alpha_composite(emblem, (0, 0))
    draw = ImageDraw.Draw(canvas)
    # 用 ascender 对齐，让文字在图形高度内视觉居中
    ascent, descent = font.getmetrics()
    text_y = (emblem_height - (ascent + descent)) // 2
    draw.text((emblem_height + gap - text_box[0], text_y), BRAND_NAME, font=font, fill=color)
    return canvas


def save_png(img: Image.Image, path: Path) -> None:
    img.save(path, "PNG", optimize=True)
    report(path, img)


def report(path: Path, img: Image.Image) -> None:
    opaque = img.width * img.height
    if img.mode == "RGBA":
        opaque = sum(img.getchannel("A").histogram()[17:])
    print(f"  {path}  {img.size[0]}x{img.size[1]} {img.mode} 不透明像素={opaque} {path.stat().st_size}B")


def svg_wrapper(lockup: Image.Image) -> str:
    buf = io.BytesIO()
    lockup.save(buf, "PNG", optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode()
    w, h = lockup.size
    return (
        f'<svg width="{w // 2}" height="{h // 2}" viewBox="0 0 {w} {h}" fill="none" '
        f'xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">\n'
        f"  <!-- 品牌源图为栅格素材，此处内嵌 2x PNG；拿到矢量源后可替换为 path。 -->\n"
        f'  <image width="{w}" height="{h}" xlink:href="data:image/png;base64,{b64}"/>\n'
        f"</svg>\n"
    )


def main() -> int:
    LOGO_DIR.mkdir(parents=True, exist_ok=True)
    master = square_master(load_source())

    print("方形图标:")
    icons = {
        "logo-embedded-chat-avatar.png": 80,
        "logo-embedded-chat-header.png": 48,
        "logo-embedded-chat-header@2x.png": 96,
        "logo-embedded-chat-header@3x.png": 144,
    }
    for name, size in icons.items():
        save_png(master.resize((size, size), Image.LANCZOS), LOGO_DIR / name)

    favicon_sizes = [16, 32, 48, 64, 128]
    fav = LOGO_DIR.parent / "favicon.ico"
    master.resize((128, 128), Image.LANCZOS).save(fav, "ICO", sizes=[(s, s) for s in favicon_sizes])
    print(f"  {fav}  {favicon_sizes} {fav.stat().st_size}B")

    print("横版 lockup:")
    light = build_lockup(master, COLOR_LIGHT, 168)
    dark = build_lockup(master, COLOR_DARK, 168)
    save_png(light, LOGO_DIR / "logo-site.png")
    save_png(dark, LOGO_DIR / "logo-site-dark.png")

    svg_path = LOGO_DIR / "logo.svg"
    svg_path.write_text(svg_wrapper(light), encoding="utf-8")
    print(f"  {svg_path}  viewBox 0 0 {light.width} {light.height} {svg_path.stat().st_size}B")
    print(f"\nlockup 宽高比 = {light.width / light.height:.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())