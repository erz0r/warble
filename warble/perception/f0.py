"""f0 extraction with more than one extractor, because extractor errors look exactly like tuning
errors. harvest is robust on real voices but can return silence on perfectly stationary synthetic
tones; dio+stonemask is the opposite. `extract` merges them and reports where they disagree.
crepe / rmvpe are used when their packages are importable.
"""

import warnings

import numpy as np

FRAME_MS = 5.0
LONE_SALIENCE = 1.5
F0_FLOOR = 60.0
F0_CEIL = 1100.0


def _world(x, sr, method):
    import pyworld as pw

    x = np.ascontiguousarray(x, dtype=np.float64)
    if method == "harvest":
        f0, t = pw.harvest(x, sr, frame_period=FRAME_MS, f0_floor=F0_FLOOR, f0_ceil=F0_CEIL)
    else:
        f0, t = pw.dio(x, sr, frame_period=FRAME_MS, f0_floor=F0_FLOOR, f0_ceil=F0_CEIL)
        f0 = pw.stonemask(x, f0, t, sr)
    return f0, t


def _crepe(x, sr):
    import crepe  # noqa: F401 - optional

    _, freq, conf, _ = crepe.predict(x, sr, step_size=int(FRAME_MS), viterbi=True, verbose=0)
    f0 = np.where(conf > 0.5, freq, 0.0)
    return f0, np.arange(len(f0)) * FRAME_MS / 1000.0


def available():
    out = ["harvest", "dio"]
    for name in ("crepe", "rmvpe"):
        try:
            __import__(name)
            out.append(name)
        except ImportError:
            pass
    return out


def run(x, sr, method):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if method in ("harvest", "dio"):
            return _world(x, sr, method)
        if method == "crepe":
            return _crepe(x, sr)
    raise ValueError(f"extractor '{method}' is not available; have {available()}")


def to_midi(f0):
    f0 = np.asarray(f0, float)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(f0 > 0, 69 + 12 * np.log2(np.maximum(f0, 1e-9) / 440.0), np.nan)


def extract(x, sr, methods=("harvest", "dio")):
    """-> dict(t (s), f0 (merged hz), per-method f0, disagreements list).
    merge rule: where both voice, harvest wins unless they differ by more than 80 cents and dio is
    closer to the median of neighbours; where only one voices, take it but mark the frame."""
    curves = {}
    t = None
    for m in methods:
        f, tt = run(x, sr, m)
        curves[m] = f
        t = tt if t is None or len(tt) < len(t) else t
    n = min(len(c) for c in curves.values())
    t = t[:n]
    for m in curves:
        curves[m] = curves[m][:n]
    names = list(curves)
    merged = curves[names[0]].copy()
    disagreements = []
    if len(names) > 1:
        a, b = curves[names[0]], curves[names[1]]
        ma, mb = to_midi(a), to_midi(b)
        only_b = (a <= 0) & (b > 0)
        merged[only_b] = b[only_b]
        # a frame only one extractor calls voiced must show harmonic structure at that f0
        # (agreed frames score > ~2.2; lone votes on fricative noise score < 1)
        lone = np.where((a > 0) != (b > 0))[0]
        for i in lone:
            if salience(x, sr, t[i], merged[i]) < LONE_SALIENCE:
                merged[i] = 0.0
        both = (a > 0) & (b > 0)
        diff = np.abs(ma - mb) * 100
        bad = both & (diff > 80)
        if bad.any():
            # resolve by harmonic salience: the true f0 has energy at its multiples, a sub- or
            # super-harmonic candidate predicts peaks that aren't there
            for i in np.where(bad)[0]:
                if salience(x, sr, t[i], b[i]) > salience(x, sr, t[i], a[i]):
                    merged[i] = b[i]
        disagreements = _runs(t, (bad | only_b | ((a > 0) & (b <= 0))), diff, names)
    return {"t": t, "f0": merged, "curves": curves, "disagreements": disagreements, "frame_ms": FRAME_MS}


def salience(x, sr, t_s, f, n_fft=2048, harmonics=6):
    """mean log-magnitude at k*f minus at (k-0.5)*f, k=1..harmonics, around time t_s."""
    if f <= 0:
        return -np.inf
    c = int(t_s * sr)
    seg = x[max(0, c - n_fft // 2): max(0, c - n_fft // 2) + n_fft]
    if len(seg) < n_fft:
        seg = np.pad(seg, (0, n_fft - len(seg)))
    mag = np.log(np.abs(np.fft.rfft(seg * np.hanning(n_fft))) + 1e-9)
    bin_hz = sr / n_fft
    score = 0.0
    used = 0
    for k in range(1, harmonics + 1):
        hk, vk = k * f / bin_hz, (k - 0.5) * f / bin_hz
        if hk >= len(mag) - 1:
            break
        score += np.interp(hk, np.arange(len(mag)), mag) - np.interp(vk, np.arange(len(mag)), mag)
        used += 1
    return score / max(1, used)


def _runs(t, mask, diff, names, min_frames=3):
    out = []
    i = 0
    n = len(mask)
    while i < n:
        if not mask[i]:
            i += 1
            continue
        j = i
        while j < n and mask[j]:
            j += 1
        if j - i >= min_frames:
            d = diff[i:j]
            d = d[np.isfinite(d)]
            out.append({
                "start_ms": round(float(t[i] * 1000), 1),
                "end_ms": round(float(t[j - 1] * 1000 + FRAME_MS), 1),
                "kind": "pitch_differs" if d.size and np.nanmedian(d) > 80 else "voicing_differs",
                "median_cents_apart": round(float(np.median(d)), 1) if d.size else None,
                "extractors": names,
            })
        i = j
    return out
