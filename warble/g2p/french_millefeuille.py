"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Core/G2p/FrenchMillefeuilleG2p.cs"""

from .g2p_pack import G2pPack


class FrenchMillefeuilleG2p(G2pPack):
    graphemes = [
        "", "", "", "", "'", "-", "a", "b", "c", "d", "e", "f",
        "g", "h", "i", "j", "k", "l", "m", "n", "o", "p", "q",
        "r", "s", "t", "u", "v", "w", "x", "y", "z", "é",
        "è", "ê", "à", "â", "î", "ô", "ù", "û", "ç", "œ",
        "ï", "(", ")", "0", "1", "2", "3", "4", "5", "6",
        "7", "8", "9",
    ]

    phonemes = [
        "", "", "", "", "ah", "eh", "ae", "ee", "oe", "ih", "oh", "oo", "ou",
        "uh", "en", "in", "on", "uy", "y", "w", "f", "k", "p", "s", "sh",
        "t", "h", "b", "d", "g", "l", "m", "n", "r", "v", "z", "j", "ng", "q",
    ]

    pack = "g2p-fr-millefeuille.zip"

    def _load_static(self):
        return self.load_pack(self.pack_path())
