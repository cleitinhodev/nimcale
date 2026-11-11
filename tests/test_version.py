# SPDX-License-Identifier: GPL-3.0-or-later
"""The version number is the same everywhere; stable versions show no test-build badge."""
import os
import re

import nimcale

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_version_consistent():
    v = nimcale.__version__
    py = re.search(r'^version = "([^"]+)"', open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8").read(), re.M)
    norm = v.replace("-beta.", "b").replace("-rc.", "rc").replace("-alpha.", "a")
    assert py and py.group(1) == norm
    vi = open(os.path.join(ROOT, "scripts", "version_info.txt"), encoding="utf-8").read()
    assert "'%s'" % v in vi
    nums = tuple(int(x) for x in re.match(r"(\d+)\.(\d+)\.(\d+)", v).groups())
    assert "filevers=(%d, %d, %d, 0)" % nums in vi


def test_test_badge_only_for_prereleases():
    assert nimcale.IS_TEST_BUILD == ("-" in nimcale.__version__)
