"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Core/G2p/ArpabetPlusG2p.cs"""

from ._cs import to_lower_invariant
from .g2p_pack import G2pPack


class ArpabetPlusG2p(G2pPack):
    graphemes = [
        "", "", "", "", "'", "-", "a", "b", "c", "d", "e",
        "f", "g", "h", "i", "j", "k", "l", "m", "n", "o", "p",
        "q", "r", "s", "t", "u", "v", "w", "x", "y", "z",
        "A", "B", "C", "D", "E",
        "F", "G", "H", "I", "J", "K", "L", "M", "N", "O", "P",
        "Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z",
    ]

    phonemes = [
        "", "", "", "", "aa", "ae", "ah", "ao", "aw", "ax", "ay", "b", "ch",
        "d", "dh", "dr", "dx", "eh", "er", "ey", "f", "g", "hh", "ih", "iy", "jh",
        "k", "l", "m", "n", "ng", "ow", "oy", "p", "q", "r", "s", "sh", "t",
        "th", "tr", "uh", "uw", "v", "w", "y", "z", "zh",
    ]

    pack = "g2p-arpabet-plus.zip"

    def _load_static(self):
        return self.load_pack(self.pack_path(), to_lower_invariant, lambda s: G2pPack.remove_tail_digits(to_lower_invariant(s)))
