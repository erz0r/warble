"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Core/G2p/GermanG2p.cs"""

from .g2p_pack import G2pPack


class GermanG2p(G2pPack):
    graphemes = [
        "", "", "", "", "2", "3", "/", "a", "b", "c", "d", "e",
        "f", "g", "h", "i", "j", "k", "l", "m", "n", "o", "p",
        "q", "r", "s", "t", "u", "v", "w", "x", "y", "z",
        "ä", "ë", "ö", "ü", "ß", "ê", "î", "ô", "á", "é",
        "í", "ú", "à", "è", "ù", "ę",
    ]

    phonemes = [
        "", "", "", "", "aa", "ae", "ah", "ao", "aw", "ax", "ay",
        "b", "cc", "ch", "d", "dh", "ee", "eh", "er", "ex", "f",
        "g", "hh", "ih", "iy", "jh", "k", "l", "m", "n", "ng",
        "oe", "ohh", "ooh", "oy", "p", "pf", "q", "r", "rr", "s",
        "sh", "t", "th", "ts", "ue", "uh", "uw", "v", "w", "x",
        "y", "yy", "z", "zh",
    ]

    pack = "g2p-de.zip"

    def _load_static(self):
        return self.load_pack(self.pack_path())
