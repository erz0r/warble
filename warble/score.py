"""the score: tracks of notes on a tick grid (480 per beat, like openutau and ust), plus a tempo map.

text format, one item per line, '#' starts a comment:

    bank ./banks/some_singer        # directives apply to the following notes
    bpm 120                         # or: bpm 140 @ bar 17   /   bpm 90 @ beat 32
    time 3/4                        # time signature from here (or: time 3/4 @ bar 9)
    key C
    lang ja
    voice default
    track lead                      # starts or switches to a named track
    volume -3                       # track gain in db; pan -1..1 with 'pan'
    ら C4 1                          # lyric, pitch, length (beats: 1, 1/2, 1.5, or ms: 350ms)
    + E4 1/2                        # continuation (melisma) of the previous syllable; +~ / +* too
    r 1                             # rest
    [k a] G4 1                      # explicit phonemes (diffsinger) or [alias] (utau)
    か A4 1 @ 5:1                    # place at bar 5 beat 1 instead of after the previous note
    さ B4 1 vel=120 expr=0.8         # per-note controls as key=value
"""

import json
import math
import os
import re
from dataclasses import dataclass, field

from .errors import WarbleError

TPQ = 480  # ticks per quarter note / beat
COMMENT_RE = re.compile(r"(^|\s)#.*$")
NOTE_RE = re.compile(r"^([A-Ga-g])([#b]?)(-?\d+)([+-]\d+c?)?$")
STEPS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# controls a note may carry; the value is parsed as a float unless listed as text
TEXT_CONTROLS = {"vib", "voice", "flags", "resampler", "phonemizer", "lang", "alt", "color"}


def parse_pitch(text, where=""):
    """'C4' -> 60, 'C#4' / 'Db4' -> 61, '60' -> 60, 'A4+20c' -> 69.2."""
    t = text.strip()
    if re.fullmatch(r"-?\d+(\.\d+)?", t):
        return float(t)
    m = NOTE_RE.match(t)
    if not m:
        raise WarbleError("bad_pitch", f"cannot read pitch '{text}'{where}", hint="use a note name like C4, F#3, Bb4, or a midi number like 60")
    tone = (int(m.group(3)) + 1) * 12 + STEPS[m.group(1).upper()] + {"#": 1, "b": -1, "": 0}[m.group(2)]
    if m.group(4):
        tone += float(m.group(4).rstrip("c")) / 100.0
    return float(tone)


def pitch_name(tone):
    t = int(round(tone))
    cents = round((tone - t) * 100)
    base = f"{NAMES[t % 12]}{t // 12 - 1}"
    return base + (f"{cents:+d}c" if cents else "")


@dataclass
class Note:
    lyric: str
    tone: float  # midi, may be fractional
    position: int  # ticks
    duration: int  # ticks
    hint: str = None  # explicit phonemes / alias from [ ... ]
    controls: dict = field(default_factory=dict)
    line: int = None  # source line for error messages
    # imported tuning that isn't a scalar control: {"pitchbend": {"start_ms", "cents": [...]}, "ust": {raw fields}}
    extra: dict = field(default_factory=dict)

    @property
    def end(self):
        return self.position + self.duration

    @property
    def is_continuation(self):
        return self.lyric.startswith("+")

    def to_json(self):
        out = {"lyric": self.lyric, "pitch": pitch_name(self.tone), "tone": self.tone, "position": self.position, "duration": self.duration}
        if self.hint:
            out["hint"] = self.hint
        if self.controls:
            out["controls"] = self.controls
        if self.extra:
            out["extra"] = self.extra
        return out


@dataclass
class Track:
    name: str
    bank: str = None
    lang: str = None
    voice: str = None
    phonemizer: str = None
    engine: str = None
    volume_db: float = 0.0
    pan: float = 0.0
    notes: list = field(default_factory=list)
    # track curves in openutau abbreviations: {"pitd": [(tick, cents), ...], "dyn": [(tick, db)], ...}
    curves: dict = field(default_factory=dict)
    fx: dict = field(default_factory=dict)  # see warble.mix
    harmonize: dict = None  # {"source", "interval", "key"}: notes are generated from another track

    def curve_at(self, abbr, ticks, default=0.0):
        import numpy as np

        pts = self.curves.get(abbr)
        if not pts:
            return np.full(np.shape(ticks), default, float)
        xs = np.array([p[0] for p in pts], float)
        ys = np.array([p[1] for p in pts], float)
        return np.interp(ticks, xs, ys)

    def to_json(self):
        return {
            "name": self.name, "bank": self.bank, "lang": self.lang, "voice": self.voice,
            "phonemizer": self.phonemizer, "engine": self.engine, "volume_db": self.volume_db, "pan": self.pan,
            "notes": [n.to_json() for n in self.notes],
            **({"curves": {k: [list(p) for p in v] for k, v in self.curves.items()}} if self.curves else {}),
        }


class TempoMap:
    """piecewise-constant tempo over ticks."""

    def __init__(self, changes=None):
        self.changes = sorted(changes or [(0, 120.0)])
        if self.changes[0][0] != 0:
            self.changes.insert(0, (0, self.changes[0][1]))
        # dedupe positions, later entry wins
        d = {}
        for t, b in self.changes:
            d[t] = b
        self.changes = sorted(d.items())
        self._ms = [0.0]
        for (t0, b0), (t1, _) in zip(self.changes, self.changes[1:]):
            self._ms.append(self._ms[-1] + (t1 - t0) * 60000.0 / (b0 * TPQ))

    def tick_to_ms(self, tick):
        i = self._seg_by_tick(tick)
        t0, bpm = self.changes[i]
        return self._ms[i] + (tick - t0) * 60000.0 / (bpm * TPQ)

    def ms_to_tick(self, ms):
        i = 0
        for j in range(len(self._ms)):
            if self._ms[j] <= ms:
                i = j
        t0, bpm = self.changes[i]
        return t0 + (ms - self._ms[i]) * bpm * TPQ / 60000.0

    def _seg_by_tick(self, tick):
        i = 0
        for j, (t, _) in enumerate(self.changes):
            if t <= tick:
                i = j
        return i

    def bpm_at(self, tick):
        return self.changes[self._seg_by_tick(tick)][1]


@dataclass
class Score:
    tracks: list = field(default_factory=list)
    tempos: list = field(default_factory=lambda: [(0, 120.0)])
    time_signatures: list = field(default_factory=lambda: [(0, 4, 4)])  # (tick, num, den)
    key: str = None
    base_dir: str = "."
    master: dict = field(default_factory=dict)  # see warble.mix
    backings: list = field(default_factory=list)  # [{"path", "at_ms" | "at_tick", "gain_db"}]

    @property
    def tempo_map(self):
        return TempoMap(self.tempos)

    def track(self, name):
        for t in self.tracks:
            if t.name == name:
                return t
        return None

    def bar_to_tick(self, bar, beat=1.0):
        """1-based bar and beat (in the bar's own beat unit) to ticks, honoring time signature changes."""
        sigs = sorted(self.time_signatures)
        tick, cur_bar = 0, 1
        num, den = sigs[0][1], sigs[0][2]
        idx = 1
        while cur_bar < bar:
            # apply a signature change that starts at this bar's tick
            while idx < len(sigs) and sigs[idx][0] <= tick:
                num, den = sigs[idx][1], sigs[idx][2]
                idx += 1
            tick += int(num * TPQ * 4 / den)
            cur_bar += 1
        while idx < len(sigs) and sigs[idx][0] <= tick:
            num, den = sigs[idx][1], sigs[idx][2]
            idx += 1
        return tick + int(round((beat - 1) * TPQ * 4 / den))

    def tick_to_bar(self, tick):
        sigs = sorted(self.time_signatures)
        t, bar = 0, 1
        num, den = sigs[0][1], sigs[0][2]
        idx = 1
        while True:
            while idx < len(sigs) and sigs[idx][0] <= t:
                num, den = sigs[idx][1], sigs[idx][2]
                idx += 1
            bar_len = int(num * TPQ * 4 / den)
            if tick < t + bar_len:
                return bar, 1 + (tick - t) / (TPQ * 4 / den)
            t += bar_len
            bar += 1

    @property
    def end_tick(self):
        return max((n.end for t in self.tracks for n in t.notes), default=0)

    def to_text(self):
        """write the score back in the text format (positions explicit only where needed)."""
        lines = []
        for t, b in self.tempos:
            lines.append(f"bpm {fmt_num(b)}" + (f" @ tick {t}" if t else ""))
        for t, n, d in self.time_signatures:
            lines.append(f"time {n}/{d}" + (f" @ tick {t}" if t else ""))
        if self.key:
            lines.append(f"key {self.key}")
        if self.master:
            lines.append("master " + " ".join(f"{k}={v}" for k, v in self.master.items()))
        for b in self.backings:
            where = f" @ {fmt_num(b['at_ms'] / 1000)}s" if b.get("at_ms") else (f" @ tick {b['at_tick']}" if b.get("at_tick") else "")
            lines.append(f"backing {b['path']}{where}" + (f" gain={fmt_num(b['gain_db'])}" if b.get("gain_db") else ""))
        for tr in self.tracks:
            lines.append(f"track {tr.name}")
            for k in ("bank", "lang", "voice", "phonemizer", "engine"):
                if getattr(tr, k):
                    lines.append(f"{k} {getattr(tr, k)}")
            if tr.volume_db:
                lines.append(f"volume {fmt_num(tr.volume_db)}")
            if tr.pan:
                lines.append(f"pan {fmt_num(tr.pan)}")
            for abbr, pts in sorted(tr.curves.items()):
                lines.append(f"curve {abbr} " + ",".join(f"{int(t)}:{fmt_num(v)}" for t, v in pts))
            if tr.fx:
                lines.append("fx " + " ".join(f"{k}={v}" for k, v in tr.fx.items()))
            if tr.harmonize:
                h = tr.harmonize
                lines.append(f"harmonize {h['source']} {h['interval']}" + (f" key={h['key']}" if h.get("key") else ""))
                continue
            pos = 0
            for n in tr.notes:
                if n.position > pos:
                    lines.append(f"r {fmt_beats(n.position - pos)}")
                lyr = f"[{n.hint}]" if n.hint else n.lyric
                ctl = " ".join(f"{k}={v if isinstance(v, str) else fmt_num(v)}" for k, v in n.controls.items() if k not in ("bank",))
                lines.append(f"{lyr} {pitch_name(n.tone)} {fmt_beats(n.duration)}" + (f" {ctl}" if ctl else ""))
                pos = n.end
        return "\n".join(lines) + "\n"

    def to_json(self):
        return {
            "tempos": [{"tick": t, "bpm": b} for t, b in self.tempos],
            "time_signatures": [{"tick": t, "num": n, "den": d} for t, n, d in self.time_signatures],
            "key": self.key,
            "tracks": [t.to_json() for t in self.tracks],
        }


def fmt_num(x):
    x = float(x)
    return str(int(x)) if x == int(x) else f"{x:g}"


def fmt_beats(ticks):
    """ticks -> '1', '1/2', '3/4', '1.25' or exact '123/480' when nothing simpler fits."""
    from fractions import Fraction

    f = Fraction(int(ticks), TPQ)
    if f.denominator == 1:
        return str(f.numerator)
    if f.denominator <= 16:
        return f"{f.numerator}/{f.denominator}"
    return f"{int(ticks)}/{TPQ}"


# ---- parsing --------------------------------------------------------------------------

def _parse_length(text, tempo_map, at_tick, where):
    """beats ('1', '1/2', '1.5', '3/8') or milliseconds ('350ms'). returns ticks."""
    t = text.strip().lower()
    try:
        if t.endswith("ms"):
            ms = float(t[:-2])
            start_ms = tempo_map.tick_to_ms(at_tick)
            return int(round(tempo_map.ms_to_tick(start_ms + ms) - at_tick))
        if "/" in t:
            a, b = t.split("/", 1)
            beats = float(a) / float(b)
        else:
            beats = float(t)
    except ValueError:
        raise WarbleError("bad_length", f"cannot read length '{text}'{where}", hint="use beats (1, 1/2, 1.5) or ms (350ms)")
    if beats <= 0:
        raise WarbleError("bad_length", f"length must be positive, got '{text}'{where}")
    return int(round(beats * TPQ))


def _parse_controls(tokens, where):
    controls = {}
    for tok in tokens:
        if "=" not in tok:
            raise WarbleError("bad_control", f"expected key=value, got '{tok}'{where}")
        k, v = tok.split("=", 1)
        k = k.strip().lower()
        if k in TEXT_CONTROLS:
            controls[k] = v
            continue
        try:
            controls[k] = float(v.rstrip("c%"))
        except ValueError:
            controls[k] = v
    return controls


def _split_note_line(line):
    """split on whitespace but keep [ ... ] hints together."""
    out, buf, depth = [], "", 0
    for ch in line:
        if ch == "[":
            depth += 1
        if ch == "]":
            depth -= 1
        if ch.isspace() and depth == 0:
            if buf:
                out.append(buf)
                buf = ""
        else:
            buf += ch
    if buf:
        out.append(buf)
    return out


def parse_text(text, base_dir=".", source="<score>"):
    score = Score(base_dir=base_dir)
    pending_tempos = []
    # first pass for tempo/time so ms lengths and '@ bar' resolve against the final map
    lines = text.splitlines()
    state = {"bank": None, "lang": None, "voice": None, "phonemizer": None, "engine": None}
    cursor = {}  # track name -> tick
    current = None

    def ensure_track(name="main"):
        nonlocal current
        t = score.track(name)
        if t is None:
            t = Track(name=name, **{k: v for k, v in state.items()})
            score.tracks.append(t)
            cursor[name] = 0
        current = t
        return t

    for lineno, raw in enumerate(lines, start=1):
        # '#' starts a comment only at line start or after whitespace, so C#4 survives
        line = COMMENT_RE.sub("", raw).strip()
        if not line:
            continue
        where = f" ({source} line {lineno})"
        parts = _split_note_line(line)
        head = parts[0].lower()
        if head == "track":
            if len(parts) < 2:
                raise WarbleError("bad_directive", f"'track' needs a name{where}")
            ensure_track(parts[1])
            continue
        if head in ("bank", "lang", "voice", "phonemizer", "engine"):
            if len(parts) < 2:
                raise WarbleError("bad_directive", f"'{head}' needs a value{where}")
            value = line.split(None, 1)[1].strip()
            if head == "bank":
                value = resolve_bank(value, base_dir)
            state[head] = value
            t = current or ensure_track()
            # a directive before any note on the track sets the track default; later it's a per-note change
            if not t.notes:
                setattr(t, head, value)
            continue
        if head in ("volume", "pan"):
            t = current or ensure_track()
            try:
                val = float(parts[1].replace("db", ""))
            except (IndexError, ValueError):
                raise WarbleError("bad_directive", f"'{head}' needs a number{where}")
            if head == "volume":
                t.volume_db = val
            else:
                t.pan = max(-1.0, min(1.0, val))
            continue
        if head in ("bpm", "tempo"):
            bpm = float(parts[1])
            at = _parse_at(parts[2:], score, cursor.get(current.name, 0) if current else 0, where)
            pending_tempos.append((at, bpm))
            score.tempos = sorted({t: b for t, b in score.tempos + [(at, bpm)]}.items())
            continue
        if head == "time":
            m = re.fullmatch(r"(\d+)/(\d+)", parts[1]) if len(parts) > 1 else None
            if not m:
                raise WarbleError("bad_directive", f"'time' needs a signature like 3/4{where}")
            at = _parse_at(parts[2:], score, cursor.get(current.name, 0) if current else 0, where)
            sigs = [s for s in score.time_signatures if s[0] != at]
            score.time_signatures = sorted(sigs + [(at, int(m.group(1)), int(m.group(2)))])
            continue
        if head == "key":
            score.key = parts[1] if len(parts) > 1 else None
            continue
        if head == "fx":
            t = current or ensure_track()
            for kv in parts[1:]:
                if "=" not in kv:
                    raise WarbleError("bad_directive", f"'fx' takes key=value pairs{where}", hint="fx eq=low:2,high:3 comp=-18:3 reverb=0.25")
                k, v = kv.split("=", 1)
                t.fx[k.lower()] = v
            continue
        if head == "master":
            for kv in parts[1:]:
                if "=" not in kv:
                    raise WarbleError("bad_directive", f"'master' takes key=value pairs{where}", hint="master lufs=-14 ceiling=-1 room=1.6 preset=pop")
                k, v = kv.split("=", 1)
                score.master[k.lower()] = v if k.lower() in ("preset", "chain") else float(v)
            continue
        if head == "backing":
            if len(parts) < 2:
                raise WarbleError("bad_directive", f"'backing' needs a file{where}")
            path = parts[1] if os.path.isabs(parts[1]) else os.path.normpath(os.path.join(base_dir, parts[1]))
            b = {"path": path, "gain_db": 0.0}
            rest = parts[2:]
            if rest and rest[0] == "@":
                if len(rest) > 1 and rest[1].endswith("s") and re.fullmatch(r"-?\d+(\.\d+)?s", rest[1]):
                    b["at_ms"] = float(rest[1][:-1]) * 1000
                    rest = rest[2:]
                else:
                    b["at_tick"] = _parse_at(rest, score, 0, where)
                    rest = rest[3:] if len(rest) > 1 and rest[1] in ("bar", "beat", "tick") else rest[2:]
            for kv in rest:
                if kv.startswith("gain="):
                    b["gain_db"] = float(kv[5:])
            score.backings.append(b)
            continue
        if head == "harmonize":
            if len(parts) < 3:
                raise WarbleError("bad_directive", f"'harmonize' needs a source track and an interval{where}", hint="harmonize lead 3 key=C")
            t = current or ensure_track()
            t.harmonize = {"source": parts[1], "interval": parts[2]}
            for kv in parts[3:]:
                if kv.startswith("key="):
                    t.harmonize["key"] = kv[4:]
            continue
        if head == "curve":
            if len(parts) < 3:
                raise WarbleError("bad_directive", f"'curve' needs a name and tick:value points{where}", hint="curve pitd 0:0,480:-20,960:0")
            t = current or ensure_track()
            pts = []
            for item in parts[2].split(","):
                a, b = item.split(":")
                pts.append((int(float(a)), float(b)))
            t.curves[parts[1].lower()] = sorted(pts)
            continue

        # a note or a rest
        t = current or ensure_track()
        tm = score.tempo_map
        pos = cursor[t.name]
        if "@" in parts:
            i = parts.index("@")
            pos = _parse_at(parts[i:], score, pos, where)
            used = 3 if len(parts) > i + 1 and parts[i + 1] in ("bar", "beat", "tick") else 2
            parts = parts[:i] + parts[i + used :]
        if head in ("r", "rest", "-"):
            if len(parts) < 2:
                raise WarbleError("bad_rest", f"rest needs a length{where}")
            cursor[t.name] = pos + _parse_length(parts[1], tm, pos, where)
            continue
        if len(parts) < 3:
            raise WarbleError("bad_note", f"a note needs lyric, pitch and length: '{line}'{where}")
        lyric, pitch_txt, length_txt = parts[0], parts[1], parts[2]
        hint = None
        if lyric.startswith("[") and lyric.endswith("]"):
            hint = lyric[1:-1].strip()
            lyric = hint
        dur = _parse_length(length_txt, tm, pos, where)
        controls = _parse_controls(parts[3:], where)
        for k in ("voice", "lang"):
            if state[k] and state[k] != getattr(t, k):
                controls.setdefault(k, state[k])
        if state["bank"] and state["bank"] != t.bank:
            controls.setdefault("bank", state["bank"])
        note = Note(lyric=lyric, tone=parse_pitch(pitch_txt, where), position=pos, duration=dur, hint=hint, controls=controls, line=lineno)
        t.notes.append(note)
        cursor[t.name] = pos + dur
    for t in score.tracks:
        t.notes.sort(key=lambda n: n.position)
        _check_overlaps(t)
    _materialize_harmonies(score)
    return score


def _materialize_harmonies(score):
    """tracks declared with `harmonize <source> <interval>` get their notes generated now."""
    import copy as _copy

    from .harmony import interval_fn, parse_key, guess_key

    for t in score.tracks:
        h = t.harmonize
        if not h or t.notes:
            continue
        src = score.track(h["source"])
        if src is None:
            raise WarbleError("track_missing", f"track '{t.name}' harmonizes '{h['source']}', which doesn't exist")
        key = h.get("key") or score.key or guess_key(src.notes)
        _, scale, _ = parse_key(key)
        fn = interval_fn(h["interval"], scale)
        for n in src.notes:
            m = _copy.deepcopy(n)
            m.tone = float(fn(n.tone))
            m.controls = {k: v for k, v in n.controls.items() if k in ("vol", "vel", "flags", "brec", "gender", "tenc", "voic", "ene", "expr")}
            t.notes.append(m)
        t.bank = t.bank or src.bank
        t.lang = t.lang or src.lang


def _parse_at(parts, score, default, where):
    """'@ bar 17', '@ beat 32', '@ 5:2' (bar:beat), '@ 5' (bar). returns ticks."""
    if not parts:
        return default
    if parts[0] != "@":
        raise WarbleError("bad_position", f"expected '@ ...' but got {' '.join(parts)}{where}")
    rest = parts[1:]
    if not rest:
        raise WarbleError("bad_position", f"'@' needs a position{where}")
    if rest[0] == "bar" and len(rest) > 1:
        return score.bar_to_tick(int(rest[1]))
    if rest[0] == "beat" and len(rest) > 1:
        return int(round(float(rest[1]) * TPQ))
    if rest[0] == "tick" and len(rest) > 1:
        return int(rest[1])
    m = re.fullmatch(r"(\d+)(?::(\d+(?:\.\d+)?))?", rest[0])
    if m:
        return score.bar_to_tick(int(m.group(1)), float(m.group(2) or 1))
    raise WarbleError("bad_position", f"cannot read position '{' '.join(rest)}'{where}", hint="use @ bar 17, @ beat 32, or @ 5:2")


def _check_overlaps(track):
    for a, b in zip(track.notes, track.notes[1:]):
        if b.position < a.end:
            raise WarbleError(
                "overlapping_notes",
                f"track '{track.name}': note '{b.lyric}' at tick {b.position} starts before '{a.lyric}' ends at {a.end}",
                hint="notes on one track are monophonic; put the second voice on its own track",
                lines=[a.line, b.line],
            )


def bank_roots():
    """installed bank folders: ./banks and $WARBLE_BANKS (os.pathsep separated)."""
    from .bank import common

    dirs = [os.path.abspath("banks")] + [os.path.abspath(d) for d in os.environ.get("WARBLE_BANKS", "").split(os.pathsep) if d]
    out = []
    for d in dirs:
        if os.path.isdir(d):
            out += common.scan(d)
    return out


def _bank_display_name(root):
    try:
        from .bank import common

        _, cy = common.load_character_yaml(root)
        if cy and cy.get("name"):
            return str(cy["name"])
        info = common.parse_character_txt(root)
        return (info or {}).get("name", "")
    except Exception:  # noqa: BLE001
        return ""


def resolve_bank(value, base_dir="."):
    """a bank path relative to the score, else to the working directory, else a bank whose folder
    name matches (case-insensitive, substring ok). unresolved values are returned as given."""
    if os.path.isabs(value) and os.path.isdir(value):
        return value
    for base in (base_dir, os.getcwd()):
        cand = os.path.normpath(os.path.join(base, value))
        if os.path.isdir(cand):
            return cand
    import unicodedata

    def key(x):
        return unicodedata.normalize("NFC", x).lower().replace(" ", "").replace("_", "")

    want = key(os.path.basename(value.rstrip("/")))
    roots = bank_roots()
    exact = [r for r in roots if key(os.path.basename(r)) == want]
    if exact:
        return exact[0]
    partial = [r for r in roots if want and want in key(os.path.basename(r))]
    if len(partial) == 1:
        return partial[0]
    if not partial:
        # every word of the request somewhere in "<character folder>/<bank folder> <display name>"
        toks = [key(t) for t in re.split(r"[\s_/\-]+", value) if t]

        def hay(r):
            return key(os.path.relpath(r, os.path.dirname(os.path.dirname(r))) + " " + _bank_display_name(r))

        partial = [r for r in roots if toks and all(t in hay(r) for t in toks)]
        if len(partial) == 1:
            return partial[0]
    if len(partial) > 1:
        raise WarbleError("bank_ambiguous", f"bank '{value}' matches several installed banks", hint="be more specific",
                          matches=[os.path.relpath(r) for r in partial])
    return os.path.normpath(os.path.join(base_dir, value))


def parse_inline(expr, defaults=None):
    """'ら:C4:1 ら:D4:1/2 r:1 +:E4:1/2' -> score. defaults can carry bank/lang/bpm."""
    lines = []
    for k in ("bank", "lang", "voice", "bpm"):
        if defaults and defaults.get(k) is not None:
            lines.append(f"{k} {defaults[k]}")
    for tok in expr.split():
        bits = tok.split(":")
        if bits[0] in ("r", "rest"):
            lines.append(f"r {bits[1] if len(bits) > 1 else 1}")
        elif len(bits) >= 3:
            # extra fields are controls: か:A4:1:vib=pop:vel=120 (a voice mix keeps its own colons)
            ctl, cur = [], None
            for b in bits[3:]:
                if "=" in b or cur is None:
                    cur = b
                    ctl.append(cur)
                else:
                    ctl[-1] += ":" + b
            lines.append(" ".join(bits[:3] + ctl))
        else:
            raise WarbleError("bad_inline", f"inline note '{tok}' should be lyric:pitch:length[:key=value...]",
                              hint="controls attach with colons, e.g. か:A4:1:vib=pop")
    return parse_text("\n".join(lines), base_dir=os.getcwd(), source="-e")


def parse_json(data, base_dir="."):
    """{"bpm": 120, "tracks": [{"name", "bank", "lang", "notes": [{"lyric","pitch","length"|"duration","position"?}]}]}"""
    score = Score(base_dir=base_dir)
    if "tempos" in data:
        score.tempos = [(int(t["tick"]), float(t["bpm"])) for t in data["tempos"]]
    elif "bpm" in data:
        score.tempos = [(0, float(data["bpm"]))]
    if "time_signatures" in data:
        score.time_signatures = [(int(s["tick"]), int(s["num"]), int(s["den"])) for s in data["time_signatures"]]
    score.key = data.get("key")
    tm = score.tempo_map
    for ti, td in enumerate(data.get("tracks") or [{"notes": data.get("notes", [])}]):
        bank = td.get("bank") or data.get("bank")
        if bank and not os.path.isabs(bank):
            bank = os.path.normpath(os.path.join(base_dir, bank))
        t = Track(name=td.get("name", f"track{ti + 1}"), bank=bank, lang=td.get("lang") or data.get("lang"),
                  voice=td.get("voice"), phonemizer=td.get("phonemizer"), engine=td.get("engine"),
                  volume_db=float(td.get("volume_db", 0)), pan=float(td.get("pan", 0)))
        pos = 0
        for i, nd in enumerate(td.get("notes", [])):
            where = f" (track {t.name} note {i})"
            if "position" in nd:
                pos = int(nd["position"])
            if nd.get("rest") or nd.get("lyric") in ("r", None) and "pitch" not in nd:
                pos += int(nd["duration"]) if "duration" in nd else _parse_length(str(nd.get("length", 1)), tm, pos, where)
                continue
            dur = int(nd["duration"]) if "duration" in nd else _parse_length(str(nd.get("length", 1)), tm, pos, where)
            tone = float(nd["tone"]) if "tone" in nd else parse_pitch(str(nd["pitch"]), where)
            lyric = str(nd.get("lyric", "a"))
            hint = nd.get("hint")
            t.notes.append(Note(lyric=lyric, tone=tone, position=pos, duration=dur, hint=hint, controls=dict(nd.get("controls", {}))))
            pos += dur
        _check_overlaps(t)
        score.tracks.append(t)
    return score


def load(path_or_text, inline=False, defaults=None):
    """load a score from a path (.txt/.score, .json, .ust, .ustx, .mid, .musicxml) or inline text."""
    if inline:
        return parse_inline(path_or_text, defaults)
    path = path_or_text
    if not os.path.isfile(path):
        raise WarbleError("score_missing", f"score file not found: {path}")
    ext = os.path.splitext(path)[1].lower()
    base = os.path.dirname(os.path.abspath(path))
    if ext == ".json":
        with open(path, encoding="utf-8") as f:
            return parse_json(json.load(f), base)
    if ext == ".ust":
        from .formats import ust

        return ust.load(path)
    if ext == ".ustx":
        from .formats import ustx

        return ustx.load(path)
    if ext in (".mid", ".midi"):
        from .formats import midi

        return midi.load(path, **(defaults or {}))
    if ext in (".musicxml", ".xml", ".mxl"):
        from .formats import musicxml

        return musicxml.load(path)
    with open(path, encoding="utf-8-sig") as f:
        return parse_text(f.read(), base_dir=base, source=os.path.basename(path))


def apply_defaults(score, bank=None, lang=None, voice=None):
    for t in score.tracks:
        if bank and not t.bank:
            t.bank = resolve_bank(bank, os.getcwd())
        if lang and not t.lang:
            t.lang = lang
        if voice and not t.voice:
            t.voice = voice
    return score


def note_groups(notes):
    """group a track's notes into words: a lyric note plus its following '+' continuations."""
    groups = []
    for n in notes:
        if n.is_continuation and groups and groups[-1][-1].end == n.position:
            groups[-1].append(n)
        else:
            groups.append([n])
    return groups


def phrases(notes):
    """split note groups into phrases at rests, as openutau's MachineLearningPhonemizer does:
    a group joins the phrase only when it starts exactly where the previous one ended."""
    out = []
    for g in note_groups(notes):
        if out and out[-1][-1][-1].end == g[0].position:
            out[-1].append(g)
        else:
            out.append([g])
    return out


def ms_of(tm, tick):
    return tm.tick_to_ms(tick)


def isclose(a, b):
    return math.isclose(a, b, abs_tol=1e-6)
