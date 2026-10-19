"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Core/G2p/PortugueseG2p.cs"""

from .g2p_pack import G2pPack


class PortugueseG2p(G2pPack):
    graphemes = [
        "", "", "", "", "-", "a", "b", "c", "d", "e", "f", "g", "h",
        "i", "j", "k", "l", "m", "n", "o", "p", "q", "r", "s", "t",
        "u", "v", "w", "x", "y", "z", "à", "á", "â", "ã", "ç",
        "è", "é", "ê", "í", "î", "ó", "ô", "õ", "ú", "û", "ü",
    ]

    phonemes = [
        "", "", "", "", "E", "J", "L", "O", "R", "S", "X", "Z",
        "a", "a~", "b", "d", "dZ", "e", "e~", "f", "g",
        "i", "i~", "j", "j~", "k", "l", "m", "n", "o", "o~",
        "p", "r", "s", "t", "tS", "u", "u~", "v", "w", "w~", "z",
    ]

    pack = "g2p-pt.zip"

    def _load_static(self):
        return self.load_pack(self.pack_path())
