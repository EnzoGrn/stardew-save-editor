"""Draws the app's icon (an original pixel-art save disk with a sprout on its label).

    pip install pillow
    python packaging/make_icon.py

Writes packaging/icon.ico (the .exe's icon) and web/static/favicon.png.
"""
from pathlib import Path

from PIL import Image

# 16x16 pixel art, one character per pixel
ART = """
................
.BBBBBBBBBBBB...
.BssLLLLLLLssB..
.BssLLLLDDLsssB.
.BssLLLLDDLsssB.
.BssLLLLLLLsssB.
.BssssssssssssB.
.BssssssssssssB.
.BswwwwwwwwwwsB.
.BswggwwwwGGwsB.
.BswgGGwwGGgwsB.
.BswwgGGGGgwwsB.
.BswwwwGGwwwwsB.
.BswwwwGGwwwwsB.
.BswwwwwwwwwwsB.
.BBBBBBBBBBBBBB.
"""
COLORS = {
    ".": (0, 0, 0, 0),
    "G": (58, 130, 46, 255),    # leaf
    "g": (120, 196, 72, 255),   # leaf light
    "B": (62, 36, 20, 255),     # outline
    "s": (176, 104, 52, 255),   # disk body
    "w": (250, 232, 190, 255),  # label
    "L": (214, 214, 206, 255),  # shutter
    "D": (90, 90, 96, 255),     # shutter slot
}

root = Path(__file__).resolve().parents[1]
rows = [r for r in ART.strip("\n").splitlines()]
image = Image.new("RGBA", (16, 16))
for y, row in enumerate(rows):
    for x, ch in enumerate(row):
        image.putpixel((x, y), COLORS[ch])

big = image.resize((256, 256), Image.NEAREST)
big.save(root / "packaging" / "icon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
image.resize((64, 64), Image.NEAREST).save(root / "web" / "static" / "favicon.png")
print("icon written")
