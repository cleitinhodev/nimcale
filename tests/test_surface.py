# SPDX-License-Identifier: GPL-3.0-or-later
"""Surface layer: texture + relief applied onto an imported 3D model (cup sample and friends)."""
import argparse
import os

import numpy as np
import pytest

from nimcale.core import surface as S
from nimcale.core.mesh import check_closed
from nimcale.core.params import ModelParams
from nimcale.core.pipeline import Pipeline
from nimcale.app import sample_path

ALL_FORMATS = ["obj", "stl", "ply", "glb", "gltf", "3mf", "off", "dae"]


@pytest.fixture(scope="module")
def plate(hm):
    from nimcale.app import coin_defaults
    p = coin_defaults(ModelParams())
    p.shape = "auto"
    return p, Pipeline().compute(hm, p)


@pytest.fixture(scope="module")
def cup():
    return S.load_surface(sample_path("cup"))


def test_samples_are_closed_and_small():
    for name in S.SAMPLES:
        path = sample_path(name)
        assert os.path.getsize(path) < 200_000, name
        m = S.load_surface(path)
        assert m.watertight, name
        assert m.n_faces > 10


def test_auto_projection_guesses():
    exp = dict(cup="cylinder", mug="cylinder", bottle="cylinder", can="cylinder", ball="sphere", box="box",
               plate="planar", slab="planar")
    for name, mode in exp.items():
        m = S.load_surface(sample_path(name))
        V = S.transform_model(m, ModelParams())
        got, _ = S.auto_projection(V, m.F, S.vertex_normals(V, m.F), m.has_uv)
        assert got == mode, (name, got)


def test_subdivision_is_conforming():
    m = S.load_surface(sample_path("box"))
    V, F, _ = S.subdivide(m.V, m.F, max_len=3.0, max_faces=200_000)
    assert len(F) > 10 * m.n_faces
    assert check_closed(F)["watertight"]
    L = np.linalg.norm(V[F] - V[F[:, [1, 2, 0]]], axis=2)
    assert L.max() <= 3.0 + 1e-9


def test_cup_wrap_covers_whole_side(cup, plate):
    p, res = plate
    p = p.copy()
    p.srf_size = 95.0
    sr = S.SurfaceBuilder().build(cup, p, res)
    assert sr.mode == "cylinder"
    # the image goes all the way round: every outer-wall vertex in the covered band is inside the decal
    side = np.abs(sr.geo.VN[:, 2]) < 0.2
    u = sr.uv_v[side & (sr.w_v > 0.5), 0]
    assert u.min() < 0.02 and u.max() > 0.98
    hist = np.histogram(u, bins=20, range=(0, 1))[0]
    assert (hist > 0).all()
    # proportions: unlocked height stretch changes v only
    p.srf_lock, p.srf_sy = False, 0.5
    sr2 = S.SurfaceBuilder().build(cup, p, res)
    assert np.allclose(sr2.uv_v[:, 0], sr.uv_v[:, 0])
    assert not np.allclose(sr2.uv_v[:, 1], sr.uv_v[:, 1])


def test_cup_displacement_along_normals(cup, plate):
    p, res = plate
    p = p.copy()
    sr = S.SurfaceBuilder().build(cup, p, res)
    d = np.einsum("ij,ij->i", sr.P - sr.geo.V, sr.geo.VN)
    relief = p.depth * p.size_mm
    assert d.max() > 0.5 * relief and d.min() >= -1e-6 and d.max() <= relief + 1e-6
    off = np.linalg.norm(sr.P - sr.geo.V, axis=1)
    assert np.allclose(off[sr.w_v < 0.5], 0.0)
    assert check_closed(sr.F)["watertight"]
    # invert flips the relief
    p.invert = True
    res_i = Pipeline().compute(_hm(), p)
    sr_i = S.SurfaceBuilder().build(cup, p, res_i)
    assert not np.allclose(sr_i.P, sr.P)


def _hm():
    from nimcale.core import images
    from nimcale.app import DEFAULT_HM
    return images.load_heightmap(DEFAULT_HM)


def cup_r(m):
    return float(np.hypot(m.V[:, 0], m.V[:, 1]).max())


def test_outer_only_and_caps(cup, plate):
    """Cylinder mode: by default only the outer wall gets relief (inside of the cup and top/bottom stay smooth)."""
    p, res = plate
    p = p.copy()
    p.srf_tile = True
    sr = S.SurfaceBuilder().build(cup, p, res, max_faces=120_000)
    V, N = sr.geo.V, sr.geo.VN
    r = np.hypot(V[:, 0], V[:, 1])
    radial = (N[:, 0] * V[:, 0] + N[:, 1] * V[:, 1]) / np.maximum(r, 1e-9)
    inner = radial < -0.5
    caps = np.abs(N[:, 2]) > 0.9
    assert inner.any() and caps.any()
    assert sr.w_v[inner].max() == 0.0 and sr.w_v[caps].max() == 0.0
    assert np.allclose(sr.P[inner], V[inner])
    p.srf_outer, p.srf_caps = False, True
    sr2 = S.SurfaceBuilder().build(cup, p, res, max_faces=120_000)
    assert sr2.w_v[inner].min() == 1.0 and sr2.w_v[caps].min() == 1.0


def test_fit_modes(cup, plate):
    p, res = plate
    p = p.copy()
    p.srf_tile = False
    spans = {}
    for fit in ("stretch", "width", "height"):
        p.srf_fit = fit
        sr = S.SurfaceBuilder().build(cup, p, res, max_faces=120_000)
        side = (sr.w_v > 0) | (np.abs(sr.geo.VN[:, 2]) < 0.5)
        spans[fit] = (np.ptp(sr.uv_v[side, 0]), np.ptp(sr.uv_v[side, 1]), sr.w_v.mean())
    # stretch covers the whole wall in both directions; width keeps the proportion so the height is cropped
    assert spans["stretch"][1] <= 1.05 and spans["width"][1] < spans["stretch"][1]
    # height keeps the proportion so the image does not go all the way around
    assert spans["height"][0] > 1.5 and spans["height"][2] < spans["stretch"][2]


def test_placement_single_tile_mirror_decal(cup, plate):
    p, res = plate
    p = p.copy()
    p.srf_scale = 0.4
    single = S.SurfaceBuilder().build(cup, p, res)
    cov = single.w_v.mean()
    assert 0.02 < cov < 0.6
    p.srf_ou = 0.2
    moved = S.SurfaceBuilder().build(cup, p, res)
    assert not np.allclose(moved.w_v, single.w_v)
    p.srf_tile = True
    tiled = S.SurfaceBuilder().build(cup, p, res)
    V, N = tiled.geo.V, tiled.geo.VN
    side = (np.abs(N[:, 2]) < 0.5) & ((N[:, 0] * V[:, 0] + N[:, 1] * V[:, 1]) > 0)
    assert tiled.w_v[side].min() == 1.0                 # the whole outer wall
    p.srf_outer, p.srf_caps = False, True
    tiled = S.SurfaceBuilder().build(cup, p, res)
    assert tiled.w_v.min() == 1.0 and tiled.uv_v.min() >= 0 and tiled.uv_v.max() <= 1
    p.srf_outer, p.srf_caps = True, False
    p.srf_tile, p.srf_ou, p.srf_mirror = False, 0.0, True
    mir = S.SurfaceBuilder().build(cup, p, res)
    ins = single.w_v > 0.5
    assert np.allclose(mir.uv_v[ins, 0], 1.0 - single.uv_v[ins, 0])
    p.srf_mirror, p.srf_proj, p.srf_axis, p.srf_scale = False, "decal", "front", 1.0
    dec = S.SurfaceBuilder().build(cup, p, res)
    front = dec.geo.VN[:, 1] < -0.3
    assert dec.w_v[~front & (dec.geo.VN[:, 1] > 0.3)].max() == 0.0     # back side untouched


@pytest.mark.parametrize("proj", ["cylinder", "sphere", "planar", "box", "decal"])
def test_projection_modes_watertight(cup, plate, proj):
    p, res = plate
    p = p.copy()
    p.srf_proj = proj
    p.srf_axis = "front" if proj in ("planar", "decal") else "top"
    sr = S.SurfaceBuilder().build(cup, p, res, max_faces=120_000)
    assert sr.mode == proj
    assert check_closed(sr.F)["watertight"]
    assert np.isfinite(sr.P).all()


@pytest.mark.parametrize("fmt", ALL_FORMATS)
def test_import_formats(tmp_path, fmt):
    trimesh = pytest.importorskip("trimesh")
    src = trimesh.load(sample_path("mug"), process=False)
    path = str(tmp_path / ("mug." + fmt))
    src.export(path)
    m = S.load_surface(path)
    assert m.watertight
    assert abs(m.n_faces - len(src.faces)) <= 2
    p = ModelParams()
    V = S.transform_model(m, p)
    ext = V.max(0) - V.min(0)
    assert abs(ext.max() - p.srf_size) < 1e-6


def test_import_multiple_submeshes_units_and_uvs(tmp_path):
    trimesh = pytest.importorskip("trimesh")
    a = trimesh.creation.box((0.1, 0.1, 0.1))               # metres
    b = trimesh.creation.icosphere(subdivisions=2, radius=0.03)
    b.apply_translation((0.2, 0, 0))
    from PIL import Image
    a.visual = trimesh.visual.TextureVisuals(uv=np.random.default_rng(0).random((len(a.vertices), 2)),
                                             image=Image.new("RGB", (4, 4)))
    b.visual = trimesh.visual.TextureVisuals(uv=np.random.default_rng(1).random((len(b.vertices), 2)),
                                             image=Image.new("RGB", (4, 4)))
    sc = trimesh.Scene([a, b])
    path = str(tmp_path / "two.glb")
    sc.export(path)
    m = S.load_surface(path)
    assert m.parts == 2 and m.has_uv
    assert m.unit == 1000.0 and abs(m.extent.max() - 280.0) < 1.0
    p = ModelParams()
    p.srf_proj = "auto"
    from nimcale.core import images
    from nimcale.app import DEFAULT_HM
    res = Pipeline().compute(images.load_heightmap(DEFAULT_HM), p)
    sr = S.SurfaceBuilder().build(m, p, res, max_faces=60_000)
    assert sr.mode == "uv"


def _surface_data(hm, tex, p, model, sr=None):
    from conftest import export_data
    d = export_data(hm, tex, p)
    d["surface"] = model
    d["surface_result"] = sr
    return d


@pytest.mark.parametrize("fmt", ["stl", "obj", "glb", "ply", "3mf", "off"])
def test_cup_export_formats_watertight(tmp_path, hm, tex, plate, cup, fmt):
    from nimcale.export.job import ExportJob, ExportOptions
    p, _ = plate
    data = _surface_data(hm, tex, p.copy(), cup)
    path = tmp_path / ("cup." + fmt)
    job = ExportJob(data, ExportOptions(fmt=fmt, path=str(path), hd=False, tex_res=512))
    job._run_safe()
    assert job.error is None, job.error
    r = job.report
    assert r["surface"] and r["watertight"] and r["input_watertight"]
    assert path.stat().st_size > 1000
    if fmt in ("obj", "glb"):
        trimesh = pytest.importorskip("trimesh")
        m = trimesh.load(str(path), force="mesh")
        m.merge_vertices(merge_tex=True, merge_norm=True)
        assert m.is_watertight
        if fmt == "obj":
            assert (tmp_path / "cup.png").exists()


def test_cup_hd_export_is_dense_and_watertight(tmp_path, hm, tex, plate, cup):
    from nimcale.export.job import ExportJob, ExportOptions
    p, res = plate
    data = _surface_data(hm, tex, p.copy(), cup)
    job = ExportJob(data, ExportOptions(fmt="stl", path=str(tmp_path / "hd.stl"), hd=True, hd_nodes=900))
    job._run_safe()
    assert job.error is None, job.error
    prev = S.SurfaceBuilder().build(cup, p, res)
    assert job.report["watertight"] and job.report["triangles"] > 1.5 * prev.n_tris
    assert abs(job.report["dims"][2] - p.srf_size) < 6


def _app():
    from nimcale.app import NimcaleApp
    app = NimcaleApp(argparse.Namespace(texture=None, heightmap=None, project=None, surface=None))
    app.load_initial()
    return app


def test_startup_has_no_surface_and_remove_restores_plate():
    app = _app()
    assert app.surface is None and app.params.shape == "circle"     # default coin, no surface
    before = app.params.copy()
    assert app.load_sample("cup")
    assert app.surface is not None and app.surface.sample == "cup"
    app.params.srf_scale = 0.7
    app.refresh(force=True)
    assert app.surface_result is not None
    assert app.remove_surface()
    assert app.surface is None
    app.refresh(force=True)
    assert app.surface_result is None
    # every plate / coin setting is intact
    for k in ("shape", "cutout", "depth", "thickness", "threshold", "size_mm", "rim_width", "fit"):
        assert getattr(app.params, k) == getattr(before, k), k
    # undo brings the surface back, redo removes it again
    app.undo()
    assert app.surface is not None
    app.redo()
    assert app.surface is None


def test_project_roundtrip_with_surface(tmp_path):
    app = _app()
    app.load_sample("mug")
    app.params.srf_proj, app.params.srf_rot = "cylinder", 12.0
    path = str(tmp_path / "s.nimcale")
    assert app.save_project(path)
    app2 = _app()
    assert app2.open_project(path)
    assert app2.surface is not None and app2.surface.n_faces == app.surface.n_faces
    assert app2.params.srf_rot == 12.0
    app2.refresh(force=True)
    assert app2.surface_result is not None


def test_drop_mesh_file_imports_surface(tmp_path):
    app = _app()
    app.handle_drops([sample_path("vase")])
    assert app.surface is not None
