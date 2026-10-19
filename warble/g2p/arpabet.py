"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Core/G2p/ArpabetG2p.cs"""

from ._cs import to_lower_invariant
from .g2p_pack import G2pPack


class ArpabetG2p(G2pPack):
    graphemes = [
        "", "", "", "", "'", "-", "a", "b", "c", "d", "e",
        "f", "g", "h", "i", "j", "k", "l", "m", "n", "o", "p",
        "q", "r", "s", "t", "u", "v", "w", "x", "y", "z",
    ]

    phonemes = [
        "", "", "", "", "aa", "ae", "ah", "ao", "aw", "ay", "b", "ch",
        "d", "dh", "eh", "er", "ey", "f", "g", "hh", "ih", "iy", "jh",
        "k", "l", "m", "n", "ng", "ow", "oy", "p", "r", "s", "sh", "t",
        "th", "uh", "uw", "v", "w", "y", "z", "zh",
    ]

    pack = "g2p-arpabet.zip"

    def _load_static(self):
        return self.load_pack(self.pack_path(), to_lower_invariant, lambda s: G2pPack.remove_tail_digits(to_lower_invariant(s)))
