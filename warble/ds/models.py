"""one diffsinger model folder (root acoustic, dsdur, dspitch, dsvariance) with what it needs to
build inputs: config, its own phoneme table, language ids, dictionary and speaker embeddings.
each sub-model has its own phoneme table; tokens must always come from the model being fed."""

import difflib
import os

import numpy as np

from ..bank import ds as dsbank
from ..errors import WarbleError


class ModelDir:
    def __init__(self, bank, folder, role):
        self.bank = bank
        self.role = role
        self.dir = folder
        self.cfg = dsbank.load_dsconfig(os.path.join(folder, "dsconfig.yaml"))
        ppath = self.cfg.file("phonemes")
        if not ppath or not os.path.isfile(ppath):
            raise WarbleError("phonemes_missing", f"{role}: phoneme list not found at {ppath}", file=os.path.join(folder, "dsconfig.yaml"))
        self.tokens, _ = dsbank.load_phonemes(ppath)
        self.phonemes_path = ppath
        self.lang_ids = {}
        lp = self.cfg.file("languages")
        if lp and os.path.isfile(lp):
            self.lang_ids = dsbank.load_languages(lp)
        elif self.cfg["use_lang_id"]:
            raise WarbleError("languages_missing", f"{role}: use_lang_id is set but the languages file is missing ({lp})")
        self._dicts = {}
        self._embeds = None

    @property
    def frame_ms(self):
        return self.cfg.frame_ms

    def model_path(self, key):
        p = self.cfg.file(key)
        if not p or not os.path.isfile(p):
            raise WarbleError("model_missing", f"{self.role}: '{key}' model not found ({p})", file=os.path.join(self.dir, "dsconfig.yaml"))
        return p

    def dict(self, lang=None):
        """dsdict-<lang>.yaml, else dsdict.yaml, in this folder (DiffSingerBasePhonemizer.LoadG2p)."""
        if lang not in self._dicts:
            path = dsbank.choose_dict(self.dir, lang)
            self._dicts[lang] = dsbank.DsDict(path) if path else None
        return self._dicts[lang]

    def token(self, ph):
        if ph not in self.tokens:
            close = difflib.get_close_matches(ph, list(self.tokens), n=6, cutoff=0.5)
            raise WarbleError(
                "phoneme_not_in_model",
                f"phoneme '{ph}' is not in the {self.role} model's phoneme list",
                hint=f"closest: {close}" if close else None,
                file=self.phonemes_path,
            )
        return self.tokens[ph]

    def lang_id(self, ph):
        return self.lang_ids.get(dsbank.phoneme_language(ph), 0)

    def speakers(self):
        return list(self.cfg.get("speakers") or [])

    def embeds(self):
        """[S, H] matrix in dsconfig speaker order."""
        if self._embeds is None and self.speakers():
            hs = int(self.cfg["hidden_size"])
            rows = []
            for s in self.speakers():
                p = os.path.join(self.dir, s + ".emb")
                if not os.path.isfile(p):
                    raise WarbleError("speaker_missing", f"{self.role}: speaker embedding not found: {p}")
                v, n = dsbank.read_speaker_embed(p, hs)
                if n < hs:
                    raise WarbleError("speaker_size", f"{p} has {n} floats, hidden_size is {hs}")
                rows.append(v)
            self._embeds = np.stack(rows).astype(np.float32)
        return self._embeds

    def speaker_index(self, suffix):
        """getSpeakerIndexBySuffix: exact, then path-tail match, else the first speaker."""
        spk = self.speakers()
        if suffix in spk:
            return spk.index(suffix)
        sf = (suffix or "").replace("\\", "/").split("/")
        for i, s in enumerate(spk):
            sp = s.replace("\\", "/").split("/")
            if suffix and len(sf) <= len(sp) and sp[-len(sf):] == sf:
                return i
        return 0

    def speaker_weights(self, mixes):
        """mixes: per-frame (or per-phone) list of {suffix: weight}. returns [T, S] weights,
        normalized the way openutau does (sum > 1 divides; sum < 1 tops up the first-listed voice)."""
        spk = self.speakers()
        W = np.zeros((len(mixes), len(spk)), np.float32)
        for t, mix in enumerate(mixes):
            default = None
            for suffix, w in mix.items():
                i = self.speaker_index(suffix)
                W[t, i] += w
                if default is None:
                    default = i
            s = W[t].sum()
            if s > 1:
                W[t] /= s
            elif s < 1:
                W[t, default if default is not None else 0] += 1 - s
        return W

    def spk_embed(self, mixes):
        return (self.speaker_weights(mixes) @ self.embeds())[None, :, :]


class DsModels:
    """all model folders of a bank, loaded lazily."""

    def __init__(self, bank):
        self.bank = bank
        self._dirs = {}

    def get(self, role):
        if role not in self._dirs:
            folder = self.bank.root if role == "acoustic" else os.path.join(self.bank.root, role)
            if role != "acoustic" and not os.path.isfile(os.path.join(folder, "dsconfig.yaml")):
                self._dirs[role] = None
            else:
                self._dirs[role] = ModelDir(self.bank, folder, role)
        return self._dirs[role]
