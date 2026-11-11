# SPDX-License-Identifier: GPL-3.0-or-later
import json
import os
import struct
import zipfile

import pytest

from conftest import export_data
from nimcale.export.job import ExportJob, ExportOptions

MESH_FMTS = ["stl", "stl_ascii", "obj", "glb", "gltf", "ply", "3mf", "off"]
EXT = {"stl_ascii": "stl"}


def run_job(data, fmt, path, **kw):
    o = ExportOptions(fmt=fmt, path=str(path), **kw)
    job = ExportJob(data, o)
    job._run_safe()
    assert job.error is None, job.error
    return job.report


@pytest.mark.parametrize("fmt", MESH_FMTS)
def test_export_formats(tmp_path, hm, tex, coin_params, fmt):
    data = export_data(hm, tex, coin_params)
    path = tmp_path / ("model." + EXT.get(fmt, fmt))
    r = run_job(data, fmt, path, hd=False, tex_res=512)
    assert path.exists() and path.stat().st_size > 1000
    assert r["watertight"]
    n = r["triangles"]
    if fmt == "stl":
        with open(path, "rb") as f:
            f.read(80)
            assert struct.unpack("<I", f.read(4))[0] == n
        assert path.stat().st_size == 84 + 50 * n
    trimesh = pytest.importorskip("trimesh")
    m = trimesh.load(str(path), force="mesh", process=True)
    assert len(m.faces) > 0.95 * n
    if fmt in ("stl", "stl_ascii", "off", "3mf"):
        assert m.is_watertight
    scale = 1000.0 if fmt in ("glb", "gltf") else 1.0       # glTF is in metres
    assert 36 < max(m.extents) * scale < 40.5               # 40 mm coin


def test_obj_has_material_and_texture(tmp_path, hm, tex, coin_params):
    data = export_data(hm, tex, coin_params)
    run_job(data, "obj", tmp_path / "c.obj", hd=False, tex_res=256)
    files = os.listdir(tmp_path)
    assert any(f.endswith(".mtl") for f in files) and any(f.endswith(".png") for f in files)


def test_3mf_package(tmp_path, hm, tex, coin_params):
    data = export_data(hm, tex, coin_params)
    run_job(data, "3mf", tmp_path / "c.3mf", hd=False)
    with zipfile.ZipFile(tmp_path / "c.3mf") as z:
        names = z.namelist()
        assert "3D/3dmodel.model" in names and "[Content_Types].xml" in names
        assert b'unit="millimeter"' in z.read("3D/3dmodel.model")[:2000]


def test_glb_structure(tmp_path, hm, tex, coin_params):
    data = export_data(hm, tex, coin_params)
    run_job(data, "glb", tmp_path / "c.glb", hd=False, tex_res=256)
    b = (tmp_path / "c.glb").read_bytes()
    assert b[:4] == b"glTF"
    jlen = struct.unpack("<I", b[12:16])[0]
    doc = json.loads(b[20:20 + jlen])
    assert doc["asset"]["version"] == "2.0" and doc["images"] and doc["materials"]


@pytest.mark.parametrize("fmt", ["height_png", "normal_png", "texture_png"])
def test_image_exports(tmp_path, hm, tex, coin_params, fmt):
    from PIL import Image
    data = export_data(hm, tex, coin_params)
    path = tmp_path / "img.png"
    run_job(data, fmt, path, hd=True, hd_nodes=512, tex_res=512)
    im = Image.open(path)
    assert max(im.size) >= 500
    if fmt == "height_png":
        assert im.mode in ("I;16", "I")


def test_hd_export_dense_and_watertight(tmp_path, hm, tex, coin_params):
    """HD export is independent of the preview resolution and produces millions of triangles."""
    data = export_data(hm, tex, coin_params)
    path = tmp_path / "hd.stl"
    r = run_job(data, "stl", path, hd=True, hd_nodes=1536)
    assert r["watertight"]
    assert r["triangles"] > 3_000_000
    assert path.stat().st_size == 84 + 50 * r["triangles"]


def test_hd_with_sculpt_and_decimate(tmp_path, hm, tex, coin_params):
    from nimcale.core.pipeline import Pipeline
    from nimcale.tools.sculpt import Sculptor
    pl = Pipeline()
    pl.compute(hm, coin_params)
    base = pl.cache["gA"]
    sc = Sculptor()
    sc.begin(base.shape, base, 300, 300)
    sc.stroke_to(base, 400, 400, 40, 0.2)
    sc.end()
    data = export_data(hm, tex, coin_params, sc.layer)
    r = run_job(data, "stl", tmp_path / "s.stl", hd=True, hd_nodes=768, decimate=0.5)
    assert r["watertight"] and r["triangles"] < 0.6 * r["triangles_full"]


def test_cancel(tmp_path, hm, tex, coin_params):
    data = export_data(hm, tex, coin_params)
    job = ExportJob(data, ExportOptions(fmt="stl", path=str(tmp_path / "x.stl"), hd=True, hd_nodes=1024))
    job.cancel()
    job._run_safe()
    assert job.cancelled and job.done
