# SPDX-License-Identifier: GPL-3.0-or-later
import os
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("NIMCALE_CONFIG_DIR", tempfile.mkdtemp(prefix="nimcale_cfg_"))


@pytest.fixture(scope="session")
def hm():
    from nimcale.core import images
    from nimcale.app import DEFAULT_HM
    return images.load_heightmap(DEFAULT_HM)


@pytest.fixture(scope="session")
def tex():
    from nimcale.core import images
    from nimcale.app import DEFAULT_TEX
    return images.load_texture(DEFAULT_TEX)


@pytest.fixture
def coin_params(hm):
    from nimcale.core.params import ModelParams
    from nimcale.app import coin_defaults
    from nimcale.core.pipeline import fit_shape_params
    p = coin_defaults(ModelParams())
    p.shape_cx, p.shape_cy, p.shape_rx, p.shape_ry = fit_shape_params(hm, p, "circle")
    p.mesh_res = 200
    return p


def export_data(hm, tex, p, sculpt=None):
    from nimcale.core.pipeline import Pipeline
    from nimcale.core.images import border_color
    res = Pipeline().compute(hm, p, sculpt)
    return dict(hm=hm, tex=tex, params=p.copy(), sculpt=sculpt, preview_result=res,
                outcol=border_color(tex.img), mix=0.5)
