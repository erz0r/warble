"""auto-tuners: starting drafts an agent then edits by hand."""

import numpy as np

from ..errors import WarbleError
from ..score import TPQ, phrases
from . import curve, ops

UTAU_VBR = {"length": 65, "period": 180, "depth": 35, "in": 20, "out": 20, "shift": 0, "drift": 0}
OPENUTAU_VBR = dict(curve.DEFAULT_VIBRATO)


def _sel(score, track, notes):
    return ops.select(score, track=track, notes=notes)


def flat(score, track=None, notes=None, **_):
    tr, idx = _sel(score, track, notes)
    ops.flat(score, tr, idx, False)
    return idx


def utau_mode1(score, track=None, notes=None, **_):
    """a raw per-frame pitchbend like utau mode1: a straight 80 ms slide into each note."""
    tr, idx = _sel(score, track, notes)
    tm = score.tempo_map
    for i in idx:
        n = tr.notes[i]
        for k in ("pts", "snap", "vbr", "vib"):
            n.controls.pop(k, None)
        prev = ops._prev_adjacent(tr.notes, i)
        if prev is None:
            n.controls.pop("raw", None)
            continue
        step = 60000.0 / (tm.bpm_at(n.position) * TPQ) * 5
        d = (prev.tone - n.tone) * 100
        k = max(2, int(80 / step))
        cents = [round(d * (1 - j / k), 1) for j in range(k + 1)]
        n.controls["raw"] = curve.format_raw({"start_ms": -40.0, "step_ms": 0, "cents": cents})
    return idx


def _portamento(score, tr, idx, length, start, vbr=None, vbr_min_ticks=None):
    for i in idx:
        n = tr.notes[i]
        n.controls.pop("raw", None)
        n.controls.pop("vib", None)
        if ops._prev_adjacent(tr.notes, i) is not None:
            n.controls["pts"] = curve.format_points([[start, 0, "io"], [start + length, 0, "io"]])
            n.controls.pop("snap", None)
        else:
            n.controls.pop("pts", None)
        if vbr and n.duration >= (vbr_min_ticks or 0):
            n.controls["vbr"] = curve.format_vibrato(curve.clamp_vibrato(vbr))
        else:
            n.controls.pop("vbr", None)


def utau_mode2(score, track=None, notes=None, **_):
    tr, idx = _sel(score, track, notes)
    _portamento(score, tr, idx, 80, -40, UTAU_VBR, TPQ)
    return idx


def openutau(score, track=None, notes=None, portamento="standard", **_):
    tr, idx = _sel(score, track, notes)
    length, start = curve.PORTAMENTO_PRESETS[portamento]
    _portamento(score, tr, idx, length, start, OPENUTAU_VBR, 481)
    return idx


def rule(score, track=None, notes=None, seed=0, vibrato=True, **_):
    """interval-aware: longer bends for bigger leaps, a preparation dip on big leaps, a little
    overshoot going up, drift everywhere, and vibrato whose onset and depth follow note length."""
    tr, idx = _sel(score, track, notes)
    tm = score.tempo_map
    finals = set()
    for ph in phrases(tr.notes):
        finals.add(id(ph[-1][-1]))
    for i in idx:
        n = tr.notes[i]
        for k in ("raw", "vib", "pts", "snap"):
            n.controls.pop(k, None)
        L = tm.tick_to_ms(n.end) - tm.tick_to_ms(n.position)
        prev = ops._prev_adjacent(tr.notes, i)
        if prev is not None and prev.tone != n.tone:
            st = abs(n.tone - prev.tone)
            dur = min(60 + 12 * st, 0.45 * L + 40)
            prep = 15 + 2 * st if st >= 4 else 0
            over = min(25, 6 + 3 * st) if n.tone > prev.tone and st >= 3 and L > 250 else 0
            ops.transition(score, tr, [i], dur, -0.55 * dur, "io", prep, over, 70)
        if L >= 600 and vibrato:
            onset = max(0.25, min(0.55, 300 / L))
            depth = min(38, 16 + L / 100)
            ops.vibrato(score, tr, [i], "", 5.6, depth, onset, 0.35, 0.12, None, None)
        else:
            n.controls.pop("vbr", None)
        if L >= 300:
            ops.drift(score, tr, [i], 6.0, 0.6, seed)
        if id(n) in finals and L >= 500:
            ops.fall(score, tr, [i], -40, 120, "i")
    return idx


def dspitch(score, track=None, notes=None, ds_bank=None, lang=None, seed=0, **_):
    """let a diffsinger pitch model draft the curve for any bank: its output becomes each note's raw layer."""
    from ..bank.ds import DsBank
    from ..ds import pitch as dspitch_mod
    from ..ds.render import DsEngine
    from ..sing import split_phrases

    if not ds_bank:
        raise WarbleError("ds_bank_needed", "the dspitch tuner needs a diffsinger bank with a pitch model", hint="pass ds_bank=<path or name>")
    from ..score import resolve_bank

    eng = DsEngine(DsBank(resolve_bank(ds_bank)))
    pmd = eng.models.get("dspitch")
    if pmd is None:
        raise WarbleError("no_pitch_model", f"{ds_bank} has no dspitch model")
    tr, idx = _sel(score, track, notes)
    tm = score.tempo_map
    want = set(idx)
    lang = lang or tr.lang
    for words in split_phrases(tr):
        ns = [n for w in words for n in w]
        if not any(tr.notes.index(n) in want for n in ns):
            continue
        res = eng.phonemizer(lang).phonemize_phrase(words, tm, lambda n: None, seed=seed)
        if res["unknown"]:
            raise WarbleError("unknown_lyrics", "the ds bank can't phonemize some lyrics for the dspitch tuner", unknown=res["unknown"])
        midi, fm, start = dspitch_mod.model_pitch(pmd, res["phones"], ns, tm, seed=seed)
        t = start + np.arange(len(midi)) * fm
        for n in ns:
            i = tr.notes.index(n)
            if i not in want:
                continue
            s, e = tm.tick_to_ms(n.position), tm.tick_to_ms(n.end)
            step = 60000.0 / (tm.bpm_at(n.position) * TPQ) * 5
            xs = np.arange(s, e, step)
            cents = (np.interp(xs, t, midi) - n.tone) * 100
            for k in ("pts", "snap", "vbr", "vib"):
                n.controls.pop(k, None)
            n.controls["raw"] = curve.format_raw({"start_ms": 0.0, "step_ms": 0, "cents": [round(float(c), 1) for c in cents]})
    return idx


TUNERS = {"flat": flat, "utau_mode1": utau_mode1, "utau_mode2": utau_mode2, "openutau": openutau, "rule": rule, "dspitch": dspitch}


def run(score, name, **kw):
    if name not in TUNERS:
        raise WarbleError("bad_tuner", f"unknown auto-tuner '{name}'", hint=f"tuners: {sorted(TUNERS)}")
    idx = TUNERS[name](score, **kw)
    return [i + 1 for i in idx]
