"""ported from csharp-kana 1.0.2 (Apache-2.0, Copyright (c) wolfgitpr, https://github.com/wolfgitpr/csharp-kana):
Kana/Kana.cs, Kana/DictUtil.cs, Kana/RomajiResList.cs (decompiled from the nuget package OpenUtau.Core depends on).

only the kana -> romaji direction openutau's DiffSingerJapanesePhonemizer uses (IsKana, KanaToRomaji with
Error.Default and no doubled sokuon, ToStrList). strings are iterated per utf-16 code unit like the c#;
every kana is in the basic multilingual plane, so python characters are the same units here.
"""

import re

ERROR_DEFAULT = 0
ERROR_IGNORE = 1

# DictUtil.KanaToRomajiMap
KANA_TO_ROMAJI = {
    "っ": "cl", "あ": "a", "い": "i", "いぇ": "ye", "う": "u", "うぁ": "wa", "うぃ": "wi", "うぇ": "we",
    "うぉ": "wo", "え": "e", "お": "o", "か": "ka", "が": "ga", "き": "ki", "きぇ": "kye", "きゃ": "kya",
    "きゅ": "kyu", "きょ": "kyo", "ぎ": "gi", "ぎぇ": "gye", "ぎゃ": "gya", "ぎゅ": "gyu", "ぎょ": "gyo", "く": "ku",
    "くぁ": "kwa", "くぃ": "kwi", "くぇ": "kwe", "くぉ": "kwo", "ぐ": "gu", "ぐぁ": "gwa", "ぐぃ": "gwi",
    "ぐぇ": "gwe", "ぐぉ": "gwo", "け": "ke", "げ": "ge", "こ": "ko", "ご": "go", "さ": "sa", "ざ": "za",
    "し": "shi", "しぇ": "she", "しゃ": "sha", "しゅ": "shu", "しょ": "sho", "ぢ": "ji", "じ": "ji", "じぇ": "je",
    "じゃ": "ja", "じゅ": "ju", "じょ": "jo", "す": "su", "すぁ": "swa", "すぃ": "swi", "すぇ": "swe", "すぉ": "swo",
    "づ": "zu", "ず": "zu", "ずぁ": "zwa", "ずぃ": "zwi", "ずぇ": "zwe", "ずぉ": "zwo", "せ": "se", "ぜ": "ze",
    "そ": "so", "ぞ": "zo", "た": "ta", "だ": "da", "ち": "chi", "ちぇ": "che", "ちゃ": "cha", "ちゅ": "chu",
    "ちょ": "cho", "つ": "tsu", "つぁ": "tsa", "つぃ": "tsi", "つぇ": "tse", "つぉ": "tso", "て": "te", "てぃ": "ti",
    "てゅ": "tyu", "で": "de", "でぃ": "di", "でゅ": "dyu", "と": "to", "とぅ": "tu", "ど": "do", "どぅ": "du",
    "な": "na", "に": "ni", "にぇ": "nye", "にゃ": "nya", "にゅ": "nyu", "にょ": "nyo", "ぬ": "nu", "ぬぁ": "nwa",
    "ぬぃ": "nwi", "ぬぇ": "nwe", "ぬぉ": "nwo", "ね": "ne", "の": "no", "は": "ha", "ば": "ba", "ぱ": "pa",
    "ひ": "hi", "ひぇ": "hye", "ひゃ": "hya", "ひゅ": "hyu", "ひょ": "hyo", "び": "bi", "びぇ": "bye", "びゃ": "bya",
    "びゅ": "byu", "びょ": "byo", "ぴ": "pi", "ぴぇ": "pye", "ぴゃ": "pya", "ぴゅ": "pyu", "ぴょ": "pyo", "ふ": "fu",
    "ふぁ": "fa", "ふぃ": "fi", "ふぇ": "fe", "ふぉ": "fo", "ぶ": "bu", "ぶぁ": "bwa", "ぶぃ": "bwi", "ぶぇ": "bwe",
    "ぶぉ": "bwo", "ぷ": "pu", "ぷぁ": "pwa", "ぷぃ": "pwi", "ぷぇ": "pwe", "ぷぉ": "pwo", "へ": "he", "べ": "be",
    "ぺ": "pe", "ほ": "ho", "ぼ": "bo", "ぽ": "po", "ま": "ma", "み": "mi", "みぇ": "mye", "みゃ": "mya",
    "みゅ": "myu", "みょ": "myo", "む": "mu", "むぁ": "mwa", "むぃ": "mwi", "むぇ": "mwe", "むぉ": "mwo", "め": "me",
    "も": "mo", "や": "ya", "ゆ": "yu", "よ": "yo", "ら": "ra", "り": "ri", "りぇ": "rye", "りゃ": "rya",
    "りゅ": "ryu", "りょ": "ryo", "る": "ru", "るぁ": "rwa", "るぃ": "rwi", "るぇ": "rwe", "るぉ": "rwo", "れ": "re",
    "ろ": "ro", "わ": "wa", "を": "o", "ん": "n", "ゔぁ": "va", "ゔぃ": "vi", "ゔ": "vu", "ゔぇ": "ve",
    "ゔぉ": "vo",
}

_KANA_SET = set(KANA_TO_ROMAJI)
_ANY_KANA = re.compile("[぀-ゟ゠-ヿ]+")


def _is_hiragana(c):
    return "぀" <= c <= "ゟ"


def _is_katakana(c):
    return "゠" <= c <= "ヿ"


def _is_small_kana(c):
    # the c# compares against 'ゃ'..'ょ' and 'ぁ'..'く' (sic)
    return ("ゃ" <= c <= "ょ") or ("ぁ" <= c <= "く")


def _convert_single_char(c):
    """ConvertSingleChar(c, KanaType.Hiragana)."""
    if "゠" <= c < "ヾ":
        return chr(ord(c) - 12448 + 12352)
    return c


def convert_kana(kana, error=ERROR_DEFAULT):
    """ConvertKana(string, error, KanaType.Hiragana)."""
    out = []
    for c in kana:
        if error != ERROR_IGNORE or _is_hiragana(c) or _is_katakana(c) or _is_small_kana(c):
            out.append(_convert_single_char(c))
    return "".join(out)


def convert_kana_list(kana_list, error=ERROR_DEFAULT):
    """ConvertKana(List<string>, error, KanaType.Hiragana)."""
    out = []
    for kana in kana_list:
        if _ANY_KANA.search(kana):
            text = "".join(chr(ord(c) - 12448 + 12352) if "゠" <= c < "ヾ" else c for c in kana)
        else:
            text = kana
            if error == ERROR_IGNORE:
                continue
        out.append(text)
    return out


def is_kana(text):
    """IsKana(string): the whole string, in hiragana, is one key of the table."""
    return convert_kana(text) in _KANA_SET


class RomajiRes:
    __slots__ = ("kana", "romaji", "error")

    def __init__(self, kana, romaji, error):
        self.kana = kana
        self.romaji = romaji
        self.error = error


def kana_to_romaji(kana_list, error=ERROR_DEFAULT, double_written_sokuon=False):
    """KanaToRomaji(List<string>, error, doubleWrittenSokuon) -> list of RomajiRes."""
    res = []
    for item in convert_kana_list(kana_list, error):
        if item != "゜" and item != "ー":
            value = KANA_TO_ROMAJI.get(item)
            if value is not None:
                res.append(RomajiRes(item, value, False))
            elif error != ERROR_IGNORE:
                res.append(RomajiRes(item, item, True))
    if double_written_sokuon:
        for num in range(len(res) - 1, -1, -1):
            if res[num].romaji == "cl" and num < len(res) - 1:
                res[num] = RomajiRes(res[num].kana, res[num + 1].romaji[0] + res[num + 1].romaji, res[num].error)
                del res[num + 1]
    return res


def to_str_list(res):
    """RomajiResList.ToStrList."""
    return [r.kana if r.error else r.romaji for r in res]
