"""import pitch from a reference vocal: extract f0, align it to the score, write per-note raw layers.

alignment: a global offset search (cross-correlation of the reference's voiced pitch with the note
grid), then each note snaps to the median of what the reference sang over its span, which absorbs
small local timing differences. octave slips of the extractor are folded back.
"""

import numpy as np

from ..errors import WarbleError
from ..perception import f0 as f0mod
from ..score import TPQ
from . import curve, ops


def import_pitch(score, wav, track=None, notes=None, offset_ms=None, max_offset_ms=3000.0, keep_vibrato=True, extractors=("harvest", "dio")):
    import soundfile as sf

    x, sr = sf.read(wav, dtype="float64", always_2d=True)
    x = x.mean(1)
    res = f0mod.extract(x, sr, extractors)
    t = res["t"] * 1000.0
    midi = f0mod.to_midi(res["f0"])
    tr, idx = ops.select(score, track=track, notes=notes)
    if not idx:
        raise WarbleError("no_notes", "selection is empty")
    tm = score.tempo_map
    grid = np.full(len(t), np.nan)
    for n in tr.notes:
        s, e = tm.tick_to_ms(n.position), tm.tick_to_ms(n.end)
        grid[(t >= s) & (t < e)] = n.tone
    if offset_ms is None:
        offset_ms = _best_offset(t, midi, grid, max_offset_ms)
    out = {"offset_ms": round(float(offset_ms), 1), "notes": []}
    ref_t = t - offset_ms  # reference time mapped onto score time
    for i in idx:
        n = tr.notes[i]
        s, e = tm.tick_to_ms(n.position), tm.tick_to_ms(n.end)
        m = (ref_t >= s) & (ref_t < e) & np.isfinite(midi)
        if m.sum() < 4:
            out["notes"].append({"note": i + 1, "status": "no voiced reference here"})
            continue
        vals = midi[m].copy()
        # fold octave slips toward the note
        vals += 12 * np.round((n.tone - vals) / 12) * (np.abs(n.tone - vals) > 9)
        step = 60000.0 / (tm.bpm_at(n.position) * TPQ) * 5
        xs = np.arange(s, e, step)
        cents = (np.interp(xs, ref_t[m], vals) - n.tone) * 100
        for k in ("pts", "snap", "vib") + (() if keep_vibrato else ("vbr",)):
            n.controls.pop(k, None)
        n.controls.pop("vbr", None)  # the reference's own vibrato is in the raw layer
        n.controls["raw"] = curve.format_raw({"start_ms": 0.0, "step_ms": 0, "cents": [round(float(c), 1) for c in cents]})
        out["notes"].append({"note": i + 1, "median_cents_vs_note": round(float(np.median(cents)), 1), "coverage": round(float(m.sum() * 5 / (e - s)), 2)})
    return out


def _best_offset(t, ref_midi, grid, max_ms):
    """offset (ms) to subtract from reference time so its pitch lines up with the note grid."""
    step = t[1] - t[0] if len(t) > 1 else 5.0
    ok_r = np.isfinite(ref_midi)
    best, best_score = 0.0, -np.inf
    for k in range(-int(max_ms / step), int(max_ms / step) + 1, 2):
        shifted = np.roll(ref_midi, -k)
        both = np.isfinite(grid) & np.roll(ok_r, -k)
        if both.sum() < 20:
            continue
        d = np.abs(((shifted[both] - grid[both]) + 6) % 12 - 6)  # octave-insensitive
        score = np.mean(d < 0.7) - 0.001 * abs(k)
        if score > best_score:
            best, best_score = k * step, score
    return best
