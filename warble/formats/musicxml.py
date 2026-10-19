"""musicxml import and export (partwise; .musicxml, .xml, or compressed .mxl).

import reads one or more parts: pitches, durations (via divisions), rests, ties (tied notes merge),
slurs (a note under a slur without its own lyric becomes a '+' continuation), lyrics (first verse;
'extend' melismas become '+'), tempo (<sound tempo> or <metronome>) and time signatures. chords
keep the top note.
"""

import os
import xml.etree.ElementTree as ET
import zipfile

from ..errors import WarbleError
from ..score import TPQ, Note, Score, Track

STEP = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def _read(path):
    if path.lower().endswith(".mxl"):
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            root_file = None
            if "META-INF/container.xml" in names:
                c = ET.fromstring(z.read("META-INF/container.xml"))
                rf = c.find(".//{*}rootfile")
                if rf is not None:
                    root_file = rf.get("full-path")
            root_file = root_file or next(n for n in names if n.endswith((".xml", ".musicxml")) and not n.startswith("META-INF"))
            return ET.fromstring(z.read(root_file))
    return ET.parse(path).getroot()


def _strip(root):
    for el in root.iter():
        if "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    return root


def load(path, part=None):
    try:
        root = _strip(_read(path))
    except (ET.ParseError, zipfile.BadZipFile, KeyError, StopIteration) as e:
        raise WarbleError("musicxml_unreadable", f"cannot read {path}: {e}")
    if root.tag == "score-timewise":
        raise WarbleError("musicxml_timewise", "timewise musicxml is not supported", hint="export partwise from your notation app")
    score = Score(base_dir=os.path.dirname(os.path.abspath(path)))
    names = {sp.get("id"): (sp.findtext("part-name") or sp.get("id")) for sp in root.iter("score-part")}
    parts = root.findall("part")
    if part is not None:
        parts = [p for p in parts if p.get("id") == part or names.get(p.get("id")) == part or str(parts.index(p)) == str(part)]
        if not parts:
            raise WarbleError("musicxml_part_missing", f"no part '{part}'", hint=f"parts: {names}")
    tempos, sigs = {}, {}
    for pi, p in enumerate(parts):
        tr = Track(name=names.get(p.get("id"), f"part{pi + 1}"))
        divisions = 1
        pos = 0
        last_start = 0
        in_slur = False
        prev_note = None
        tie_open = False
        for meas in p.findall("measure"):
            for el in meas:
                if el.tag == "attributes":
                    d = el.findtext("divisions")
                    if d:
                        divisions = int(float(d))
                    t = el.find("time")
                    if t is not None and t.findtext("beats"):
                        try:
                            sigs[pos] = (int(t.findtext("beats")), int(t.findtext("beat-type")))
                        except ValueError:
                            pass
                elif el.tag == "direction":
                    snd = el.find(".//sound")
                    if snd is not None and snd.get("tempo"):
                        tempos[pos] = float(snd.get("tempo"))
                    met = el.find(".//metronome")
                    if met is not None and met.findtext("per-minute") and pos not in tempos:
                        unit = met.findtext("beat-unit") or "quarter"
                        mult = {"half": 2, "quarter": 1, "eighth": 0.5, "16th": 0.25}.get(unit, 1)
                        if met.find("beat-unit-dot") is not None:
                            mult *= 1.5
                        try:
                            tempos[pos] = float(met.findtext("per-minute")) * mult
                        except ValueError:
                            pass
                elif el.tag == "sound" and el.get("tempo"):
                    tempos[pos] = float(el.get("tempo"))
                elif el.tag == "backup":
                    pos -= int(round(int(el.findtext("duration")) * TPQ / divisions))
                elif el.tag == "forward":
                    pos += int(round(int(el.findtext("duration")) * TPQ / divisions))
                elif el.tag == "note":
                    if el.find("grace") is not None:
                        continue
                    dur = int(round(int(el.findtext("duration") or 0) * TPQ / divisions))
                    if el.find("chord") is not None:
                        # keep the top note of a chord
                        pitch = _pitch(el)
                        if prev_note is not None and pitch is not None and pitch > prev_note.tone and prev_note.position == last_start:
                            prev_note.tone = pitch
                        continue
                    if (el.findtext("voice") or "1") != "1":
                        pos += dur
                        continue
                    start = pos
                    last_start = start
                    pos += dur
                    if el.find("rest") is not None:
                        prev_note = None
                        tie_open = False
                        continue
                    pitch = _pitch(el)
                    ties = {t.get("type") for t in el.findall("tie")} | {t.get("type") for t in el.findall(".//tied")}
                    slurs = [s.get("type") for s in el.findall(".//slur")]
                    lyric_el = el.find("lyric")
                    text = None
                    extend = False
                    if lyric_el is not None:
                        text = "".join(t.text or "" for t in lyric_el.findall("text")) or None
                        extend = lyric_el.find("extend") is not None and text is None
                    if tie_open and prev_note is not None and prev_note.end == start and prev_note.tone == pitch:
                        prev_note.duration += dur  # tied: one longer note
                    else:
                        if text:
                            lyr = text.strip()
                        elif (in_slur or extend) and prev_note is not None and prev_note.end == start:
                            lyr = "+"
                        else:
                            lyr = "a" if not tr.notes else ("+" if prev_note is not None and prev_note.end == start and in_slur else "a")
                        prev_note = Note(lyric=lyr, tone=float(pitch), position=start, duration=dur)
                        tr.notes.append(prev_note)
                    tie_open = "start" in ties
                    if "start" in slurs:
                        in_slur = True
                    if "stop" in slurs and "start" not in slurs:
                        in_slur = False
        if tr.notes:
            score.tracks.append(tr)
    score.tempos = sorted(tempos.items()) or [(0, 120.0)]
    if score.tempos[0][0] != 0:
        score.tempos.insert(0, (0, score.tempos[0][1]))
    score.time_signatures = sorted((t, a, b) for t, (a, b) in sigs.items()) or [(0, 4, 4)]
    if not score.tracks:
        raise WarbleError("musicxml_no_notes", f"{path} has no notes")
    unlyric = sum(1 for t in score.tracks for n in t.notes if n.lyric == "a")
    score.import_report = {"source": path, "parts": names, "tracks": [t.name for t in score.tracks],
                           "notes": sum(len(t.notes) for t in score.tracks), "notes_without_lyrics": unlyric}
    return score


def _pitch(el):
    p = el.find("pitch")
    if p is None:
        return None
    step = STEP[p.findtext("step").strip().upper()]
    alter = float(p.findtext("alter") or 0)
    octave = int(p.findtext("octave"))
    return (octave + 1) * 12 + step + alter


NAMES = ["C", "C", "D", "D", "E", "F", "F", "G", "G", "A", "A", "B"]
ALTER = [0, 1, 0, 1, 0, 0, 1, 0, 1, 0, 1, 0]
TYPES = [(1920, "whole"), (960, "half"), (480, "quarter"), (240, "eighth"), (120, "16th"), (60, "32nd")]


def save(score, path):
    root = ET.Element("score-partwise", version="3.1")
    pl = ET.SubElement(root, "part-list")
    for i, tr in enumerate(score.tracks, start=1):
        sp = ET.SubElement(pl, "score-part", id=f"P{i}")
        ET.SubElement(sp, "part-name").text = tr.name
    num, den = score.time_signatures[0][1], score.time_signatures[0][2]
    bar_len = int(num * TPQ * 4 / den)
    for i, tr in enumerate(score.tracks, start=1):
        part = ET.SubElement(root, "part", id=f"P{i}")
        # split notes and rests at barlines (with ties)
        events = []
        pos = 0
        for k, n in enumerate(tr.notes):
            if n.position > pos:
                events.append((pos, n.position - pos, None, None))
            nxt_cont = k + 1 < len(tr.notes) and tr.notes[k + 1].lyric.startswith("+") and tr.notes[k + 1].position == n.end
            events.append((n.position, n.duration, n, nxt_cont))
            pos = n.end
        end = max(pos, bar_len)
        n_bars = (end + bar_len - 1) // bar_len
        if pos < n_bars * bar_len:
            events.append((pos, n_bars * bar_len - pos, None, None))
        tempos = dict(score.tempos)
        cur_bar = None
        meas = None
        slur_open = False
        for start, dur, n, cont in events:
            remaining, t = dur, start
            first = True
            while remaining > 0:
                b = t // bar_len
                if b != cur_bar:
                    cur_bar = b
                    meas = ET.SubElement(part, "measure", number=str(b + 1))
                    if b == 0:
                        at = ET.SubElement(meas, "attributes")
                        ET.SubElement(at, "divisions").text = str(TPQ)
                        tm = ET.SubElement(at, "time")
                        ET.SubElement(tm, "beats").text = str(num)
                        ET.SubElement(tm, "beat-type").text = str(den)
                    for tt, bpm in tempos.items():
                        if b * bar_len <= tt < (b + 1) * bar_len and (b == 0 and tt == 0 or tt > 0):
                            d = ET.SubElement(meas, "direction", placement="above")
                            dt = ET.SubElement(ET.SubElement(d, "direction-type"), "metronome")
                            ET.SubElement(dt, "beat-unit").text = "quarter"
                            ET.SubElement(dt, "per-minute").text = f"{bpm:g}"
                            ET.SubElement(d, "sound", tempo=f"{bpm:g}")
                chunk = min(remaining, (b + 1) * bar_len - t)
                ne = ET.SubElement(meas, "note")
                if n is None:
                    ET.SubElement(ne, "rest")
                else:
                    tone = int(round(n.tone))
                    p = ET.SubElement(ne, "pitch")
                    ET.SubElement(p, "step").text = NAMES[tone % 12]
                    if ALTER[tone % 12]:
                        ET.SubElement(p, "alter").text = "1"
                    ET.SubElement(p, "octave").text = str(tone // 12 - 1)
                ET.SubElement(ne, "duration").text = str(chunk)
                if n is not None:
                    tie_stop = not first
                    tie_start = remaining - chunk > 0
                    for typ, on in (("stop", tie_stop), ("start", tie_start)):
                        if on:
                            ET.SubElement(ne, "tie", type=typ)
                ET.SubElement(ne, "voice").text = "1"
                tname = next((nm for tk, nm in TYPES if chunk >= tk), "32nd")
                ET.SubElement(ne, "type").text = tname
                if n is not None:
                    nots = None
                    if not first or remaining - chunk > 0:
                        nots = ET.SubElement(ne, "notations")
                        if not first:
                            ET.SubElement(nots, "tied", type="stop")
                        if remaining - chunk > 0:
                            ET.SubElement(nots, "tied", type="start")
                    if first:
                        is_cont = n.lyric.startswith("+")
                        if (cont and not is_cont) or (is_cont and not cont):
                            nots = nots if nots is not None else ET.SubElement(ne, "notations")
                            ET.SubElement(nots, "slur", type="start" if cont and not is_cont else "stop", number="1")
                        if not is_cont:
                            ly = ET.SubElement(ne, "lyric", number="1")
                            ET.SubElement(ly, "syllabic").text = "single"
                            ET.SubElement(ly, "text").text = n.lyric if not n.hint else n.hint
                t += chunk
                remaining -= chunk
                first = False
    tree = ET.ElementTree(root)
    ET.indent(tree)
    with open(path, "wb") as f:
        f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write(b'<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 3.1 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">\n')
        tree.write(f, encoding="utf-8")
    return path
