"""one pass over a wav: every frame feature that metrics, artifacts and plots need."""

import hashlib
import os

import numpy as np

from . import f0 as f0mod
from . import features as fx

_CACHE = {}


class Analysis:
    pass


def analyze_audio(path, extractors=("harvest", "dio"), formant_times=None):
    st = os.stat(path)
    key = (os.path.abspath(path), st.st_mtime, st.st_size, tuple(extractors))
    if key in _CACHE:
        return _CACHE[key]
    raw, sr = fx.load(path)
    x = fx.mono(raw)
    a = Analysis()
    a.path = path
    a.raw = raw
    a.x = x
    a.sr = sr
    a.channels = raw.shape[1]
    a.duration_ms = len(x) * 1000.0 / sr
    pf = f0mod.extract(x, sr, extractors)
    a.t_ms = pf["t"] * 1000.0
    a.f0 = pf["f0"]
    a.midi = f0mod.to_midi(a.f0)
    a.f0_curves = pf["curves"]
    a.extractor_disagreements = pf["disagreements"]
    t_rms, rms = fx.frame_rms_db(x, sr)
    a.rms_db = np.interp(a.t_ms, t_rms * 1000, rms)
    # trackers hallucinate low pitches in near-silence; a frame must be audible to count as voiced
    a.f0 = np.where(a.rms_db > -55, a.f0, 0.0)
    a.midi = f0mod.to_midi(a.f0)
    a.voiced = a.f0 > 0
    a.sp, a.ap = fx.world_features(x, sr, a.f0, pf["t"])
    a.breath_db = fx.breathiness_from_ap(a.ap, sr)
    a.hnr_db = fx.hnr_from_ap(a.ap, sr)
    f, ts, sdb, mag = fx.stft_db(x, sr, n_fft=2048)
    a.spec_f, a.spec_t_ms, a.spec_db = f, ts * 1000, sdb
    cen = fx.spectral_centroid(mag, f)
    a.centroid = np.interp(a.t_ms, ts * 1000, cen)
    fb, mel_hz = fx.mel_filterbank(sr, 2048, 128, 40.0, min(16000.0, sr / 2))
    a.mel_db = 20 * np.log10(fb @ mag + 1e-9)
    a.mel_hz = mel_hz
    # spectral flux on log-mel, per stft frame
    d = np.diff(a.mel_db, axis=1)
    a.flux = np.concatenate([[0.0], np.sqrt(np.mean(np.maximum(d, 0) ** 2, axis=0))])
    a.lufs = fx.lufs(x, sr)
    a.st_t, a.st_lufs = fx.short_term_lufs(x, sr)
    a.hash = hashlib.sha1(f"{key}".encode()).hexdigest()[:12]
    _CACHE[key] = a
    return a


def frames_in(a, start_ms, end_ms):
    return (a.t_ms >= start_ms) & (a.t_ms < end_ms)
