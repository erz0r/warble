"""compare a python port with goldens produced by openutau itself (ref/harness)."""

import json
import os

from ...bank.utau import name_to_tone
from . import by_openutau_class, load_all
from .api import TimeAxis
from .runner import notes_from_case, run
from .singer import Singer

GOLDEN_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "tests", "parity", "goldens")


def run_cases(cls, bank_dir, cases, bpm=120.0):
    singer = Singer(bank_dir)
    results = []
    for case in cases:
        pz = cls()
        pz.set_singer(singer)
        pz.set_timing(TimeAxis([(0, bpm)]))
        try:
            groups = notes_from_case(case, name_to_tone)
            per = run(pz, groups)
            phs = []
            for gi, (g, res) in enumerate(zip(groups, per)):
                for p in res:
                    phs.append({"phoneme": p.phoneme, "position": p.position - g[0].position, "group": gi, "error": p.error})
            results.append({"id": case.get("id"), "phonemes": phs})
        except Exception as e:  # noqa: BLE001
            results.append({"id": case.get("id"), "error": f"{type(e).__name__}: {e}"})
    return results


def compare(golden_path, bank_root=None):
    """-> {"golden", "phonemizer", "cases", "mismatches": [...], "passed": bool}"""
    load_all()
    with open(golden_path, encoding="utf-8") as f:
        g = json.load(f)
    cls = by_openutau_class(g["phonemizer"])
    bank = g["bank"]
    if bank_root and not os.path.isabs(bank):
        bank = os.path.join(bank_root, bank)
    out = {"golden": os.path.basename(golden_path), "phonemizer": g["phonemizer"], "cases": len(g["cases"]), "mismatches": []}
    if cls is None:
        out["status"] = "not ported"
        out["passed"] = False
        return out
    ours = run_cases(cls, bank, g["cases"], g.get("bpm", 120.0))
    for case, want, got in zip(g["cases"], g["results"], ours):
        w = [(p["phoneme"], p["position"], p["group"]) for p in want.get("phonemes", [])]
        o = [(p["phoneme"], p["position"], p["group"]) for p in got.get("phonemes", [])]
        if w != o or bool(want.get("error")) != bool(got.get("error")):
            out["mismatches"].append({"id": case.get("id"), "lyrics": [n["lyric"] for n in case["notes"]], "openutau": w, "warble": o,
                                      "openutau_error": want.get("error"), "warble_error": got.get("error")})
    out["passed"] = not out["mismatches"]
    out["status"] = "ported" if out["passed"] else "mismatch"
    return out
