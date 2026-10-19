"""classic phonemizers, one module per port, discovered automatically. see api.py."""

import importlib
import pkgutil

from .api import REGISTRY, Phonemizer, phonemizer  # noqa: F401

_LOADED = False
LOAD_ERRORS = {}


def load_all():
    global _LOADED
    if _LOADED:
        return REGISTRY
    for m in pkgutil.iter_modules(__path__):
        if m.name in ("api", "singer", "runner", "parity") or m.name.startswith("_"):
            continue
        try:
            importlib.import_module(f"{__name__}.{m.name}")
        except Exception as e:  # noqa: BLE001 - one broken port must not hide the others
            LOAD_ERRORS[m.name] = f"{type(e).__name__}: {e}"
    _LOADED = True
    return REGISTRY


def by_openutau_class(name):
    load_all()
    for cls in REGISTRY.values():
        if cls.openutau_class == name:
            return cls
    return None
