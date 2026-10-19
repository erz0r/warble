"""per-note pitch controls applied on top of the base curve (model or rule).

controls (score `key=value` on a note):
  cents=<n>        constant offset in cents
  vib=<preset>     none, subtle, pop, ballad, opera, wide   (or vib=rate:depth[:delay], e.g. vib=5.5:40:0.3)
  vibrate=<hz> vibdepth=<cents> vibdelay=<0..1 of the note> override preset fields

the tuning layer (section 5 of the spec) builds richer curves; this is the minimum to sing.
"""

import numpy as np

# rate hz, depth cents, onset delay (fraction of note), fade-in (fraction of note)
VIBRATO_PRESETS = {
    "none": (0.0, 0.0, 0.0, 0.0),
    "subtle": (5.5, 18.0, 0.45, 0.25),
    "pop": (5.8, 30.0, 0.35, 0.2),
    "ballad": (5.2, 40.0, 0.3, 0.3),
    "opera": (6.0, 70.0, 0.1, 0.15),
    "wide": (5.0, 60.0, 0.5, 0.2),
}


def vibrato_params(controls):
    spec = controls.get("vib")
    if spec is None and not any(k in controls for k in ("vibrate", "vibdepth")):
        return None
    if isinstance(spec, str) and spec in VIBRATO_PRESETS:
        rate, depth, delay, fade = VIBRATO_PRESETS[spec]
    elif isinstance(spec, str) and ":" in spec:
        bits = [float(b) for b in spec.split(":")]
        rate, depth = bits[0], bits[1]
        delay = bits[2] if len(bits) > 2 else 0.3
        fade = 0.2
    else:
        rate, depth, delay, fade = VIBRATO_PRESETS["pop"]
    rate = float(controls.get("vibrate", rate))
    depth = float(controls.get("vibdepth", depth))
    delay = float(controls.get("vibdelay", delay))
    return rate, depth, delay, fade


def apply_pitchbends(out, frame_t, notes, spans, tm=None):
    """utau mode1 PitchBend: cents relative to the note's own pitch every 5 ticks from PBStart ms.
    over its span it replaces whatever transition the base curve had, as in utau."""
    for n, (s, e) in zip(notes, spans):
        pb = n.extra.get("pitchbend") if n.extra else None
        if not pb or not pb.get("cents"):
            continue
        step = pb.get("interval_ms")
        if step is None:
            bpm = tm.bpm_at(n.position) if tm else 120.0
            step = 60000.0 / (bpm * 480) * 5
        t0 = s + float(pb.get("start_ms", 0.0))
        xs = t0 + np.arange(len(pb["cents"])) * step
        m = (frame_t >= xs[0]) & (frame_t <= min(xs[-1], e))
        if m.any():
            out[m] = n.tone + np.interp(frame_t[m], xs, np.asarray(pb["cents"], float)) / 100.0
    return out


def apply_note_controls(midi, frame_t, notes, spans, tm=None):
    out = np.array(midi, dtype=np.float64)
    out = apply_pitchbends(out, frame_t, notes, spans, tm)
    for n, (s, e) in zip(notes, spans):
        c = n.controls
        m = (frame_t >= s) & (frame_t < e)
        if not m.any():
            continue
        if "cents" in c:
            out[m] += float(c["cents"]) / 100.0
        vp = vibrato_params(c)
        if vp and vp[1] > 0:
            rate, depth, delay, fade = vp
            length = e - s
            onset = s + delay * length
            fade_ms = max(1.0, fade * length)
            t = frame_t[m]
            env = np.clip((t - onset) / fade_ms, 0, 1)
            # fade out over the last 15% so the vibrato doesn't fight the next transition
            env *= np.clip((e - t) / max(1.0, 0.15 * length), 0, 1)
            out[m] += env * (depth / 100.0) * np.sin(2 * np.pi * rate * (t - onset) / 1000.0)
    return out
