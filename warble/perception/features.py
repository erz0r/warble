"""frame features for perception: spectrograms, loudness, aperiodicity, centroid, hnr, formants."""

import warnings

import numpy as np

HOP_MS = 5.0


def load(path):
    import soundfile as sf

    x, sr = sf.read(path, dtype="float64", always_2d=True)
    return x, sr


def mono(x):
    return x.mean(axis=1) if x.ndim == 2 else x


def stft_db(x, sr, n_fft=2048, hop_ms=HOP_MS):
    from scipy.signal import stft

    hop = max(1, int(sr * hop_ms / 1000))
    f, t, Z = stft(x, sr, nperseg=n_fft, noverlap=n_fft - hop, boundary="zeros", padded=True)
    mag = np.abs(Z)
    return f, t, 20 * np.log10(mag + 1e-9), mag


def mel_filterbank(sr, n_fft, n_mels=128, fmin=40.0, fmax=None):
    fmax = fmax or sr / 2

    def hz2mel(h):
        return 2595 * np.log10(1 + h / 700.0)

    def mel2hz(m):
        return 700 * (10 ** (m / 2595.0) - 1)

    mels = np.linspace(hz2mel(fmin), hz2mel(fmax), n_mels + 2)
    hz = mel2hz(mels)
    bins = np.fft.rfftfreq(n_fft, 1 / sr)
    fb = np.zeros((n_mels, len(bins)))
    for m in range(1, n_mels + 1):
        lo, c, hi = hz[m - 1], hz[m], hz[m + 1]
        fb[m - 1] = np.clip(np.minimum((bins - lo) / (c - lo + 1e-9), (hi - bins) / (hi - c + 1e-9)), 0, None)
    return fb, hz[1:-1]


def frame_rms_db(x, sr, hop_ms=HOP_MS, win_ms=20.0):
    hop = max(1, int(sr * hop_ms / 1000))
    win = max(hop, int(sr * win_ms / 1000))
    n = 1 + max(0, (len(x) - win)) // hop
    idx = np.arange(win)[None, :] + hop * np.arange(n)[:, None]
    fr = x[np.clip(idx, 0, len(x) - 1)]
    rms = np.sqrt(np.mean(fr ** 2, axis=1))
    t = (np.arange(n) * hop + win / 2) / sr
    return t, 20 * np.log10(rms + 1e-9)


def lufs(x, sr):
    """integrated loudness (bs.1770) when pyloudnorm is available, else a k-weighting-free estimate."""
    try:
        import pyloudnorm as pyln

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return float(pyln.Meter(sr).integrated_loudness(x))
    except Exception:  # noqa: BLE001
        r = np.sqrt(np.mean(x ** 2)) + 1e-12
        return float(20 * np.log10(r) - 0.691)


def short_term_lufs(x, sr, hop_ms=100.0, win_ms=400.0):
    try:
        import pyloudnorm as pyln

        meter = pyln.Meter(sr, block_size=win_ms / 1000)
    except Exception:  # noqa: BLE001
        meter = None
    hop = int(sr * hop_ms / 1000)
    win = int(sr * win_ms / 1000)
    ts, vals = [], []
    for s in range(0, max(1, len(x) - win), hop):
        seg = x[s:s + win]
        if meter is not None:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                try:
                    v = meter.integrated_loudness(seg)
                except Exception:  # noqa: BLE001
                    v = -70.0
        else:
            v = 20 * np.log10(np.sqrt(np.mean(seg ** 2)) + 1e-9)
        ts.append((s + win / 2) / sr)
        vals.append(max(-70.0, v if np.isfinite(v) else -70.0))
    return np.array(ts), np.array(vals)


def world_features(x, sr, f0, t):
    """aperiodicity (d4c) and spectral envelope (cheaptrick) on the f0 grid."""
    import pyworld as pw

    x = np.ascontiguousarray(x, dtype=np.float64)
    f0c = np.ascontiguousarray(np.asarray(f0, dtype=np.float64))
    tc = np.ascontiguousarray(np.asarray(t, dtype=np.float64))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        sp = pw.cheaptrick(x, f0c, tc, sr)
        ap = pw.d4c(x, f0c, tc, sr, threshold=0.0)
    return sp, ap


def breathiness_from_ap(ap, sr, lo=1000.0, hi=5000.0):
    """mean aperiodicity between lo and hi hz, in db (0 = all noise)."""
    n = ap.shape[1]
    freqs = np.linspace(0, sr / 2, n)
    m = (freqs >= lo) & (freqs <= hi)
    return 20 * np.log10(np.mean(ap[:, m], axis=1) + 1e-6)


def spectral_centroid(mag, freqs):
    p = mag ** 2
    return (p * freqs[:, None]).sum(0) / (p.sum(0) + 1e-12)


def hnr_from_ap(ap, sr, lo=100.0, hi=4000.0):
    """harmonic-to-noise ratio estimate from world aperiodicity (db)."""
    n = ap.shape[1]
    freqs = np.linspace(0, sr / 2, n)
    m = (freqs >= lo) & (freqs <= hi)
    a = np.clip(np.mean(ap[:, m] ** 2, axis=1), 1e-6, 1 - 1e-6)
    return 10 * np.log10((1 - a) / a)


def formants(x, sr, times_s, n=3, order=None, win_ms=30.0):
    """lpc formant tracks at the given times. returns [len(times), n] hz (nan when unsure)."""
    from scipy.signal import lfilter

    target_sr = 11025
    if sr != target_sr:
        from math import gcd

        from scipy.signal import resample_poly

        g = gcd(int(sr), target_sr)
        y = resample_poly(x, target_sr // g, int(sr) // g)
    else:
        y = x
    order = order or 2 + target_sr // 1000
    y = lfilter([1, -0.63], [1], y)  # pre-emphasis
    win = int(target_sr * win_ms / 1000)
    out = np.full((len(times_s), n), np.nan)
    hamming = np.hamming(win)
    for k, ts in enumerate(times_s):
        c = int(ts * target_sr)
        seg = y[max(0, c - win // 2): c - win // 2 + win]
        if len(seg) < win or np.max(np.abs(seg)) < 1e-4:
            continue
        seg = seg * hamming
        r = np.correlate(seg, seg, "full")[win - 1: win + order]
        a = _levinson(r, order)
        if a is None:
            continue
        roots = np.roots(a)
        roots = roots[np.imag(roots) > 0.01]
        ang = np.arctan2(np.imag(roots), np.real(roots))
        fr = ang * target_sr / (2 * np.pi)
        bw = -0.5 * target_sr / (2 * np.pi) * np.log(np.abs(roots) + 1e-12)
        good = sorted(f for f, b in zip(fr, bw) if 90 < f < 5000 and b < 400)
        for j in range(min(n, len(good))):
            out[k, j] = good[j]
    return out


def _levinson(r, order):
    a = np.zeros(order + 1)
    a[0] = 1.0
    e = r[0]
    if e <= 0:
        return None
    for i in range(1, order + 1):
        acc = r[i] + np.dot(a[1:i], r[i - 1:0:-1])
        k = -acc / e
        a_new = a.copy()
        a_new[1:i] = a[1:i] + k * a[i - 1:0:-1]
        a_new[i] = k
        a = a_new
        e *= 1 - k * k
        if e <= 0:
            return None
    return a
