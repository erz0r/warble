"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Core/G2p/KoreanG2p.cs"""

from ._cs import to_lower_invariant
from .g2p_pack import G2pPack


class KoreanG2p(G2pPack):
    graphemes = [
        "", "", "", "", "ㄱ", "ㄲ", "ㄳ", "ㄴ", "ㄵ", "ㄶ", "ㄷ",
        "ㄸ", "ㄹ", "ㄺ", "ㄻ", "ㄼ", "ㄾ", "ㅀ", "ㅁ", "ㅂ", "ㅃ",
        "ㅄ", "ㅅ", "ㅆ", "ㅇ", "ㅈ", "ㅉ", "ㅊ", "ㅋ", "ㅌ", "ㅍ",
        "ㅎ", "ㅏ", "ㅐ", "ㅑ", "ㅒ", "ㅓ", "ㅔ", "ㅕ", "ㅖ", "ㅗ",
        "ㅘ", "ㅙ", "ㅚ", "ㅛ", "ㅜ", "ㅝ", "ㅞ", "ㅟ", "ㅠ", "ㅡ",
        "ㅢ", "ㅣ",
    ]

    phonemes = [
        "", "", "", "", "K", "L", "M", "N", "NG", "P", "T",
        "a", "b", "ch", "d", "e", "eo", "eu", "g", "h",
        "i", "j", "jj", "k", "kk", "m", "n", "o", "p", "pp",
        "r", "s", "ss", "t", "tt", "u", "w", "y",
    ]

    pack = "g2p-ko.zip"

    def _load_static(self):
        return self.load_pack(self.pack_path(), to_lower_invariant, lambda s: G2pPack.remove_tail_digits(to_lower_invariant(s)))

    def predict(self, grapheme):
        sb = []
        for item in grapheme:
            ok, jamo = self.try_divide_hangeul(item)
            sb.append(jamo if ok else item)
        return super().predict("".join(sb))

    onset = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
    nucleus = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
    coda = " ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"

    UNICODE_HANGEUL_BASE = 0xAC00
    UNICODE_HANGEUL_LAST = 0xD79F

    def try_divide_hangeul(self, c):
        """-> (ok, jamo string)"""
        check = ord(c)
        if check > self.UNICODE_HANGEUL_LAST or check < self.UNICODE_HANGEUL_BASE:
            return False, ""
        code = check - self.UNICODE_HANGEUL_BASE
        coda_code = code % 28
        code = (code - coda_code) // 28
        nucleus_code = code % 21
        code = (code - nucleus_code) // 21
        onset_code = code
        return True, f"{self.onset[onset_code]}{self.nucleus[nucleus_code]}{self.coda[coda_code]}"
