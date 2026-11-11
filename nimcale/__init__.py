# SPDX-License-Identifier: GPL-3.0-or-later
"""Nimcale - turn an image + height map into a 3D relief model (coins, plates, medals)."""

__version__ = "1.1.0-beta.1"
# test builds (pre-releases from the dev/surface branch) show a "test version" badge in the app
IS_TEST_BUILD = "beta" in __version__ or "alpha" in __version__ or "rc" in __version__
APP_NAME = "Nimcale"
APP_ID = "Nimcale"

URL_SITE = "https://www.bugzinho.com/"
URL_PROJECT = "https://github.com/cleitinhodev/nimcale"
URL_DONATE = "https://www.bugzinho.com/donate"
URL_ISSUES = "https://github.com/cleitinhodev/nimcale/issues"
URL_LICENSE = "https://www.gnu.org/licenses/gpl-3.0.html"
