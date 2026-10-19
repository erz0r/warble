"""tuning ops. each op edits the controls of a selection of notes and nothing else.

ops are registered with their parameters so the cli, the json batch format and the mcp server all
share one definition. a batch is a list of {"op": name, "notes": "3-7", ...params}.
"""

import math
import re

from ..errors import WarbleError
from . import curve

OPS = {}


def op(name, help, **params):
    """params: name -> (type, default, help)."""

    def deco(fn):
        OPS[name] = {"fn": fn, "help": help, "params": params}
        return fn

    return deco


# ---- selection ---------------------------------------------------------------------------------

def parse_range(text):
    out = set()
    for part in str(text).split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part[1:]:
            a, b = part.split("-", 1)
            out |= set(range(int(a), int(b) + 1))
        else:
            out.add(int(part))
    return out


def select(score, track=None, notes=None, lyric=None, phrase=None, min_beats=None, max_beats=None, interval=None, **_):
    """-> (track, [note indexes 0-based]). interval like '>=3', '<=-2', '=0' compares the signed
    semitone step from the previous adjacent note; 'abs>=4' compares its size."""
    from ..score import TPQ, phrases

    tr = _track(score, track)
    idx = list(range(len(tr.notes)))
    if notes:
        want = parse_range(notes)
        idx = [i for i in idx if i + 1 in want]
    if lyric:
        idx = [i for i in idx if tr.notes[i].lyric == lyric]
    if phrase:
        want = parse_range(phrase)
        keep = set()
        pos = {id(n): i for i, n in enumerate(tr.notes)}
        for k, ph in enumerate(phrases(tr.notes), start=1):
            if k in want:
                keep |= {pos[id(n)] for w in ph for n in w}
        idx = [i for i in idx if i in keep]
    if min_beats is not None:
        idx = [i for i in idx if tr.notes[i].duration >= float(min_beats) * TPQ]
    if max_beats is not None:
        idx = [i for i in idx if tr.notes[i].duration <= float(max_beats) * TPQ]
    if interval:
        m = re.fullmatch(r"(abs)?(>=|<=|=|>|<)(-?\d+(?:\.\d+)?)", str(interval).replace(" ", ""))
        if not m:
            raise WarbleError("bad_interval", f"interval filter '{interval}' should look like '>=3', '<-2' or 'abs>=4'")
        keep = []
        for i in idx:
            p = _prev_adjacent(tr.notes, i)
            if p is None:
                continue
            d = tr.notes[i].tone - p.tone
            if m.group(1):
                d = abs(d)
            v = float(m.group(3))
            ok = {">=": d >= v, "<=": d <= v, "=": d == v, ">": d > v, "<": d < v}[m.group(2)]
            if ok:
                keep.append(i)
        idx = keep
    return tr, idx


def _track(score, name):
    if name is None:
        return score.tracks[0]
    for t in score.tracks:
        if t.name == name:
            return t
    raise WarbleError("track_missing", f"no track '{name}'", hint=f"tracks: {[t.name for t in score.tracks]}")


def _prev_adjacent(notes, i):
    if i > 0 and notes[i - 1].end == notes[i].position:
        return notes[i - 1]
    return None


def _len_ms(score, n):
    tm = score.tempo_map
    return tm.tick_to_ms(n.end) - tm.tick_to_ms(n.position)


def _points(n):
    return curve.note_points(n) or []


def _set_points(n, pts):
    pts = sorted(pts, key=lambda p: p[0])
    if pts:
        n.controls["pts"] = curve.format_points(pts)
    else:
        n.controls.pop("pts", None)


def _split(n, length):
    """a note's points split into its head (before the middle) and tail."""
    pts = _points(n)
    return [p for p in pts if p[0] < length / 2], [p for p in pts if p[0] >= length / 2]


# ---- pitch ops ------------------------------------------------------------------------------------

@op("transition", "shape the bend from the previous note into this one",
    dur_ms=(float, 80.0, "length of the bend"), start_ms=(float, -40.0, "where it starts, relative to the note boundary"),
    shape=(str, "io", "io (s-curve), l (linear), i (ease in), o (ease out)"),
    prep_cents=(float, 0.0, "dip away from the target before moving (preparation)"),
    overshoot_cents=(float, 0.0, "how far past the target the pitch goes"), settle_ms=(float, 60.0, "time to settle after an overshoot"))
def transition(score, tr, idx, dur_ms, start_ms, shape, prep_cents, overshoot_cents, settle_ms):
    done = []
    for i in idx:
        n = tr.notes[i]
        prev = _prev_adjacent(tr.notes, i)
        if prev is None:
            continue
        L = _len_ms(score, n)
        d = (n.tone - prev.tone) * 100
        sgn = 1 if d >= 0 else -1
        head = [[start_ms, -d, shape]]
        if prep_cents:
            head.append([start_ms + 0.3 * dur_ms, -d - sgn * prep_cents, shape])
        end = start_ms + dur_ms
        if overshoot_cents:
            head.append([end, sgn * overshoot_cents, "io"])
            head.append([min(end + settle_ms, L / 2 - 1), 0.0, "io"])
        else:
            head.append([end, 0.0, "io"])
        _, tail = _split(n, L)
        _set_points(n, head + tail)
        n.controls.pop("snap", None)
        done.append(i)
    return done


@op("scoop", "start below (or above) the note and slide in", cents=(float, -80.0, "start offset"), dur_ms=(float, 90.0, "slide length"),
    shape=(str, "o", "curve shape"))
def scoop(score, tr, idx, cents, dur_ms, shape):
    for i in idx:
        n = tr.notes[i]
        _, tail = _split(n, _len_ms(score, n))
        _set_points(n, [[0.0, cents, shape], [dur_ms, 0.0, "io"]] + tail)
        n.controls["snap"] = 0
    return idx


@op("fall", "fall off at the end of the note", cents=(float, -150.0, "how far it falls"), dur_ms=(float, 120.0, "fall length"),
    shape=(str, "i", "curve shape"))
def fall(score, tr, idx, cents, dur_ms, shape):
    for i in idx:
        n = tr.notes[i]
        L = _len_ms(score, n)
        head, _ = _split(n, L)
        start = max(L / 2, L - dur_ms)
        _set_points(n, head + [[start, 0.0, shape], [L, cents, "io"]])
    return idx


@op("fry", "a creaky dip at the end of the note", cents=(float, -250.0, "dip depth"), dur_ms=(float, 60.0, "dip length"))
def fry(score, tr, idx, cents, dur_ms):
    return fall(score, tr, idx, cents, dur_ms, "l")


@op("flat", "hold the note's pitch flat: no bends, no vibrato, no drift", keep_vibrato=(bool, False, "keep vibrato"))
def flat(score, tr, idx, keep_vibrato):
    for i in idx:
        n = tr.notes[i]
        L = _len_ms(score, n)
        _set_points(n, [[0.0, 0.0, "io"], [L, 0.0, "io"]])
        n.controls["snap"] = 0
        for k in ("raw", "drift", "cents") + (() if keep_vibrato else ("vbr", "vib")):
            n.controls.pop(k, None)
    return idx


@op("unbend", "remove drawn bends so the engine's own curve (pitch model or rule) is used again")
def unbend(score, tr, idx):
    for i in idx:
        for k in ("pts", "snap", "raw"):
            tr.notes[i].controls.pop(k, None)
    return idx


@op("offset", "shift the note's pitch by cents", cents=(float, 0.0, "offset; 0 removes it"))
def offset(score, tr, idx, cents):
    for i in idx:
        if cents:
            tr.notes[i].controls["cents"] = cents
        else:
            tr.notes[i].controls.pop("cents", None)
    return idx


@op("drift", "slow random wander", depth_cents=(float, 8.0, "depth"), rate_hz=(float, 0.7, "speed"), seed=(int, 0, "seed (per note it adds the note number)"))
def drift(score, tr, idx, depth_cents, rate_hz, seed):
    for i in idx:
        if depth_cents:
            tr.notes[i].controls["drift"] = f"{depth_cents:g}:{rate_hz:g}:{seed + i}"
        else:
            tr.notes[i].controls.pop("drift", None)
    return idx


# ---- vibrato -------------------------------------------------------------------------------------

VIBRATO_PRESETS = {
    "none": None,
    "subtle": dict(rate_hz=5.5, depth_cents=15, onset=0.45, fade_in=0.25, fade_out=0.1),
    "pop": dict(rate_hz=5.8, depth_cents=28, onset=0.35, fade_in=0.25, fade_out=0.1),
    "ballad": dict(rate_hz=5.2, depth_cents=40, onset=0.3, fade_in=0.35, fade_out=0.15),
    "opera": dict(rate_hz=6.0, depth_cents=70, onset=0.1, fade_in=0.2, fade_out=0.1),
    "wide_late": dict(rate_hz=5.0, depth_cents=60, onset=0.55, fade_in=0.3, fade_out=0.1),
}


@op("vibrato", "add or edit vibrato (a preset, then any field overrides)",
    preset=(str, "", "none, subtle, pop, ballad, opera, wide_late"), rate_hz=(float, None, "rate"),
    depth_cents=(float, None, "depth"), onset=(float, None, "where it starts, 0..1 of the note"),
    fade_in=(float, None, "fade-in, 0..1 of the vibrato"), fade_out=(float, None, "fade-out, 0..1 of the vibrato"),
    phase=(float, None, "phase shift, 0..1 of a period"), drift_pct=(float, None, "shift the center, -100..100 % of depth"))
def vibrato(score, tr, idx, preset, rate_hz, depth_cents, onset, fade_in, fade_out, phase, drift_pct):
    for i in idx:
        n = tr.notes[i]
        if preset == "none":
            n.controls.pop("vbr", None)
            n.controls.pop("vib", None)
            continue
        cur = curve.note_vibrato(n) or dict(curve.DEFAULT_VIBRATO)
        if preset:
            if preset not in VIBRATO_PRESETS:
                raise WarbleError("bad_preset", f"unknown vibrato preset '{preset}'", hint=f"presets: {sorted(VIBRATO_PRESETS)}")
            p = VIBRATO_PRESETS[preset]
            cur.update(length=100 * (1 - p["onset"]), period=1000 / p["rate_hz"], depth=p["depth_cents"], **{"in": 100 * p["fade_in"], "out": 100 * p["fade_out"]})
        if rate_hz is not None:
            cur["period"] = 1000.0 / rate_hz
        if depth_cents is not None:
            cur["depth"] = depth_cents
        if onset is not None:
            cur["length"] = 100 * (1 - onset)
        if fade_in is not None:
            cur["in"] = 100 * fade_in
        if fade_out is not None:
            cur["out"] = 100 * fade_out
        if phase is not None:
            cur["shift"] = 100 * phase
        if drift_pct is not None:
            cur["drift"] = drift_pct
        n.controls.pop("vib", None)
        n.controls["vbr"] = curve.format_vibrato(curve.clamp_vibrato(cur))
    return idx


@op("copy_vibrato", "copy one note's vibrato onto the selection", source=(int, 0, "note number to copy from"))
def copy_vibrato(score, tr, idx, source):
    src = tr.notes[source - 1]
    v = curve.note_vibrato(src)
    for i in idx:
        if v:
            tr.notes[i].controls["vbr"] = curve.format_vibrato(v)
        else:
            tr.notes[i].controls.pop("vbr", None)
        tr.notes[i].controls.pop("vib", None)
    return idx


# ---- dynamics, timbre, timing -------------------------------------------------------------------------

EXPRESSIONS = {
    "vol": "volume % (utau intensity), 100 = normal",
    "atk": "attack %, 100 = normal",
    "dec": "decay % at the note end, 0 = none",
    "brec": "breathiness (ds variance offset, openutau units)",
    "ene": "energy (ds variance offset)",
    "voic": "voicing (ds variance, 100 = normal)",
    "tenc": "tension (ds variance offset)",
    "gender": "formant shift (ds key shift / openutau GENC units, + = deeper)",
    "vel": "consonant speed, 100 = normal (utau velocity / ds speed)",
    "expr": "pitch expressiveness 0..1 (ds pitch model)",
    "flags": "utau resampler flags, e.g. g-5B60",
    "voice": "voice mode or mix, e.g. soft:0.7,power:0.3",
    "mod": "utau modulation %",
    "pre": "utau preutterance delta ms",
    "ovl": "utau overlap delta ms",
    "cons": "consonant length multiplier (ds: scales the leading consonants; utau: sets velocity)",
    "phdur": "ds: explicit phoneme lengths in ms for the word, comma separated (0 = keep predicted)",
}


@op("set", "set an expression on the selection (see `warble tune ops` for the list); value '' removes it",
    key=(str, "", "expression name"), value=(str, "", "value"))
def set_expr(score, tr, idx, key, value):
    if key not in EXPRESSIONS:
        raise WarbleError("bad_expression", f"unknown expression '{key}'", hint=f"expressions: {sorted(EXPRESSIONS)}")
    for i in idx:
        n = tr.notes[i]
        if value in ("", None):
            n.controls.pop(key, None)
            continue
        if key == "cons" and _engine_of(tr) == "utau":
            # utau consonant stretch is 2^(1 - vel/100); a multiplier m maps to vel = 100 * (1 - log2 m)
            n.controls["vel"] = round(100 * (1 - math.log2(max(0.05, float(value)))), 2)
            continue
        try:
            n.controls[key] = float(value) if key not in ("flags", "voice", "phdur") else value
        except ValueError:
            n.controls[key] = value
    return idx


@op("ramp", "ramp an expression across the selection from one value to another", key=(str, "", "expression"),
    start=(float, 0.0, "value on the first note"), end=(float, 0.0, "value on the last note"))
def ramp(score, tr, idx, key, start, end):
    if key not in EXPRESSIONS:
        raise WarbleError("bad_expression", f"unknown expression '{key}'")
    for k, i in enumerate(idx):
        f = k / max(1, len(idx) - 1)
        tr.notes[i].controls[key] = round(start + (end - start) * f, 3)
    return idx


@op("nudge", "move note starts by ms; the previous note's end follows so nothing overlaps", ms=(float, 0.0, "+ later, - earlier"))
def nudge(score, tr, idx, ms):
    tm = score.tempo_map
    for i in idx:
        n = tr.notes[i]
        start_ms = tm.tick_to_ms(n.position) + ms
        new_pos = int(round(tm.ms_to_tick(start_ms)))
        prev = tr.notes[i - 1] if i > 0 else None
        lo = prev.position + 10 if prev is not None else 0
        new_pos = max(lo, min(new_pos, n.end - 10))
        delta = new_pos - n.position
        if prev is not None and prev.end == n.position:
            prev.duration += delta
        elif prev is not None and new_pos < prev.end:
            prev.duration = new_pos - prev.position
        n.position = new_pos
        n.duration -= delta
    return idx


def _engine_of(tr):
    from ..bank import common

    if tr.bank:
        kind, _ = common.detect(tr.bank)
        return "ds" if kind == "diffsinger" else "utau"
    return None


# ---- reuse -----------------------------------------------------------------------------------------

TUNING_KEYS = ("pts", "snap", "vbr", "vib", "raw", "cents", "drift", "vol", "atk", "dec", "brec", "ene", "voic", "tenc", "gender", "vel", "expr", "flags", "mod")


@op("copy_tuning", "copy tuning controls note by note from one phrase (or note range) to the selection",
    from_notes=(str, "", "source note range, e.g. 1-8"), keys=(str, "", "comma list of controls to copy (default: all tuning)"))
def copy_tuning(score, tr, idx, from_notes, keys):
    src = sorted(parse_range(from_notes))
    ks = [k.strip() for k in keys.split(",") if k.strip()] or list(TUNING_KEYS)
    for s_i, d_i in zip(src, idx):
        sn, dn = tr.notes[s_i - 1], tr.notes[d_i]
        for k in ks:
            if k in sn.controls:
                dn.controls[k] = sn.controls[k]
            else:
                dn.controls.pop(k, None)
    return idx[: len(src)]


def apply(score, ops_list):
    """run a batch: [{"op": name, "notes"/"lyric"/"phrase"/...: selection, ...params}]. returns a log."""
    log = []
    for spec in ops_list:
        spec = dict(spec)
        name = spec.pop("op", None)
        if name not in OPS:
            raise WarbleError("bad_op", f"unknown op '{name}'", hint=f"ops: {sorted(OPS)}")
        sel_keys = ("track", "notes", "lyric", "phrase", "min_beats", "max_beats", "interval")
        sel = {k: spec.pop(k) for k in sel_keys if k in spec}
        tr, idx = select(score, **sel)
        params = {}
        for p, (typ, default, _) in OPS[name]["params"].items():
            v = spec.pop(p, default)
            if v is not None and typ is not str and not isinstance(v, typ):
                try:
                    v = typ(v) if typ is not bool else str(v).lower() in ("1", "true", "yes")
                except (TypeError, ValueError):
                    raise WarbleError("bad_param", f"{name}: '{p}' should be {typ.__name__}, got {v!r}")
            params[p] = v
        if spec:
            raise WarbleError("bad_param", f"{name}: unknown parameters {sorted(spec)}", hint=f"parameters: {sorted(OPS[name]['params'])}")
        done = OPS[name]["fn"](score, tr, idx, **params)
        log.append({"op": name, "selection": sel, "notes": [i + 1 for i in done], "params": params})
    return log


def describe():
    return {name: {"help": o["help"], "params": {p: {"type": t.__name__, "default": d, "help": h} for p, (t, d, h) in o["params"].items()}}
            for name, o in OPS.items()} | {"_expressions": EXPRESSIONS, "_vibrato_presets": sorted(VIBRATO_PRESETS),
                                          "_selection": "notes=3-7,12  lyric=ら  phrase=2  min_beats=1  max_beats=2  interval='>=3' (signed step from the previous note) or 'abs>=4'  track=name"}
