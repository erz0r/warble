"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Core/G2p/FilipinoG2p.cs"""

from ._cs import to_lower_invariant
from .g2p_pack import G2pPack


class FilipinoG2p(G2pPack):
    graphemes = [
        "", "", "", "", "'", "-", "a", "b", "c", "d", "e", "f", "g",
        "h", "i", "j", "k", "l", "m", "n", "o", "p", "q", "r", "s", "t",
        "u", "v", "w", "x", "y", "z", "ñ",
    ]

    phonemes = [
        "", "", "", "", "a", "b", "d", "dx", "dy", "e", "f", "g", "h", "hh", "i",
        "j", "k", "l", "m", "n", "ng", "ny", "o", "p", "q", "s",
        "sy", "t", "th", "ts", "u", "v", "w", "z",
    ]

    pack = "g2p-fil.zip"

    def _load_static(self):
        return self.load_pack(self.pack_path(), to_lower_invariant, lambda s: G2pPack.remove_tail_digits(to_lower_invariant(s)))
