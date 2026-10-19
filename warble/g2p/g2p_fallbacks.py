"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Core/Api/G2pFallbacks.cs"""

from .ig2p import IG2p


class G2pFallbacks(IG2p):
    def __init__(self, dictionaries):
        self.dictionaries = list(dictionaries)

    def is_valid_symbol(self, symbol):
        for d in self.dictionaries:
            if d.is_valid_symbol(symbol):
                return True
        return False

    def is_vowel(self, symbol):
        for d in self.dictionaries:
            if d.is_valid_symbol(symbol):
                return d.is_vowel(symbol)
        return False

    def is_glide(self, symbol):
        for d in self.dictionaries:
            if d.is_valid_symbol(symbol):
                return d.is_glide(symbol)
        return False

    def query(self, grapheme):
        for d in self.dictionaries:
            result = d.query(grapheme)
            if result is not None:
                return result
        return None

    def unpack_hint(self, hint, separator=" "):
        for d in self.dictionaries:
            result = d.unpack_hint(hint, separator)
            if result is not None:
                return result
        return None

    # warble helpers (not in the c#): the merged symbol tables, earlier dictionaries winning
    def symbols(self):
        out = {}
        for d in self.dictionaries:
            for k in (d.symbols() if hasattr(d, "symbols") else {}):
                if k not in out:
                    out[k] = self.is_vowel(k)
        return out

    def glides(self):
        return {s for s in self.symbols() if self.is_glide(s)}
