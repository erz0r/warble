"""openutau's g2p layer (grapheme to phoneme), shared by the classic phonemizer ports and diffsinger.

ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Core/Api/IG2p.cs, IG2pSymbols.cs,
G2pDictionary.cs, G2pDictionaryData.cs, G2pFallbacks.cs, G2pRemapper.cs, G2pPack.cs and OpenUtau.Core/G2p/*.cs.

    from warble.g2p import get_g2p
    g2p = get_g2p("en")                 # or ArpabetG2p()
    g2p.query("hello")                  # ['hh', 'ah', 'l', 'ow'] (dictionary first, then the onnx model)
    g2p.is_vowel("ah"), g2p.is_glide("l"), g2p.is_valid_symbol("zh")
    g2p.unpack_hint("hh ah l ow")       # hint symbols, invalid ones dropped
    g2p.symbols()                       # {symbol: is_vowel} (pack g2ps)

every query returns a fresh list, or None when the g2p has no answer (empty input, a lone punctuation mark,
or nothing predicted). packs load once per class (dictionary on construction, onnx session on first use).
"""

from .arpabet import ArpabetG2p
from .arpabet_plus import ArpabetPlusG2p
from .filipino import FilipinoG2p
from .french import FrenchG2p
from .french_millefeuille import FrenchMillefeuilleG2p
from .g2p_dictionary import G2pDictionary
from .g2p_dictionary_data import G2pDictionaryData
from .g2p_fallbacks import G2pFallbacks
from .g2p_pack import G2pPack
from .g2p_remapper import G2pRemapper
from .german import GermanG2p
from .german_marzipan import GermanMarzipanG2p
from .ig2p import IG2p, IG2pSymbols
from .italian import ItalianG2p
from .japanese_monophone import JapaneseMonophoneG2p
from .korean import KoreanG2p
from .portuguese import PortugueseG2p
from .russian import RussianG2p
from .spanish import SpanishG2p

# language key -> g2p class. keys follow the zip names (g2p-<key>.zip); plain iso codes alias the default pack.
G2P_CLASSES = {
    "arpabet": ArpabetG2p,
    "arpabet-plus": ArpabetPlusG2p,
    "de": GermanG2p,
    "de-marzipan": GermanMarzipanG2p,
    "es": SpanishG2p,
    "fil": FilipinoG2p,
    "fr": FrenchG2p,
    "fr-millefeuille": FrenchMillefeuilleG2p,
    "it": ItalianG2p,
    "ja-mono": JapaneseMonophoneG2p,
    "ko": KoreanG2p,
    "pt": PortugueseG2p,
    "ru": RussianG2p,
}
_ALIASES = {"en": "arpabet", "ja": "ja-mono", "tl": "fil"}

# openutau class name -> python class, for ports that name the c# type
BY_OPENUTAU_CLASS = {f"OpenUtau.Core.G2p.{cls.__name__}": cls for cls in G2P_CLASSES.values()}


def get_g2p(lang):
    """a g2p for a language key (see G2P_CLASSES; 'en', 'ja', 'tl' are aliases). raises KeyError."""
    key = lang.lower().replace("_", "-")
    key = _ALIASES.get(key, key)
    return G2P_CLASSES[key]()


def languages():
    return sorted(G2P_CLASSES)


__all__ = [
    "IG2p", "IG2pSymbols", "G2pDictionary", "G2pDictionaryData", "G2pFallbacks", "G2pRemapper", "G2pPack",
    "ArpabetG2p", "ArpabetPlusG2p", "FilipinoG2p", "FrenchG2p", "FrenchMillefeuilleG2p", "GermanG2p",
    "GermanMarzipanG2p", "ItalianG2p", "JapaneseMonophoneG2p", "KoreanG2p", "PortugueseG2p", "RussianG2p",
    "SpanishG2p", "G2P_CLASSES", "BY_OPENUTAU_CLASS", "get_g2p", "languages",
]
