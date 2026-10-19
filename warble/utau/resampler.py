"""resampler items, the utau command-line bridge, and the built-in world resampler.

ResamplerItem math and the pitchbend encoding are ported from openutau (MIT, Copyright (c) 2014
StAkira): OpenUtau.Core/Classic/ResamplerItem.cs, ExeResampler.cs, OpenUtau.Core/Util/Base64.cs.
"""

import hashlib
import math
import os
import shutil
import subprocess
import sys

import numpy as np

from ..errors import WarbleError

SR = 44100
B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
CACHE_DIR = os.environ.get("WARBLE_CACHE_RES", os.path.join(os.path.expanduser("~"), ".cache", "warble", "resampler"))


def tone_name(tone):
    return f"{NOTE_NAMES[tone % 12]}{tone // 12 - 1}"


def encode_int12(v):
    if v < 0:
        v += 4096
    return B64[(v >> 6) & 0x3F] + B64[v & 0x3F]


def encode_pitchbend(values):
    """Base64EncodeInt12: two chars per value, runs of repeats written as '#<n>#' after the first."""
    out, last, dups = [], None, 0
    for b in (encode_int12(int(v)) for v in values):
        if b == last:
            dups += 1
        elif dups == 0:
            out.append(b)
        else:
            out.append(f"#{dups}#")
            dups = 0
            out.append(b)
        last = b
    if dups:
        out.append(f"#{dups}#")
    return "".join(out)


def decode_pitchbend(s):
    """inverse of encode_pitchbend, for tests and for reading ust Pitches."""
    vals, i = [], 0
    while i < len(s):
        if s[i] == "#":
            j = s.index("#", i + 1)
            vals.extend([vals[-1]] * int(s[i + 1:j]))
            i = j + 1
            continue
        v = (B64.index(s[i]) << 6) | B64.index(s[i + 1])
        vals.append(v - 4096 if v >= 2048 else v)
        i += 2
    return vals


def fmt(x):
    """format a number the way .net's invariant ToString does: shortest round-trip, no '.0'."""
    if isinstance(x, (int, np.integer)):
        return str(int(x))
    x = float(x)
    if x == int(x) and abs(x) < 1e15:
        return str(int(x))
    return repr(x)


class Item:
    """everything one resampler call needs, computed like openutau's ResamplerItem."""

    def __init__(self, phone, tm, pitch_cents_at, resampler_name="builtin"):
        oto = phone["oto"]
        self.phone = phone
        self.input_file = phone["wav_path"]
        self.tone = int(round(phone["tone"]))
        self.flags = phone.get("flags", "")
        self.velocity = int(round(phone.get("vel", 100)))
        self.volume = int(round(phone.get("vol", 100)))
        self.modulation = int(round(phone.get("mod", 0)))
        self.preutter = phone["preutter"]
        self.overlap = phone["overlap"]
        stretch = 2 ** (1.0 - self.velocity * 0.01)
        pulled = round(phone["preutter"] / stretch - oto.preutter, 3)
        pulled = min(max(pulled, 0.0), max(0.0, oto.offset))
        self.offset = oto.offset - pulled
        pitch_leading = (oto.preutter + pulled) * stretch
        self.skip_over = pitch_leading - phone["preutter"]
        self.consonant = oto.consonant + pulled
        self.cutoff = oto.cutoff - pulled if oto.cutoff < 0 else oto.cutoff
        dur_correction = phone["preutter"] - phone["tail_intrude"] + phone["tail_overlap"]
        need = phone["end_ms"] - phone["position_ms"] + dur_correction + self.skip_over
        need = max(need, self.consonant)
        self.dur_required = math.ceil(need / 50.0 + 0.5) * 50.0
        self.tempo = phone["tempo"]
        self.stretch = stretch
        # pitch points every 5 ticks at the phone's tempo, from (position - pitch leading) to envelope end
        interval_ms = 60000.0 / (self.tempo * 480) * 5
        span_ms = phone["envelope"][4][0] + pitch_leading
        count = max(0, math.ceil((span_ms / (60000.0 / (self.tempo * 480))) / 5.0))
        start = phone["position_ms"] - pitch_leading
        self.pitch_start_ms = start
        self.pitch_interval_ms = interval_ms
        self.pitches = [int(round(pitch_cents_at(start + interval_ms * i) - self.tone * 100)) for i in range(count)]
        self.resampler = resampler_name

    def args(self, input_path, output_path):
        """the standard utau resampler argument list."""
        return [
            input_path, output_path, tone_name(self.tone), str(self.velocity), self.flags,
            fmt(self.offset), fmt(self.dur_required), fmt(self.consonant), fmt(self.cutoff),
            str(self.volume), str(self.modulation), f"!{fmt(self.tempo)}", encode_pitchbend(self.pitches),
        ]

    def key(self):
        h = hashlib.sha256()
        st = os.stat(self.input_file)
        for part in [self.resampler, self.input_file, st.st_size, st.st_mtime] + self.args("in", "out"):
            h.update(str(part).encode())
            h.update(b"\0")
        return h.hexdigest()[:24]

    def envelope_samples(self):
        """EnvelopeMsToSamples: shift so p0 is 0, then add the skipped samples."""
        env = self.phone["envelope"]
        shift = -env[0][0]
        skip = int(self.skip_over * SR / 1000)
        return [((x + shift) * SR / 1000 + skip, y / 100.0) for x, y in env]

    def apply_envelope(self, samples):
        env = self.envelope_samples()
        xs = np.array([p[0] for p in env])
        ys = np.array([p[1] for p in env])
        idx = np.arange(len(samples), dtype=np.float64)
        gain = np.interp(idx, xs, ys, left=ys[0], right=ys[-1])
        return samples * gain.astype(np.float32)


# ---- wav io ------------------------------------------------------------------------------

_WAV_CACHE = {}


def load_wav(path):
    import soundfile as sf

    st = os.stat(path)
    key = (path, st.st_mtime, st.st_size)
    if key not in _WAV_CACHE:
        x, sr = sf.read(path, dtype="float32", always_2d=True)
        x = x[:, 0]
        if sr != SR:
            from math import gcd

            from scipy.signal import resample_poly

            g = gcd(sr, SR)
            x = resample_poly(x, SR // g, sr // g).astype(np.float32)
        _WAV_CACHE[key] = x
    return _WAV_CACHE[key]


# ---- built-in world resampler ---------------------------------------------------------------

BUILTIN_FLAGS = {"g": "gender/formant shift, -100..100, positive is deeper", "B": "breathiness 0..100, 50 is neutral",
                 "b": "alias of B", "P": "peak normalization 0..100 (default 86)"}
_ANALYSIS = {}


def parse_flags(text):
    """'g-10B60P86' -> {'g': -10, 'B': 60, 'P': 86}. unknown letters are returned too."""
    import re

    out = {}
    for m in re.finditer(r"([A-Za-z]+)(-?\d+(?:\.\d+)?)?", text or ""):
        out[m.group(1)] = float(m.group(2)) if m.group(2) else None
    return out


def _analyze(path, start_ms, end_ms):
    import pyworld as pw

    key = (path, round(start_ms, 3), round(end_ms, 3), os.stat(path).st_mtime)
    if key not in _ANALYSIS:
        x = load_wav(path).astype(np.float64)
        a = max(0, int(start_ms * SR / 1000))
        b = min(len(x), max(a + 1, int(end_ms * SR / 1000)))
        seg = x[a:b]
        if len(seg) < SR * 0.02:
            seg = np.pad(seg, (0, int(SR * 0.02) - len(seg)))
        f0, t = pw.harvest(seg, SR, frame_period=5.0, f0_floor=60, f0_ceil=1100)
        sp = pw.cheaptrick(seg, f0, t, SR)
        ap = pw.d4c(seg, f0, t, SR)
        _ANALYSIS[key] = (f0, sp, ap, len(seg) * 1000.0 / SR)
    return _ANALYSIS[key]


def builtin(item, warnings):
    """pitch-shift and time-stretch one sample with world: the fixed (consonant) region is only
    scaled by velocity, the rest stretches to fill the required length."""
    import pyworld as pw

    x = load_wav(item.input_file)
    file_ms = len(x) * 1000.0 / SR
    start = item.offset
    end = start - item.cutoff if item.cutoff < 0 else file_ms - item.cutoff
    end = min(end, file_ms)
    if end <= start + 5:
        raise WarbleError("oto_region_empty", f"alias '{item.phone['alias']}': cutoff leaves no audio ({start:.1f}..{end:.1f} ms)", file=item.input_file)
    f0, sp, ap, src_ms = _analyze(item.input_file, start, end)
    fp = 5.0
    n_out = max(2, int(math.ceil(item.dur_required / fp)))
    t_out = np.arange(n_out) * fp
    cons_out = item.consonant * item.stretch
    src_fixed = min(item.consonant, src_ms)
    rest_src = max(1e-3, src_ms - src_fixed)
    rest_out = max(1e-3, item.dur_required - cons_out)
    t_src = np.where(t_out < cons_out, t_out / item.stretch, src_fixed + (t_out - cons_out) * rest_src / rest_out)
    t_src = np.clip(t_src, 0, src_ms - fp)
    fi = t_src / fp
    i0 = np.clip(np.floor(fi).astype(int), 0, len(f0) - 1)
    i1 = np.clip(i0 + 1, 0, len(f0) - 1)
    w = (fi - i0)[:, None]
    lsp = np.log(np.maximum(sp, 1e-12))
    sp_o = np.exp(lsp[i0] * (1 - w) + lsp[i1] * w)
    ap_o = ap[i0] * (1 - w) + ap[i1] * w
    voiced = (f0[i0] > 0) & (f0[i1] > 0) | (f0[np.clip(np.round(fi).astype(int), 0, len(f0) - 1)] > 0)
    # target pitch from the pitchbend points; output time 0 is where the pitchbend starts
    cents = np.interp(t_out, np.arange(len(item.pitches)) * item.pitch_interval_ms, item.pitches) if item.pitches else np.zeros(n_out)
    target = 440.0 * 2 ** ((item.tone - 69 + cents / 100.0) / 12.0)
    if item.modulation:
        src_f0 = np.where(f0[i0] > 0, f0[i0], np.nan)
        mean = np.nanmedian(f0[f0 > 0]) if np.any(f0 > 0) else np.nan
        if np.isfinite(mean):
            dev = np.nan_to_num(np.log2(src_f0 / mean), nan=0.0)
            target = target * 2 ** (dev * item.modulation / 100.0)
    f0_o = np.where(voiced, target, 0.0)
    flags = parse_flags(item.flags)
    for k in flags:
        if k not in BUILTIN_FLAGS:
            warnings.add(f"built-in resampler ignores flag '{k}'")
    g = flags.get("g") or 0.0
    if g:
        # warp the spectral envelope: positive g lowers formants
        ratio = 2 ** (-float(g) / 400.0)
        nb = sp_o.shape[1]
        src_bins = np.clip(np.arange(nb) * ratio, 0, nb - 1)
        sp_o = np.exp(np.stack([np.interp(src_bins, np.arange(nb), row) for row in np.log(sp_o)]))
    breath = flags.get("B", flags.get("b"))
    if breath is not None and breath != 50:
        k = float(breath) / 50.0
        ap_o = np.clip(1 - (1 - ap_o) ** (1 / max(k, 1e-3)), 0.0, 1.0) if k > 1 else np.clip(ap_o * k, 0.0, 1.0)
    y = pw.synthesize(np.ascontiguousarray(f0_o), np.ascontiguousarray(sp_o), np.ascontiguousarray(ap_o), SR, fp)
    y = y[: int(item.dur_required * SR / 1000)].astype(np.float32)
    peak_pct = flags.get("P", 86.0)
    if peak_pct:
        # utau resamplers normalize to a peak; P0 turns it off
        pk = float(np.max(np.abs(y))) or 1.0
        src_pk = float(np.max(np.abs(x[int(start * SR / 1000):int(end * SR / 1000)]))) or 1.0
        y = y * min(src_pk / pk, 4.0)
    return y * (item.volume / 100.0)


# ---- external resamplers -------------------------------------------------------------------

def resampler_dirs():
    dirs = []
    env = os.environ.get("WARBLE_RESAMPLERS")
    if env:
        dirs += env.split(os.pathsep)
    dirs.append(os.path.abspath("resamplers"))
    return [d for d in dirs if os.path.isdir(d)]


def find_resampler(name):
    for d in resampler_dirs():
        for root, _, files in os.walk(d):
            for f in files:
                stem, ext = os.path.splitext(f)
                if f == name or stem == name:
                    return os.path.join(root, f)
    raise WarbleError("resampler_missing", f"resampler '{name}' not found in {resampler_dirs() or ['./resamplers']}",
                      hint="put the executable (or a folder with it) into ./resamplers or $WARBLE_RESAMPLERS")


def command_for(exe):
    ext = os.path.splitext(exe)[1].lower()
    if ext in (".exe", ".bat"):
        if sys.platform.startswith("win"):
            return [exe]
        wine = shutil.which("wine") or shutil.which("wine64")
        if not wine:
            raise WarbleError("wine_missing", f"{exe} is a windows executable and wine is not installed", hint="install wine, or use a native build (e.g. straycat-rs)")
        return [wine, exe]
    if ext == ".py":
        return [sys.executable, exe]
    return [exe]


def external(item, exe, workdir):
    cmd = command_for(exe)
    os.makedirs(workdir, exist_ok=True)
    out = os.path.join(workdir, f"res-{item.key()}.wav")
    args = item.args(item.input_file, out)
    try:
        proc = subprocess.run(cmd + args, capture_output=True, timeout=120)
    except subprocess.TimeoutExpired:
        raise WarbleError("resampler_timeout", f"{exe} took over 120 s on alias '{item.phone['alias']}'")
    if not os.path.isfile(out) or os.path.getsize(out) <= 44:
        raise WarbleError(
            "resampler_failed",
            f"{os.path.basename(exe)} produced no audio for alias '{item.phone['alias']}' (note {item.phone.get('note_index')})",
            exit_code=proc.returncode,
            stderr=proc.stderr.decode(errors="replace")[-800:],
            args=args,
        )
    import soundfile as sf

    y, sr = sf.read(out, dtype="float32", always_2d=True)
    y = y[:, 0]
    if sr != SR:
        from math import gcd

        from scipy.signal import resample_poly

        g = gcd(sr, SR)
        y = resample_poly(y, SR // g, sr // g).astype(np.float32)
    return y, args
