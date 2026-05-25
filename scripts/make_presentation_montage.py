from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw


def main() -> int:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("output/presentation_previews")
    files = sorted(src.glob("slide-*.png"))
    thumb_w, thumb_h = 480, 270
    pad, label_h, cols = 22, 34, 2
    rows = (len(files) + cols - 1) // cols
    sheet = Image.new(
        "RGB",
        (cols * (thumb_w + pad) + pad, rows * (thumb_h + label_h + pad) + pad),
        "#ede7dc",
    )
    draw = ImageDraw.Draw(sheet)
    for index, path in enumerate(files):
        image = Image.open(path).convert("RGB")
        image.thumbnail((thumb_w, thumb_h), Image.LANCZOS)
        x = pad + (index % cols) * (thumb_w + pad)
        y = pad + (index // cols) * (thumb_h + label_h + pad)
        bg = Image.new("RGB", (thumb_w, thumb_h), "#ffffff")
        bg.paste(image, ((thumb_w - image.width) // 2, (thumb_h - image.height) // 2))
        sheet.paste(bg, (x, y))
        draw.rectangle([x, y, x + thumb_w, y + thumb_h], outline="#c8bda9", width=2)
        draw.text((x, y + thumb_h + 8), path.stem, fill="#302a22")

    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("output/presentation_previews_montage.jpg")
    sheet.save(out, quality=92)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
