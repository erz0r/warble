"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Core/Api/G2pDictionary.cs

the c# stores entries in a trie; a dict keyed by the whole grapheme answers every query the same way
(a node with no symbols and a missing node both give null)."""

from .g2p_dictionary_data import G2pDictionaryData
from .ig2p import IG2p


class G2pDictionary(IG2p):
    def __init__(self, root, phoneme_symbols, glide_symbols):
        self.root = root  # grapheme -> list of symbols
        self.phoneme_symbols = phoneme_symbols  # (phoneme, isVowel)
        self.glide_symbols = glide_symbols

    def is_valid_symbol(self, symbol):
        return symbol in self.phoneme_symbols

    def is_vowel(self, symbol):
        return self.phoneme_symbols.get(symbol, False)

    def is_glide(self, symbol):
        return symbol in self.glide_symbols

    def query(self, grapheme):
        symbols = self.root.get(grapheme)
        if symbols is None:
            return None
        return list(symbols)

    def unpack_hint(self, hint, separator=" "):
        return [s for s in hint.split(separator) if s in self.phoneme_symbols]

    # warble helpers (not in the c#): the symbol tables
    def symbols(self):
        """{symbol: is_vowel}"""
        return dict(self.phoneme_symbols)

    def glides(self):
        return set(self.glide_symbols)

    class Builder:
        def __init__(self):
            self.root = {}
            self.phoneme_symbols = {}
            self.glide_symbols = set()

        def add_symbol(self, symbol, type_or_is_vowel, is_glide=None):
            """AddSymbol(symbol, string type) / AddSymbol(symbol, bool isVowel[, bool isGlide])."""
            if isinstance(type_or_is_vowel, bool) or type_or_is_vowel is None and is_glide is not None:
                is_vowel = bool(type_or_is_vowel)
                self.phoneme_symbols[symbol] = is_vowel
                if is_glide is not None:
                    if is_glide and not is_vowel:
                        self.glide_symbols.add(symbol)
                    else:
                        self.glide_symbols.discard(symbol)
                return self
            type_ = type_or_is_vowel
            self.phoneme_symbols[symbol] = type_ == "vowel"
            if type_ == "semivowel" or type_ == "liquid":
                self.glide_symbols.add(symbol)
            else:
                self.glide_symbols.discard(symbol)
            return self

        def add_entry(self, grapheme, symbols):
            """must finish adding symbols before adding entries, otherwise symbols get ignored."""
            if grapheme is None:
                raise TypeError("grapheme is null")  # NullReferenceException in BuildTrie
            self.root[grapheme] = [s for s in symbols if s in self.phoneme_symbols]
            return self

        def load(self, data):
            """Load(string yaml) or Load(G2pDictionaryData)."""
            if isinstance(data, str):
                data = G2pDictionaryData.deserialize(data)
            if data.symbols is not None:
                for sd in data.symbols:
                    self.add_symbol(sd.symbol, sd.type)
            if data.entries is not None:
                for entry in data.entries:
                    if entry.phonemes is None:
                        raise TypeError("phonemes is null")  # ArgumentNullException in Where
                    self.add_entry(entry.grapheme, entry.phonemes)
            return self

        def build(self):
            return G2pDictionary(self.root, self.phoneme_symbols, self.glide_symbols)

    @staticmethod
    def new_builder():
        return G2pDictionary.Builder()
