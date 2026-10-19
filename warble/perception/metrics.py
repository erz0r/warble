"""per-note numbers: pitch against intent, transitions, vibrato, voicing, loudness, timbre."""

import numpy as np

from . import features as fx
from .analysis import frames_in


def _r(x, n=1):
    return None if x is None or not np.isfinite(x) else round(float(x), n)


def vibrato_fit(t_ms, cents, min_cycles=2.0):
    """fit vibrato on a pitch segment (cents): detrend with a 200 ms moving average, take the
    spectral peak between 3 and 10 hz as the rate, the rms of the residual (times sqrt 2) as the
    depth, and the share of residual power near the peak as regularity.
    -> dict(rate_hz, depth_cents, regularity 0..1, cycles) or None."""
    ok = np.isfinite(cents)
    if ok.sum() < 30:
        return None
    t = t_ms[ok]
    c = cents[ok]
    step = 5.0
    tu = np.arange(t[0], t[-1], step)
    cu = np.interp(tu, t, c)
    w = max(3, int(200 / step) | 1)
    pad = np.pad(cu, (w // 2, w // 2), mode="edge")
    trend = np.convolve(pad, np.ones(w) / w, mode="valid")[: len(cu)]
    r = (cu - trend) * np.hanning(len(cu))
    n = 4096
    spec = np.abs(np.fft.rfft(r, n)) ** 2
    freqs = np.fft.rfftfreq(n, step / 1000.0)
    band = (freqs >= 3.0) & (freqs <= 10.0)
    if not band.any() or spec[band].sum() <= 0:
        return None
    k = np.argmax(np.where(band, spec, 0))
    rate = float(freqs[k])
    near = band & (np.abs(freqs - rate) <= 0.8)
    regularity = float(spec[near].sum() / (spec[(freqs > 0.5) & (freqs < 15)].sum() + 1e-12))
    resid = cu - trend
    depth = float(np.sqrt(2) * np.std(resid[len(resid) // 8: -len(resid) // 8 or None]))
    cycles = rate * (t[-1] - t[0]) / 1000.0
    if cycles < min_cycles or depth < 6 or regularity < 0.35:
        return None
    return {"rate_hz": round(rate, 2), "depth_cents": round(depth, 1), "regularity": round(regularity, 2), "cycles": round(cycles, 1)}


def note_metrics(a, intent, note, prev_note=None, formant=True):
    s, e = note["start_ms"], note["end_ms"]
    out = {"note": note["index"], "lyric": note["lyric"], "pitch": note["pitch"], "start_ms": round(s, 1), "end_ms": round(e, 1)}
    vowels = [p for p in intent.phones if p["vowel"] and p["end_ms"] > s + 1 and p["start_ms"] < e - 1]
    sung = sung_mask(a, intent, s, e)
    out["expected_voiced_ms"] = round(sung.sum() * 5.0, 1)
    if sung.sum() == 0:
        out["note_kind"] = "unvoiced"  # e.g. っ / cl, a rest-like note
        return out
    intended = intent.pitch_at(a.t_ms)
    v = sung & a.voiced
    out["voiced_ratio"] = _r(v.sum() / sung.sum(), 3)
    if v.sum() >= 3:
        err = (a.midi[v] - intended[v]) * 100
        err = err[np.isfinite(err)]
        if err.size:
            out["median_cents_error"] = _r(np.median(err))
            out["worst_cents_error"] = _r(err[np.argmax(np.abs(err))])
            out["within_20c_pct"] = _r(np.mean(np.abs(err) <= 20) * 100)
            out["frames"] = int(err.size)
        # error against the plain note pitch too, to separate tuning choices from engine errors
        en = (a.midi[v] - note["tone"]) * 100
        out["median_cents_vs_note"] = _r(np.median(en))
    # onset: where voicing (re)starts before this note's first vowel, if there is a gap at all
    if vowels and vowels[0]["start_ms"] >= s - 200:
        vs = vowels[0]["start_ms"]
        look = np.where(frames_in(a, vs - 150, vs + 150))[0]
        if look.size:
            silent = ~a.voiced[look] | (a.rms_db[look] < -45)
            before = [k for k in range(len(look)) if a.t_ms[look[k]] < vs + 100 and silent[k]]
            if before:
                k = before[-1] + 1
                while k < len(look) and silent[k]:
                    k += 1
                if k < len(look):
                    out["onset_offset_ms"] = _r(a.t_ms[look[k]] - vs)
            else:
                out["onset"] = "legato"
    # transition into this note
    if prev_note is not None and abs(prev_note["end_ms"] - s) < 1 and prev_note["tone"] != note["tone"]:
        vm = sung_mask(a, intent, prev_note["start_ms"], e, trim=10.0) if intent.phones else None
        out["transition"] = transition_stats(a, note, prev_note, vm)
        if out["transition"] and intent.pitch_t_ms is not None:
            # the same numbers for the intended curve, so a chosen overshoot isn't read as an error
            class _I:
                pass

            ia = _I()
            ia.t_ms, ia.midi = a.t_ms, intent.pitch_at(a.t_ms)
            ia.voiced = np.isfinite(ia.midi)
            it = transition_stats(ia, note, prev_note, vm)
            if it:
                out["transition"]["intended_overshoot_cents"] = it.get("overshoot_cents")
                out["transition"]["intended_settle_ms"] = it.get("settle_ms_after_boundary")
    # vibrato on the stable part
    stable = frames_in(a, s + 0.25 * (e - s), e - 0.12 * (e - s)) & a.voiced
    if e - s >= 350 and stable.sum() > 30:
        meas = vibrato_fit(a.t_ms[stable], (a.midi[stable] - note["tone"]) * 100)
        if meas:
            out["vibrato"] = meas
        it = vibrato_fit(a.t_ms[stable], (intended[stable] - note["tone"]) * 100)
        if it:
            out["intended_vibrato"] = it
        spread = np.nanstd((a.midi[stable] - note["tone"]) * 100)
        out["stable_pitch_std_cents"] = _r(spread)
    # loudness and timbre
    out["rms_db"] = _r(np.mean(a.rms_db[sung]))
    if v.any():
        out["breathiness_db"] = _r(np.mean(a.breath_db[v]))
        out["hnr_db"] = _r(np.mean(a.hnr_db[v]))
        out["centroid_hz"] = _r(np.mean(a.centroid[v]), 0)
        if formant:
            ts = a.t_ms[v][:: max(1, v.sum() // 12)] / 1000.0
            fm = fx.formants(a.x, a.sr, ts)
            if np.isfinite(fm).any():
                out["formants_hz"] = [_r(np.nanmedian(fm[:, k]), 0) if np.isfinite(fm[:, k]).any() else None for k in range(3)]
    return out


def sung_mask(a, intent, s, e, trim=15.0):
    """frames inside vowel phones within [s, e), trimmed at the edges where trackers glitch."""
    if not intent.phones:
        return frames_in(a, s, e)
    m = np.zeros(len(a.t_ms), bool)
    for p in intent.phones:
        pe = p.get("solo_end_ms", p["end_ms"])
        if p["vowel"] and pe > s and p["start_ms"] < e:
            m |= frames_in(a, max(s, p["start_ms"] + trim), min(e, pe - trim))
    return m


def transition_stats(a, note, prev, vowel_mask=None):
    """how the pitch moves from the previous note into this one (vowel frames only)."""
    s = note["start_ms"]
    up = note["tone"] > prev["tone"]
    win = frames_in(a, max(prev["start_ms"], s - 200), min(note["end_ms"], s + 300)) & a.voiced
    if vowel_mask is not None:
        win &= vowel_mask
    if win.sum() < 5:
        return None
    t = a.t_ms[win]
    m = a.midi[win]
    target = note["tone"]
    # start: last frame before s that sits within 20c of the previous note
    before = (t < s) & (np.abs(m - prev["tone"]) * 100 < 20)
    start_ms = t[before][-1] if before.any() else None
    # settle: first time after s it stays within 20c of target for 30 ms
    settle = None
    for i in range(len(t)):
        if t[i] < s - 100:
            continue
        j = i
        while j < len(t) and abs(m[j] - target) * 100 < 20:
            j += 1
        if j < len(t) and t[j - 1] - t[i] >= 30 or (j == len(t) and j > i):
            settle = t[i]
            break
    after = t >= s
    over = None
    if after.any():
        d = (m[after] - target) * 100
        over = float(np.max(d)) if up else float(-np.min(d))
    prep = None
    pre = (t < s) & (t > s - 200)
    if pre.any():
        d = (m[pre] - prev["tone"]) * 100
        prep = float(-np.min(d)) if up else float(np.max(d))
    return {
        "interval_semitones": round(note["tone"] - prev["tone"], 2),
        "starts_ms_before_boundary": _r(s - start_ms) if start_ms is not None else None,
        "settle_ms_after_boundary": _r(settle - s) if settle is not None else None,
        "overshoot_cents": _r(max(0.0, over)) if over is not None else None,
        "preparation_dip_cents": _r(max(0.0, prep)) if prep is not None else None,
    }
