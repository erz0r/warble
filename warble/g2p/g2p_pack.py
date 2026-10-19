"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Core/Api/G2pPack.cs

a g2p pack is a zip (warble/g2p/data/g2p-*.zip) with dict.txt (cmudict style, two spaces between grapheme
and phonemes), phones.txt (symbol and type) and g2p.onnx, a transformer that predicts phonemes for words
the dictionary lacks. query() looks the dictionary up first, then the prediction cache, then runs the model.

the c# keeps the loaded dictionary, session and prediction cache in static fields of each subclass; here
they live in a per-subclass state dict built on first use (the onnx session is created lazily on the first
prediction, which changes nothing observable)."""

import os
import threading
import zipfile

import numpy as np

from ._cs import is_all_punct, is_digit, read_lines, split_ws, to_lower_invariant, trim
from .g2p_dictionary import G2pDictionary
from .ig2p import IG2p

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
_LOCK = threading.RLock()


def extract_text(path, key):
    """Zip.ExtractText: the entry's lines, or None when the entry is missing."""
    with zipfile.ZipFile(path) as z:
        if key not in z.namelist():
            return None
        return read_lines(z.read(key))


def extract_bytes(path, key):
    with zipfile.ZipFile(path) as z:
        if key not in z.namelist():
            return None
        return z.read(key)


class _LazySession:
    """an onnxruntime InferenceSession over g2p.onnx, created on first run."""

    def __init__(self, path):
        self.path = path
        self._session = None

    def run(self, feeds):
        if self._session is None:
            import onnxruntime as ort

            opts = ort.SessionOptions()
            opts.log_severity_level = 3
            self._session = ort.InferenceSession(extract_bytes(self.path, "g2p.onnx"), sess_options=opts,
                                                 providers=["CPUExecutionProvider"])
        return self._session.run(None, feeds)


def _identity(s):
    return s


class G2pPack(IG2p):
    # subclasses set these (the c# static tables and the resource they load)
    graphemes = []
    phonemes = []
    pack = None  # zip file name under warble/g2p/data

    # ---- c# LoadPack ---------------------------------------------------------------------------
    @staticmethod
    def load_pack(path, prep_grapheme=None, prep_phoneme=None):
        prep_grapheme = prep_grapheme or _identity
        prep_phoneme = prep_phoneme or _identity
        dict_txt = extract_text(path, "dict.txt")
        phones_txt = extract_text(path, "phones.txt")
        builder = G2pDictionary.new_builder()
        for line in phones_txt:
            parts = split_ws(trim(line))
            if len(parts) == 2:
                builder.add_symbol(prep_phoneme(parts[0]), parts[1])
        for line in dict_txt:
            if line.startswith(";;;"):
                continue
            parts = trim(line).split("  ")
            if len(parts) == 2:
                builder.add_entry(prep_grapheme(parts[0]), [prep_phoneme(s) for s in split_ws(parts[1])])
        d = builder.build()
        session = _LazySession(path)
        return d, session

    @staticmethod
    def remove_tail_digits(s):
        while len(s) > 0 and is_digit(s[-1]):
            s = s[:-1]
        return s

    # ---- per-class static state ----------------------------------------------------------------
    def _load_static(self):
        """the body of the c# constructor's lock block; subclasses override."""
        raise NotImplementedError

    def __init__(self):
        cls = type(self)
        with _LOCK:
            st = cls.__dict__.get("_static")
            if st is None:
                grapheme_indexes = {}
                for i, g in enumerate(cls.graphemes[4:]):
                    if g in grapheme_indexes:
                        raise ValueError(f"duplicate grapheme {g!r}")  # ToDictionary throws
                    grapheme_indexes[g] = i + 4
                d, session = self._load_static()
                st = {"grapheme_indexes": grapheme_indexes, "dict": d, "session": session, "pred_cache": {}}
                cls._static = st
        self.grapheme_indexes = st["grapheme_indexes"]
        self.phoneme_table = cls.phonemes
        self.dict = st["dict"]
        self.session = st["session"]
        self.pred_cache = st["pred_cache"]

    def pack_path(self):
        return os.path.join(DATA_DIR, self.pack)

    # ---- IG2p ------------------------------------------------------------------------------------
    def is_valid_symbol(self, symbol):
        return self.dict.is_valid_symbol(symbol)

    def is_vowel(self, symbol):
        return self.dict.is_vowel(symbol)

    def is_glide(self, symbol):
        return self.dict.is_glide(symbol)

    def query(self, grapheme):
        if len(grapheme) == 0 or is_all_punct(grapheme):
            return None
        phonemes = self.dict.query(grapheme)
        if phonemes is None:
            phonemes = self.pred_cache.get(grapheme)
            if phonemes is None:
                phonemes = self.predict(grapheme)
                if len(phonemes) == 0:
                    return None
                self.pred_cache[grapheme] = phonemes
        return list(phonemes)

    def unpack_hint(self, hint, separator=" "):
        return self.dict.unpack_hint(hint, separator)

    # warble helpers (not in the c#): the symbol tables
    def symbols(self):
        """{symbol: is_vowel} from phones.txt"""
        return self.dict.symbols()

    def glides(self):
        return self.dict.glides()

    def predict(self, grapheme):
        src = self.encode_word(grapheme)
        if src.size == 0 or self.session is None:
            return []
        tgt = [2]
        t = 0
        src_length = src.shape[1]
        while t < src_length and len(tgt) < 48:
            outputs = self.session.run({"src": src, "tgt": np.array([tgt], dtype=np.int32), "t": np.array([t], dtype=np.int32)})
            pred = int(np.asarray(outputs[0]).reshape(-1)[0])
            if pred != 2:
                tgt.append(pred)
            else:
                t += 1
        return self.decode_phonemes(tgt[1:])

    def encode_word(self, grapheme):
        encoded = []
        for c in to_lower_invariant(grapheme):
            index = self.grapheme_indexes.get(c)
            if index is not None:
                encoded.append(index)
        return np.array([encoded], dtype=np.int32).reshape(1, len(encoded))

    def decode_phonemes(self, indexes):
        out = []
        for idx in indexes:
            if idx < 0:
                raise IndexError(idx)  # c# arrays don't wrap
            out.append(self.phoneme_table[idx])
        return out
