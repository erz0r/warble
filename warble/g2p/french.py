"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Core/G2p/FrenchG2p.cs"""

from .g2p_pack import G2pPack


class FrenchG2p(G2pPack):
    graphemes = [
        "", "", "", "", "-", "a", "b", "c", "d", "e", "f", "g",
        "h", "i", "j", "k", "l", "m", "n", "o", "p", "q", "r",
        "s", "t", "u", "v", "w", "x", "y", "z", "à", "á", "â", "ä",
        "æ", "ç", "è", "é", "ê", "ë", "î", "ï", "ñ", "ô", "ö",
        "ù", "ú", "û", "ü", "ÿ",
    ]

    phonemes = [
        "", "", "", "", "aa", "ai", "an", "au", "bb", "ch", "dd",
        "ee", "ei", "eu", "ff", "gg", "gn", "ii", "in", "jj", "kk",
        "ll", "mm", "nn", "oe", "on", "oo", "ou", "pp", "rr", "ss",
        "tt", "un", "uu", "uy", "vv", "ww", "yy", "zz",
    ]

    pack = "g2p-fr.zip"

    def _load_static(self):
        return self.load_pack(self.pack_path())
