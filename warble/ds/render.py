"""render one diffsinger phrase to audio.

ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Core/DiffSinger/DiffSingerRenderer.cs
(InvokeDiffsinger) and DiffSingerVariance.cs.
"""

import time

import numpy as np

from .. import onnxrun, pitchctl
from ..bank import ds as dsbank
from ..errors import WarbleError
from . import pitch as dspitch
from . import util, voices
from .models import DsModels
from .phonemizer import Phonemizer

DEFAULT_STEPS = 20
VARIANCE_STEPS = 20
VARIANCES = ("energy", "breathiness", "voicing", "tension")
# user offset -> model units, as DiffSingerUtils.VarianceDeltaFunctions; controls use openutau curve units
DELTA = {
    "energy": ("ene", 0.0, lambda x, y: x + y * 12 / 100, (-96, 0)),
    "breathiness": ("brec", 0.0, lambda x, y: x + y * 12 / 100, (-96, 0)),
    "voicing": ("voic", 100.0, lambda x, y: x + (y - 100) * 12 / 100, (-96, 0)),
    "tension": ("tenc", 0.0, lambda x, y: x + y / 20, (-10, 10)),
}


class DsEngine:
    """per-bank state kept warm between renders."""

    def __init__(self, bank, vocoder_dirs=None):
        self.bank = bank
        self.models = DsModels(bank)
        self.acoustic = self.models.get("acoustic")
        voc = dsbank.resolve_vocoder(bank.root, bank.config, vocoder_dirs)
        if voc["source"] == "missing":
            raise WarbleError("vocoder_missing", voc["error"], bank=bank.root)
        if voc.get("mismatches"):
            raise WarbleError("vocoder_mismatch", f"vocoder at {voc['dir']} does not match the acoustic model: {voc['mismatches']}")
        self.vocoder = voc
        self._phonemizers = {}

    def phonemizer(self, lang):
        if lang not in self._phonemizers:
            self._phonemizers[lang] = Phonemizer(self.bank, self.models, lang)
        return self._phonemizers[lang]

    def phonemize_phrase(self, words, tm, lang, voice_of, seed=None, **_):
        return self.phonemizer(lang).phonemize_phrase(words, tm, voice_of, seed=seed)

    def depth(self, depth=None):
        cfg = self.bank.config
        if not cfg.use_variable_depth:
            return 1.0
        md = cfg.max_depth
        if md <= 0:
            raise WarbleError("max_depth_unset", f"{self.bank.name}: variable depth is on but max_depth is unset or negative")
        return min(1.0 if depth is None else float(depth), md)

    def render_phrase(self, words, tm, lang, voice_of, steps=None, depth=None, seed=None, pitch_steps=None, timings=None, allow_unknown=False, **_):
        timings = timings if timings is not None else {}
        t0 = time.time()
        ph = self.phonemizer(lang)
        res = ph.phonemize_phrase(words, tm, voice_of, seed=seed)
        timings["phonemize"] = timings.get("phonemize", 0) + time.time() - t0
        if res["unknown"] and not allow_unknown:
            # unknown words were replaced by SP; rendering them silent is only done on request
            return {"phonemes": res, "error": "unknown_lyrics"}
        phones = res["phones"]
        notes = [n for w in words for n in w]
        ac = self.acoustic
        cfg = ac.cfg
        fm = ac.frame_ms
        segs = util.padded_segments(phones, fm)
        durations = util.padded_durations(segs, fm)
        T = int(sum(durations))
        start_ms = phones[0]["position_ms"] - util.HEAD_FRAMES * fm
        frame_t = start_ms + np.arange(T) * fm
        spans = dspitch.note_spans(notes, tm)
        nidx = util.frame_note_index(frame_t, spans)

        def ctl(name, default):
            return np.array([float(notes[i].controls.get(name, default)) for i in nidx], np.float64)

        def mixes_by_frame(s_ms, f_ms, n):
            t = s_ms + np.arange(n) * f_ms
            ix = util.frame_note_index(t, spans)
            return [voices.resolve(self.bank, voice_of(notes[i]), notes[i].tone) for i in ix]

        # pitch
        t0 = time.time()
        pmd = self.models.get("dspitch")
        if pmd is not None:
            expr_t = None
            if any("expr" in n.controls for n in notes):
                pt = start_ms + np.arange(T) * pmd.frame_ms
                pix = util.frame_note_index(pt, spans)
                expr_t = np.array([float(notes[i].controls.get("expr", 1.0)) for i in pix])
            midi_p, pfm, pstart = dspitch.model_pitch(pmd, phones, notes, tm, mixes_by_frame, expr_t, steps=pitch_steps or dspitch.PITCH_STEPS, seed=seed)
            midi = np.interp(frame_t, pstart + np.arange(len(midi_p)) * pfm, midi_p)
            pitch_source = "model"
        else:
            midi = dspitch.rule_pitch(notes, tm, start_ms, fm, T)
            pitch_source = "rule"
        base_midi = midi.copy()
        midi = pitchctl.apply_note_controls(midi, frame_t, notes, spans, tm)
        timings["pitch"] = timings.get("pitch", 0) + time.time() - t0
        f0 = util.tone_to_freq(midi).astype(np.float32)

        # acoustic inputs
        apath = ac.model_path("acoustic")
        names = set(onnxrun.input_names(apath))
        feeds = {
            "tokens": np.array([[ac.token(s[0]) for s in segs]], np.int64),
            "durations": np.array([durations], np.int64),
            "f0": f0[None, :],
        }
        feeds.update(util.sampling_feeds(cfg, int(steps or DEFAULT_STEPS), self.depth(depth), names))
        if cfg["use_lang_id"] or "languages" in names:
            feeds["languages"] = np.array([[ac.lang_id(phones[s[2]]["phoneme"]) if s[2] >= 0 else 0 for s in segs]], np.int64)
        if ac.speakers():
            feeds["spk_embed"] = ac.spk_embed(mixes_by_frame(start_ms, fm, T))
        warnings = []
        if cfg["use_key_shift_embed"] or "gender" in names:
            rng = cfg.key_shift_range()
            g = ctl("gender", 0.0)
            if rng:
                pos_scale = 0 if rng[1] == 0 else 12 / rng[1] / 100
                neg_scale = 0 if rng[0] == 0 else -12 / rng[0] / 100
                feeds["gender"] = np.where(g < 0, -g * pos_scale, -g * neg_scale).astype(np.float32)[None, :]
            else:
                if np.any(g != 0):
                    warnings.append("gender requested but dsconfig has no augmentation_args.random_pitch_shifting.range; fed 0")
                feeds["gender"] = np.zeros((1, T), np.float32)
        if cfg["use_speed_embed"] or "velocity" in names:
            feeds["velocity"] = np.power(2.0, (ctl("vel", 100.0) - 100.0) / 100.0).astype(np.float32)[None, :]
        need_var = [v for v in VARIANCES if cfg[f"use_{v}_embed"] or v in names]
        variance_curves = {}
        if need_var:
            t0 = time.time()
            vmd = self.models.get("dsvariance")
            if vmd is None:
                raise WarbleError(
                    "variance_model_missing",
                    f"{self.bank.name}'s acoustic model takes {need_var} but the bank has no dsvariance",
                    hint="this bank cannot render without its variance model",
                )
            pred = self._variance(vmd, phones, midi, start_ms, fm, mixes_by_frame, seed)
            for v in need_var:
                if v not in pred:
                    raise WarbleError("variance_output_missing", f"acoustic model needs '{v}' but the variance model does not predict it")
                key, default, fn, (lo, hi) = DELTA[v]
                user = ctl(key, default)
                curve = np.clip(fn(pred[v], user), lo, hi).astype(np.float32)
                feeds[v] = curve[None, :]
                variance_curves[v] = curve
            timings["variance"] = timings.get("variance", 0) + time.time() - t0

        t0 = time.time()
        mel = onnxrun.run(apath, feeds, "acoustic", seed=seed)
        mel = next(iter(mel.values())).astype(np.float32)
        mel = mel * np.float32(self.vocoder.get("mel_base_scale", 1.0))
        timings["acoustic"] = timings.get("acoustic", 0) + time.time() - t0
        t0 = time.time()
        wav = onnxrun.run(self.vocoder["model_path"], {"mel": mel, "f0": f0[None, :]}, "vocoder")
        wav = next(iter(wav.values())).reshape(-1).astype(np.float32)
        timings["vocoder"] = timings.get("vocoder", 0) + time.time() - t0
        return {
            "samples": wav,
            "sample_rate": int(self.vocoder["config"]["sample_rate"]),
            "start_ms": start_ms,
            "phonemes": res,
            "frame_ms": fm,
            "frame_times_ms": frame_t,
            "pitch_midi": midi,
            "base_pitch_midi": base_midi,
            "pitch_source": pitch_source,
            "variance": variance_curves,
            "warnings": warnings,
        }

    def _variance(self, vmd, phones, midi_ac, ac_start_ms, ac_fm, mixes_by_frame, seed):
        fm = vmd.frame_ms
        segs = util.padded_segments(phones, fm)
        ph_dur = util.padded_durations(segs, fm)
        T = int(sum(ph_dur))
        start_ms = phones[0]["position_ms"] - util.HEAD_FRAMES * fm
        d = vmd.dict()
        feeds = {"tokens": np.array([[vmd.token(s[0]) for s in segs]], np.int64)}
        if vmd.cfg["predict_dur"]:
            is_vowel = (lambda p: d.is_vowel(p)) if d else (lambda p: False)
            wdiv, wdur = util.padded_word_div_and_dur(segs, ph_dur, is_vowel)
            feeds["word_div"] = np.array([wdiv], np.int64)
            feeds["word_dur"] = np.array([wdur], np.int64)
        else:
            feeds["ph_dur"] = np.array([ph_dur], np.int64)
        if vmd.cfg["use_lang_id"]:
            feeds["languages"] = np.array([[vmd.lang_id(phones[s[2]]["phoneme"]) if s[2] >= 0 else 0 for s in segs]], np.int64)
        lin = onnxrun.run(vmd.model_path("linguistic"), feeds, "variance-linguistic")
        t = start_ms + np.arange(T) * fm
        pitch = np.interp(t, ac_start_ms + np.arange(len(midi_ac)) * ac_fm, midi_ac).astype(np.float32)
        vpath = vmd.model_path("variance")
        names = set(onnxrun.input_names(vpath))
        preds = [v for v in VARIANCES if vmd.cfg[f"predict_{v}"] or v in names]
        vf = {"encoder_out": lin["encoder_out"], "ph_dur": np.array([ph_dur], np.int64), "pitch": pitch[None, :]}
        for v in preds:
            vf[v] = np.zeros((1, T), np.float32)
        vf["retake"] = np.ones((1, T, len(preds)), bool)
        vf.update(util.sampling_feeds(vmd.cfg, VARIANCE_STEPS, 1.0, names - {"depth"}))
        if "depth" in names:
            vf["depth"] = np.float32(1.0) if vmd.cfg["use_continuous_acceleration"] else np.int64(1000)
        if vmd.speakers():
            vf["spk_embed"] = vmd.spk_embed(mixes_by_frame(start_ms, fm, T))
        out = onnxrun.run(vpath, vf, "variance", seed=seed)
        res = {}
        acT = len(midi_ac)
        for v in preds:
            arr = out.get(f"{v}_pred")
            if arr is None:
                continue
            res[v] = util.resample_padded_curve(arr.reshape(-1), acT, util.HEAD_FRAMES, util.TAIL_FRAMES, util.HEAD_FRAMES, util.TAIL_FRAMES, fm, ac_fm)
        return res
