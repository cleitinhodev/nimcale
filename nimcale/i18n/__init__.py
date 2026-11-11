# SPDX-License-Identifier: GPL-3.0-or-later
"""Tiny translation layer: tr("key", **fmt). Locale files live in nimcale/i18n/locales/<code>.json."""
import json
import locale
import os
import sys

LOCALE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "locales")

# code, native name, english name
LANGUAGES = [
    ("pt-BR", "Português (Brasil)", "Portuguese (Brazil)"),
    ("en", "English", "English"),
    ("es", "Español", "Spanish"),
    ("fr", "Français", "French"),
    ("de", "Deutsch", "German"),
    ("it", "Italiano", "Italian"),
    ("ru", "Русский", "Russian"),
    ("pl", "Polski", "Polish"),
    ("tr", "Türkçe", "Turkish"),
    ("zh-CN", "简体中文", "Chinese (Simplified)"),
    ("ja", "日本語", "Japanese"),
    ("ko", "한국어", "Korean"),
]
CODES = [c for c, _, _ in LANGUAGES]
DEFAULT = "pt-BR"
FALLBACK = "en"

_current = FALLBACK
_strings = {}
_fallback = {}


def _load(code):
    path = os.path.join(LOCALE_DIR, code + ".json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def detect_system_language():
    """Best supported language for the OS UI language (pt-BR when undetectable, en when unsupported)."""
    name = None
    if sys.platform == "win32":
        try:
            import ctypes
            lcid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            name = locale.windows_locale.get(lcid)
        except Exception:
            name = None
    if not name:
        for var in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
            v = (os.environ.get(var) or "").split(":")[0].split(".")[0]
            if v and v not in ("C", "POSIX"):
                name = v
                break
    if not name:
        try:
            name = locale.getlocale()[0]
        except Exception:
            name = None
    return match_language(name)


def match_language(name):
    if not name:
        return DEFAULT
    n = name.replace("-", "_").lower()
    if n.startswith("pt"):
        return "pt-BR"
    if n.startswith("zh"):
        return "zh-CN"
    for code in CODES:
        if n.split("_")[0] == code.split("-")[0].lower():
            return code
    return FALLBACK


def set_language(code):
    global _current, _strings, _fallback
    if code == "auto" or code not in CODES:
        code = detect_system_language()
    _fallback = _load(FALLBACK)
    _strings = _load(code) if code != FALLBACK else _fallback
    _current = code
    return code


def current():
    return _current


def tr(key, **kw):
    s = _strings.get(key) or _fallback.get(key) or key
    if kw:
        try:
            return s.format(**kw)
        except (KeyError, IndexError, ValueError):
            return s
    return s


def has(key):
    return key in _strings or key in _fallback
