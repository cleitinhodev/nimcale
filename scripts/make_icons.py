#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the .ico files and PNG variants from the artwork in artwork/."""
import os
import sys

from PIL import Image, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ART = os.path.join(ROOT, "artwork")
OUT = os.path.join(ROOT, "nimcale", "assets")
SIZES = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]


def square_crop(im, margin=0.02):
    im = im.convert("RGBA")
    bbox = im.split()[3].point(lambda a: 255 if a > 8 else 0).getbbox() or (0, 0) + im.size
    x0, y0, x1, y1 = bbox
    side = int(max(x1 - x0, y1 - y0) * (1 + 2 * margin))
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(im.crop((cx - side // 2, cy - side // 2, cx - side // 2 + side, cy - side // 2 + side)), (0, 0))
    return canvas


def sized(im, s):
    out = im.resize((s, s), Image.LANCZOS)
    if s <= 48:
        out = out.filter(ImageFilter.UnsharpMask(radius=0.6, percent=60, threshold=1))
    return out


def make_ico(src, dst):
    im = square_crop(Image.open(src))
    frames = [sized(im, s) for s in SIZES]
    frames[-1].save(dst, format="ICO", sizes=[(s, s) for s in SIZES], append_images=frames[:-1])
    return im


def main():
    os.makedirs(os.path.join(OUT, "icons"), exist_ok=True)
    os.makedirs(os.path.join(OUT, "app_settings"), exist_ok=True)
    icon = make_ico(os.path.join(ART, "nimcale_icon.png"), os.path.join(OUT, "icons", "nimcale.ico"))
    fav = make_ico(os.path.join(ART, "nimcale_favicom.png"), os.path.join(OUT, "icons", "nimcale_window.ico"))
    icon.resize((512, 512), Image.LANCZOS).save(os.path.join(OUT, "icons", "nimcale_icon_512.png"), optimize=True)
    icon.resize((64, 64), Image.LANCZOS).save(os.path.join(OUT, "icons", "nimcale_icon_64.png"), optimize=True)
    fav.resize((256, 256), Image.LANCZOS).save(os.path.join(OUT, "icons", "nimcale_window_256.png"), optimize=True)
    # HelloImGui uses assets/app_settings/icon.png as the GLFW window icon
    fav.resize((256, 256), Image.LANCZOS).save(os.path.join(OUT, "app_settings", "icon.png"), optimize=True)
    for ico in ("nimcale.ico", "nimcale_window.ico"):
        p = os.path.join(OUT, "icons", ico)
        print(p, os.path.getsize(p), Image.open(p).info.get("sizes"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
