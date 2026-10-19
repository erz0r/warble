"""utau .ust import.

notes, rests, tempo (global and per-note), lyrics, and the per-note fields that map onto engine
controls: Intensity -> vol, Velocity -> vel, Modulation -> mod, Flags -> flags, PreUtterance /
VoiceOverlap -> absolute preutter / overlap overrides. mode1 PitchBend (+PBStart) becomes a pitch
bend the renderer applies. every raw field is kept in note.extra["ust"] so export can round-trip it.
"""

import os
import re

from ..errors import WarbleError
from ..score import Note, Score, Track
from ..textenc import decode_bytes

CONTROL_MAP = {"Intensity": "vol", "Velocity": "vel", "Modulation": "mod", "Moduration": "mod"}


def parse_sections(text):
    sections = []
    cur = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = re.fullmatch(r"\[#(.+)\]", line)
        if m:
            cur = {"_name": m.group(1)}
            sections.append(cur)
            continue
        if cur is not None and "=" in line:
            k, v = line.split("=", 1)
            cur[k.strip()] = v.strip()
        elif cur is not None and cur["_name"] == "VERSION":
            cur["version"] = line
    return sections


def _float(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def load(path):
    with open(path, "rb") as f:
        data = f.read()
    head = data[:2048].decode("ascii", errors="ignore")
    m = re.search(r"Charset=([\w\-]+)", head)
    text, enc, how = decode_bytes(data, m.group(1) if m else None, preferred="cp932")
    secs = parse_sections(text)
    setting = next((s for s in secs if s["_name"] == "SETTING"), {})
    bpm = _float(setting.get("Tempo"), 120.0)
    score = Score(base_dir=os.path.dirname(os.path.abspath(path)))
    score.tempos = [(0, bpm)]
    track = Track(name="ust")
    track.extra_info = {"ust_encoding": enc, "voice_dir": setting.get("VoiceDir"), "flags": setting.get("Flags"), "mode2": setting.get("Mode2")}
    pos = 0
    for s in secs:
        name = s["_name"]
        if not re.fullmatch(r"\d+", name):
            continue  # VERSION, SETTING, TRACKEND, PREV, NEXT, INSERT, DELETE
        length = int(_float(s.get("Length"), 0) or 0)
        if "Tempo" in s and _float(s["Tempo"]):
            score.tempos = sorted({t: b for t, b in score.tempos + [(pos, _float(s["Tempo"]))]}.items())
        lyric = s.get("Lyric", "")
        if length <= 0:
            continue
        if lyric in ("R", "r", "") or lyric.lower() == "rest":
            pos += length
            continue
        tone = _float(s.get("NoteNum"))
        if tone is None:
            raise WarbleError("ust_bad_note", f"{path}: note [#{name}] has no NoteNum")
        controls = {}
        for k, c in CONTROL_MAP.items():
            v = _float(s.get(k))
            if v is not None:
                controls[c] = v
        if s.get("Flags"):
            controls["flags"] = s["Flags"]
        pre = _float(s.get("PreUtterance"))
        if pre is not None:
            controls["preutter"] = pre
        ovl = _float(s.get("VoiceOverlap"))
        if ovl is not None:
            controls["overlap"] = ovl
        extra = {"ust": {k: v for k, v in s.items() if not k.startswith("_")}}
        pb = s.get("PitchBend") or s.get("Piches") or s.get("Pitches")
        if pb:
            cents = [_float(x, 0.0) for x in pb.split(",") if x.strip() != ""]
            extra["pitchbend"] = {"start_ms": _float(s.get("PBStart"), 0.0), "cents": cents}
        note = Note(lyric=lyric, tone=tone, position=pos, duration=length, controls=controls, extra=extra, line=None)
        note.ust_index = name
        track.notes.append(note)
        pos += length
    score.tracks.append(track)
    return score
