# SPDX-License-Identifier: GPL-3.0-or-later
"""Back side ("Verso"): every mode must give one closed, printable solid (preview and HD exports)."""
import numpy as np
import pytest

from conftest import export_data
from nimcale.core import back, mesh as meshmod
from nimcale.core.params import ModelParams
from nimcale.core.pipeline import Pipeline
from nimcale.export.job import ExportJob, ExportOptions

CASES = {
    "flat": {},
    "mirror": dict(bk_mode="mirror"),
    "coin2": dict(bk_mode="coin2", bk_invert=True),
    "hollow": dict(bk_mode="hollow", thickness=0.08),
    "grid": dict(bk_mode="ribs", bk_ribs="grid", thickness=0.08),
    "honeycomb": dict(bk_mode="ribs", bk_ribs="honeycomb", thickness=0.08),
    "lines": dict(bk_mode="ribs", bk_ribs="lines", bk_rib_angle=30, thickness=0.08),
    "hole": dict(bk_hole=True),
    "magnet": dict(bk_magnet=True, thickness=0.08),
    "hang": dict(bk_hang=True, thickness=0.08),
    "text": dict(bk_text="Nimcale\\n2026", thickness=0.06),
    "emboss": dict(bk_text="Nimcale", bk_text_mode="emboss", bk_text_rot=15),
    "stand": dict(bk_stand=True),
    "chamfer": dict(bk_chamfer=0.6),
    "all": dict(bk_mode="ribs", bk_hole=True, bk_magnet=True, bk_text="OI", bk_stand=True,
                bk_chamfer=0.4, thickness=0.1),
}


def _params(coin_params, kw):
    p = coin_params.copy()
    p.update(kw)
    return p


def _assert_solid(P, F):
    assert meshmod.check_closed(F)["watertight"]
    trimesh = pytest.importorskip("trimesh")
    m = trimesh.Trimesh(P, F, process=False)
    assert m.is_watertight and m.is_winding_consistent
    assert m.volume > 0


@pytest.mark.parametrize("name", list(CASES))
def test_back_preview_watertight(hm, coin_params, name):
    p = _params(coin_params, CASES[name])
    res = Pipeline().compute(hm, p)
    if name == "flat":
        assert not back.is_active(p) and res.zb is None
    else:
        assert res.zb is not None
        zf = res.hf * p.depth
        inside = res.sdf > 0
        assert np.all(res.zb[inside] <= zf[inside] + 1e-6)      # back always below the front
    m = meshmod.build_solid(res.hf, res.sdf, res.size, p.depth, p.thickness, res=p.mesh_res,
                            zb=res.zb, holes=res.holes)
    _assert_solid(m.P, m.F)


def test_flat_back_keeps_old_mesh(hm, coin_params):
    """Flat back = exactly the mesh of 1.1 (the top surface is untouched)."""
    res = Pipeline().compute(hm, coin_params)
    a = meshmod.build_solid(res.hf, res.sdf, res.size, coin_params.depth, coin_params.thickness, res=200)
    b = meshmod.build_solid(res.hf, res.sdf, res.size, coin_params.depth, coin_params.thickness, res=200,
                            zb=res.zb, holes=res.holes)
    assert np.array_equal(a.P, b.P) and np.array_equal(a.F, b.F)


def test_mirror_keeps_front(hm, coin_params):
    a = Pipeline().compute(hm, coin_params)
    b = Pipeline().compute(hm, _params(coin_params, dict(bk_mode="mirror", bk_hole=True)))
    assert np.allclose(a.hf, b.hf)


def test_hole_goes_through(hm, coin_params):
    p = _params(coin_params, dict(bk_hole=True, bk_hole_d=5.0))
    res = Pipeline().compute(hm, p)
    assert res.holes is not None and (res.holes <= 0).any()
    m = meshmod.build_solid(res.hf, res.sdf, res.size, p.depth, p.thickness, res=200, zb=res.zb, holes=res.holes)
    trimesh = pytest.importorskip("trimesh")
    tm = trimesh.Trimesh(m.P, m.F, process=False)
    assert tm.euler_number == 0          # genus 1: a real through hole


def test_params_roundtrip_and_old_projects():
    p = ModelParams()
    p.update(dict(bk_mode="ribs", bk_ribs="grid", bk_text="Oi", bk_magnet=True, bk_mag_d=12.0))
    q = ModelParams.from_dict(p.to_dict())
    assert q.key() == p.key() and q.bk_mode == "ribs" and q.bk_mag_d == 12.0
    old = {k: v for k, v in p.to_dict().items() if not k.startswith("bk_")}     # a 1.1 project
    r = ModelParams.from_dict(old)
    assert r.bk_mode == "flat" and not back.is_active(r)
    r.update(dict(bk_mode="bogus", bk_ribs="bogus", bk_text_mode="bogus"))
    assert r.bk_mode in back.BACK_MODES and r.bk_ribs in back.RIB_PATTERNS and r.bk_text_mode in back.TEXT_MODES


def _run(data, fmt, path, **kw):
    job = ExportJob(data, ExportOptions(fmt=fmt, path=str(path), **kw))
    job._run_safe()
    assert job.error is None, job.error
    return job.report


@pytest.mark.parametrize("name", ["mirror", "coin2", "hollow", "honeycomb", "hang", "text", "stand", "all"])
def test_back_hd_export_watertight(tmp_path, hm, tex, coin_params, name):
    trimesh = pytest.importorskip("trimesh")
    data = export_data(hm, tex, _params(coin_params, CASES[name]))
    path = tmp_path / "hd.stl"
    r = _run(data, "stl", path, hd=True, hd_nodes=512)
    assert r["watertight"]
    m = trimesh.load(str(path), force="mesh")
    assert m.is_watertight and m.is_winding_consistent


@pytest.mark.parametrize("fmt", ["obj", "glb", "3mf", "ply"])
def test_back_export_formats(tmp_path, hm, tex, coin_params, fmt):
    trimesh = pytest.importorskip("trimesh")
    data = export_data(hm, tex, _params(coin_params, dict(bk_mode="coin2", bk_hole=True)))
    path = tmp_path / ("m." + fmt)
    r = _run(data, fmt, path, hd=False, tex_res=256)
    assert r["watertight"]
    if fmt in ("obj", "glb"):
        assert r.get("back_atlas")              # front | back texture atlas
    m = trimesh.load(str(path), force="mesh")
    assert len(m.faces) > 0.95 * r["triangles"]


def test_back_images(hm, tex, coin_params):
    """Heads and tails with its own back images (and the back reusing the front by default)."""
    from nimcale.core import images
    p = _params(coin_params, dict(bk_mode="coin2"))
    bhm = images.HeightImage(np.flipud(hm.full).copy(), hm.orig_size, "back.png")
    a = Pipeline().compute(hm, p)
    b = Pipeline().compute(hm, p, back_hm=bhm)
    assert not np.allclose(a.zb, b.zb)
    m = meshmod.build_solid(b.hf, b.sdf, b.size, p.depth, p.thickness, res=200, zb=b.zb, holes=b.holes)
    _assert_solid(m.P, m.F)
