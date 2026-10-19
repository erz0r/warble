"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Core/G2p/SpanishG2p.cs"""

from ._cs import to_lower_invariant
from .g2p_pack import G2pPack


class SpanishG2p(G2pPack):
    graphemes = [
        "", "", "", "", "'", "-", "a", "b", "c", "d", "e",
        "f", "g", "h", "i", "j", "k", "l", "m", "n", "o", "p",
        "q", "r", "s", "t", "u", "v", "w", "x", "y", "z",
        "Á", "É", "Í", "Ó", "Ú", "á", "ã", "é", "ë", "ê", "í",
        "ñ", "ó", "ú", "ü",
    ]

    phonemes = [
        "", "", "", "", "a", "b", "B", "ch", "d", "D", "e", "f",
        "g", "G", "gn", "i", "I", "k", "l", "ll", "m", "n", "o",
        "p", "r", "rr", "s", "t", "u", "U", "w", "x", "y", "Y", "z",
    ]

    pack = "g2p-es.zip"

    def _load_static(self):
        return self.load_pack(self.pack_path(), to_lower_invariant, None)
