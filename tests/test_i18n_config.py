# SPDX-License-Identifier: GPL-3.0-or-later
import importlib.util
import json
import os

from nimcale import i18n
from nimcale.config import AppConfig

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _keys():
    spec = importlib.util.spec_from_file_location("i18n_keys", os.path.join(ROOT, "scripts", "i18n_keys.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.used_keys()


def test_locales_complete():
    keys = _keys()
    assert len(keys) > 400
    for code in i18n.CODES:
        d = json.load(open(os.path.join(i18n.LOCALE_DIR, code + ".json"), encoding="utf-8"))
        missing = [k for k in keys if k not in d]
        assert not missing, (code, missing[:10])


def test_language_matching():
    assert i18n.match_language("pt_BR") == "pt-BR"
    assert i18n.match_language("pt_PT") == "pt-BR"
    assert i18n.match_language("de_DE") == "de"
    assert i18n.match_language("zh_TW") == "zh-CN"
    assert i18n.match_language("nl_NL") == "en"
    assert i18n.match_language(None) == "pt-BR"


def test_tr_format_and_fallback():
    i18n.set_language("pt-BR")
    assert i18n.tr("menu.file") == "Arquivo"
    assert i18n.tr("no.such.key") == "no.such.key"
    i18n.set_language("en")
    assert i18n.tr("menu.file") == "File"


def test_config_roundtrip():
    c = AppConfig.load()
    c.language, c.neon, c.font_size = "ja", False, 18.0
    c.save()
    d = AppConfig.load()
    assert d.language == "ja" and d.neon is False and d.font_size == 18.0
