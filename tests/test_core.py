# SPDX-License-Identifier: GPL-3.0-or-later
import numpy as np
import pytest

from nimcale.core import mesh as meshmod
from nimcale.core.orient import Orient
from nimcale.core.params import ModelParams, ViewParams, SHAPES
from nimcale.core.pipeline import Pipeline


def test_default_images(hm, tex):
    assert hm.work.ndim == 2 and hm.work.dtype == np.float32
    assert 0.0 <= hm.work.min() and hm.work.max() <= 1.0
    assert tex.img.mode == "RGB"
    assert hm.orig_size == (1024, 1024) and tex.orig_size == (1254, 1254)


def test_params_roundtrip():
    p = ModelParams()
    p.depth, p.shape, p.flip_x = 0.07, "hexagon", True
    q = ModelParams.from_dict(p.to_dict())
    assert q.key() == p.key()
    v = ViewParams()
    v.update({"mode": 1, "material": "gold"})
    assert v.mode == 1 and v.material == "gold"


@pytest.mark.parametrize("flip_x,flip_y,rot", [(False, False, 0), (True, False, 1), (False, True, 2), (True, True, 3)])
def test_orient_roundtrip(flip_x, flip_y, rot):
    p = ModelParams()
    p.flip_x, p.flip_y, p.rot90 = flip_x, flip_y, rot
    p.crop_l, p.crop_t = 0.1, 0.05
    o = Orient(p, 800, 600)
    for u, v in [(0.1, 0.2), (0.5, 0.5), (0.9, 0.7)]:
        su, sv = o.plate_to_src(u, v)
        u2, v2 = o.src_to_plate(su, sv)
        assert abs(u2 - u) < 1e-9 and abs(v2 - v) < 1e-9


def test_pipeline_coin(hm, coin_params):
    res = Pipeline().compute(hm, coin_params)
    assert res.hf.shape == res.sdf.shape
    inside = res.sdf > 0
    frac = inside.mean()
    assert 0.6 < frac < 0.75          # circle of radius ~0.47 => pi*0.47^2 ~ 0.70
    assert res.hf[inside].max() <= 1.0 + 1e-6


def test_pipeline_cache(hm, coin_params):
    pl = Pipeline()
    a = pl.compute(hm, coin_params)
    rev = pl.revision
    b = pl.compute(hm, coin_params)
    assert pl.revision == rev and a.hf is b.hf
    coin_params.depth = 0.08     # depth does not change the field
    pl.compute(hm, coin_params)
    coin_params.blur = 3.0
    c = pl.compute(hm, coin_params)
    assert pl.revision != rev and not np.array_equal(c.hf, a.hf)


@pytest.mark.parametrize("shape", [s for s in SHAPES])
@pytest.mark.parametrize("cutout", [True, False])
def test_solid_watertight(hm, coin_params, shape, cutout):
    p = coin_params
    p.shape, p.cutout = shape, cutout
    p.rim_width, p.rim_height, p.bevel = 0.03, 0.8, 0.01
    res = Pipeline().compute(hm, p)
    m = meshmod.build_solid(res.hf, res.sdf, res.size, p.depth, p.thickness, res=160)
    r = meshmod.check_closed(m.F)
    assert r["watertight"], r
    assert meshmod.volume(m.P, m.F) > 0          # outward orientation


def test_transforms_watertight(hm, coin_params):
    p = coin_params
    p.flip_x, p.rot90, p.crop_l, p.crop_b = True, 1, 0.1, 0.07
    p.invert, p.noise_amp, p.detail = False, 0.2, 0.5
    res = Pipeline().compute(hm, p)
    m = meshmod.build_solid(res.hf, res.sdf, res.size, p.depth, p.thickness, res=150)
    assert meshmod.check_closed(m.F)["watertight"]


def test_mesh_res_controls_triangles(hm, coin_params):
    res = Pipeline().compute(hm, coin_params)
    a = meshmod.build_solid(res.hf, res.sdf, res.size, 0.05, 0.03, res=100).n_tris
    b = meshmod.build_solid(res.hf, res.sdf, res.size, 0.05, 0.03, res=200).n_tris
    assert 3.5 < b / a < 4.5
    est = meshmod.estimate_triangles(res.sdf, 200)
    assert abs(est - b) / b < 0.1


def test_decimate(hm, coin_params):
    res = Pipeline().compute(hm, coin_params)
    m = meshmod.build_solid(res.hf, res.sdf, res.size, 0.05, 0.03, res=150)
    d = meshmod.decimate(m, 0.5)
    assert d.n_tris < m.n_tris * 0.6
    assert meshmod.check_closed(d.F)["watertight"]
