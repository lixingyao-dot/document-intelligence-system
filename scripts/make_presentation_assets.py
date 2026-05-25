from __future__ import annotations

import sys
from pathlib import Path
from shutil import copy2

from PIL import Image, ImageDraw


def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit("usage: make_presentation_assets.py <image-dir>")

    src = Path(sys.argv[1])
    outdir = Path.cwd() / "output" / "presentation_assets"
    outdir.mkdir(parents=True, exist_ok=True)
    files = sorted(src.glob("*.png"))

    thumb_w, thumb_h = 360, 220
    pad = 24
    label_h = 42
    cols = 3
    rows = (len(files) + cols - 1) // cols
    sheet = Image.new(
        "RGB",
        (cols * (thumb_w + pad) + pad, rows * (thumb_h + label_h + pad) + pad),
        "#f7f4ed",
    )
    draw = ImageDraw.Draw(sheet)
    meta = []

    for i, path in enumerate(files):
        copy2(path, outdir / f"img{i + 1:02d}.png")
        image = Image.open(path).convert("RGB")
        meta.append((path.name, image.width, image.height, path.stat().st_size))
        image.thumbnail((thumb_w, thumb_h), Image.LANCZOS)

        x = pad + (i % cols) * (thumb_w + pad)
        y = pad + (i // cols) * (thumb_h + label_h + pad)
        bg = Image.new("RGB", (thumb_w, thumb_h), "#ffffff")
        bg.paste(image, ((thumb_w - image.width) // 2, (thumb_h - image.height) // 2))
        sheet.paste(bg, (x, y))
        draw.rectangle([x, y, x + thumb_w, y + thumb_h], outline="#d5cec0", width=2)
        draw.text((x, y + thumb_h + 8), f"{i + 1:02d} {path.name[:24]}", fill="#24201a")
        draw.text(
            (x, y + thumb_h + 25),
            f"{meta[-1][1]}x{meta[-1][2]}  {meta[-1][3] / 1024:.1f}KB",
            fill="#6b6255",
        )

    sheet_path = outdir / "contact_sheet.jpg"
    sheet.save(sheet_path, quality=92)
    print(f"CONTACT_SHEET\t{sheet_path}")
    for i, (name, width, height, size) in enumerate(meta, 1):
        print(f"{i:02d}\t{name}\t{width}x{height}\t{size / 1024:.1f}KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
