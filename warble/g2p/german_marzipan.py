"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Core/G2p/GermanMarzipanG2p.cs"""

from .g2p_pack import G2pPack


class GermanMarzipanG2p(G2pPack):
    graphemes = [
        "", "", "", "", "a", "b", "c", "d", "e", "f", "g", "h",
        "i", "j", "k", "l", "m", "n", "o", "p", "q", "r", "s",
        "t", "u", "v", "w", "x", "y", "z", "ä", "ë", "ö", "ü", "ß",
    ]

    phonemes = [
        "", "", "", "", "a", "er", "eh", "e", "ih", "i", "uh",
        "u", "oh", "o", "ueh", "ue", "oeh", "oe", "ex", "ei", "au",
        "eu", "w", "j", "p", "t", "k", "f", "s", "sh", "ch",
        "xh", "h", "pf", "ts", "tsh", "th", "m", "n", "ng", "b",
        "d", "g", "v", "z", "l", "r", "dsh", "zh", "rh", "rr",
        "rx", "dh", "q", "vf", "cl",
    ]

    pack = "g2p-de-marzipan.zip"

    def _load_static(self):
        return self.load_pack(self.pack_path())
