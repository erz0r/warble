#!/usr/bin/env python3
"""a utau resampler stand-in: records its arguments, writes the requested length of the input
from the offset (no pitch change), so the bridge can be checked end to end."""
import json
import os
import sys

import numpy as np
import soundfile as sf

args = sys.argv[1:]
log = os.environ.get("MOCK_RESAMPLER_LOG")
if log:
    with open(log, "a") as f:
        f.write(json.dumps(args, ensure_ascii=False) + "\n")
inp, out, tone, vel, flags, offset, length, cons, cutoff, vol, mod, tempo, pb = args[:13]
if "crash" in flags:
    sys.exit(3)
x, sr = sf.read(inp, dtype="float32", always_2d=True)
x = x[:, 0]
a = int(float(offset) * sr / 1000)
n = int(float(length) * sr / 1000)
seg = x[a:a + n]
if len(seg) < n:
    seg = np.pad(seg, (0, n - len(seg)))
sf.write(out, seg * float(vol) / 100, sr, subtype="PCM_16")
