"""a/b comparison of two renders (or a render and a reference recording)."""

import numpy as np


def dtw_path(A, B, band=0.15):
    """dtw over feature frames (columns). returns index arrays (ia, ib). banded for speed."""
    a = A.T
    b = B.T
    # downsample long inputs so the matrix stays small
    step = max(1, int(np.ceil(max(len(a), len(b)) / 1500)))
    a2, b2 = a[::step], b[::step]
    n, m = len(a2), len(b2)
    an = a2 - a2.mean(1, keepdims=True)
    bn = b2 - b2.mean(1, keepdims=True)
    cost = np.full((n + 1, m + 1), np.inf)
    cost[0, 0] = 0
    w = max(int(band * max(n, m)), abs(n - m) + 5)
    for i in range(1, n + 1):
        jc = int(i * m / n)
        lo, hi = max(1, jc - w), min(m, jc + w)
        d = np.sqrt(np.mean((an[i - 1][None, :] - bn[lo - 1:hi]) ** 2, axis=1))
        for k, j in enumerate(range(lo, hi + 1)):
            cost[i, j] = d[k] + min(cost[i - 1, j], cost[i, j - 1], cost[i - 1, j - 1])
    i, j = n, m
    path = []
    while i > 0 and j > 0:
        path.append((i - 1, j - 1))
        c = (cost[i - 1, j - 1], cost[i - 1, j], cost[i, j - 1])
        k = int(np.argmin(c))
        if k == 0:
            i, j = i - 1, j - 1
        elif k == 1:
            i -= 1
        else:
            j -= 1
    path.reverse()
    ia = np.array([p[0] for p in path]) * step
    ib = np.array([p[1] for p in path]) * step
    return np.clip(ia, 0, len(a) - 1), np.clip(ib, 0, len(b) - 1)


def global_diff(a, b):
    ia, ib = dtw_path(a.mel_db, b.mel_db)
    mel_dist = float(np.mean(np.sqrt(np.mean((a.mel_db[:, ia] - b.mel_db[:, ib]) ** 2, axis=0))))
    # map dtw (stft frames, 5 ms hop) onto f0 frames
    ta, tb = a.spec_t_ms[ia], b.spec_t_ms[ib]
    fa = np.interp(ta, a.t_ms, np.where(a.voiced, a.midi, np.nan))
    fb = np.interp(tb, b.t_ms, np.where(b.voiced, b.midi, np.nan))
    both = np.isfinite(fa) & np.isfinite(fb)
    cents = (fb[both] - fa[both]) * 100
    timing = tb - ta
    return {
        "mel_distance_db": round(mel_dist, 2),
        "pitch_diff_cents": {"median": round(float(np.median(cents)), 1), "mean_abs": round(float(np.mean(np.abs(cents))), 1),
                             "p95_abs": round(float(np.percentile(np.abs(cents), 95)), 1)} if cents.size else None,
        "timing_shift_ms": {"median": round(float(np.median(timing)), 1), "max_abs": round(float(np.max(np.abs(timing))), 1)},
        "lufs": {"a": round(a.lufs, 2), "b": round(b.lufs, 2), "diff": round(b.lufs - a.lufs, 2)},
        "dynamics": {k: {"a": f(a), "b": f(b)} for k, f in (("crest_db", _crest), ("loudness_range_lu", _lra), ("centroid_hz", _centroid))},
        "duration_ms": {"a": round(a.duration_ms, 1), "b": round(b.duration_ms, 1)},
    }


def _crest(x):
    pk = float(np.max(np.abs(x.x))) + 1e-12
    rms = float(np.sqrt(np.mean(x.x ** 2))) + 1e-12
    return round(20 * np.log10(pk / rms), 2)


def _lra(x):
    v = x.st_lufs[x.st_lufs > -60]
    return round(float(np.percentile(v, 95) - np.percentile(v, 10)), 2) if v.size > 4 else None


def _centroid(x):
    m = x.rms_db > -40
    return round(float(np.median(x.centroid[m])), 0) if m.any() else None


METRIC_KEYS = ["median_cents_error", "within_20c_pct", "voiced_ratio", "onset_offset_ms", "rms_db", "breathiness_db", "hnr_db"]


def note_deltas(ra, rb):
    """per-note metric changes between two inspect reports, matched by note number."""
    na = {n["note"]: n for n in ra.get("notes", [])}
    out = []
    for nb in rb.get("notes", []):
        n0 = na.get(nb["note"])
        if not n0:
            continue
        d = {"note": nb["note"], "lyric": nb["lyric"]}
        for k in METRIC_KEYS:
            if n0.get(k) is not None and nb.get(k) is not None:
                d[k] = {"a": n0[k], "b": nb[k], "delta": round(nb[k] - n0[k], 2)}
        va, vb = n0.get("vibrato"), nb.get("vibrato")
        if va or vb:
            d["vibrato"] = {"a": va, "b": vb}
        out.append(d)
    return out


def verdict(ra, rb):
    """did B improve on A? counts notes that got closer to the intended pitch and artifacts."""
    better = worse = 0
    for d in note_deltas(ra, rb):
        e = d.get("median_cents_error")
        if e:
            if abs(e["b"]) + 3 < abs(e["a"]):
                better += 1
            elif abs(e["b"]) > abs(e["a"]) + 3:
                worse += 1
    aa = sum(1 for x in ra.get("artifacts", []) if x["severity"] != "info")
    ab = sum(1 for x in rb.get("artifacts", []) if x["severity"] != "info")
    return {"notes_closer_to_intent": better, "notes_further_from_intent": worse, "artifacts": {"a": aa, "b": ab, "delta": ab - aa}}
