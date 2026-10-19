"""artifact detectors. each finding has a timestamp (audio ms), a severity and a short message."""

import numpy as np

from .analysis import frames_in


def _ev(kind, t_ms, severity, msg, **extra):
    d = {"kind": kind, "t_ms": round(float(t_ms), 1), "severity": severity, "message": msg}
    d.update({k: v for k, v in extra.items() if v is not None})
    return d


def _runs(mask, min_len=1):
    out, i, n = [], 0, len(mask)
    while i < n:
        if mask[i]:
            j = i
            while j < n and mask[j]:
                j += 1
            if j - i >= min_len:
                out.append((i, j))
            i = j
        else:
            i += 1
    return out


def clicks(a, intent=None):
    """single-sample discontinuities: the second difference spikes far above its local level."""
    from scipy.ndimage import uniform_filter1d

    x = a.x
    d = np.abs(np.diff(x, 2))
    if d.size < 10:
        return []
    base = uniform_filter1d(d, size=int(a.sr * 0.01)) + 1e-6
    ratio = d / base
    cand = np.where((ratio > 14) & (d > 0.03))[0]
    # a glottal pulse in a low, buzzy voice also spikes, but it has a twin one pitch period away;
    # a click stands alone. compare against the largest spike within ±25 ms outside ±1 ms.
    near, far = int(a.sr * 0.001), int(a.sr * 0.025)
    keep = []
    for i in cand:
        lo, hi = max(0, i - far), min(len(d), i + far)
        ctx = np.concatenate([d[lo:max(lo, i - near)], d[min(hi, i + near):hi]])
        if ctx.size == 0 or d[i] > 3.0 * ctx.max():
            keep.append(i)
    cand = keep
    out = []
    last = -1e9
    joins = [j["t_ms"] for j in intent.joins] if intent else []
    for i in cand:
        t = (i + 1) * 1000.0 / a.sr
        if t - last < 8:
            continue
        last = t
        near_join = min((abs(t - j) for j in joins), default=1e9) < 25
        sev = "error" if d[i] > 0.2 else "warning"
        out.append(_ev("click", t, sev, f"discontinuity of {d[i]:.3f} ({ratio[i]:.0f}x local level)" + (" at a sample join" if near_join else ""),
                       at_join=near_join or None))
    return out[:200]


def join_dips(a, intent):
    """utau joins whose crossfade loses level (phase cancellation) or jumps in timbre."""
    if not intent or not intent.joins:
        return []
    out = []
    for j in intent.joins:
        if not j.get("voiced_onset", True):
            continue  # a stop or fricative onset dips by nature
        t = j["t_ms"]
        mid = frames_in(a, t - 10, t + 10)
        left = frames_in(a, t - 60, t - 25)
        right = frames_in(a, t + 25, t + 60)
        if not (mid.any() and left.any() and right.any()):
            continue
        lv, mv, rv = np.mean(a.rms_db[left]), np.mean(a.rms_db[mid]), np.mean(a.rms_db[right])
        dip = min(lv, rv) - mv
        if dip > 6 and min(lv, rv) > -45:
            out.append(_ev("join_dip", t, "warning" if dip < 12 else "error", f"level drops {dip:.1f} dB in the crossfade {j['from']} -> {j['to']}", dip_db=round(float(dip), 1)))
    return out


def spectral_jumps(a, intent):
    """frames where the log-mel spectrum changes much more than usual, away from phone boundaries."""
    flux = a.flux
    if flux.size < 10:
        return []
    med = np.median(flux)
    mad = np.median(np.abs(flux - med)) + 1e-6
    thr = med + 10 * mad
    bounds = ([p["start_ms"] for p in intent.phones] + [p["end_ms"] for p in intent.phones]
              + [p.get("audio_start_ms", p["start_ms"]) for p in intent.phones]) if intent else []
    out = []
    for i in np.where(flux > max(thr, 6.0))[0]:
        t = a.spec_t_ms[i]
        if bounds and min(abs(t - b) for b in bounds) < 30:
            continue
        k = min(len(a.rms_db) - 1, int(t / 5))
        if a.rms_db[k] < -45 or a.rms_db[max(0, k - 8)] < -40:
            continue  # quiet, or a phrase starting out of silence
        out.append(_ev("spectral_jump", t, "warning", f"sudden spectral change ({flux[i]:.1f} dB vs typical {med:.1f})"))
    return _dedupe(out, 30)


def pitch_problems(a, intent):
    """pitch jumps, octave errors and robotic flatness, judged against the intended curve."""
    out = []
    if not intent:
        return out
    intended = intent.pitch_at(a.t_ms)
    v = a.voiced & np.isfinite(intended)
    if intent.phones:
        # judge pitch only where a vowel is sung; consonants make trackers jump around
        from .metrics import sung_mask

        v &= sung_mask(a, intent, 0, a.duration_ms, trim=10.0)
    err = np.where(v, (a.midi - intended) * 100, np.nan)
    # octave errors: runs of ~1200 cents off
    oct_mask = np.isfinite(err) & (np.abs(np.abs(err) - 1200) < 150)
    for i, j in _runs(oct_mask, 6):
        sign = "up" if np.nanmedian(err[i:j]) > 0 else "down"
        ex = _extractor_note(a, a.t_ms[i], a.t_ms[j - 1])
        out.append(_ev("octave_error", a.t_ms[i], "error", f"pitch an octave {sign} for {a.t_ms[j - 1] - a.t_ms[i] + 5:.0f} ms" + ex,
                       duration_ms=round(float(a.t_ms[j - 1] - a.t_ms[i] + 5), 1)))
    # jumps: frame-to-frame steps the intent doesn't have
    dm = np.diff(a.midi) * 100
    di = np.diff(intended) * 100
    both = v[1:] & v[:-1]
    jump = both & (np.abs(dm - np.nan_to_num(di)) > 120) & ~oct_mask[1:] & ~oct_mask[:-1]
    for i in np.where(jump)[0]:
        out.append(_ev("pitch_jump", a.t_ms[i + 1], "warning", f"pitch jumps {dm[i]:+.0f} cents in one frame (intended {np.nan_to_num(di[i]):+.0f})"))
    out = _dedupe(out, 20)
    # robotic flatness on long notes
    for n in intent.notes:
        if n["end_ms"] - n["start_ms"] < 600:
            continue
        m = frames_in(a, n["start_ms"] + 200, n["end_ms"] - 100) & a.voiced
        if m.sum() < 60:
            continue
        sd = np.std(a.midi[m]) * 100
        if sd < 3:
            out.append(_ev("robotic_flatness", n["start_ms"], "info", f"note {n['index']} ({n['lyric']}) holds dead-flat pitch (spread {sd:.1f} cents over {m.sum() * 5} ms)", note=n["index"]))
    return out


def _extractor_note(a, t0, t1):
    for d in a.extractor_disagreements:
        if d["start_ms"] <= t1 and d["end_ms"] >= t0:
            return " (extractors disagree here; may be a tracking error, check `pitch extract`)"
    return ""


def dropouts(a, intent):
    """unvoiced runs inside vowels: either an aperiodic smear or a gap in the audio."""
    out = []
    if not intent:
        return out
    for p in intent.phones:
        pe = p.get("solo_end_ms", p["end_ms"])
        if not p["vowel"] or pe - p["start_ms"] < 80:
            continue
        m = frames_in(a, p["start_ms"] + 25, pe - 25)
        idx = np.where(m)[0]
        if not idx.size:
            continue
        unv = ~a.voiced[idx]
        for i, j in _runs(unv, 6):
            t0 = a.t_ms[idx[i]]
            loud = np.mean(a.rms_db[idx[i]:idx[j - 1] + 1])
            kind = "dropout" if loud < -50 else "unvoiced_in_vowel"
            msg = (f"silence inside vowel '{p['phoneme']}' for {(j - i) * 5} ms" if kind == "dropout"
                   else f"vowel '{p['phoneme']}' goes unvoiced for {(j - i) * 5} ms (noisy or creaky)")
            out.append(_ev(kind, t0, "warning" if (j - i) * 5 < 60 else "error", msg + _extractor_note(a, t0, t0 + (j - i) * 5), duration_ms=(j - i) * 5))
    return out


def rest_noise(a, intent):
    out = []
    if not intent:
        return out
    for s, e in intent.rests(a.duration_ms):
        m = frames_in(a, s, e)
        if m.sum() < 4:
            continue
        lv = np.max(a.rms_db[m])
        if lv > -55:
            t = a.t_ms[m][np.argmax(a.rms_db[m])]
            out.append(_ev("rest_noise", t, "warning" if lv < -35 else "error", f"sound in a rest: peaks at {lv:.0f} dBFS ({s:.0f}-{e:.0f} ms should be silent)", level_db=round(float(lv), 1)))
    return out


def signal_checks(a):
    out = []
    x = a.raw
    clip = np.abs(x) >= 0.999
    if clip.any():
        runs = _runs(clip.any(axis=1), 1)
        for i, j in runs[:20]:
            out.append(_ev("clipping", i * 1000.0 / a.sr, "error", f"{j - i} clipped sample(s)"))
    dc = np.mean(x, axis=0)
    if np.max(np.abs(dc)) > 0.005:
        out.append(_ev("dc_offset", 0, "warning", f"dc offset {np.max(np.abs(dc)):.4f}"))
    # energy in the top band, a sign of aliasing or imaging above the samples' real bandwidth
    f = a.spec_f
    p = 10 ** (a.spec_db / 10)
    total = p.sum()
    top = p[f > min(18000, a.sr / 2 * 0.85)].sum()
    if total > 0:
        ratio = 10 * np.log10(top / total + 1e-12)
        a.top_band_db = round(float(ratio), 1)
        if ratio > -30:
            out.append(_ev("hf_energy", 0, "warning", f"{ratio:.0f} dB of the energy is above {min(18000, a.sr / 2 * 0.85):.0f} Hz (aliasing, imaging or hiss)"))
    return out


def buzz(a, intent):
    """voiced, periodic energy inside unvoiced consonants: resampler or vocoder buzz."""
    out = []
    if not intent:
        return out
    fricatives = {"s", "sh", "f", "h", "hy", "ts", "ch", "k", "t", "p", "q", "cl"}
    for p in intent.phones:
        name = p["phoneme"].split("/")[-1]
        if p["vowel"] or name not in fricatives or p["end_ms"] - p["start_ms"] < 40:
            continue
        m = frames_in(a, p["start_ms"] + 5, p["end_ms"] - 5)
        if m.sum() < 4:
            continue
        hnr = np.mean(a.hnr_db[m])
        vr = np.mean(a.voiced[m])
        if hnr > 12 and vr > 0.7 and np.mean(a.rms_db[m]) > -40:
            out.append(_ev("buzz", p["start_ms"], "warning", f"unvoiced '{p['phoneme']}' sounds periodic (hnr {hnr:.0f} dB, {vr * 100:.0f}% voiced)"))
    return out


def silence_checks(a):
    rms = 20 * np.log10(np.sqrt(np.mean(a.x ** 2)) + 1e-12)
    if rms < -70:
        return [_ev("silent", 0, "error", f"render is silent (rms {rms:.0f} dBFS)")]
    v = np.mean(a.voiced[a.rms_db > -40]) if (a.rms_db > -40).any() else 0
    if v < 0.05 and rms > -50:
        return [_ev("all_noise", 0, "error", "audio has energy but almost no pitched frames: noise, not singing")]
    return []


def _dedupe(evs, ms):
    out = []
    for e in sorted(evs, key=lambda e: e["t_ms"]):
        if out and out[-1]["kind"] == e["kind"] and e["t_ms"] - out[-1]["t_ms"] < ms:
            continue
        out.append(e)
    return out


def detect_all(a, intent):
    evs = []
    evs += silence_checks(a)
    evs += signal_checks(a)
    evs += clicks(a, intent)
    evs += join_dips(a, intent)
    evs += spectral_jumps(a, intent)
    evs += pitch_problems(a, intent)
    evs += dropouts(a, intent)
    evs += rest_noise(a, intent)
    evs += buzz(a, intent)
    return sorted(evs, key=lambda e: e["t_ms"])
