# SPDX-License-Identifier: GPL-3.0-or-later
"""Loading of the color texture and of the height map."""
import os

import numpy as np
from PIL import Image, ImageOps

Image.MAX_IMAGE_PIXELS = None          # user's own images: no decompression-bomb limit

MAX_TEX = 4096      # longest side of the color texture kept in memory / on the GPU
MAX_FULL = 8192     # longest side of the full-resolution height map (HD export source)
MAX_WORK = 2048     # longest side of the interactive working height map
IMG_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".tga", ".gif", ".ppm", ".pgm", ".exr")
FIT_STRETCH, FIT_FILL, FIT_CONTAIN = 0, 1, 2


def is_image_file(path):
    return os.path.splitext(str(path))[1].lower() in IMG_EXTS


def _open(path):
    im = Image.open(path)
    im.load()
    try:
        im = ImageOps.exif_transpose(im)
    except Exception:
        pass
    return im


def _cap(im, maxside, resample=Image.LANCZOS):
    w, h = im.size
    m = max(w, h)
    if m > maxside:
        k = maxside / float(m)
        im = im.resize((max(1, int(round(w * k))), max(1, int(round(h * k)))), resample)
    return im


class TextureImage:
    """Color image (PIL RGB) plus its alpha mask when the file had transparency."""

    def __init__(self, img, orig_size, path="", alpha=None):
        self.img = img
        self.orig_size = orig_size
        self.path = path
        self.alpha = alpha

    @property
    def size(self):
        return self.img.size


def load_texture(path):
    im = _open(path)
    orig = im.size
    alpha = None
    if im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info):
        rgba = im.convert("RGBA")
        a = np.asarray(rgba)[..., 3]
        if a.min() < 250:
            alpha = Image.fromarray(a, "L")
        bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        im = Image.alpha_composite(bg, rgba)
    elif im.mode in ("I;16", "I;16L", "I;16B", "I;16N", "I", "F"):
        a = np.asarray(im, dtype=np.float32)
        a = (a - a.min()) / max(1e-9, float(a.max() - a.min()))
        im = Image.fromarray((a * 255).astype(np.uint8), "L")
    im = _cap(im.convert("RGB"), MAX_TEX)
    if alpha is not None:
        alpha = _cap(alpha, MAX_TEX)
    return TextureImage(im, orig, path, alpha)


def texture_from_pil(img, path=""):
    img = _cap(img.convert("RGB"), MAX_TEX)
    return TextureImage(img, img.size, path)


def _to_float(im):
    mode = im.mode
    if mode in ("I;16", "I;16L", "I;16B", "I;16N"):
        return np.asarray(im).astype(np.float32) / 65535.0
    if mode == "I":
        a = np.asarray(im, dtype=np.float32)
        return a / (65535.0 if a.max() > 255 else 255.0)
    if mode == "F":
        a = np.asarray(im, dtype=np.float32)
        if a.max() > 1.0 or a.min() < 0.0:
            a = (a - a.min()) / max(1e-9, float(a.max() - a.min()))
        return a
    has_alpha = mode in ("RGBA", "LA", "PA") or (mode == "P" and "transparency" in im.info)
    if has_alpha:
        rgba = im.convert("RGBA")
        arr = np.asarray(rgba)
        alpha = arr[..., 3].astype(np.float32) / 255.0
        gray = np.asarray(rgba.convert("RGB").convert("L"), dtype=np.float32) / 255.0
        return gray * alpha if alpha.min() < 0.99 else gray
    if mode in ("RGB", "RGBX", "CMYK", "YCbCr", "P", "LAB", "HSV"):
        rgb = np.asarray(im.convert("RGB"), dtype=np.float32) / 255.0
        return rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114
    return np.asarray(im.convert("L"), dtype=np.float32) / 255.0


class HeightImage:
    """Height map: full resolution (for HD export) + working resolution (interactive)."""

    def __init__(self, full, orig_size, path=""):
        self.full = np.ascontiguousarray(np.clip(full, 0.0, 1.0), dtype=np.float32)
        self.orig_size = orig_size
        self.path = path
        h, w = self.full.shape
        m = max(w, h)
        if m > MAX_WORK:
            k = MAX_WORK / float(m)
            self.work = resize_field(self.full, (max(8, int(round(w * k))), max(8, int(round(h * k)))), "box")
        else:
            self.work = self.full

    @property
    def shape(self):
        return self.work.shape


def load_heightmap(path):
    im = _open(path)
    orig = im.size
    a = _to_float(im)
    h, w = a.shape
    m = max(w, h)
    if m > MAX_FULL:
        k = MAX_FULL / float(m)
        a = resize_field(a, (max(8, int(round(w * k))), max(8, int(round(h * k)))), "box")
    return HeightImage(a, orig, path)


_RESAMPLE = {"nearest": Image.NEAREST, "bilinear": Image.BILINEAR, "bicubic": Image.BICUBIC,
             "lanczos": Image.LANCZOS, "box": Image.BOX}


def resize_field(a, size, method="bicubic"):
    """Resize a float32 field to size=(w, h)."""
    h, w = a.shape
    if (w, h) == tuple(size):
        return a
    im = Image.fromarray(np.ascontiguousarray(a, dtype=np.float32), "F")
    out = np.asarray(im.resize(tuple(int(x) for x in size), _RESAMPLE.get(method, Image.BICUBIC)), dtype=np.float32)
    return np.ascontiguousarray(out)


def border_color(img):
    arr = np.asarray(img, dtype=np.float32) / 255.0
    border = np.concatenate([arr[:, 0], arr[:, -1], arr[0, :], arr[-1, :]], axis=0)
    return tuple(float(x) for x in np.median(border, axis=0))


def fit_base_scale(mode, tex_aspect, plate_aspect):
    """Base scale (sx, sy) of the texture over the height map: 0 stretch, 1 fill (crop), 2 contain."""
    ta, pa = float(tex_aspect), float(plate_aspect)
    if mode == FIT_STRETCH or abs(ta - pa) < 1e-6:
        return 1.0, 1.0
    if mode == FIT_FILL:
        return (ta / pa, 1.0) if ta > pa else (1.0, pa / ta)
    return (1.0, pa / ta) if ta > pa else (ta / pa, 1.0)
