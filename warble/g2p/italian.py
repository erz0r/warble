"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Core/G2p/ItalianG2p.cs"""

from .g2p_pack import G2pPack


class ItalianG2p(G2pPack):
    graphemes = [
        "", "", "", "", "'", "a", "b", "c", "d", "e",
        "f", "g", "h", "i", "j", "k", "l", "m", "n",
        "o", "p", "q", "r", "s", "t", "u", "v", "w",
        "x", "y", "z", "à", "è", "é", "ì", "í", "ò",
        "ù", "ú",
    ]

    phonemes = [
        "", "", "", "", "a", "b", "d", "dz", "dZZ", "e",
        "EE", "f", "g", "i", "j", "JJ", "k", "l", "LL",
        "m", "n", "nf", "ng", "o", "OO", "p", "r", "s",
        "SS", "t", "ts", "tSS", "u", "v", "w", "z",
    ]

    pack = "g2p-it.zip"

    def _load_static(self):
        return self.load_pack(self.pack_path(), lambda s: s, G2pPack.remove_tail_digits)
