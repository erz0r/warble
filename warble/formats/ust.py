"""utau .ust import and export.

import maps ust fields onto score notes and controls:
  Length/Lyric/NoteNum/Tempo            notes, rests ('R'), tempo changes
  Intensity -> vol, Velocity -> vel, Modulation -> mod, Flags -> flags
  PreUtterance / VoiceOverlap -> preutter / overlap (absolute overrides)
  StartPoint -> stp
  PBS/PBW/PBY/PBM (mode2) -> pts, VBR -> vbr          (see warble.tuning.curve)
  PitchBend + PBStart (mode1) -> raw
  Envelope -> env (raw) and dec (= 100 - v3, as openutau reads it)
export writes the same fields back, so tuning survives a round trip through utau or openutau.
mode2 parsing follows openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Core/Classic/UstNote.cs.
"""

import os
import re

from ..errors import WarbleError
from ..score import Note, Score, Track
from ..textenc import decode_bytes
from ..tuning import curve

CONTROL_MAP = {"Intensity": "vol", "Velocity": "vel", "Modulation": "mod", "Moduration": "mod"}
PBM_TO_SHAPE = {"r": "o", "s": "l", "j": "i", "": "io"}
SHAPE_TO_PBM = {"o": "r", "l": "s", "i": "j", "io": "", "sp": "", "h": "s"}


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


def mode2_points(pbs, pbw, pby, pbm):
    """ParsePitchBend: PBS 'x;y' (or 'x,y'), PBW widths, PBY heights (0.1 semitones), PBM shapes.
    returns [[x_ms, y_cents, shape], ...] or None."""
    if not pbs:
        return None
    parts = pbs.split(";") if ";" in pbs else pbs.split(",")
    x0 = _float(parts[0], 0.0) if parts else 0.0
    y0 = _float(parts[1], 0.0) if len(parts) > 1 else 0.0
    pts = [[x0, y0 * 10, "io"]]
    w = [_float(s, 0.0) for s in pbw.split(",")] if pbw else []
    y = [_float(s, 0.0) for s in pby.split(",")] if pby else []
    while len(y) < len(w):
        y.append(0.0)
    x = x0
    for wi, yi in zip(w, y):
        x += wi
        pts.append([x, yi * 10, "io"])
    if pbm:
        for i, m in enumerate(pbm.split(",")):
            if i < len(pts):
                pts[i][2] = PBM_TO_SHAPE.get(m.strip(), "io")
    return pts if len(pts) > 1 else None


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
    score.ust_setting = {k: v for k, v in setting.items() if not k.startswith("_")}
    score.ust_encoding = enc
    mode2 = str(setting.get("Mode2", "")).lower() == "true"
    pos = 0
    prev_end = None
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
        for key, ctl in (("PreUtterance", "preutter"), ("VoiceOverlap", "overlap"), ("StartPoint", "stp")):
            v = _float(s.get(key))
            if v is not None:
                controls[ctl] = v
        pts = mode2_points(s.get("PBS"), s.get("PBW"), s.get("PBY"), s.get("PBM"))
        if pts:
            controls["pts"] = curve.format_points(pts)
            # openutau: a note that doesn't touch the previous one doesn't snap its first point
            if prev_end is None or pos > prev_end:
                controls["snap"] = 0
        if s.get("VBR"):
            v = curve.parse_vibrato(s["VBR"])
            if v["length"] > 0:
                controls["vbr"] = curve.format_vibrato(v)
        if s.get("Envelope"):
            controls["env"] = s["Envelope"].replace(",", ";")
            ev = [_float(x) for x in s["Envelope"].split(",")]
            if len(ev) >= 6 and ev[5] is not None:
                controls["dec"] = 100 - ev[5]
        pb = s.get("PitchBend") or s.get("Piches") or s.get("Pitches")
        extra = {}
        if pb:
            cents = [_float(x, 0.0) for x in pb.split(",") if x.strip() != ""]
            start = _float(s.get("PBStart"), 0.0)
            raw = curve.format_raw({"start_ms": start, "step_ms": 0, "cents": cents})  # step 0 = 5 ticks
            if mode2 and pts:
                # utau sings the mode2 curve; the mode1 array is stale but kept for export
                extra["ust_mode1"] = raw
            else:
                controls["raw"] = raw
        note = Note(lyric=lyric, tone=tone, position=pos, duration=length, controls=controls, extra=extra)
        track.notes.append(note)
        pos += length
        prev_end = pos
    score.tracks.append(track)
    return score


def save(score, path, track_index=0, voice_dir=None, encoding=None):
    """write one track as a ust (version 1.2, mode2)."""
    tr = score.tracks[track_index]
    tempos = dict(score.tempos)
    lines = ["[#VERSION]", "UST Version1.2", "[#SETTING]", f"Tempo={_num(score.tempos[0][1])}", "Tracks=1",
             f"ProjectName={tr.name}", f"VoiceDir={voice_dir or tr.bank or ''}", "OutFile=", "CacheDir=", "Mode2=True"]
    idx = 0
    pos = 0

    def section():
        nonlocal idx
        lines.append(f"[#{idx:04d}]")
        idx += 1

    def tempo_at(p):
        if p in tempos and p != 0:
            lines.append(f"Tempo={_num(tempos[p])}")

    for n in tr.notes:
        if n.position > pos:
            section()
            lines += [f"Length={n.position - pos}", "Lyric=R", f"NoteNum={int(round(n.tone))}", "PreUtterance="]
            tempo_at(pos)
            pos = n.position
        section()
        lines += [f"Length={n.duration}", f"Lyric={n.hint if n.hint else n.lyric}", f"NoteNum={int(round(n.tone))}"]
        tempo_at(n.position)
        c = n.controls
        lines.append(f"PreUtterance={_num(c['preutter'])}" if "preutter" in c else "PreUtterance=")
        if "overlap" in c:
            lines.append(f"VoiceOverlap={_num(c['overlap'])}")
        if "stp" in c:
            lines.append(f"StartPoint={_num(c['stp'])}")
        for ctl, key in (("vol", "Intensity"), ("vel", "Velocity"), ("mod", "Modulation")):
            if ctl in c:
                lines.append(f"{key}={_num(c[ctl])}")
        if c.get("flags"):
            lines.append(f"Flags={c['flags']}")
        if c.get("env"):
            lines.append(f"Envelope={str(c['env']).replace(';', ',')}")
        pts = curve.note_points(n)
        if pts:
            lines.append(f"PBS={_num(pts[0][0])};{_num(pts[0][1] / 10)}")
            pbw, pby = [], []
            for a, b in zip(pts, pts[1:]):
                pbw.append(_num(b[0] - a[0]))
                pby.append(_num(b[1] / 10))
            lines.append(f"PBW={','.join(pbw)}")
            lines.append(f"PBY={','.join(pby)}")
            lines.append(f"PBM={','.join(SHAPE_TO_PBM.get(p[2], '') for p in pts)}")
        v = curve.note_vibrato(n)
        if v:
            lines.append("VBR=" + ",".join(_num(v[k]) for k in ("length", "period", "depth", "in", "out", "shift", "drift")))
        raw = c.get("raw") or (n.extra or {}).get("ust_mode1")
        if raw:
            r = curve.parse_raw(str(raw))
            lines += ["PBType=5", f"PitchBend={','.join(_num(x) for x in r['cents'])}", f"PBStart={_num(r['start_ms'])}"]
        pos = n.end
    lines.append("[#TRACKEND]")
    text = "\r\n".join(lines) + "\r\n"
    enc = encoding or "cp932"
    try:
        data = text.encode(enc)
    except UnicodeEncodeError:
        text = text.replace("[#SETTING]", "[#SETTING]\r\nCharset=UTF-8", 1)
        data = text.encode("utf-8")
    with open(path, "wb") as f:
        f.write(data)
    return path


def _num(x):
    x = float(x)
    if x == int(x):
        return str(int(x))
    return f"{x:.6g}"
