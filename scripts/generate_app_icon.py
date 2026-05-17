#!/usr/bin/env python3
"""Generate assets/app-icon.ico for Windows exe (no Python branding)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_ICO = ROOT / "assets" / "app-icon.ico"
OUT_PNG = ROOT / "frontend" / "public" / "app-icon.png"

# Brand colors
BG_TOP = (88, 101, 242)      # #5865F2
BG_BOTTOM = (67, 56, 202)    # #4338CA
DOC_FILL = (255, 255, 255)
DOC_LINE = (99, 102, 241)
ACCENT = (250, 204, 21)      # sparkle highlight


def _lerp(a: int, b: int, t: float) -> int:
    return int(a + (b - a) * t)


def _draw_icon(size: int):
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Rounded app tile background
    pad = max(1, size // 16)
    radius = max(4, size // 5)
    for y in range(size):
        t = y / max(size - 1, 1)
        r = _lerp(BG_TOP[0], BG_BOTTOM[0], t)
        g = _lerp(BG_TOP[1], BG_BOTTOM[1], t)
        b = _lerp(BG_TOP[2], BG_BOTTOM[2], t)
        draw.line([(pad, y), (size - pad, y)], fill=(r, g, b, 255))
    draw.rounded_rectangle(
        [pad, pad, size - pad - 1, size - pad - 1],
        radius=radius,
        fill=None,
        outline=(255, 255, 255, 40),
        width=max(1, size // 32),
    )

    # Document sheet
    m = size // 5
    doc_w = size - m * 2
    doc_h = int(doc_w * 1.15)
    doc_x0 = m
    doc_y0 = (size - doc_h) // 2
    doc_x1 = doc_x0 + doc_w
    doc_y1 = doc_y0 + doc_h
    fold = max(3, size // 8)

    draw.polygon(
        [
            (doc_x0, doc_y0),
            (doc_x1 - fold, doc_y0),
            (doc_x1, doc_y0 + fold),
            (doc_x1, doc_y1),
            (doc_x0, doc_y1),
        ],
        fill=DOC_FILL,
    )
    draw.polygon(
        [
            (doc_x1 - fold, doc_y0),
            (doc_x1, doc_y0 + fold),
            (doc_x1 - fold, doc_y0 + fold),
        ],
        fill=(226, 232, 240, 255),
    )

    line_x0 = doc_x0 + max(2, size // 14)
    line_x1 = doc_x1 - max(2, size // 10)
    y = doc_y0 + max(4, size // 10)
    line_h = max(1, size // 28)
    gap = max(2, size // 16)
    while y < doc_y1 - max(4, size // 8):
        draw.rectangle([line_x0, y, line_x1, y + line_h], fill=DOC_LINE)
        y += line_h + gap

    # Small accent dot (intelligence hint)
    if size >= 32:
        cx = doc_x1 - max(4, size // 10)
        cy = doc_y1 - max(4, size // 10)
        r = max(2, size // 18)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=ACCENT)

    return img


def main() -> None:
    try:
        from PIL import Image
    except ImportError as exc:
        raise SystemExit("Install Pillow first: pip install pillow") from exc

    OUT_ICO.parent.mkdir(parents=True, exist_ok=True)
    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)

    ico_sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img256 = _draw_icon(256)
    # Pillow 从 256 主图生成多尺寸 ICO（electron-builder / NSIS 要求含 256x256）
    img256.save(OUT_ICO, format="ICO", sizes=ico_sizes)
    img256.save(OUT_PNG, format="PNG")
    print(f"Wrote {OUT_ICO}")
    print(f"Wrote {OUT_PNG}")


if __name__ == "__main__":
    main()
