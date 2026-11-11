# SPDX-License-Identifier: GPL-3.0-or-later
import numpy as np

from nimcale.core.params import ModelParams
from nimcale.core.pipeline import Pipeline
from nimcale.tools.history import History, Snapshot
from nimcale.tools.sculpt import Sculptor, BRUSHES


def test_history_undo_redo():
    h = History(limit=5)
    p = ModelParams()
    states = []
    for d in (0.01, 0.02, 0.03):
        p.depth = d
        states.append(Snapshot(p, None, None, None))
    for s in states[:-1]:
        h.push(s)
    cur = states[-1]
    s = h.undo(cur)
    assert abs(s.params.depth - 0.02) < 1e-9
    s2 = h.redo(s)
    assert abs(s2.params.depth - 0.03) < 1e-9
    for _ in range(10):
        h.push(states[0])
    assert len(h.undo_stack) <= 5


def test_sculpt_brushes(hm, coin_params):
    pl = Pipeline()
    pl.compute(hm, coin_params)
    base = pl.cache["gA"]
    h, w = base.shape
    sc = Sculptor()
    sc.strength = 1.0
    for b in BRUSHES:
        sc.brush = b
        sc.begin(base.shape, base, w / 2, h / 2)
        for k in range(10):
            sc.stroke_to(base, w / 2 + k * 3, h / 2, 30, 0.05)
        sc.end()
    assert sc.layer is not None and sc.layer.shape == base.shape
    sc.reset()
    sc.brush = "raise"
    sc.begin(base.shape, base, w / 2, h / 2)
    sc.stroke_to(base, w / 2, h / 2, 30, 0.1)
    sc.end()
    assert sc.layer[int(h / 2), int(w / 2)] > 0
    res1 = pl.compute(hm, coin_params, sc.layer, sc.rev)
    res0 = Pipeline().compute(hm, coin_params)
    assert res1.hf.max() >= res0.hf.max() - 1e-6
    assert not np.array_equal(res1.hf, res0.hf)


def test_sculpt_copy_on_write(hm, coin_params):
    pl = Pipeline()
    pl.compute(hm, coin_params)
    base = pl.cache["gA"]
    sc = Sculptor()
    sc.begin(base.shape, base, 10, 10)
    sc.stroke_to(base, 10, 10, 8, 0.1)
    sc.end()
    snap = sc.layer
    before = snap.copy()
    sc.begin(base.shape, base, 10, 10)
    sc.stroke_to(base, 10, 10, 8, 0.1)
    sc.end()
    assert np.array_equal(snap, before) and sc.layer is not snap
