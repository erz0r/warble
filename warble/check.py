"""`check`: everything that can be verified about a score without rendering it."""

import os

from .bank import common
from .errors import WarbleError
from .score import pitch_name


def check(score, engine=None, vocoder_dirs=None):
    from .phonemize import phonemize

    problems, info = [], {"tracks": []}
    tm = score.tempo_map
    for tr in score.tracks:
        t_info = {"track": tr.name, "bank": tr.bank, "notes": len(tr.notes)}
        if tr.notes:
            t_info["range"] = [pitch_name(min(n.tone for n in tr.notes)), pitch_name(max(n.tone for n in tr.notes))]
            t_info["duration_s"] = round(tm.tick_to_ms(tr.notes[-1].end) / 1000, 2)
        if not tr.bank:
            problems.append({"severity": "error", "track": tr.name, "message": "no bank"})
        elif not os.path.isdir(tr.bank) or common.detect(tr.bank)[0] not in ("diffsinger", "utau"):
            problems.append({"severity": "error", "track": tr.name, "message": f"bank not found or unsupported: {tr.bank}"})
        else:
            kind = common.detect(tr.bank)[0]
            t_info["type"] = kind
            if kind == "utau":
                from .bank.utau import UtauBank
                from .utau.voice import Voice

                v = Voice(UtauBank(tr.bank, check_wavs=False))
                ranged = [s for s in v.subbanks if s["tone_ranges"]]
                if ranged:
                    lo = min(min(s["tones"]) for s in ranged)
                    hi = max(max(s["tones"]) for s in ranged)
                    for i, n in enumerate(tr.notes, start=1):
                        if not lo <= n.tone <= hi:
                            problems.append({"severity": "warning", "track": tr.name, "note": i,
                                             "message": f"{n.lyric} {pitch_name(n.tone)} is outside the bank's pitch subbanks ({pitch_name(lo)}-{pitch_name(hi)})"})
            if kind == "diffsinger" and not tr.lang:
                problems.append({"severity": "warning", "track": tr.name, "message": "diffsinger track without 'lang': only dsdict.yaml and explicit phonemes will work"})
        info["tracks"].append(t_info)
    for b in score.backings:
        if not os.path.isfile(b["path"]):
            problems.append({"severity": "error", "message": f"backing file missing: {b['path']}"})
    try:
        ph = phonemize(score, engine=engine, vocoder_dirs=vocoder_dirs)
        for u in ph["unknown"]:
            problems.append({"severity": "error", "track": u.get("track"), "lyric": u["lyric"],
                             "message": f"cannot sing '{u['lyric']}'", "closest": u.get("closest")})
    except WarbleError as e:
        problems.append({"severity": "error", "message": e.message, "code": e.code, **({"hint": e.hint} if e.hint else {})})
    info["problems"] = problems
    info["ok"] = not any(p["severity"] == "error" for p in problems)
    return info
