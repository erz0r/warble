"""the note pitch model: control points with shapes, a vibrato object, and an optional raw layer.

ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Core/Ustx/UNote.cs (UPitch,
PitchPoint, UVibrato.Evaluate), Render/RenderPhrase.cs (pitch construction) and Util/MusicMath.cs
(shape easing). units differ slightly from openutau's files: point y is in cents here (openutau
stores 0.1 semitones), so y_cents = 10 * openutau_y.

per note, in the score:
    pts=x:y:shape,...        x ms from the note start, y cents from the note pitch,
                             shape io (s-curve), l (linear), i (ease in), o (ease out), sp (spline),
                             h (hold: stay at y until the next point)
    vbr=length,period,depth,in,out,shift,drift[,vollink]
                             openutau / ust order: length % of note, period ms, depth cents,
                             fade in/out % of the vibrato, phase shift % of a period, drift %
    snap=0                   don't pin the first point to the previous note's pitch
    raw=start_ms:step_ms:c0;c1;...  per-frame cents layer (ust mode1 PitchBend lands here)
    cents=n                  constant offset
    drift=depth:rate[:seed]  slow random wander: depth cents, rate hz, reproducible with the seed
"""

import math

import numpy as np

SHAPES = ("io", "l", "i", "o", "sp", "h")
DEFAULT_VIBRATO = {"length": 75.0, "period": 175.0, "depth": 25.0, "in": 10.0, "out": 10.0, "shift": 0.0, "drift": 0.0, "vollink": 0.0}
PORTAMENTO_PRESETS = {"standard": (80, -40), "fast": (50, -25), "slow": (120, -60), "snap": (2, -1)}
EP = 0.001


def interp_shape(x0, x1, y0, y1, x, shape):
    if x1 - x0 < EP:
        return y1
    u = (x - x0) / (x1 - x0)
    if shape in ("io", "sp"):
        return y0 + (y1 - y0) * (1 - math.cos(u * math.pi)) / 2
    if shape == "i":
        return y0 + (y1 - y0) * (1 - math.cos(u * math.pi / 2))
    if shape == "o":
        return y0 + (y1 - y0) * math.sin(u * math.pi / 2)
    if shape == "h":
        return y0
    return y0 + (y1 - y0) * u


def clamp_vibrato(v):
    out = dict(DEFAULT_VIBRATO)
    out.update({k: float(val) for k, val in v.items()})
    out["length"] = min(100, max(0, out["length"]))
    out["period"] = min(500, max(5, out["period"]))
    out["depth"] = min(200, max(5, out["depth"]))
    out["in"] = min(100, max(0, out["in"]))
    out["out"] = min(100 - out["in"], max(0, out["out"]))
    out["shift"] = min(100, max(0, out["shift"]))
    out["drift"] = min(100, max(-100, out["drift"]))
    return out


def vibrato_cents(npos, nperiod, v):
    """UVibrato.Evaluate, returned as cents offset from the note."""
    nstart = 1 - v["length"] / 100
    nin = v["length"] / 100 * v["in"] / 100
    nout = v["length"] / 100 * v["out"] / 100
    t = (npos - nstart) / nperiod + v["shift"] / 100
    y = math.sin(2 * math.pi * t) * v["depth"] + v["depth"] / 100 * v["drift"]
    if npos < nstart:
        return 0.0
    if npos < nstart + nin and nin > 0:
        return y * (npos - nstart) / nin
    if npos > 1 - nout and nout > 0:
        return y * (1 - npos) / nout
    return y


# ---- parsing to and from score controls ---------------------------------------------------

def parse_points(text):
    pts = []
    for item in str(text).split(","):
        if not item.strip():
            continue
        bits = item.split(":")
        x, y = float(bits[0]), float(bits[1])
        shape = bits[2] if len(bits) > 2 and bits[2] else "io"
        if shape not in SHAPES:
            raise ValueError(f"unknown point shape '{shape}' (use {SHAPES})")
        pts.append([x, y, shape])
    pts.sort(key=lambda p: p[0])
    return pts


def format_points(pts):
    return ",".join(f"{_n(x)}:{_n(y)}" + ("" if s == "io" else f":{s}") for x, y, s in pts)


def parse_vibrato(text):
    keys = ["length", "period", "depth", "in", "out", "shift", "drift", "vollink"]
    vals = [float(v) for v in str(text).split(",") if v.strip() != ""]
    return clamp_vibrato(dict(zip(keys, vals)))


def format_vibrato(v):
    keys = ["length", "period", "depth", "in", "out", "shift", "drift"]
    s = ",".join(_n(v[k]) for k in keys)
    return s + (f",{_n(v['vollink'])}" if v.get("vollink") else "")


def parse_raw(text):
    start, step, vals = str(text).split(":", 2)
    return {"start_ms": float(start), "step_ms": float(step), "cents": [float(c) for c in vals.split(";") if c != ""]}


def format_raw(r):
    return f"{_n(r['start_ms'])}:{_n(r['step_ms'])}:" + ";".join(_n(c) for c in r["cents"])


def _n(x):
    x = float(x)
    return str(int(x)) if x == int(x) else f"{x:.4g}" if abs(x) < 1e4 else str(round(x, 3))


def note_points(n):
    v = n.controls.get("pts")
    return parse_points(v) if v not in (None, "") else None


# named styles for `vib=<name>`: (rate hz, depth cents, onset as fraction of the note, fade-in as
# fraction of the note). converted to the vibrato object below.
VIBRATO_STYLES = {
    "none": (0.0, 0.0, 0.0, 0.0),
    "subtle": (5.5, 18.0, 0.45, 0.25),
    "pop": (5.8, 30.0, 0.35, 0.2),
    "ballad": (5.2, 40.0, 0.3, 0.3),
    "opera": (6.0, 70.0, 0.1, 0.15),
    "wide": (5.0, 60.0, 0.5, 0.2),
}


def style_to_vibrato(rate, depth, onset, fade):
    length = 100 * (1 - onset)
    return clamp_vibrato({"length": length, "period": 1000.0 / rate if rate else 175.0, "depth": depth,
                          "in": min(100.0, 100 * fade / max(1e-3, 1 - onset)), "out": 15.0})


def note_vibrato(n):
    c = n.controls
    if "vbr" in c:
        v = parse_vibrato(c["vbr"])
        return v if v["length"] > 0 else None
    spec = c.get("vib")
    if spec is None and not any(k in c for k in ("vibrate", "vibdepth")):
        return None
    if isinstance(spec, str) and spec in VIBRATO_STYLES:
        rate, depth, onset, fade = VIBRATO_STYLES[spec]
    elif isinstance(spec, str) and ":" in spec:
        bits = [float(b) for b in spec.split(":")]
        rate, depth = bits[0], bits[1]
        onset = bits[2] if len(bits) > 2 else 0.3
        fade = 0.2
    else:
        rate, depth, onset, fade = VIBRATO_STYLES["pop"]
    rate = float(c.get("vibrate", rate))
    depth = float(c.get("vibdepth", depth))
    onset = float(c.get("vibdelay", onset))
    if depth <= 0 or rate <= 0:
        return None
    return style_to_vibrato(rate, depth, onset, fade)


def note_raw(n):
    if "raw" in n.controls:
        return parse_raw(n.controls["raw"])
    pb = n.extra.get("pitchbend") if n.extra else None
    if pb and pb.get("cents"):
        return {"start_ms": float(pb.get("start_ms", 0)), "step_ms": pb.get("interval_ms"), "cents": pb["cents"]}
    return None


# ---- composition ------------------------------------------------------------------------------

def compose(frame_t, notes, tm, base_midi=None, track=None):
    """the pitch an engine should sing, in midi per frame.

    base_midi is the engine's own idea (pitch model or rule curve). notes that carry explicit
    points own their span: there the base is replaced by the step grid plus the points, as openutau
    builds it. vibrato objects, the raw layer and cents offsets are added on top."""
    t = np.asarray(frame_t, float)
    spans = [(tm.tick_to_ms(n.position), tm.tick_to_ms(n.end)) for n in notes]
    # step grid: each note's tone until the next note starts; before the first / after the last, hold
    step = np.full(len(t), notes[0].tone, float)
    for n, (s, e) in zip(notes, spans):
        step[t >= s] = n.tone
    out = np.array(base_midi, float) if base_midi is not None else step.copy()
    for i, (n, (s, e)) in enumerate(zip(notes, spans)):
        pts = note_points(n)
        if not pts:
            continue
        prev = notes[i - 1] if i > 0 and abs(spans[i - 1][1] - s) < 1e-6 else None
        snap = str(n.controls.get("snap", "1")) not in ("0", "false", "no")
        abs_pts = [[s + x, n.tone * 100 + y, sh] for x, y, sh in pts]
        if snap:
            abs_pts[0][1] = (prev.tone if prev is not None else n.tone) * 100
        # autocomplete like RenderPhrase: extend flat to the note edges
        first_x = abs_pts[0][0]
        if first_x > s:
            abs_pts.insert(0, [s, abs_pts[0][1], "io"])
        if abs_pts[-1][0] < e:
            abs_pts.append([e, abs_pts[-1][1], "io"])
        lo, hi = abs_pts[0][0], abs_pts[-1][0]
        m = (t >= lo) & (t < hi)
        if not m.any():
            continue
        xs = t[m]
        vals = np.empty(len(xs))
        k = 0
        for j, x in enumerate(xs):
            while k < len(abs_pts) - 2 and x >= abs_pts[k + 1][0]:
                k += 1
            p0, p1 = abs_pts[k], abs_pts[k + 1]
            if p0[2] == "sp" and len(pts) > 2:
                pm = abs_pts[max(0, k - 1)]
                p2 = abs_pts[min(len(abs_pts) - 1, k + 2)]
                vals[j] = _catmull(pm, p0, p1, p2, x)
            else:
                vals[j] = interp_shape(p0[0], p1[0], p0[1], p1[1], x, p0[2])
        # the user's points own their span: they replace the base there
        out[m] = vals / 100.0
    # vibrato
    for n, (s, e) in zip(notes, spans):
        v = note_vibrato(n)
        if not v:
            continue
        m = (t >= s) & (t < e)
        if not m.any() or e <= s:
            continue
        nperiod = v["period"] / (e - s)
        npos = (t[m] - s) / (e - s)
        out[m] += np.array([vibrato_cents(p, nperiod, v) for p in npos]) / 100.0
    # raw per-frame layer (ust mode1): replaces the curve over its span, relative to the note
    for n, (s, e) in zip(notes, spans):
        r = note_raw(n)
        if not r:
            continue
        stp = r["step_ms"] or 60000.0 / (tm.bpm_at(n.position) * 480) * 5
        xs = s + r["start_ms"] + np.arange(len(r["cents"])) * stp
        m = (t >= xs[0]) & (t <= min(xs[-1], e))
        if m.any():
            out[m] = n.tone + np.interp(t[m], xs, np.asarray(r["cents"], float)) / 100.0
    for n, (s, e) in zip(notes, spans):
        if "cents" in n.controls:
            m = (t >= s) & (t < e)
            out[m] += float(n.controls["cents"]) / 100.0
        if n.controls.get("drift"):
            m = (t >= s) & (t < e)
            if m.any():
                out[m] += drift_cents(t[m] - s, e - s, str(n.controls["drift"])) / 100.0
    if track is not None and track.curves.get("pitd"):
        # openutau's pitch deviation curve: cents added everywhere
        ticks = np.array([tm.ms_to_tick(x) for x in t])
        out += track.curve_at("pitd", ticks) / 100.0
    return out


def drift_cents(t_rel, length, spec):
    """smooth random wander: a few low-frequency sines with seeded phases, faded at both ends so
    transitions stay clean."""
    bits = spec.split(":")
    depth = float(bits[0])
    rate = float(bits[1]) if len(bits) > 1 else 0.7
    seed = int(float(bits[2])) if len(bits) > 2 else 0
    rng = np.random.default_rng(seed)
    y = np.zeros(len(t_rel))
    for k in range(3):
        f = rate * (0.6 + 0.8 * rng.random())
        y += np.sin(2 * np.pi * f * t_rel / 1000.0 + rng.random() * 2 * np.pi) / (k + 1)
    y = y / 1.83 * depth
    fade = np.clip(np.minimum(t_rel, length - t_rel) / max(1.0, min(80.0, length / 4)), 0, 1)
    return y * fade


def _catmull(pm, p0, p1, p2, x):
    """cubic hermite through p0..p1 with catmull-rom tangents, a stand-in for CubicSplineSegment."""
    x0, x1 = p0[0], p1[0]
    if x1 - x0 < EP:
        return p1[1]
    u = (x - x0) / (x1 - x0)
    m0 = (p1[1] - pm[1]) / max(EP, (x1 - pm[0])) * (x1 - x0)
    m1 = (p2[1] - p0[1]) / max(EP, (p2[0] - x0)) * (x1 - x0)
    h00, h10, h01, h11 = 2 * u**3 - 3 * u**2 + 1, u**3 - 2 * u**2 + u, -2 * u**3 + 3 * u**2, u**3 - u**2
    return h00 * p0[1] + h10 * m0 + h01 * p1[1] + h11 * m1
