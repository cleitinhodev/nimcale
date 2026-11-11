# SPDX-License-Identifier: GPL-3.0-or-later
"""Native file dialogs (portable-file-dialogs; IFileDialog on Windows)."""
import os

from imgui_bundle import portable_file_dialogs as pfd

from nimcale.core.images import IMG_EXTS


def image_filters(tr):
    pat = " ".join("*" + e for e in IMG_EXTS)
    return [tr("dlg.images"), pat, tr("dlg.all_files"), "*"]


def open_file(title, filters, folder=""):
    try:
        res = pfd.open_file(title, folder or "", filters).result()
    except Exception:
        return None
    if res:
        return res[0]
    return None


def open_files(title, filters, folder=""):
    try:
        return list(pfd.open_file(title, folder or "", filters, pfd.opt.multiselect).result() or [])
    except Exception:
        return []


def save_file(title, filters, default_path="", ext=None):
    try:
        res = pfd.save_file(title, default_path or "", filters, pfd.opt.force_overwrite).result()
    except Exception:
        return None
    if not res:
        return None
    if ext and not os.path.splitext(res)[1]:
        res += "." + ext
    return res


def message(title, text, kind="info"):
    icon = {"info": pfd.icon.info, "warning": pfd.icon.warning, "error": pfd.icon.error}.get(kind, pfd.icon.info)
    try:
        pfd.message(title, text, pfd.choice.ok, icon).result()
    except Exception:
        pass
