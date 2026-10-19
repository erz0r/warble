"""openutau .ustx import and export (yaml, ustx_version 0.6+).

maps tempos, time signatures, tracks (singer -> bank by name, phonemizer, volume, pan), voice
parts' notes (lyric, tone, pitch points with snap_first, vibrato, index-0 phoneme expressions) and
part curves (pitd, dyn, genc, brec, tenc, voic, ene, velc, pexp) onto the score. pitch point y is
stored in 0.1 semitones in ustx and in cents here. field names follow openutau's yamldotnet
underscored serialization (MIT, Copyright (c) 2014 StAkira).
"""

import os

import yaml

from ..errors import WarbleError
from ..score import Note, Score, Track
from ..tuning import curve

EXPR_TO_CONTROL = {"vel": "vel", "vol": "vol", "atk": "atk", "dec": "dec", "mod": "mod", "genc": "gender", "gen": "gender",
                   "brec": "brec", "bre": "brec", "tenc": "tenc", "voic": "voic", "ene": "ene", "shft": "shift"}
CONTROL_TO_EXPR = {"vel": "vel", "vol": "vol", "atk": "atk", "dec": "dec", "mod": "mod", "gender": "genc", "brec": "brec",
                   "tenc": "tenc", "voic": "voic", "ene": "ene", "shift": "shft"}
CURVES = {"pitd", "dyn", "genc", "brec", "tenc", "voic", "ene", "velc", "pexp"}
SHAPES = {"io", "l", "i", "o", "sp"}


def load(path):
    with open(path, encoding="utf-8-sig") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict) or "voice_parts" not in data and "tracks" not in data:
        raise WarbleError("ustx_bad", f"{path} does not look like an openutau project")
    res = int(data.get("resolution", 480))
    scale = 480 / res
    score = Score(base_dir=os.path.dirname(os.path.abspath(path)))
    tempos = data.get("tempos") or [{"position": 0, "bpm": data.get("bpm", 120)}]
    score.tempos = sorted((int(t.get("position", 0) * scale), float(t["bpm"])) for t in tempos)
    sigs = data.get("time_signatures") or [{"bar_position": 0, "beat_per_bar": data.get("beat_per_bar", 4), "beat_unit": data.get("beat_unit", 4)}]
    # bar positions -> ticks
    sig_out, tick, bar, cur = [], 0, 0, (4, 4)
    for sg in sorted(sigs, key=lambda x: x.get("bar_position", 0)):
        bp = int(sg.get("bar_position", 0))
        tick += (bp - bar) * int(cur[0] * 480 * 4 / cur[1])
        bar = bp
        cur = (int(sg.get("beat_per_bar", 4)), int(sg.get("beat_unit", 4)))
        sig_out.append((tick, cur[0], cur[1]))
    score.time_signatures = sig_out or [(0, 4, 4)]
    score.key = str(data["key"]) if data.get("key") is not None else None
    from ..score import resolve_bank

    tracks = []
    for i, t in enumerate(data.get("tracks") or []):
        rs = t.get("renderer_settings") or {}
        singer = t.get("singer")
        bank = None
        if singer:
            try:
                b = resolve_bank(singer, score.base_dir)
                bank = b if os.path.isdir(b) else None
            except WarbleError:
                bank = None
        tr = Track(name=t.get("track_name") or f"track{i + 1}", bank=bank, phonemizer=_phonemizer_name(t.get("phonemizer")),
                   volume_db=float(t.get("volume", 0) or 0), pan=float(t.get("pan", 0) or 0) / 100.0,
                   engine={"DIFFSINGER": "ds", "CLASSIC": "utau", "WORLDLINE-R": "utau"}.get(str(rs.get("renderer", "")).upper()))
        tr.singer_name = singer
        tr.voice_colors = t.get("voice_color_names") or []
        tracks.append(tr)
    for part in data.get("voice_parts") or []:
        tno = int(part.get("track_no", 0))
        while tno >= len(tracks):
            tracks.append(Track(name=f"track{len(tracks) + 1}"))
        tr = tracks[tno]
        base = int(int(part.get("position", 0)) * scale)
        for nd in part.get("notes") or []:
            pos = base + int(nd["position"] * scale)
            dur = int(nd["duration"] * scale)
            lyric = str(nd.get("lyric", "a"))
            hint = None
            if "[" in lyric and lyric.endswith("]"):
                lyric, hint = lyric[: lyric.index("[")].strip() or lyric, lyric[lyric.index("[") + 1:-1]
            controls = {}
            pitch = nd.get("pitch") or {}
            pts = [[float(p.get("x", 0)), float(p.get("y", 0)) * 10, p.get("shape", "io") if p.get("shape", "io") in SHAPES else "io"]
                   for p in pitch.get("data") or []]
            if len(pts) >= 2:
                controls["pts"] = curve.format_points(pts)
                if not pitch.get("snap_first", True):
                    controls["snap"] = 0
            v = nd.get("vibrato") or {}
            if float(v.get("length", 0) or 0) > 0:
                controls["vbr"] = curve.format_vibrato(curve.clamp_vibrato({
                    "length": v.get("length", 0), "period": v.get("period", 175), "depth": v.get("depth", 25), "in": v.get("in", 10),
                    "out": v.get("out", 10), "shift": v.get("shift", 0), "drift": v.get("drift", 0), "vollink": v.get("vol_link", 0)}))
            for e in nd.get("phoneme_expressions") or []:
                if int(e.get("index", 0)) != 0:
                    continue
                abbr = str(e.get("abbr", "")).lower()
                if abbr in EXPR_TO_CONTROL:
                    controls[EXPR_TO_CONTROL[abbr]] = float(e["value"])
                elif abbr == "clr" and tr.voice_colors:
                    k = int(e["value"])
                    if 0 <= k < len(tr.voice_colors):
                        controls["voice"] = tr.voice_colors[k]
            for k, val in (nd.get("warble") or {}).items():
                controls.setdefault(k, val)
            tr.notes.append(Note(lyric=lyric, tone=float(nd["tone"]), position=pos, duration=dur, hint=hint, controls=controls))
        for c in part.get("curves") or []:
            abbr = str(c.get("abbr", "")).lower()
            if abbr in CURVES and c.get("xs"):
                pts = [(base + int(x * scale), float(y)) for x, y in zip(c["xs"], c["ys"])]
                tr.curves[abbr] = sorted(tr.curves.get(abbr, []) + pts)
    for tr in tracks:
        tr.notes.sort(key=lambda n: n.position)
    score.tracks = [t for t in tracks if t.notes] or tracks[:1]
    return score


def _phonemizer_name(full):
    if not full:
        return None
    from ..utau.phonemizers import _short, resolve

    cls = resolve(full)
    return _short(cls) if cls else None


def save(score, path):
    from ..utau.phonemizers import resolve

    tracks, parts = [], []
    for i, tr in enumerate(score.tracks):
        singer = getattr(tr, "singer_name", None) or (os.path.basename(tr.bank) if tr.bank else "")
        cls = resolve(tr.phonemizer) if tr.phonemizer else None
        ph = cls.openutau_class if cls else None
        tracks.append({"singer": singer, "phonemizer": ph, "renderer_settings": {"renderer": "DIFFSINGER" if tr.engine == "ds" else None},
                       "track_name": tr.name, "mute": False, "solo": False, "volume": tr.volume_db, "pan": tr.pan * 100,
                       "voice_color_names": getattr(tr, "voice_colors", []) or []})
        notes = []
        colors = getattr(tr, "voice_colors", []) or []
        for n in tr.notes:
            c = n.controls
            pts = curve.note_points(n) or []
            nd = {"position": n.position, "duration": n.duration, "tone": int(round(n.tone)),
                  "lyric": f"{n.lyric}[{n.hint}]" if n.hint and n.hint != n.lyric else n.lyric,
                  "pitch": {"data": [{"x": p[0], "y": p[1] / 10, "shape": p[2] if p[2] in SHAPES else "io"} for p in pts],
                            "snap_first": str(c.get("snap", "1")) not in ("0", "false")}}
            v = curve.note_vibrato(n)
            nd["vibrato"] = ({"length": v["length"], "period": v["period"], "depth": v["depth"], "in": v["in"], "out": v["out"], "shift": v["shift"],
                              "drift": v["drift"], "vol_link": v.get("vollink", 0)} if v else {"length": 0, "period": 175, "depth": 25, "in": 10, "out": 10,
                                                                                               "shift": 0, "drift": 0, "vol_link": 0})
            exps = [{"index": 0, "abbr": CONTROL_TO_EXPR[k], "value": float(c[k])} for k in CONTROL_TO_EXPR if k in c]
            if c.get("voice") in colors:
                exps.append({"index": 0, "abbr": "clr", "value": colors.index(c["voice"])})
            nd["phoneme_expressions"] = exps
            nd["phoneme_overrides"] = []
            # controls openutau has no field for ride along; openutau ignores unknown keys
            rest = {k: v for k, v in c.items() if k not in CONTROL_TO_EXPR and k not in ("pts", "snap", "vbr") and not (k == "voice" and v in colors)}
            if "vib" in rest and v:
                rest.pop("vib")
            if rest:
                nd["warble"] = rest
            notes.append(nd)
        curves = [{"xs": [int(t) for t, _ in pts], "ys": [v for _, v in pts], "abbr": abbr} for abbr, pts in tr.curves.items()]
        end = max((n.end for n in tr.notes), default=0)
        parts.append({"name": tr.name, "comment": "", "track_no": i, "position": 0, "duration": end, "notes": notes, "curves": curves})
    # time signatures by bar
    sigs, bar, last_tick, cur = [], 0, 0, (4, 4)
    for t, a, b in sorted(score.time_signatures):
        bar += (t - last_tick) // int(cur[0] * 480 * 4 / cur[1])
        last_tick, cur = t, (a, b)
        sigs.append({"bar_position": bar, "beat_per_bar": a, "beat_unit": b})
    data = {"name": os.path.splitext(os.path.basename(path))[0], "comment": "", "output_dir": "Vocal", "cache_dir": "UCache",
            "ustx_version": "0.6", "resolution": 480, "bpm": score.tempos[0][1], "beat_per_bar": sigs[0]["beat_per_bar"],
            "beat_unit": sigs[0]["beat_unit"], "time_signatures": sigs, "tempos": [{"position": t, "bpm": b} for t, b in score.tempos],
            "tracks": tracks, "voice_parts": parts, "wave_parts": []}
    if score.key:
        data["key"] = score.key
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
    return path
