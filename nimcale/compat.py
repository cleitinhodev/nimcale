# SPDX-License-Identifier: GPL-3.0-or-later
"""Small helpers that keep Nimcale working across imgui-bundle / hello_imgui versions.

Enum members and RunnerParams fields have been renamed between releases; a missing name must never
crash the program at start-up."""
import sys


def enum_value(enum_cls, *names, default=None):
    """First member of ``enum_cls`` that exists among ``names`` (else ``default``)."""
    for n in names:
        v = getattr(enum_cls, n, None)
        if v is not None:
            return v
    if default is not None:
        return default
    raise AttributeError("%s has none of %s" % (getattr(enum_cls, "__name__", enum_cls), ", ".join(names)))


def set_opt(obj, name, value):
    """Set an optional attribute; silently skipped (logged) when this version does not have it."""
    try:
        if not hasattr(obj, name):
            raise AttributeError(name)
        setattr(obj, name, value)
        return True
    except (AttributeError, TypeError) as e:
        print("compat: %s.%s not available (%s)" % (type(obj).__name__, name, e), file=sys.stderr, flush=True)
        return False
