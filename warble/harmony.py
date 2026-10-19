"""harmony parts from a melody.

intervals:
  3, 6, -3, 4, 5 ...    diatonic steps in the score's key (3 = a third above, -6 = a sixth below);
                        chromatic melody notes snap to the scale first, then move back by the same
                        accidental
  +4st, -5st            a fixed number of semitones
  8, -8 (or oct, -oct)  octave doubling
keys: 'C', 'Am', 'F#m', 'Bb', 'Ebmajor', 'G dorian' (modes: major/ionian, minor/aeolian, dorian,
phrygian, lydian, mixolydian, harmonicminor). with no key, it is guessed from the melody.
"""

import copy
import re

from .errors import WarbleError
from .score import Track

NOTE = {"c": 0, "d": 2, "e": 4, "f": 5, "g": 7, "a": 9, "b": 11}
MODES = {
    "major": [0, 2, 4, 5, 7, 9, 11], "ionian": [0, 2, 4, 5, 7, 9, 11],
    "minor": [0, 2, 3, 5, 7, 8, 10], "aeolian": [0, 2, 3, 5, 7, 8, 10],
    "dorian": [0, 2, 3, 5, 7, 9, 10], "phrygian": [0, 1, 3, 5, 7, 8, 10], "lydian": [0, 2, 4, 6, 7, 9, 11],
    "mixolydian": [0, 2, 4, 5, 7, 9, 10], "harmonicminor": [0, 2, 3, 5, 7, 8, 11],
}


def parse_key(text):
    """-> (tonic pitch class, scale degrees as pitch classes, name)."""
    t = str(text).strip().replace(" ", "").lower()
    m = re.fullmatch(r"([a-g])([#b♯♭]?)(m|maj|major|min|minor|ionian|aeolian|dorian|phrygian|lydian|mixolydian|harmonicminor)?", t)
    if not m:
        raise WarbleError("bad_key", f"cannot read key '{text}'", hint="e.g. C, Am, F#m, Bb, G dorian")
    tonic = (NOTE[m.group(1)] + {"#": 1, "♯": 1, "b": -1, "♭": -1, "": 0}[m.group(2)]) % 12
    mode = {"m": "minor", "min": "minor", "maj": "major", None: "major"}.get(m.group(3), m.group(3))
    return tonic, [(tonic + d) % 12 for d in MODES[mode]], f"{text}"


def guess_key(notes):
    """krumhansl-style: the major/minor key whose scale covers the most note-time."""
    weight = [0.0] * 12
    for n in notes:
        weight[int(round(n.tone)) % 12] += n.duration
    best = None
    for tonic in range(12):
        for mode in ("major", "minor"):
            pcs = {(tonic + d) % 12 for d in MODES[mode]}
            score = sum(weight[p] for p in pcs) + (0.3 * weight[tonic]) + (0.1 * weight[(tonic + 7) % 12])
            if best is None or score > best[0]:
                best = (score, tonic, mode)
    _, tonic, mode = best
    names = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
    return names[tonic] + ("m" if mode == "minor" else "")


def shift_diatonic(tone, steps, scale):
    """move a pitch by scale steps (steps=2 is a third). chromatic pitches keep their accidental."""
    t = int(round(tone))
    frac = tone - t
    pc = t % 12
    octave = t // 12
    accidental = 0
    if pc not in scale:
        # snap down to the scale and remember the offset
        for d in (1, -1, 2, -2):
            if (pc - d) % 12 in scale:
                accidental = d
                pc = (pc - d) % 12
                break
    sorted_scale = sorted(scale)
    idx = sorted_scale.index(pc)
    k = idx + steps
    new_oct = octave + k // len(sorted_scale)
    new_pc = sorted_scale[k % len(sorted_scale)]
    out = new_oct * 12 + new_pc + accidental
    # keep the motion in the asked direction even when the scale's start sits above the tonic
    while steps > 0 and out <= t:
        out += 12
    while steps < 0 and out >= t:
        out -= 12
    return out + frac


def interval_fn(spec, scale):
    s = str(spec).strip().lower().replace(" ", "")
    if s.endswith("below") or s.startswith("below"):
        s = "-" + s.replace("below", "")
    if s in ("-", "-octave"):
        s = "-oct"
    if s in ("oct", "8", "+8"):
        return lambda t: t + 12
    if s in ("-oct", "-8"):
        return lambda t: t - 12
    m = re.fullmatch(r"([+-]?\d+)st", s)
    if m:
        k = int(m.group(1))
        return lambda t: t + k
    m = re.fullmatch(r"([+-]?)(\d+)(th|rd|nd|st)?", s)
    if not m:
        raise WarbleError("bad_interval", f"cannot read interval '{spec}'", hint="3, -3, 6, +4st, -5st, oct")
    n = int(m.group(2))
    if n < 2:
        raise WarbleError("bad_interval", "a diatonic interval is 2 (a second) or more; use 'oct' or +Nst otherwise")
    steps = (n - 1) * (-1 if m.group(1) == "-" else 1)
    return lambda t: shift_diatonic(t, steps, scale)


def harmonize(score, source, interval, name=None, key=None, bank=None, voice=None, lang=None, volume_db=-4.0, pan=None,
              notes=None, keep_tuning=False):
    """add a track whose notes follow `source` at `interval`. returns (track, info)."""
    from .tuning.ops import parse_range

    src = next((t for t in score.tracks if t.name == source), None)
    if src is None:
        raise WarbleError("track_missing", f"no track '{source}'", hint=f"tracks: {[t.name for t in score.tracks]}")
    key = key or score.key or guess_key(src.notes)
    _, scale, _ = parse_key(key)
    fn = interval_fn(interval, scale)
    name = name or f"{source}_{str(interval).replace('-', 'below')}"
    if any(t.name == name for t in score.tracks):
        raise WarbleError("track_exists", f"track '{name}' already exists", hint="pick another --name or remove it first")
    want = parse_range(notes) if notes else None
    tr = Track(name=name, bank=bank or src.bank, lang=lang or src.lang, voice=voice or src.voice, phonemizer=src.phonemizer,
               engine=src.engine, volume_db=volume_db, pan=pan if pan is not None else (-src.pan if src.pan else 0.0))
    keep = ("pts", "snap", "vbr", "vib", "drift") if keep_tuning else ()
    for i, n in enumerate(src.notes, start=1):
        if want and i not in want:
            continue
        m = copy.deepcopy(n)
        m.tone = float(fn(n.tone))
        m.controls = {k: v for k, v in n.controls.items() if k in keep or k in ("vol", "vel", "flags", "brec", "gender", "tenc", "voic", "ene", "expr")}
        tr.notes.append(m)
    score.tracks.append(tr)
    return tr, {"track": name, "from": source, "interval": str(interval), "key": key, "notes": len(tr.notes),
                "range": [min((n.tone for n in tr.notes), default=None), max((n.tone for n in tr.notes), default=None)]}
