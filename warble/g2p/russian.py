"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Core/G2p/RussianG2p.cs"""

from .g2p_pack import G2pPack


class RussianG2p(G2pPack):
    graphemes = [
        "", "", "", "", "-", "а", "б", "в", "г", "д", "е", "ж", "з",
        "и", "й", "к", "л", "м", "н", "о", "п", "р", "с", "т", "у",
        "ф", "х", "ц", "ч", "ш", "щ", "ъ", "ы", "ь", "э", "ю", "я", "ё",
    ]

    phonemes = [
        "", "", "", "", "a", "aa", "ay", "b", "bb", "c", "ch",
        "d", "dd", "ee", "f", "ff", "g", "gg", "h", "hh", "i", "ii",
        "j", "ja", "je", "jo", "ju", "k", "kk", "l", "ll", "m", "mm",
        "n", "nn", "oo", "p", "pp", "r", "rr", "s", "sch", "sh", "ss",
        "t", "tt", "u", "uj", "uu", "v", "vv", "y", "yy", "z", "zh", "zz",
    ]

    pack = "g2p-ru.zip"

    def _load_static(self):
        return self.load_pack(self.pack_path())
