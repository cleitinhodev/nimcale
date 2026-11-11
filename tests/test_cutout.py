# SPDX-License-Identifier: GPL-3.0-or-later
"""Automatic outline: imported images are cut along their own outline, not the coin circle."""
import argparse

import numpy as np
import pytest
from PIL import Image, ImageDraw

from nimcale.core import cutout, images
from nimcale.core.params import ModelParams
from nimcale.core.pipeline import Pipeline, adjust_levels


def star_points(cx, cy, r1, r2, n=5):
    pts = []
    for i in range(2 * n):
        r = r1 if i % 2 == 0 else r2
        a = np.pi / 2 + i * np.pi / n
        pts.append((cx + r * np.cos(a), cy - r * np.sin(a)))
    return pts


def make_star(path, bg="black", fg=200, size=(400, 300), mode="L"):
    if mode == "RGBA":
        im = Image.new("RGBA", size, (0, 0, 0, 0))
        ImageDraw.Draw(im).polygon(star_points(size[0] / 2, size[1] / 2, 130, 55), fill=(fg, fg, fg, 255))
    else:
        im = Image.new("L", size, 0 if bg == "black" else 255)
        ImageDraw.Draw(im).polygon(star_points(size[0] / 2, size[1] / 2, 130, 55), fill=fg)
    im.save(path)
    return path


def star_truth(size=(400, 300)):
    im = Image.new("L", size, 0)
    ImageDraw.Draw(im).polygon(star_points(size[0] / 2, size[1] / 2, 130, 55), fill=255)
    return np.asarray(im) > 127


def iou(a, b):
    return (a & b).sum() / float((a | b).sum())


def auto_params():
    p = ModelParams()
    p.cutout, p.shape = True, "auto"
    return p


def plate_mask(res):
    return (res.sdf > 0)[::-1]          # plate convention (row 0 = v 0) -> image convention


def resized_truth(shape):
    t = Image.fromarray(star_truth().astype(np.uint8) * 255).resize((shape[1], shape[0]), Image.NEAREST)
    return np.asarray(t) > 127


@pytest.mark.parametrize("bg", ["black", "white"])
def test_star_heightmap_outline_follows_it(tmp_path, bg):
    hm = images.load_heightmap(make_star(str(tmp_path / "s.png"), bg=bg, fg=200 if bg == "black" else 60))
    p = auto_params()
    res = Pipeline().compute(hm, p)
    assert res.info["bg"] == ("dark" if bg == "black" else "white")
    m = plate_mask(res)
    assert iou(m, resized_truth(m.shape)) > 0.9
    # definitely not a circle / not the whole plate
    assert 0.1 < m.mean() < 0.4


def test_transparent_background(tmp_path):
    hm = images.load_heightmap(make_star(str(tmp_path / "t.png"), mode="RGBA", fg=255))
    assert hm.alpha is not None
    res = Pipeline().compute(hm, auto_params())
    assert res.info["bg"] == "transparent"
    m = plate_mask(res)
    assert iou(m, resized_truth(m.shape)) > 0.9


def test_picked_color_background(tmp_path):
    im = Image.new("L", (400, 300), 128)
    ImageDraw.Draw(im).polygon(star_points(200, 150, 130, 55), fill=230)
    im.save(tmp_path / "g.png")
    hm = images.load_heightmap(str(tmp_path / "g.png"))
    p = auto_params()
    p.bg_mode, p.bg_r = "color", 128 / 255.0
    p.bg_g = p.bg_b = p.bg_r
    p.threshold = 0.2
    res = Pipeline().compute(hm, p)
    m = plate_mask(res)
    assert res.info["bg"] == "color" and iou(m, resized_truth(m.shape)) > 0.9


def test_grow_shrink_islands_largest(tmp_path):
    im = Image.new("L", (400, 300), 0)
    d = ImageDraw.Draw(im)
    d.rectangle((50, 50, 250, 250), fill=200)
    d.rectangle((300, 100, 340, 140), fill=200)          # second object (1.4 % of the image)
    d.rectangle((370, 20, 373, 23), fill=200)            # speck
    d.rectangle((120, 120, 160, 160), fill=0)            # hole
    im.save(tmp_path / "r.png")
    hm = images.load_heightmap(str(tmp_path / "r.png"))
    g = adjust_levels(hm.work, ModelParams())
    p = auto_params()
    base, _ = cutout.object_mask(g, p, 1.0)
    lab_n = __import__("scipy.ndimage", fromlist=["label"]).label(base)[1]
    assert lab_n == 2                                    # speck removed, two objects kept
    assert base[140, 140]                                # hole filled
    p.fill_holes = False
    assert not cutout.object_mask(g, p, 1.0)[0][140, 140]
    p.fill_holes, p.keep_largest = True, True
    m, _ = cutout.object_mask(g, p, 1.0)
    assert not m[120, 320] and m[100, 100]
    p.keep_largest, p.min_island = False, 0.0
    m, _ = cutout.object_mask(g, p, 1.0)
    assert m[21, 371]                                    # speck kept with no minimum area
    p.min_island = 0.05
    p.mask_grow = 10
    grown, _ = cutout.object_mask(g, p, 1.0)
    p.mask_grow = -10
    shrunk, _ = cutout.object_mask(g, p, 1.0)
    assert shrunk.sum() < base.sum() < grown.sum()
    assert grown[45, 150] and not base[45, 150] and not shrunk[55, 150]


def test_texture_alpha_source(tmp_path):
    # height map without a usable background (flat noise), texture with transparency gives the outline
    rng = np.random.default_rng(1)
    Image.fromarray((rng.random((300, 400)) * 80 + 120).astype(np.uint8), "L").save(tmp_path / "n.png")
    make_star(str(tmp_path / "tx.png"), mode="RGBA", fg=60)
    hm = images.load_heightmap(str(tmp_path / "n.png"))
    tex = images.load_texture(str(tmp_path / "tx.png"))
    p = auto_params()
    p.fit = 0
    res = Pipeline().compute(hm, p, tex=tex)
    assert res.info["source"] == "tex_alpha"
    m = plate_mask(res)
    assert iou(m, resized_truth(m.shape)) > 0.85
    p.outline_src = "tex_color"                         # colour key against the (white composited) border
    res = Pipeline().compute(hm, p, tex=tex)
    assert res.info["source"] == "tex_color"
    assert iou(plate_mask(res), resized_truth(m.shape)) > 0.85


def test_feather_changes_edge_only(hm):
    p = auto_params()
    a = Pipeline().compute(hm, p).sdf
    p.mask_feather = 4.0
    b = Pipeline().compute(hm, p).sdf
    assert not np.allclose(a, b) and abs((a > 0).mean() - (b > 0).mean()) < 0.02


def _app(**kw):
    from nimcale.app import NimcaleApp
    a = argparse.Namespace(texture=None, heightmap=None, project=None)
    for k, v in kw.items():
        setattr(a, k, v)
    app = NimcaleApp(a)
    app.load_initial()
    return app


def test_import_switches_coin_to_auto_outline(tmp_path):
    app = _app()
    assert app.params.shape == "circle"                  # default coin preset
    app.params.rim_width, app.params.bevel = 0.03, 0.02  # coin edge (not chosen by the user via the UI)
    assert app.import_heightmap(make_star(str(tmp_path / "s.png"), bg="white", fg=60))
    p = app.params
    assert p.cutout and p.shape == "auto" and p.outline_src == "auto" and p.bg_mode == "auto"
    assert p.rim_width == 0.0 and p.bevel == 0.0
    app.refresh(force=True)
    m = plate_mask(app.result)
    assert app.result.info["bg"] == "white"
    assert iou(m, resized_truth(m.shape)) > 0.9


def test_explicit_user_shape_is_kept(tmp_path):
    app = _app()
    app.params.shape = "ellipse"
    app.params.rim_width = 0.03
    app.mark_shape_choice()
    app.import_heightmap(make_star(str(tmp_path / "s.png")))
    assert app.params.shape == "ellipse" and app.params.rim_width == 0.03


def test_cli_heightmap_starts_with_auto_outline(tmp_path):
    app = _app(heightmap=make_star(str(tmp_path / "s.png")))
    assert app.params.shape == "auto"


def test_hd_export_of_star_is_watertight(tmp_path):
    from conftest import export_data
    from nimcale.export.job import ExportJob, ExportOptions
    hm = images.load_heightmap(make_star(str(tmp_path / "s.png"), bg="white", fg=40))
    tex = images.load_texture(str(tmp_path / "s.png"))
    p = auto_params()
    p.mask_grow, p.mask_feather, p.mesh_res = 3.0, 1.0, 200
    data = export_data(hm, tex, p)
    job = ExportJob(data, ExportOptions(fmt="stl", path=str(tmp_path / "s.stl"), hd=True, hd_nodes=600))
    job._run_safe()
    assert job.error is None, job.error
    assert job.report["watertight"]


def test_project_keeps_heightmap_alpha(tmp_path):
    app = _app(heightmap=make_star(str(tmp_path / "t.png"), mode="RGBA", fg=255))
    path = str(tmp_path / "p.nimcale")
    app.save_project(path)
    app2 = _app()
    app2.open_project(path)
    assert app2.hm.alpha is not None
    assert app2.params.shape == "auto"
