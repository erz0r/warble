"""external utau wavtools, called with the standard argument list.

ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Core/Classic/ExeWavtool.cs.
openutau writes a .bat that calls the wavtool once per note; we call it directly, in order:

    wavtool <output> <input> <stp> <length> <p1> <p2> <p3> <v1> <v2> <v3> <v4> <overlap> <p4> <p5> <v5>

where length is '<ticks>@<tempo>+<correction ms>'. classic wavtools append raw data to
<output>.dat and a header to <output>.whd, which are joined at the end.
"""

import os
import subprocess

import numpy as np

from ..errors import WarbleError
from .resampler import SR, command_for, fmt


def envelope_args(item):
    """GetEnvelope: p1 p2 p3 v1 v2 v3 v4 overlap p4 p5 v5, relative to the first point."""
    env = item.phone["envelope"]
    (x0, y0), (x1, y1), (x2, y2), (x3, y3), (x4, y4) = env
    vals = [x0 - x0, x1 - x0, x4 - x3, y0, y1, y3, y4, item.overlap, x4 - x4, x2 - x1, y2]
    return [fmt(round(v, 6)) for v in vals]


def length_arg(item):
    corr = item.phone["preutter"] - item.phone["tail_intrude"] + item.phone["tail_overlap"]
    ticks = item.phone.get("duration_ticks")
    if ticks is None:
        ticks = int(round(item.phone["duration_ms"] * item.tempo * 480 / 60000.0))
    return f"{fmt(ticks)}@{fmt(item.tempo)}{'+' if corr >= 0 else ''}{fmt(round(corr, 6))}"


def concatenate(items, sample_paths, exe, workdir, origin_ms):
    """run the wavtool over every resampled note; returns (samples, calls)."""
    os.makedirs(workdir, exist_ok=True)
    out = os.path.join(workdir, f"wavtool-{os.getpid()}-{abs(hash(tuple(sample_paths))) % 10**8}.wav")
    for p in (out, out + ".whd", out + ".dat"):
        if os.path.exists(p):
            os.remove(p)
    cmd = command_for(exe)
    calls = []
    # a leading rest so the output timeline starts where the phrase does
    first = items[0]
    lead = first.phone["position_ms"] - first.phone["preutter"] - origin_ms
    for item, path in zip(items, sample_paths):
        args = [out, path, fmt(round(item.skip_over, 6)), length_arg(item)] + envelope_args(item)
        proc = subprocess.run(cmd + args, capture_output=True, timeout=60)
        calls.append(args)
        if proc.returncode != 0 and not (os.path.exists(out) or os.path.exists(out + ".dat")):
            raise WarbleError("wavtool_failed", f"{os.path.basename(exe)} failed on alias '{item.phone['alias']}'",
                              exit_code=proc.returncode, stderr=proc.stderr.decode(errors="replace")[-800:], args=args)
    if os.path.exists(out + ".whd") and os.path.exists(out + ".dat"):
        with open(out, "wb") as f:
            for part in (out + ".whd", out + ".dat"):
                with open(part, "rb") as g:
                    f.write(g.read())
    if not os.path.exists(out):
        raise WarbleError("wavtool_no_output", f"{os.path.basename(exe)} wrote no output file", calls=calls[-3:])
    import soundfile as sf

    y, sr = sf.read(out, dtype="float32", always_2d=True)
    y = y[:, 0]
    if sr != SR:
        from math import gcd

        from scipy.signal import resample_poly

        g = gcd(sr, SR)
        y = resample_poly(y, SR // g, sr // g).astype(np.float32)
    if lead > 0:
        y = np.concatenate([np.zeros(int(round(lead * SR / 1000)), np.float32), y])
    return y, calls
