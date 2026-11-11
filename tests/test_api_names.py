# SPDX-License-Identifier: GPL-3.0-or-later
"""Static audit: every attribute chain used on imgui-bundle modules must exist in the installed version.

This catches typos / renamed enum members (e.g. hello_imgui.DockingLayoutCondition.xxx) in code paths
that the screenshot-based tests may not execute."""
import ast
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, "nimcale")


def _modules():
    import imgui_bundle
    from imgui_bundle import imgui, hello_imgui, immapp, icons_fontawesome_6, portable_file_dialogs, glfw_utils
    import glfw
    return {"glfw": glfw, "imgui": imgui, "hello_imgui": hello_imgui, "immapp": immapp, "fa": icons_fontawesome_6,
            "icons_fontawesome_6": icons_fontawesome_6, "pfd": portable_file_dialogs,
            "portable_file_dialogs": portable_file_dialogs, "glfw_utils": glfw_utils, "imgui_bundle": imgui_bundle}


def _aliases(tree, mods):
    """local name -> module, from 'from imgui_bundle import x as y' / 'import imgui_bundle.x as y'."""
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name == "glfw":
                    out[a.asname or "glfw"] = mods["glfw"]
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("imgui_bundle"):
            for a in node.names:
                key = a.name
                if node.module != "imgui_bundle":
                    continue
                if key in mods:
                    out[a.asname or a.name] = mods[key]
    return out


def _chains(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and not isinstance(getattr(node, "_parent", None), ast.Attribute):
            parts = []
            cur = node
            while isinstance(cur, ast.Attribute):
                parts.append(cur.attr)
                cur = cur.value
            if isinstance(cur, ast.Name):
                yield node.lineno, cur.id, list(reversed(parts))


def _files():
    for d, _, fs in os.walk(PKG):
        for f in fs:
            if f.endswith(".py"):
                yield os.path.join(d, f)


# platform-specific functions (only present on that OS), always used inside try/except
PLATFORM_ONLY = {"glfw.get_win32_window", "glfw.get_cocoa_window", "glfw.get_x11_window", "glfw.get_x11_display"}


def test_imgui_bundle_names_exist():
    mods = _modules()
    bad = []
    checked = 0
    for path in _files():
        src = open(path, encoding="utf-8").read()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            for ch in ast.iter_child_nodes(node):
                ch._parent = node
        al = _aliases(tree, mods)
        if not al:
            continue
        for line, root, parts in _chains(tree):
            if root not in al:
                continue
            obj = al[root]
            checked += 1
            for i, p in enumerate(parts):
                if "%s.%s" % (root, ".".join(parts[:i + 1])) in PLATFORM_ONLY:
                    break
                if not hasattr(obj, p):
                    # attributes of *instances* (e.g. io.key_ctrl) are not checked; only module/class chains
                    if isinstance(obj, type) or hasattr(obj, "__file__") or type(obj).__name__ == "module":
                        bad.append("%s:%d %s.%s" % (os.path.relpath(path, ROOT), line, root, ".".join(parts[:i + 1])))
                    break
                obj = getattr(obj, p)
    assert checked > 200, checked      # the audit really looked at the code
    assert not bad, "unknown imgui-bundle names:\n" + "\n".join(bad)
