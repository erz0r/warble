"""diffsinger bank loading and inspection.

ported from openutau (MIT, Copyright (c) 2014 StAkira):
OpenUtau.Core/DiffSinger/DiffSingerConfig.cs, DiffSingerSinger.cs, DiffSingerUtils.cs,
DiffSingerVocoder.cs, DiffSingerSpeakerEmbedManager.cs.
"""

import json
import os

from .. import onnxinfo
from .common import camel_to_snake, load_character_yaml, load_yaml

# defaults from DiffSingerConfig.cs, with yamldotnet's underscored key names
DSCONFIG_DEFAULTS = {
    "phonemes": "phonemes.txt",
    "languages": None,
    "acoustic": None,
    "vocoder": None,
    "speakers": None,
    "hidden_size": 256,
    "use_key_shift_embed": False,
    "use_speed_embed": False,
    "use_energy_embed": False,
    "use_breathiness_embed": False,
    "use_voicing_embed": False,
    "use_tension_embed": False,
    "augmentation_args": None,
    "use_continuous_acceleration": False,
    "use_lang_id": False,
    "use_shallow_diffusion": None,
    "use_variable_depth": None,
    "max_depth": 0.0,
    "dur": None,
    "dur_type": None,
    "linguistic": None,
    "pitch": None,
    "variance": None,
    "predict_dur": True,
    "predict_energy": True,
    "predict_breathiness": True,
    "predict_voicing": False,
    "predict_tension": False,
    "use_expr": False,
    "use_note_rest": False,
    "sample_rate": 44100,
    "hop_size": 512,
    "win_size": 2048,
    "fft_size": 2048,
    "num_mel_bins": 128,
    "mel_fmin": 40.0,
    "mel_fmax": 16000.0,
    "mel_base": "10",
    "mel_scale": "slaney",
}

VOCODER_DEFAULTS = {
    "name": "vocoder",
    "model": "model.onnx",
    "sample_rate": 44100,
    "hop_size": 512,
    "win_size": 2048,
    "fft_size": 2048,
    "num_mel_bins": 128,
    "mel_fmin": 40.0,
    "mel_fmax": 16000.0,
    "mel_base": "10",
    "mel_scale": "slaney",
    "pitch_controllable": False,
}

# these must agree between the acoustic model and the vocoder; mel_base may differ
VOCODER_MATCH_KEYS = ["sample_rate", "hop_size", "win_size", "fft_size", "num_mel_bins", "mel_fmin", "mel_fmax", "mel_scale"]

SUBMODELS = ["dsdur", "dspitch", "dsvariance"]
MAX_MEL_BINS = 255


class DsConfig(dict):
    """a dsconfig.yaml with openutau's defaults filled in. `explicit` holds the keys the file set."""

    def __init__(self, path, raw):
        super().__init__(DSCONFIG_DEFAULTS)
        self.path = path
        self.dir = os.path.dirname(path)
        self.explicit = {}
        self.unknown = {}
        for k, v in (raw or {}).items():
            key = camel_to_snake(k)
            if key in DSCONFIG_DEFAULTS:
                self[key] = v
                self.explicit[key] = v
            else:
                self.unknown[k] = v

    @property
    def frame_ms(self):
        return 1000.0 * self["hop_size"] / self["sample_rate"]

    @property
    def use_variable_depth(self):
        if self["use_variable_depth"] is not None:
            return bool(self["use_variable_depth"])
        if self["use_shallow_diffusion"] is not None:
            return bool(self["use_shallow_diffusion"])
        return False

    @property
    def max_depth(self):
        md = float(self["max_depth"] or 0)
        return md if self["use_continuous_acceleration"] else md / 1000.0

    def file(self, key):
        val = self.get(key)
        return os.path.join(self.dir, val) if val else None

    def key_shift_range(self):
        aa = self.get("augmentation_args") or {}
        aa = {camel_to_snake(k): v for k, v in aa.items()} if isinstance(aa, dict) else {}
        rps = aa.get("random_pitch_shifting") or {}
        rps = {camel_to_snake(k): v for k, v in rps.items()} if isinstance(rps, dict) else {}
        rng = rps.get("range")
        return list(rng) if rng else None


def load_dsconfig(path):
    return DsConfig(path, load_yaml(path))


def load_phonemes(path):
    """phonemes.txt maps line index to token; phonemes.json maps name to id."""
    if path.lower().endswith(".json"):
        with open(path, encoding="utf-8-sig") as f:
            return {str(k): int(v) for k, v in json.load(f).items()}, "json"
    with open(path, encoding="utf-8-sig") as f:
        lines = f.read().splitlines()
    table = {}
    for i, line in enumerate(lines):
        table[line] = i  # later duplicates win, as in openutau's dictionary assignment
    return table, "txt"


def load_languages(path):
    with open(path, encoding="utf-8-sig") as f:
        return {str(k): int(v) for k, v in json.load(f).items()}


def phoneme_language(ph):
    return ph.split("/", 1)[0] if "/" in ph else ""


class DsDict:
    """a dsdict yaml: symbols with types, entries grapheme -> phonemes."""

    def __init__(self, path):
        self.path = path
        data = load_yaml(path) or {}
        self.symbols = {}
        for s in data.get("symbols") or []:
            if isinstance(s, dict) and "symbol" in s:
                self.symbols[str(s["symbol"])] = str(s.get("type") or "")
        self.entries = {}
        self.dropped = []  # (grapheme, phoneme) pairs openutau would silently drop
        for e in data.get("entries") or []:
            if not isinstance(e, dict) or "grapheme" not in e:
                continue
            g = str(e["grapheme"])
            phs = [str(p) for p in (e.get("phonemes") or [])]
            for p in phs:
                if p not in self.symbols:
                    self.dropped.append((g, p))
            self.entries[g] = phs
        self.other_keys = sorted(k for k in data if k not in ("symbols", "entries"))
        # SP and AP are always vowels (DiffSingerBasePhonemizer.LoadG2p)
        self.symbols.setdefault("SP", "vowel")
        self.symbols.setdefault("AP", "vowel")

    def is_vowel(self, sym):
        return self.symbols.get(sym) == "vowel"

    def is_glide(self, sym):
        return self.symbols.get(sym) in ("semivowel", "liquid")


def find_dicts(folder):
    out = []
    if not os.path.isdir(folder):
        return out
    for fn in sorted(os.listdir(folder)):
        if fn.startswith("dsdict") and fn.endswith((".yaml", ".yml")):
            out.append(os.path.join(folder, fn))
    return out


def dict_language(path):
    stem = os.path.splitext(os.path.basename(path))[0]
    return stem.split("-", 1)[1] if "-" in stem else ""


def choose_dict(folder, lang):
    """dsdict-<lang>.yaml for the chosen language, else dsdict.yaml (DiffSingerBasePhonemizer.LoadG2p)."""
    names = ([f"dsdict-{lang}.yaml"] if lang else []) + ["dsdict.yaml"]
    for n in names:
        p = os.path.join(folder, n)
        if os.path.isfile(p):
            return p
    return None


def read_speaker_embed(path, hidden_size):
    import numpy as np

    data = np.fromfile(path, dtype="<f4")
    return data[:hidden_size], len(data)


# ---- vocoder resolution ----------------------------------------------------------------

def vocoder_search_dirs(bank_root, extra=None):
    dirs = []
    for d in extra or []:
        dirs.append(os.path.abspath(d))
    env = os.environ.get("WARBLE_VOCODERS")
    if env:
        dirs.extend(os.path.abspath(p) for p in env.split(os.pathsep) if p)
    dirs.append(os.path.abspath("vocoders"))
    parent = os.path.dirname(os.path.abspath(bank_root))
    dirs.append(os.path.join(parent, "vocoders"))
    dirs.append(os.path.join(os.path.dirname(parent), "vocoders"))
    seen, out = set(), []
    for d in dirs:
        if d not in seen and os.path.isdir(d):
            seen.add(d)
            out.append(d)
    return out


def load_vocoder_config(folder):
    path = os.path.join(folder, "vocoder.yaml")
    raw = load_yaml(path) or {}
    cfg = dict(VOCODER_DEFAULTS)
    for k, v in raw.items():
        cfg[camel_to_snake(k)] = v
    cfg["_dir"] = folder
    cfg["_model_path"] = os.path.join(folder, cfg["model"])
    return cfg


def installed_vocoders(dirs):
    out = []
    for d in dirs:
        for name in sorted(os.listdir(d)):
            folder = os.path.join(d, name)
            if os.path.isfile(os.path.join(folder, "vocoder.yaml")):
                out.append((name, folder))
    return out


def vocoder_mismatches(acoustic_cfg, voc_cfg):
    bad = []
    for k in VOCODER_MATCH_KEYS:
        a, v = acoustic_cfg.get(k), voc_cfg.get(k)
        if isinstance(a, (int, float)) and isinstance(v, (int, float)):
            if abs(float(a) - float(v)) > 1e-6:
                bad.append({"key": k, "acoustic": a, "vocoder": v})
        elif str(a).lower() != str(v).lower():
            bad.append({"key": k, "acoustic": a, "vocoder": v})
    return bad


def mel_base_scale(acoustic_cfg, voc_cfg):
    """factor to multiply the acoustic mel by so the vocoder reads it in its own log base."""
    a, v = str(acoustic_cfg.get("mel_base", "10")), str(voc_cfg.get("mel_base", "10"))
    if a == v:
        return 1.0
    if a == "10" and v == "e":
        return 2.30259
    if a == "e" and v == "10":
        return 0.434294
    raise ValueError(f"unknown mel_base pair acoustic={a} vocoder={v}")


def resolve_vocoder(bank_root, cfg, extra_dirs=None):
    """openutau order: bundled dsvocoder/, then the dsconfig 'vocoder' name in installed vocoders.
    when the named one is missing, openutau falls back to pc-nsf-hifigan; we instead offer any
    installed vocoder whose mel parameters match, and say so."""
    bundled = os.path.join(bank_root, "dsvocoder")
    dirs = vocoder_search_dirs(bank_root, extra_dirs)
    result = {"search_dirs": dirs}
    if os.path.isfile(os.path.join(bundled, "vocoder.yaml")):
        result.update(source="bundled", dir=bundled)
    elif cfg.get("vocoder"):
        name = str(cfg["vocoder"])
        result["named"] = name
        for d in dirs:
            folder = os.path.join(d, name)
            if os.path.isfile(os.path.join(folder, "vocoder.yaml")):
                result.update(source="named", dir=folder)
                break
    if "dir" not in result:
        candidates = []
        for name, folder in installed_vocoders(dirs):
            try:
                vc = load_vocoder_config(folder)
            except Exception:  # noqa: BLE001
                continue
            if not vocoder_mismatches(cfg, vc):
                candidates.append({"name": name, "dir": folder})
        result["source"] = "missing"
        result["compatible_installed"] = candidates
        want = f"the vocoder named '{cfg['vocoder']}'" if cfg.get("vocoder") else "a vocoder (dsconfig names none and there is no dsvocoder/)"
        result["error"] = (
            f"{want} is not installed. put a folder with vocoder.yaml + onnx into one of "
            f"{dirs or ['./vocoders']}. openvpi's pc_nsf_hifigan "
            f"(https://github.com/openvpi/vocoders/releases) is the usual fallback; it must match "
            f"sample_rate={cfg['sample_rate']} hop_size={cfg['hop_size']} num_mel_bins={cfg['num_mel_bins']}."
        )
        if candidates:
            result["error"] += f" compatible installed vocoders that could stand in: {[c['name'] for c in candidates]}"
        return result
    vc = load_vocoder_config(result["dir"])
    result["config"] = {k: v for k, v in vc.items() if not k.startswith("_")}
    result["model_path"] = vc["_model_path"]
    result["model_exists"] = os.path.isfile(vc["_model_path"])
    result["mismatches"] = vocoder_mismatches(cfg, vc)
    try:
        result["mel_base_scale"] = mel_base_scale(cfg, vc)
    except ValueError as e:
        result["mismatches"].append({"key": "mel_base", "error": str(e)})
    if not (1 <= int(vc["num_mel_bins"]) <= MAX_MEL_BINS):
        result["mismatches"].append({"key": "num_mel_bins", "error": f"must be 1..{MAX_MEL_BINS}"})
    return result


# ---- the bank --------------------------------------------------------------------------

class DsBank:
    def __init__(self, root):
        self.root = os.path.abspath(root)
        self.character_yaml_path, self.character = load_character_yaml(self.root)
        self.character = self.character or {}
        self.config = load_dsconfig(os.path.join(self.root, "dsconfig.yaml"))
        self.submodels = {}
        for sub in SUBMODELS:
            p = os.path.join(self.root, sub, "dsconfig.yaml")
            if os.path.isfile(p):
                self.submodels[sub] = load_dsconfig(p)

    @property
    def name(self):
        return self.character.get("name") or os.path.basename(self.root)

    def subbanks(self):
        return self.character.get("subbanks") or []

    def all_configs(self):
        yield "acoustic", self.config
        for sub, cfg in self.submodels.items():
            yield sub, cfg
