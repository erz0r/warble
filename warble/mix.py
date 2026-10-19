"""mixing: per-track effects, a shared reverb, backing tracks, loudness and a limiter.

score directives:
    fx eq=low:+2,high:+3,mid:2500:-3:1.0 comp=-18:3 delay=320:0.3:0.15 reverb=0.25 gain=-2
        eq bands: low:<db>[:<hz>] (shelf, 200 hz), high:<db>[:<hz>] (shelf, 6 khz), mid:<hz>:<db>[:<q>]
        comp: threshold db : ratio [: attack ms : release ms]
        delay: ms : feedback : mix          reverb: send 0..1 to the shared room
    master lufs=-14 ceiling=-1 room=1.6 preset=pop chain=OTT(depth=15)
        lufs: loudness target, ceiling: limiter ceiling in dBFS, room: reverb decay seconds,
        chain: installed vst3/au effects on the master bus (see warble.plugins)
    fx ... chain=OTT(depth=30)>Some Deesser()   installed effects on a track, after eq/comp/delay
    backing ./inst.wav @ 2.5s gain=-6     (or @ bar 3)
"""

import numpy as np
from scipy.signal import fftconvolve, lfilter

from .errors import WarbleError

PRESETS = {
    "dry": {"track": {}, "master": {"room": 1.2}},
    "pop": {"track": {"eq": "low:-1,mid:3000:2:0.8,high:2", "comp": "-20:3", "reverb": "0.18"}, "master": {"room": 1.4, "lufs": -14, "ceiling": -1}},
    "ballad": {"track": {"eq": "low:-1,high:1.5", "comp": "-22:2.5", "reverb": "0.32", "delay": "380:0.25:0.12"}, "master": {"room": 2.4, "lufs": -16, "ceiling": -1}},
    "choir": {"track": {"eq": "low:-2,high:1", "comp": "-20:2", "reverb": "0.4"}, "master": {"room": 2.8, "lufs": -16, "ceiling": -1}},
}


# ---- filters --------------------------------------------------------------------------------

def _biquad(kind, f0, sr, db=0.0, q=0.707):
    """rbj audio eq cookbook coefficients."""
    A = 10 ** (db / 40)
    w0 = 2 * np.pi * f0 / sr
    cw, sw = np.cos(w0), np.sin(w0)
    alpha = sw / (2 * q)
    if kind == "peak":
        b = [1 + alpha * A, -2 * cw, 1 - alpha * A]
        a = [1 + alpha / A, -2 * cw, 1 - alpha / A]
    elif kind == "lowshelf":
        sa = 2 * np.sqrt(A) * alpha
        b = [A * ((A + 1) - (A - 1) * cw + sa), 2 * A * ((A - 1) - (A + 1) * cw), A * ((A + 1) - (A - 1) * cw - sa)]
        a = [(A + 1) + (A - 1) * cw + sa, -2 * ((A - 1) + (A + 1) * cw), (A + 1) + (A - 1) * cw - sa]
    elif kind == "highshelf":
        sa = 2 * np.sqrt(A) * alpha
        b = [A * ((A + 1) + (A - 1) * cw + sa), -2 * A * ((A - 1) + (A + 1) * cw), A * ((A + 1) + (A - 1) * cw - sa)]
        a = [(A + 1) - (A - 1) * cw + sa, 2 * ((A - 1) - (A + 1) * cw), (A + 1) - (A - 1) * cw - sa]
    elif kind == "highpass":
        b = [(1 + cw) / 2, -(1 + cw), (1 + cw) / 2]
        a = [1 + alpha, -2 * cw, 1 - alpha]
    else:
        raise ValueError(kind)
    return np.array(b) / a[0], np.array(a) / a[0]


def parse_eq(spec):
    bands = []
    for item in str(spec).split(","):
        bits = item.strip().split(":")
        if not bits[0]:
            continue
        k = bits[0].lower()
        if k == "low":
            bands.append(("lowshelf", float(bits[2]) if len(bits) > 2 else 200.0, float(bits[1]), 0.707))
        elif k == "high":
            bands.append(("highshelf", float(bits[2]) if len(bits) > 2 else 6000.0, float(bits[1]), 0.707))
        elif k == "mid":
            bands.append(("peak", float(bits[1]), float(bits[2]), float(bits[3]) if len(bits) > 3 else 1.0))
        elif k == "hp":
            bands.append(("highpass", float(bits[1]), 0.0, 0.707))
        else:
            raise WarbleError("bad_fx", f"unknown eq band '{bits[0]}'", hint="low:<db>, high:<db>, mid:<hz>:<db>[:q], hp:<hz>")
    return bands


def eq(x, sr, spec):
    for kind, f0, db, q in parse_eq(spec):
        b, a = _biquad(kind, min(f0, sr / 2 * 0.95), sr, db, q)
        x = lfilter(b, a, x, axis=0)
    return x


def compress(x, sr, spec):
    bits = [float(v) for v in str(spec).split(":")]
    thr, ratio = bits[0], bits[1] if len(bits) > 1 else 3.0
    atk = (bits[2] if len(bits) > 2 else 10.0) / 1000
    rel = (bits[3] if len(bits) > 3 else 120.0) / 1000
    mono = x if x.ndim == 1 else x.mean(axis=1)
    # rms detector with attack/release smoothing on the level in db
    win = max(1, int(sr * 0.005))
    p = np.convolve(mono ** 2, np.ones(win) / win, mode="same")
    lvl = 10 * np.log10(p + 1e-12)
    over = np.maximum(0, lvl - thr)
    target = -over * (1 - 1 / ratio)
    g = np.empty_like(target)
    ca, cr = np.exp(-1 / (sr * atk)), np.exp(-1 / (sr * rel))
    # one-pole smoothing, decimated for speed then interpolated back
    step = max(1, int(sr * 0.001))
    tg = target[::step]
    sm = np.empty_like(tg)
    cur = 0.0
    ca2, cr2 = ca ** step, cr ** step
    for i, v in enumerate(tg):
        c = ca2 if v < cur else cr2
        cur = c * cur + (1 - c) * v
        sm[i] = cur
    g = np.interp(np.arange(len(target)), np.arange(len(sm)) * step, sm)
    makeup = (abs(thr) * (1 - 1 / ratio)) * 0.35
    gain = 10 ** ((g + makeup) / 20)
    return x * (gain[:, None] if x.ndim == 2 else gain)


def delay(x, sr, spec):
    bits = [float(v) for v in str(spec).split(":")]
    ms, fb = bits[0], bits[1] if len(bits) > 1 else 0.3
    mix = bits[2] if len(bits) > 2 else 0.2
    d = int(sr * ms / 1000)
    if d <= 0:
        return x
    wet = np.zeros_like(x)
    k, g = 1, 1.0
    while g > 0.01 and k * d < len(x):
        wet[k * d:] += x[: len(x) - k * d] * g
        g *= fb
        k += 1
    return x + wet * mix


def reverb_ir(sr, decay_s, seed=7):
    """a stereo room: decaying noise, darker as it decays, with a short predelay."""
    rng = np.random.default_rng(seed)
    n = int(sr * min(6.0, decay_s * 1.2))
    t = np.arange(n) / sr
    env = np.exp(-6.9 * t / max(0.1, decay_s))  # -60 dB at decay_s
    ir = rng.standard_normal((n, 2)) * env[:, None]
    # high frequencies die faster: blend in a lowpassed copy over time
    b, a = [0.25], [1, -0.75]
    lp = lfilter(b, a, ir, axis=0)
    w = np.clip(t / max(0.05, decay_s * 0.6), 0, 1)[:, None]
    ir = ir * (1 - w) + lp * w * 2.0
    pre = int(sr * 0.02)
    ir = np.vstack([np.zeros((pre, 2)), ir])
    return ir / np.sqrt(np.sum(ir ** 2) / 2)


def pan_stereo(x, pan):
    ang = (np.clip(pan, -1, 1) + 1) * np.pi / 4
    return np.stack([x * np.cos(ang), x * np.sin(ang)], axis=1) * np.sqrt(2)


def limiter(x, sr, ceiling_db=-1.0, lookahead_ms=5.0, release_ms=80.0):
    ceil = 10 ** (ceiling_db / 20)
    peak = np.max(np.abs(x), axis=1) if x.ndim == 2 else np.abs(x)
    la = max(1, int(sr * lookahead_ms / 1000))
    from scipy.ndimage import maximum_filter1d

    env = maximum_filter1d(peak, size=2 * la + 1)
    want = np.minimum(1.0, ceil / np.maximum(env, 1e-9))
    rel = np.exp(-1 / (sr * release_ms / 1000))
    step = max(1, int(sr * 0.0005))
    w = want[::step]
    out = np.empty_like(w)
    cur = 1.0
    r2 = rel ** step
    for i, v in enumerate(w):
        cur = v if v < cur else r2 * cur + (1 - r2) * v
        out[i] = cur
    g = np.interp(np.arange(len(want)), np.arange(len(out)) * step, out)
    g = np.minimum(g, want)
    y = x * (g[:, None] if x.ndim == 2 else g)
    return np.clip(y, -ceil, ceil)


def loudness(x, sr):
    from .perception.features import lufs

    return lufs(x, sr)


def normalize_lufs(x, sr, target):
    cur = loudness(x, sr)
    if not np.isfinite(cur) or cur < -70:
        return x, cur
    return x * 10 ** ((target - cur) / 20), cur


# ---- the mix ----------------------------------------------------------------------------------

def track_fx(track, master):
    fx = dict(PRESETS.get(master.get("preset", ""), {}).get("track", {}))
    fx.update(getattr(track, "fx", {}) or {})
    return fx


def process_track(mono, sr, track, master):
    """mono vocal -> (stereo dry, mono reverb send)."""
    fx = track_fx(track, master)
    y = mono.astype(np.float64) * 10 ** (track.volume_db / 20)
    if fx.get("gain"):
        y *= 10 ** (float(fx["gain"]) / 20)
    if fx.get("eq"):
        y = eq(y, sr, fx["eq"])
    if fx.get("comp"):
        y = compress(y, sr, fx["comp"])
    if fx.get("delay"):
        y = delay(y, sr, fx["delay"])
    send = float(fx.get("reverb", 0) or 0)
    if fx.get("chain"):
        from .plugins import run_chain

        st = run_chain(y, sr, fx["chain"])  # dual-mono in, stereo out
        bal = (np.clip(track.pan, -1, 1) + 1) * np.pi / 4
        st = st * np.array([np.cos(bal), np.sin(bal)]) * np.sqrt(2)
        return st, st.mean(axis=1) * send
    return pan_stereo(y, track.pan), y * send


def master_settings(score, preset=None):
    m = dict(PRESETS.get(preset or (score.master or {}).get("preset", ""), {}).get("master", {}))
    m.update({k: v for k, v in (score.master or {}).items()})
    if preset:
        m["preset"] = preset
    return m


def place(buf, x, start):
    """add x into buf at sample start (either may be stereo or mono)."""
    if start < 0:
        x = x[-start:]
        start = 0
    end = min(len(buf), start + len(x))
    if end > start:
        buf[start:end] += x[: end - start]


def load_backing(path, sr):
    import soundfile as sf

    try:
        x, s = sf.read(path, dtype="float64", always_2d=True)
    except Exception as e:  # noqa: BLE001
        raise WarbleError("backing_unreadable", f"cannot read backing track {path}: {e}")
    if x.shape[1] == 1:
        x = np.repeat(x, 2, axis=1)
    x = x[:, :2]
    if s != sr:
        from math import gcd

        from scipy.signal import resample_poly

        g = gcd(int(s), int(sr))
        x = resample_poly(x, sr // g, int(s) // g, axis=0)
    return x
