"""the `phonemizers` command: every phonemizer warble has, its language, and which banks it fits."""

from .probe import list_banks


def catalog(dirs):
    from .utau import phonemizers as up

    items = []
    for name, cls in sorted(up.names().items()):
        items.append({"name": name, "engine": "utau", "language": cls.language, "openutau": cls.openutau_class, "title": cls.name})
    from .ds import g2p_phonemizers as gp

    for cls in gp.CLASSES:
        items.append({"name": cls.openutau_class.rsplit(".", 1)[-1], "engine": "diffsinger",
                      "language": cls.language or "any (dsdict.yaml; with lang <x>: dsdict-<x>.yaml)",
                      "lang": list(cls.lang_keys), "openutau": cls.openutau_class, "title": cls.name})
    banks = list_banks(dirs)
    fits = []
    for b in banks:
        if b["type"] == "diffsinger":
            fits.append({"bank": b["path"], "phonemizers": ["diffsinger"], "languages": b.get("languages")})
        elif b["type"] == "utau":
            from .bank.utau import UtauBank

            try:
                bank = UtauBank(b["path"], check_wavs=False)
                name, how, warn = up.choose(bank, b.get("reclist", "cv"))
                fits.append({"bank": b["path"], "default": name, "chosen_by": how, "warning": warn})
            except Exception as e:  # noqa: BLE001
                fits.append({"bank": b["path"], "default": None, "error": getattr(e, "message", str(e))})
    return {"phonemizers": items, "banks": fits}
