"""ported from csharp-pinyin 1.0.0 (Apache-2.0, Copyright (c) wolfgitpr, https://github.com/wolfgitpr/csharp-pinyin):
Pinyin/ChineseG2p.cs, DictUtil.cs, ToneConverter.cs, ManTone.cs, CanTone.cs, ManToneUtil.cs, Pinyin.cs, Jyutping.cs,
PinyinRes.cs, PinyinResList.cs (decompiled from the nuget package OpenUtau.Core depends on).

the hanzi -> pinyin / jyutping g2p that openutau's chinese phonemizers use. the dictionaries are the
library's embedded resources, copied to data/chinese (see SOURCE.md) and loaded lazily.

candidates (all readings of a polyphonic character) are not computed: openutau never reads them, so
they cannot affect any output.
"""

import os
import re

DATA = os.path.join(os.path.dirname(__file__), "data", "chinese")


def _utf16_len(s):
    """c# string.Length counts utf-16 code units."""
    return len(s.encode("utf-16-le")) // 2


def _lines(dict_dir, file_name):
    # StreamReader(UTF8) strips a bom; ReadToEnd().Split(Environment.NewLine) ("\n" on unix)
    path = os.path.join(DATA, dict_dir, file_name)
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        data = f.read()
    text = data.decode("utf-8-sig", errors="replace")
    return text.split("\n")


# ---- DictUtil ----------------------------------------------------------------------------------------
def load_dict_str(dict_dir, file_name, result_map):
    lines = _lines(dict_dir, file_name)
    if lines is None:
        return False
    for line in lines:
        parts = line.strip().split(":")
        if len(parts) == 2:
            result_map[parts[0]] = parts[1]
    return True


def load_dict_list(dict_dir, file_name, result_map):
    lines = _lines(dict_dir, file_name)
    if lines is None:
        return False
    for line in lines:
        parts = line.strip().split(":")
        if len(parts) == 2:
            result_map[parts[0]] = [v for v in parts[1].split(",") if v]
    return True


def load_additional_dict(dict_dir, file_name, result_map):
    lines = _lines(dict_dir, file_name)
    if lines is None:
        return False
    for line in lines:
        parts = line.strip().split(":")
        if len(parts) == 2:
            source = [v for v in parts[1].split(" ") if v]
            result_map[parts[0]] = [ManToneUtil.tone3_to_tone(x) for x in source]
    return True


# ---- ToneConverter / ManTone / CanTone ---------------------------------------------------------------
class ToneConverter:
    def __init__(self):
        self.m_converts = {}

    def convert(self, s, style, v_to_u=False, neutral_tone_with_five=False):
        fn = self.m_converts.get(style)
        if fn is None:
            return s
        return fn(s, v_to_u, neutral_tone_with_five)


TONE_TO_NUM = {
    "ā": ("a", "1"), "á": ("a", "2"), "ǎ": ("a", "3"), "à": ("a", "4"),
    "ō": ("o", "1"), "ó": ("o", "2"), "ǒ": ("o", "3"), "ò": ("o", "4"),
    "ē": ("e", "1"), "é": ("e", "2"), "ě": ("e", "3"), "è": ("e", "4"),
    "ī": ("i", "1"), "í": ("i", "2"), "ǐ": ("i", "3"), "ì": ("i", "4"),
    "ū": ("u", "1"), "ú": ("u", "2"), "ǔ": ("u", "3"), "ù": ("u", "4"),
    "ǖ": ("v", "1"), "ǘ": ("v", "2"), "ǚ": ("v", "3"), "ǜ": ("v", "4"),
    "ń": ("n", "2"), "ň": ("n", "3"), "ǹ": ("n", "4"), "ḿ": ("m", "2"),
}


class ManTone(ToneConverter):
    NORMAL = 0
    TONE = 1
    TONE2 = 2
    TONE3 = 8

    def __init__(self):
        super().__init__()
        self.m_converts = {0: self.tone_to_normal, 1: self.tone_to_tone, 2: self.tone_to_tone2, 8: self.tone_to_tone3}

    @staticmethod
    def tone_to_normal(pinyin, v_to_u=False, neutral_tone_with_five=False):
        sb = []
        for c in pinyin:
            if "a" <= c <= "z":
                sb.append(c)
            elif c in TONE_TO_NUM:
                sb.append(TONE_TO_NUM[c][0])
            else:
                sb.append(c)
        s = "".join(sb)
        if not v_to_u:
            s = s.replace("ü", "v")
        return s

    @staticmethod
    def tone_to_tone(pinyin, v_to_u=False, neutral_tone_with_five=False):
        if v_to_u:
            return pinyin
        return "".join(c if "a" <= c <= "z" else ("v" if c == "ü" else c) for c in pinyin)

    @staticmethod
    def tone_to_tone2(pinyin, v_to_u=False, neutral_tone_with_five=False):
        sb = []
        for c in pinyin:
            if "a" <= c <= "z":
                sb.append(c)
            elif c in TONE_TO_NUM:
                base, item = TONE_TO_NUM[c]
                sb.append(base)
                if neutral_tone_with_five or item != "5":
                    sb.append(item)
            else:
                if not v_to_u and c == "ü":
                    c = "v"
                sb.append(c)
        return "".join(sb)

    @staticmethod
    def tone_to_tone3(pinyin, v_to_u=False, neutral_tone_with_five=False):
        sb = []
        tone = "5"
        for c2 in pinyin:
            if "a" <= c2 <= "z":
                sb.append(c2)
                continue
            if c2 in TONE_TO_NUM:
                sb.append(TONE_TO_NUM[c2][0])
                tone = TONE_TO_NUM[c2][1]
                continue
            if not v_to_u and c2 == "ü":
                c2 = "v"
            sb.append(c2)
        sb.append(tone)
        if not neutral_tone_with_five and tone == "5":
            sb.pop()
        return "".join(sb)


class CanTone(ToneConverter):
    NORMAL = 0
    TONE3 = 8

    def __init__(self):
        super().__init__()
        self.m_converts = {0: self.tone3_to_normal}

    @staticmethod
    def tone3_to_normal(pinyin, v_to_u=False, neutral_tone_with_five=False):
        if len(pinyin) < 1:
            raise ValueError("Substring length is negative")  # c# Substring(0, -1) throws
        return pinyin[:-1]


# ---- ManToneUtil -------------------------------------------------------------------------------------
class ManToneUtil:
    PHONETIC_SYMBOL_REVERSE = {
        "a1": "ā", "a2": "á", "a3": "ǎ", "a4": "à", "e1": "ē", "e2": "é", "e3": "ě", "e4": "è",
        "i1": "ī", "i2": "í", "i3": "ǐ", "i4": "ì", "o1": "ō", "o2": "ó", "o3": "ǒ", "o4": "ò",
        "u1": "ū", "u2": "ú", "u3": "ǔ", "u4": "ù", "v1": "ǖ", "v2": "ǘ", "v3": "ǚ", "v4": "ǜ",
    }

    @staticmethod
    def right_mark_index(s):
        if "iou" in s:
            return s.find("u")
        if "uei" in s:
            return s.find("i")
        if "uen" in s:
            return s.find("u")
        for item in ["a", "o", "e"]:
            n = s.find(item)
            if n != -1:
                return n
        for item in ["iu", "ui"]:
            n = s.find(item)
            if n != -1:
                return n + 1
        for item in ["i", "u", "v", "ü"]:
            n = s.find(item)
            if n != -1:
                return n
        for item in ["n", "m", "ê"]:
            n = s.find(item)
            if n != -1:
                return n
        return -1

    @staticmethod
    def is_tone_number(c):
        return "0" <= c <= "4"

    @staticmethod
    def is_phonetic_symbol(c):
        return c in "aeiouüv"

    @staticmethod
    def tone_to_tone(tone2):
        text = tone2.replace("ü", "v").replace("5", "").replace("0", "")
        out = []
        i = 0
        while i < len(text):
            c = text[i]
            if ManToneUtil.is_phonetic_symbol(c):
                if i + 1 < len(text) and ManToneUtil.is_tone_number(text[i + 1]):
                    key = text[i:i + 2]
                    if key in ManToneUtil.PHONETIC_SYMBOL_REVERSE:
                        out.append(ManToneUtil.PHONETIC_SYMBOL_REVERSE[key])
                        i += 2
                    else:
                        out.append(c)
                        i += 1
                else:
                    out.append(c)
                    i += 1
            else:
                out.append(c)
                i += 1
        return "".join(out).replace("ü", "v")

    @staticmethod
    def tone3_to_tone2(pinyin, v_to_u=False):
        if len(pinyin) < 1:
            raise ValueError("Substring length is negative")
        text = pinyin[:-1]
        num = ManToneUtil.right_mark_index(text)
        if num == -1:
            num = len(text) - 1
        return text[:num + 1] + pinyin[-1:] + text[num + 1:]

    @staticmethod
    def tone3_to_tone(pinyin):
        return ManToneUtil.tone_to_tone(ManToneUtil.tone3_to_tone2(pinyin, True))


# ---- PinyinRes ---------------------------------------------------------------------------------------
class PinyinRes:
    __slots__ = ("hanzi", "pinyin", "error")

    def __init__(self, hanzi="", pinyin=None, error=True):
        self.hanzi = hanzi
        self.pinyin = hanzi if pinyin is None else pinyin
        self.error = error


def to_str_list(res):
    return [r.hanzi if r.error else r.pinyin for r in res]


# ---- ChineseG2p --------------------------------------------------------------------------------------
_SPLIT = re.compile("(?![ー゜])([a-zA-Z]+|[+-]|[0-9]|[一-龥]|[぀-ゟ゠-ヿ][ャュョゃゅょァィゥェォぁぃぅぇぉ]?)")


class ChineseG2p:
    def __init__(self, language, tone_converter):
        dict_dir = language
        self.converter = tone_converter
        self.phrases_map = {}
        self.trans_dict = {}
        self.word_dict = {}
        self.phrases_dict = {}
        load_dict_str(dict_dir, "phrases_map.txt", self.phrases_map)
        load_dict_list(dict_dir, "phrases_dict.txt", self.phrases_dict)
        load_additional_dict(dict_dir, "user_dict.txt", self.phrases_dict)
        load_dict_list(dict_dir, "word.txt", self.word_dict)
        load_dict_str(dict_dir, "trans_word.txt", self.trans_dict)

    @staticmethod
    def split_string(s):
        return [m.group(0) for m in _SPLIT.finditer(s)]

    @staticmethod
    def _reset_zh(inp, res, positions):
        out = []
        for i in range(len(inp)):
            num = positions.index(i) if i in positions else -1
            if num != -1:
                out.append(PinyinRes(inp[i], res[num].pinyin, False))
            else:
                out.append(PinyinRes(inp[i], inp[i], True))
        return out

    def _zh_position(self, inp, res, positions):
        for i, text in enumerate(inp):
            if text:
                text2 = self.trans_dict.get(text, text)
                if text2 in self.word_dict:
                    res.append(text2)
                    positions.append(i)

    def _conv(self, pinyin, style, v_to_u, n5):
        return self.converter.convert(pinyin, style, v_to_u, n5)

    def hanzi_to_pinyin(self, inp, style=0, error=0, candidates=True, v_to_u=False, neutral_tone_with_five=False):
        if isinstance(inp, str):
            inp = self.split_string(inp)
        lst = []
        positions = []
        self._zh_position(inp, lst, positions)
        res = []
        num = 0
        n = len(lst)

        def phrase(start, length):
            text = "".join(lst[start:start + length])
            value = self.phrases_dict.get(text)
            if value is None:
                return None, None
            return text, [self._conv(p, style, v_to_u, neutral_tone_with_five) for p in value]

        def add_phrase(start, text, value):
            for k in range(_utf16_len(text)):
                if k >= len(value) or start + k >= n:
                    raise IndexError("Index was out of range")  # c# List indexer throws
                res.append(PinyinRes(lst[start + k], value[k], False))

        def remove_last(k):
            if k < 0 or k > len(res):
                raise ValueError("RemoveRange out of range")
            if k:
                del res[len(res) - k:]

        while num < n:
            text = lst[num]
            if not self.is_hanzi(text):
                res.append(PinyinRes(text))
                num += 1
                continue
            if not self.is_polyphonic(text):
                d = self.get_default_pinyin(text, style, v_to_u, neutral_tone_with_five)
                res.append(PinyinRes(text, d[0] if d else "", False))
                num += 1
                continue
            flag = False
            num2 = 4
            while num2 >= 2 and not flag:
                if num + num2 <= n:
                    t, v = phrase(num, num2)
                    if t is not None:
                        add_phrase(num, t, v)
                        num += num2
                        flag = True
                if num >= 1 and num + num2 <= n and not flag:
                    t, v = phrase(num - 1, num2)
                    if t is not None:
                        remove_last(1)
                        add_phrase(num - 1, t, v)
                        num += num2 - 1
                        flag = True
                if num + 1 - num2 >= 0 and not flag and num + 1 <= n:
                    t, v = phrase(num + 1 - num2, num2)
                    if t is not None:
                        remove_last(num2 - 1)
                        add_phrase(num + 1 - num2, t, v)
                        num += 1
                        flag = True
                if num + 2 - num2 >= 0 and num + 2 <= n and not flag:
                    t, v = phrase(num + 2 - num2, num2)
                    if t is not None:
                        remove_last(num2 - 2)
                        add_phrase(num + 2 - num2, t, v)
                        num += 2
                        flag = True
                num2 -= 1
            if not flag:
                d = self.get_default_pinyin(text, style, v_to_u, neutral_tone_with_five)
                res.append(PinyinRes(text, d[0] if d else "", False))
                num += 1
        return self._reset_zh(inp, res, positions)

    def is_hanzi(self, text):
        return self.trad_to_sim(text) in self.word_dict

    def is_polyphonic(self, text):
        return text in self.phrases_map

    def trad_to_sim(self, text):
        return self.trans_dict.get(text, text)

    def get_default_pinyin(self, hanzi, style=0, v_to_u=False, neutral_tone_with_five=False):
        value = self.word_dict.get(hanzi)
        if value is None:
            return [hanzi]
        out = []
        seen = set()
        for item in value:
            p = self._conv(item, style, v_to_u, neutral_tone_with_five)
            if p not in seen:
                seen.add(p)
                out.append(p)
        if not out:
            return [hanzi]
        return out


class Pinyin(ChineseG2p):
    _instance = None

    def __init__(self):
        super().__init__("mandarin", ManTone())

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance


class Jyutping(ChineseG2p):
    _instance = None

    def __init__(self):
        super().__init__("cantonese", CanTone())

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance


def cs_len(s):
    return _utf16_len(s)
