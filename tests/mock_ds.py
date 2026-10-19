"""mock diffsinger banks built from tiny onnx graphs.

input/output names, dtypes and ranks match real diffsinger exports (checked against
adachi rei ds v111.1). outputs are simple deterministic functions of the inputs:
- durations come from the token embedding, so they vary per phoneme
- pitch follows the note grid, so a render's f0 should land on the notes
- the mel is a harmonic comb at f0, and the vocoder is a sine synth at f0 scaled by mel energy,
  so `inspect` can measure pitch on mock renders
"""

import json
import os

import numpy as np
import onnx
import yaml
from onnx import TensorProto, helper, numpy_helper

OPSET = 15
HIDDEN = 16


class G:
    """a tiny graph builder."""

    def __init__(self, name):
        self.name = name
        self.nodes, self.inputs, self.outputs, self.inits = [], [], [], []
        self.n = 0

    def inp(self, name, dtype, shape):
        self.inputs.append(helper.make_tensor_value_info(name, dtype, shape))
        return name

    def out(self, name, dtype, shape):
        self.outputs.append(helper.make_tensor_value_info(name, dtype, shape))

    def const(self, arr, name=None):
        self.n += 1
        name = name or f"c{self.n}"
        self.inits.append(numpy_helper.from_array(np.asarray(arr), name))
        return name

    def op(self, op_type, inputs, out=None, **attrs):
        self.n += 1
        out = out or f"t{self.n}"
        self.nodes.append(helper.make_node(op_type, inputs, [out], **attrs))
        return out

    def save(self, path):
        graph = helper.make_graph(self.nodes, self.name, self.inputs, self.outputs, self.inits)
        model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", OPSET)])
        model.ir_version = 8
        onnx.checker.check_model(model)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        onnx.save(model, path)


def _sink(g, names):
    """tie unused inputs into the graph with a zero-weight sum so onnxruntime keeps them."""
    terms = []
    for n, dtype in names:
        x = g.op("Cast", [n], to=TensorProto.FLOAT) if dtype != TensorProto.FLOAT else n
        terms.append(g.op("ReduceSum", [x], keepdims=0))
    if not terms:
        return g.const(np.float32(0))
    total = terms[0]
    for t in terms[1:]:
        total = g.op("Add", [total, t])
    return g.op("Mul", [total, g.const(np.float32(0))])


def _frames_from_counts(g, counts, values, total):
    """expand per-item values by per-item frame counts: values[1,M] float, counts[1,M] int64,
    total = scalar int64 frame count. returns [1,T] float."""
    cum = g.op("CumSum", [g.op("Squeeze", [counts, g.const(np.array([0], np.int64))]), g.const(np.int64(0))])  # [M]
    t = g.op("Range", [g.const(np.int64(0)), total, g.const(np.int64(1))])  # [T]
    ge = g.op("GreaterOrEqual", [g.op("Unsqueeze", [t, g.const(np.array([1], np.int64))]), g.op("Unsqueeze", [cum, g.const(np.array([0], np.int64))])])  # [T,M]
    idx = g.op("ReduceSum", [g.op("Cast", [ge], to=TensorProto.INT64), g.const(np.array([1], np.int64))], keepdims=0)  # [T]
    m = g.op("Shape", [values])
    mlast = g.op("Sub", [g.op("Gather", [m, g.const(np.int64(1))]), g.const(np.int64(1))])
    idx = g.op("Min", [idx, mlast])
    vals = g.op("Squeeze", [values, g.const(np.array([0], np.int64))])
    picked = g.op("Gather", [vals, idx])
    return g.op("Unsqueeze", [picked, g.const(np.array([0], np.int64))])


# ---- models ---------------------------------------------------------------------------

def linguistic(path, vocab, word_mode, use_lang):
    g = G("linguistic")
    tokens = g.inp("tokens", TensorProto.INT64, [1, "n_tokens"])
    sinks = []
    if use_lang:
        sinks.append((g.inp("languages", TensorProto.INT64, [1, "n_tokens"]), TensorProto.INT64))
    if word_mode:
        sinks.append((g.inp("word_div", TensorProto.INT64, [1, "n_words"]), TensorProto.INT64))
        sinks.append((g.inp("word_dur", TensorProto.INT64, [1, "n_words"]), TensorProto.INT64))
    else:
        sinks.append((g.inp("ph_dur", TensorProto.INT64, [1, "n_tokens"]), TensorProto.INT64))
    rng = np.random.default_rng(1)
    emb = rng.uniform(0.2, 1.0, size=(vocab, HIDDEN)).astype(np.float32)
    e = g.op("Gather", [g.const(emb), tokens])
    g.op("Add", [e, _sink(g, sinks)], out="encoder_out")
    g.op("Less", [tokens, g.const(np.int64(0))], out="x_masks")
    g.out("encoder_out", TensorProto.FLOAT, [1, "n_tokens", HIDDEN])
    g.out("x_masks", TensorProto.BOOL, [1, "n_tokens"])
    g.save(path)


def duration(path, rel, speakers):
    g = G("dur")
    enc = g.inp("encoder_out", TensorProto.FLOAT, [1, "n_tokens", HIDDEN])
    sinks = [(g.inp("x_masks", TensorProto.BOOL, [1, "n_tokens"]), TensorProto.BOOL), (g.inp("ph_midi", TensorProto.INT64, [1, "n_tokens"]), TensorProto.INT64)]
    if rel:
        sinks.append((g.inp("word_div", TensorProto.INT64, [1, "n_words"]), TensorProto.INT64))
        sinks.append((g.inp("word_dur", TensorProto.INT64, [1, "n_words"]), TensorProto.INT64))
    if speakers:
        sinks.append((g.inp("spk_embed", TensorProto.FLOAT, [1, "n_tokens", HIDDEN]), TensorProto.FLOAT))
    s = g.op("ReduceMean", [enc], axes=[2], keepdims=0)  # 0.2..1.0
    d = g.op("Add", [g.op("Mul", [s, g.const(np.float32(12))]), g.const(np.float32(2))])  # ~4..14 frames
    g.op("Add", [d, _sink(g, sinks)], out="ph_dur_pred")
    g.out("ph_dur_pred", TensorProto.FLOAT, [1, "n_tokens"])
    g.save(path)


def sampling(g, cfg):
    names = []
    if cfg.get("use_continuous_acceleration"):
        names.append((g.inp("steps", TensorProto.INT64, []), TensorProto.INT64))
        if cfg.get("use_variable_depth"):
            names.append((g.inp("depth", TensorProto.FLOAT, []), TensorProto.FLOAT))
    else:
        names.append((g.inp("speedup", TensorProto.INT64, []), TensorProto.INT64))
        if cfg.get("use_shallow_diffusion") or cfg.get("use_variable_depth"):
            names.append((g.inp("depth", TensorProto.INT64, []), TensorProto.INT64))
    return names


def pitch(path, cfg, speakers):
    g = G("pitch")
    sinks = [(g.inp("encoder_out", TensorProto.FLOAT, [1, "n_tokens", HIDDEN]), TensorProto.FLOAT), (g.inp("ph_dur", TensorProto.INT64, [1, "n_tokens"]), TensorProto.INT64)]
    note_midi = g.inp("note_midi", TensorProto.FLOAT, [1, "n_notes"])
    if cfg.get("use_note_rest"):
        sinks.append((g.inp("note_rest", TensorProto.BOOL, [1, "n_notes"]), TensorProto.BOOL))
    note_dur = g.inp("note_dur", TensorProto.INT64, [1, "n_notes"])
    pitch_in = g.inp("pitch", TensorProto.FLOAT, [1, "n_frames"])
    if cfg.get("use_expr"):
        sinks.append((g.inp("expr", TensorProto.FLOAT, [1, "n_frames"]), TensorProto.FLOAT))
    sinks.append((g.inp("retake", TensorProto.BOOL, [1, "n_frames"]), TensorProto.BOOL))
    if speakers:
        sinks.append((g.inp("spk_embed", TensorProto.FLOAT, [1, "n_frames", HIDDEN]), TensorProto.FLOAT))
    sinks += sampling(g, cfg)
    total = g.op("Gather", [g.op("Shape", [pitch_in]), g.const(np.int64(1))])
    grid = _frames_from_counts(g, note_dur, note_midi, total)
    g.op("Add", [grid, _sink(g, sinks)], out="pitch_pred")
    g.out("pitch_pred", TensorProto.FLOAT, [1, "n_frames"])
    g.save(path)


def variance(path, cfg, speakers):
    g = G("variance")
    sinks = [(g.inp("encoder_out", TensorProto.FLOAT, [1, "n_tokens", HIDDEN]), TensorProto.FLOAT), (g.inp("ph_dur", TensorProto.INT64, [1, "n_tokens"]), TensorProto.INT64)]
    p = g.inp("pitch", TensorProto.FLOAT, [1, "n_frames"])
    preds = [v for v in ("energy", "breathiness", "voicing", "tension") if cfg.get(f"predict_{v}")]
    for v in preds:
        sinks.append((g.inp(v, TensorProto.FLOAT, [1, "n_frames"]), TensorProto.FLOAT))
    sinks.append((g.inp("retake", TensorProto.BOOL, [1, "n_frames", len(preds)]), TensorProto.BOOL))
    if speakers:
        sinks.append((g.inp("spk_embed", TensorProto.FLOAT, [1, "n_frames", HIDDEN]), TensorProto.FLOAT))
    sinks += sampling(g, cfg)
    zero = g.op("Mul", [p, g.const(np.float32(0))])
    base = g.op("Add", [zero, _sink(g, sinks)])
    levels = {"energy": -20.0, "breathiness": -60.0, "voicing": -10.0, "tension": 0.0}
    for v in preds:
        g.op("Add", [base, g.const(np.float32(levels[v]))], out=f"{v}_pred")
        g.out(f"{v}_pred", TensorProto.FLOAT, [1, "n_frames"])
    g.save(path)


def _mel_centers(cfg):
    """center frequency of each mel bin (slaney-ish via htk formula, close enough for a mock)."""
    lo, hi, n = cfg["mel_fmin"], cfg["mel_fmax"], cfg["num_mel_bins"]
    m = np.linspace(2595 * np.log10(1 + lo / 700), 2595 * np.log10(1 + hi / 700), n)
    return (700 * (10 ** (m / 2595) - 1)).astype(np.float32)


def acoustic(path, cfg, silent_ids=(0, 1, 2)):
    """mel[t,k] = log-ish comb of harmonics of f0 (in the bank's mel_base), silent on SP/AP/PAD
    frames like a real acoustic model."""
    g = G("acoustic")
    tokens = g.inp("tokens", TensorProto.INT64, [1, "n_tokens"])
    sinks = []
    if cfg.get("use_lang_id"):
        sinks.append((g.inp("languages", TensorProto.INT64, [1, "n_tokens"]), TensorProto.INT64))
    durations = g.inp("durations", TensorProto.INT64, [1, "n_tokens"])
    f0 = g.inp("f0", TensorProto.FLOAT, [1, "n_frames"])
    for flag, name in (("use_key_shift_embed", "gender"), ("use_speed_embed", "velocity"), ("use_energy_embed", "energy"), ("use_breathiness_embed", "breathiness"), ("use_voicing_embed", "voicing"), ("use_tension_embed", "tension")):
        if cfg.get(flag):
            sinks.append((g.inp(name, TensorProto.FLOAT, [1, "n_frames"]), TensorProto.FLOAT))
    if cfg.get("speakers"):
        sinks.append((g.inp("spk_embed", TensorProto.FLOAT, [1, "n_frames", HIDDEN]), TensorProto.FLOAT))
    sinks += sampling(g, cfg)
    centers = np.log(_mel_centers(cfg)).reshape(1, 1, -1, 1)
    harm = np.log(np.arange(1, 13, dtype=np.float32)).reshape(1, 1, 1, -1)
    lf0 = g.op("Log", [g.op("Max", [f0, g.const(np.float32(1.0))])])
    lf0 = g.op("Unsqueeze", [lf0, g.const(np.array([2, 3], np.int64))])  # [1,T,1,1]
    diff = g.op("Sub", [g.op("Add", [lf0, g.const(harm)]), g.const(centers)])  # [1,T,K,H]
    bump = g.op("Exp", [g.op("Mul", [g.op("Mul", [diff, diff]), g.const(np.float32(-200.0))])])
    amp = np.float32(1.0) / np.arange(1, 13, dtype=np.float32).reshape(1, 1, 1, -1)
    comb = g.op("ReduceSum", [g.op("Mul", [bump, g.const(amp)]), g.const(np.array([3], np.int64))], keepdims=0)  # [1,T,K]
    # per-frame gate: 0 on SP/AP/PAD tokens, 1 on phonemes
    sounding = g.op("Cast", [tokens], to=TensorProto.FLOAT)
    for sid in silent_ids:
        sounding = g.op("Mul", [sounding, g.op("Cast", [g.op("Not", [g.op("Equal", [tokens, g.const(np.int64(sid))])])], to=TensorProto.FLOAT)])
    gate_tok = g.op("Min", [sounding, g.const(np.float32(1.0))])
    total = g.op("Gather", [g.op("Shape", [f0]), g.const(np.int64(1))])
    gate = _frames_from_counts(g, durations, gate_tok, total)  # [1,T]
    comb = g.op("Mul", [comb, g.op("Unsqueeze", [gate, g.const(np.array([2], np.int64))])])
    ln = g.op("Log", [g.op("Add", [comb, g.const(np.float32(1e-3))])])
    if str(cfg.get("mel_base", "10")) == "10":
        ln = g.op("Mul", [ln, g.const(np.float32(0.434294))])
    g.op("Add", [ln, _sink(g, sinks)], out="mel")
    g.out("mel", TensorProto.FLOAT, [1, "n_frames", cfg["num_mel_bins"]])
    g.save(path)


def vocoder(path, cfg):
    """waveform = harmonic sines at f0, amplitude from mean mel energy, silent where f0 <= 0."""
    g = G("vocoder")
    mel = g.inp("mel", TensorProto.FLOAT, [1, "n_frames", cfg["num_mel_bins"]])
    f0 = g.inp("f0", TensorProto.FLOAT, [1, "n_frames"])
    hop, sr = cfg["hop_size"], cfg["sample_rate"]
    shape = g.op("Concat", [g.const(np.array([1], np.int64)), g.op("Mul", [g.op("Gather", [g.op("Shape", [f0]), g.const(np.array([1], np.int64))]), g.const(np.array([hop], np.int64))])], axis=0)

    def upsample(x):  # [1,T] -> [1,T*hop]
        x3 = g.op("Unsqueeze", [x, g.const(np.array([2], np.int64))])
        x3 = g.op("Expand", [x3, g.const(np.array([1, 1, hop], np.int64))])
        return g.op("Reshape", [x3, shape])

    f0s = upsample(f0)
    phase = g.op("CumSum", [g.op("Mul", [f0s, g.const(np.float32(2 * np.pi / sr))]), g.const(np.int64(1))])
    s1 = g.op("Sin", [phase])
    s2 = g.op("Mul", [g.op("Sin", [g.op("Mul", [phase, g.const(np.float32(2))])]), g.const(np.float32(0.5))])
    s3 = g.op("Mul", [g.op("Sin", [g.op("Mul", [phase, g.const(np.float32(3))])]), g.const(np.float32(0.25))])
    wave = g.op("Add", [g.op("Add", [s1, s2]), s3])
    energy = g.op("ReduceMax", [mel], axes=[2], keepdims=0)  # [1,T]
    base = np.float32(np.e if str(cfg.get("mel_base", "10")) == "e" else 10.0)
    amp = g.op("Pow", [g.const(base), energy])  # back to linear comb height (~0..1.2)
    amp = g.op("Min", [g.op("Mul", [amp, g.const(np.float32(0.25))]), g.const(np.float32(0.3))])
    voiced = g.op("Cast", [g.op("Greater", [f0, g.const(np.float32(1.0))])], to=TensorProto.FLOAT)
    amp = g.op("Mul", [amp, voiced])
    # linear interpolation between frames so level changes ramp instead of stepping (no clicks)
    amp3 = g.op("Unsqueeze", [amp, g.const(np.array([1], np.int64))])  # [1,1,T]
    amp3 = g.op("Resize", [amp3, "", g.const(np.array([1.0, 1.0, float(hop)], np.float32))], mode="linear",
                coordinate_transformation_mode="half_pixel")
    amp = g.op("Reshape", [amp3, shape])
    g.op("Mul", [wave, amp], out="waveform")
    g.out("waveform", TensorProto.FLOAT, [1, "n_samples"])
    g.save(path)


# ---- banks ----------------------------------------------------------------------------

JA = {
    "vowels": ["a", "i", "u", "e", "o", "N"],
    "consonants": ["k", "s", "t", "n", "h", "m", "r", "g"],
    "glides": ["y", "w"],
}
KANA = {
    "あ": ["a"], "い": ["i"], "う": ["u"], "え": ["e"], "お": ["o"], "ん": ["N"],
    "か": ["k", "a"], "き": ["k", "i"], "く": ["k", "u"], "け": ["k", "e"], "こ": ["k", "o"],
    "さ": ["s", "a"], "し": ["s", "i"], "す": ["s", "u"], "た": ["t", "a"], "な": ["n", "a"],
    "ら": ["r", "a"], "り": ["r", "i"], "る": ["r", "u"], "れ": ["r", "e"], "ろ": ["r", "o"],
    "ま": ["m", "a"], "が": ["g", "a"], "や": ["y", "a"], "わ": ["w", "a"],
}
EN = {
    "vowels": ["aa", "iy", "uw", "eh"],
    "consonants": ["l", "v", "d", "k"],
    "glides": ["w"],
    "words": {"love": ["l", "aa", "v"], "day": ["d", "eh", "iy"], "key": ["k", "iy"], "we": ["w", "iy"]},
}


def _symbols(lang_spec, prefix=""):
    syms = []
    for v in lang_spec["vowels"]:
        syms.append({"symbol": prefix + v, "type": "vowel"})
    for c in lang_spec["consonants"]:
        syms.append({"symbol": prefix + c, "type": "consonant"})
    for gl in lang_spec["glides"]:
        syms.append({"symbol": prefix + gl, "type": "semivowel"})
    return syms


def _write_yaml(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def _phoneme_list(multilang):
    base = ["<PAD>", "AP", "SP"]
    if multilang:
        return base + [f"ja/{s['symbol']}" for s in _symbols(JA)] + [f"en/{s['symbol']}" for s in _symbols(EN)]
    return base + [s["symbol"] for s in _symbols(JA)]


def _write_phonemes(folder, phonemes, fmt):
    os.makedirs(folder, exist_ok=True)
    if fmt == "json":
        path = os.path.join(folder, "phonemes.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({p: i for i, p in enumerate(phonemes)}, f, ensure_ascii=False)
        return "phonemes.json"
    path = os.path.join(folder, "phonemes.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join("" if p == "<PAD>" else p for p in phonemes) + "\n")
    return "phonemes.txt"


def _write_dicts(folder, multilang):
    if multilang:
        ja_entries = [{"grapheme": k, "phonemes": [f"ja/{p}" for p in v]} for k, v in KANA.items()]
        en_entries = [{"grapheme": k, "phonemes": [f"en/{p}" for p in v]} for k, v in EN["words"].items()]
        allsyms = _symbols(JA, "ja/") + _symbols(EN, "en/")
        _write_yaml(os.path.join(folder, "dsdict-ja.yaml"), {"symbols": allsyms, "entries": ja_entries})
        _write_yaml(os.path.join(folder, "dsdict-en.yaml"), {"symbols": allsyms, "entries": en_entries})
        _write_yaml(os.path.join(folder, "dsdict.yaml"), {"symbols": allsyms, "entries": ja_entries})
    else:
        entries = [{"grapheme": k, "phonemes": v} for k, v in KANA.items()]
        _write_yaml(os.path.join(folder, "dsdict.yaml"), {"symbols": _symbols(JA), "entries": entries})


def _write_speakers(folder, names):
    rng = np.random.default_rng(7)
    for n in names:
        p = os.path.join(folder, n + ".emb")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        rng.normal(0, 1, HIDDEN).astype("<f4").tofile(p)


def build_ds_bank(root, *, name, multilang=False, phonemes_fmt="json", dsdur=True, dur_rel=False, dspitch=True,
                  dsvariance=True, speakers=None, continuous=True, variable_depth=True, vocoder_mode="bundled",
                  vocoder_dirs_root=None, voc_mel_base=None, acoustic_variance=("energy", "breathiness")):
    """write one mock bank. returns its path."""
    os.makedirs(root, exist_ok=True)
    phonemes = _phoneme_list(multilang)
    base_cfg = {
        "sample_rate": 44100, "hop_size": 512, "win_size": 2048, "fft_size": 2048, "num_mel_bins": 128,
        "mel_fmin": 40, "mel_fmax": 16000, "mel_base": "e" if continuous else "10", "mel_scale": "slaney",
    }
    sampling_cfg = {"use_continuous_acceleration": continuous}
    if variable_depth:
        sampling_cfg["use_variable_depth" if continuous else "use_shallow_diffusion"] = True
        sampling_cfg["max_depth"] = 0.6 if continuous else 600
    lang_cfg = {}
    if multilang:
        lang_cfg = {"use_lang_id": True, "languages": "languages.json"}
    spk_cfg = {"speakers": speakers, "hidden_size": HIDDEN} if speakers else {}

    def write_common(folder):
        pf = _write_phonemes(folder, phonemes, phonemes_fmt)
        if multilang:
            with open(os.path.join(folder, "languages.json"), "w") as f:
                json.dump({"ja": 1, "en": 2}, f)
        if speakers:
            _write_speakers(folder, speakers)
        return pf

    # acoustic
    pf = write_common(root)
    cfg = {"phonemes": pf, "acoustic": "acoustic.onnx", **lang_cfg, **spk_cfg, **base_cfg, **sampling_cfg,
           "use_key_shift_embed": True, "use_speed_embed": True,
           "augmentation_args": {"random_pitch_shifting": {"range": [-5.0, 5.0]}}}
    for v in acoustic_variance:
        cfg[f"use_{v}_embed"] = True
    if vocoder_mode == "named":
        cfg["vocoder"] = "mock_vocoder"
    _write_yaml(os.path.join(root, "dsconfig.yaml"), cfg)
    acoustic(os.path.join(root, "acoustic.onnx"), cfg)
    _write_dicts(root, multilang)

    char = {"name": name, "singer_type": "diffsinger", "text_file_encoding": "utf-8", "default_phonemizer": "OpenUtau.Plugin.Builtin.DiffSingerPhonemizer"}
    if speakers:
        char["subbanks"] = [{"color": s, "suffix": s} for s in speakers]
    _write_yaml(os.path.join(root, "character.yaml"), char)
    with open(os.path.join(root, "readme.txt"), "w") as f:
        f.write("mock bank for warble tests. not a real voice.\n")

    sub_common = {**lang_cfg, **spk_cfg, "hop_size": 512, "sample_rate": 44100}
    if dsdur:
        d = os.path.join(root, "dsdur")
        pf = write_common(d)
        dcfg = {"phonemes": pf, "linguistic": "linguistic.onnx", "dur": "dur.onnx", "predict_dur": True, **sub_common}
        if dur_rel:
            dcfg["dur_type"] = "rel"
        _write_yaml(os.path.join(d, "dsconfig.yaml"), dcfg)
        linguistic(os.path.join(d, "linguistic.onnx"), len(phonemes), True, multilang)
        duration(os.path.join(d, "dur.onnx"), dur_rel, bool(speakers))
        _write_dicts(d, multilang)
    if dspitch:
        d = os.path.join(root, "dspitch")
        pf = write_common(d)
        pcfg = {"phonemes": pf, "linguistic": "linguistic.onnx", "pitch": "pitch.onnx", "predict_dur": False,
                "use_expr": True, "use_note_rest": True, **sub_common, **sampling_cfg}
        _write_yaml(os.path.join(d, "dsconfig.yaml"), pcfg)
        linguistic(os.path.join(d, "linguistic.onnx"), len(phonemes), False, multilang)
        pitch(os.path.join(d, "pitch.onnx"), pcfg, bool(speakers))
        _write_dicts(d, multilang)
    if dsvariance:
        d = os.path.join(root, "dsvariance")
        pf = write_common(d)
        vcfg = {"phonemes": pf, "linguistic": "linguistic.onnx", "variance": "variance.onnx", "predict_dur": False,
                "predict_energy": True, "predict_breathiness": True, **sub_common, **sampling_cfg}
        _write_yaml(os.path.join(d, "dsconfig.yaml"), vcfg)
        linguistic(os.path.join(d, "linguistic.onnx"), len(phonemes), False, multilang)
        variance(os.path.join(d, "variance.onnx"), vcfg, bool(speakers))

    vcfg = dict(base_cfg)
    if voc_mel_base:
        vcfg["mel_base"] = voc_mel_base
    vcfg.update({"name": "mock_vocoder", "model": "mock_vocoder.onnx", "pitch_controllable": True})
    if vocoder_mode == "bundled":
        vdir = os.path.join(root, "dsvocoder")
    else:
        vdir = os.path.join(vocoder_dirs_root, "mock_vocoder")
    _write_yaml(os.path.join(vdir, "vocoder.yaml"), vcfg)
    vocoder(os.path.join(vdir, "mock_vocoder.onnx"), vcfg)
    return root


DS_VARIANTS = {
    # everything on, multilingual json phonemes, continuous acceleration, two speakers, bundled vocoder
    "ds_full": dict(multilang=True, phonemes_fmt="json", speakers=["files/alto", "files/soprano"]),
    # bare acoustic model only, txt phonemes, speedup sampling with shallow diffusion, named vocoder
    # whose mel_base differs (exercises the 2.30259 / 0.434294 scaling)
    "ds_minimal": dict(phonemes_fmt="txt", dsdur=False, dspitch=False, dsvariance=False, continuous=False,
                       vocoder_mode="named", voc_mel_base="e", acoustic_variance=()),
    # rel duration model, pitch but no variance, speedup without variable depth
    "ds_rel": dict(phonemes_fmt="txt", dur_rel=True, dsvariance=False, continuous=False, variable_depth=False,
                   acoustic_variance=()),
}


def build_all(base):
    out = {}
    vocs = os.path.join(base, "vocoders")
    for name, kw in DS_VARIANTS.items():
        out[name] = build_ds_bank(os.path.join(base, "banks", name), name=name, vocoder_dirs_root=vocs, **kw)
    return out


if __name__ == "__main__":
    import sys

    print(json.dumps(build_all(sys.argv[1] if len(sys.argv) > 1 else "tests/fixtures"), indent=2))
