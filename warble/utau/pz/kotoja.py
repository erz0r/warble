"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Plugin.Builtin/KOtoJAPhonemizer.cs

korean lyrics (hangeul, korean romaji or japanese-romaji phonetic hints) on japanese banks.

the c# uses WanaKanaNet's WanaKana.ToHiragana. that library has no python equivalent here, so a
small port of wanakana's romaji -> hiragana tree (wanakana v4, which WanaKanaNet 1.0.0 follows, with
default options) lives at the bottom of this module as `_wanakana_to_hiragana`.
"""

import copy
import re

from . import korean_phonemizer_util as ku
from .api import Phoneme, alt_str, phonemizer
from .base_korean_phonemizer import BaseKoreanPhonemizer, cdiv

# ㄱ ㄲ ㄴ ㄷ ㄸ ㄹ ㅁ ㅂ ㅃ ㅅ ㅆ ㅇ ㅈ ㅉ ㅊ ㅋ ㅌ ㅍ ㅎ
initials = ["g", "k", "n", "d", "t", "r", "m", "b", "p", "s", "s", "", "j", "ch", "ch", "k", "t", "p", "h"]
# ㅏ ㅐ ㅑ ㅒ ㅓ ㅔ ㅕ ㅖ ㅗ ㅘ ㅙ ㅚ ㅛ ㅜ ㅝ ㅞ ㅟ ㅠ ㅡ ㅢ ㅣ
medials = ["a", "e", "ya", "ye", "o", "e", "yo", "ye", "o", "wa", "we", "we", "yo", "u", "wo", "we", "wi", "yu", "u", "wi", "i"]
# - ㄱ ㄲ ㄳ ㄴ ㄵ ㄶ ㄷ ㄹ ㄺ ㄻ ㄼ ㄽ ㄾ ㄿ ㅀ ㅁ ㅂ ㅄ ㅅ ㅆ ㅇ ㅈ ㅊ ㅋ ㅌ ㅍ ㅎ H B bre
finals = ["", "k", "k", "k", "n", "n", "n", "t", "r", "r", "r", "r", "r", "r", "r", "r", "m", "p", "p", "t", "t", "n", "t", "t", "k", "t", "p", "t", "", "", ""]
sonorants = ["n"]
extras = ["f", "v", "z", "ts", "sh"]

consonants = [
    "ch=ち,ちぇ,ちゃ,ちゅ,ちょ", "gy=ぎ,ぎぇ,ぎゃ,ぎゅ,ぎょ", "ts=つ,つぁ,つぃ,つぇ,つぉ", "ty=てぃ,てぇ,てゃ,てゅ,てょ", "py=ぴ,ぴぇ,ぴゃ,ぴゅ,ぴょ",
    "ry=り,りぇ,りゃ,りゅ,りょ", "ny=に,にぇ,にゃ,にゅ,にょ", "r=ら,る,るぁ,るぃ,るぇ,るぉ,れ,ろ", "hy=ひ,ひぇ,ひゃ,ひゅ,ひょ",
    "dy=でぃ,でぇ,でゃ,でゅ,でょ", "by=び,びぇ,びゃ,びゅ,びょ", "b=ば,ぶ,ぶぁ,ぶぃ,ぶぇ,ぶぉ,べ,ぼ", "d=だ,で,ど,どぅ",
    "g=が,ぐ,ぐぁ,ぐぃ,ぐぇ,ぐぉ,げ,ご", "f=ふ,ふぁ,ふぃ,ふぇ,ふぉ,ふぃぇ,ふゃ,ふゅ,ふょ", "h=は,へ,ほ", "k=か,く,くぁ,くぃ,くぇ,くぉ,け,こ",
    "j=じ,じぇ,じゃ,じゅ,じょ", "m=ま,む,むぁ,むぃ,むぇ,むぉ,め,も", "n=な,ぬ,ぬぁ,ぬぃ,ぬぇ,ぬぉ,ね,の", "p=ぱ,ぷ,ぷぁ,ぷぃ,ぷぇ,ぷぉ,ぺ,ぽ",
    "s=さ,す,すぁ,すぃ,すぇ,すぉ,せ,そ", "sh=し,しぇ,しゃ,しゅ,しょ", "t=た,て,と,とぅ", "v=ヴ,ヴぁ,ヴぃ,ヴぇ,ヴぉ,ヴぃぇ,ヴゃ,ヴゅ,ヴょ",
    "ky=き,きぇ,きゃ,きゅ,きょ", "w=うぃ,うぇ,うぉ,わ,を", "y=いぇ,や,ゆ,よ", "z=ざ,ず,ずぁ,ずぃ,ずぇ,ずぉ,ぜ,ぞ", "my=み,みぇ,みゃ,みゅ,みょ",
]
substitution = ["ty,ch,ts=t", "j,dy=d", "gy=g", "ky=k", "py=p", "ny=n", "ry=r", "my=m", "hy,f=h", "by,v=b"]


def _to_dictionary(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise ValueError(f"An item with the same key has already been added. Key: {k}")
        out[k] = v
    return out


consonant_lookup = _to_dictionary((cv, parts[0]) for line in consonants for parts in [line.split("=")] for cv in parts[1].split(","))
substitute_lookup = _to_dictionary((orig, parts[1]) for line in substitution for parts in [line.split("=")] for orig in parts[0].split(","))

alt_cv = {
    "wo": "ulo", "kwi": "kuli", "kwe": "kule", "kwo": "kulo", "twa": "ta", "twi": "teli", "twe": "te", "two": "to",
    "nwa": "nula", "nwi": "nuli", "nwe": "nule", "nwo": "nulo", "hwa": "fa", "hwi": "fi", "hwe": "fe", "hwo": "fo",
    "mwa": "mula", "mwi": "muli", "mwe": "mule", "mwo": "mulo", "rwa": "rula", "rwi": "ruli", "rwe": "rule", "rwo": "rulo",
    "zwa": "zula", "zwi": "zuli", "zwe": "zule", "zwo": "zulo", "dwa": "da", "dwi": "deli", "dwe": "de", "dwo": "do",
    "bwa": "bula", "bwi": "buli", "bwe": "bule", "bwo": "bulo", "pwa": "pula", "pwi": "puli", "pwe": "pule", "pwo": "pulo",
    "chwa": "tsa", "chwi": "tsi", "chwe": "tse", "chwo": "tso", "jwa": "zula", "jwi": "zuli", "jwe": "zule", "jwo": "zulo",
    "ti": "teli", "tye": "tele", "tya": "telya", "tyu": "telyu", "tyo": "telyo", "tu": "tolu",
    "di": "deli", "dye": "dele", "dya": "delya", "dyu": "delyu", "dyo": "delyo", "du": "dolu",
    "zi": "zuli", "zye": "zulile", "zya": "zulya", "zyu": "zulyu", "zyo": "zulyo",
    "chye": "che", "chya": "cha", "chyu": "chu", "chyo": "cho", "fye": "file", "vye": "vile",
    "shye": "she", "shya": "sha", "shyu": "shu", "shyo": "sho", "shwa": "sha", "shwi": "shi", "shwe": "she", "shwo": "sho",
    "fwa": "fa", "fwi": "fi", "fwe": "fe", "fwo": "fo", "vwa": "va", "vwi": "vi", "vwe": "ve", "vwo": "vo",
    "tswa": "tsa", "tswi": "tsi", "tswe": "tse", "tswo": "tso", "tsye": "tse", "tsya": "tsa", "tsyu": "tsu", "tsyo": "tso",
}

conditional_alt = {
    "ulo": "wo", "kwa": "ka", "kwi": "ki", "kwe": "ke", "kwo": "ko", "swa": "sa", "swi": "si", "swe": "se", "swo": "so",
    "nwa": "na", "nwi": "ni", "nwe": "ne", "nwo": "no", "fa": "ha", "fi": "hi", "fe": "he", "fo": "ho",
    "mwa": "ma", "mwi": "mi", "mwe": "me", "mwo": "mo", "rwa": "ra", "rwi": "ri", "rwe": "re", "rwo": "ro",
    "gwa": "ga", "gwi": "gi", "gwe": "ge", "gwo": "go", "zwa": "za", "zwi": "ji", "zwe": "ze", "zwo": "zo",
    "jwa": "ja", "jwi": "ji", "jwe": "je", "jwo": "jo", "chwa": "cha", "chwi": "chi", "chwe": "che", "chwo": "cho",
    "bwa": "ba", "bwi": "bi", "bwe": "be", "bwo": "bo", "pwa": "pa", "pwi": "pi", "pwe": "pe", "pwo": "po",
    "ye": "e", "kye": "ke", "sye": "se", "che": "te", "nye": "ne", "hye": "he", "mye": "me", "rye": "re", "gye": "ge",
    "je": "ze", "bye": "be", "pye": "pe", "tye": "te", "ti": "chi", "tya": "cha", "tyu": "chu", "tyo": "cho", "tu": "tsu",
    "tsa": "cha", "tsi": "chi", "tse": "che", "tso": "cho", "di": "ji", "dye": "de", "dya": "ja", "dyu": "ju", "dyo": "jo",
    "du": "zu", "zye": "je", "zya": "ja", "zyu": "ju", "zyo": "jo", "fye": "pye", "fya": "pya", "fyu": "pyu", "fyo": "pyo",
    "va": "ba", "vi": "bi", "vu": "bu", "ヴ": "ぶ", "ve": "be", "vo": "bo", "vye": "bye", "vya": "bya", "vyu": "byu", "vyo": "byo",
    "chye": "se", "jye": "ze", "we": "e", "wi": "i", "k": "ku", "t": "to", "p": "pu", "r": "ru", "m": "mu",
}

_END_SOUNDS = ("R", "-", "H", "B", "bre", "息", "吸")


def _s(x):
    """c# string interpolation of a possibly-null string."""
    return "" if x is None else x


def _first_code(s):
    """Encoding.Unicode bytes of the first char -> its utf-16 code unit (throws on an empty string)."""
    c = s[0]
    o = ord(c)
    if o > 0xFFFF:  # an astral char: s[0] in c# is its high surrogate
        o = 0xD800 + ((o - 0x10000) >> 10)
    return o


def _utf16_len(s):
    return sum(2 if ord(c) > 0xFFFF else 1 for c in s)


@phonemizer("KO to JA Phonemizer", "KO to JA", language="KO", openutau_class="OpenUtau.Plugin.Builtin.KOtoJAPhonemizer", author="Lotte V")
class KOtoJAPhonemizer(BaseKoreanPhonemizer):
    def set_up(self, groups):
        ku.romanize_notes(groups, False)

    @staticmethod
    def get_imf(syllable):
        numval = _first_code(syllable)
        numval -= 44032
        i = cdiv(numval, 588)
        numval -= i * 588
        m = cdiv(numval, 28)
        numval -= m * 28
        f = numval
        return [ku._idx(initials, i), ku._idx(medials, m), ku._idx(finals, f)]

    @staticmethod
    def get_imf_from_hint(hint):
        hint_split = hint.split(" ")
        i = hint_split[0] if hint_split[0] in initials + extras else ""
        m = hint_split[0] if not i else ku._idx(hint_split, 1)
        f = hint_split[-1] if (len(hint_split) > 2 or (len(hint_split) == 2 and not i)) else ""
        return [i, m, f]

    @staticmethod
    def get_last_sound_of_alias(lyric):
        last_sound = lyric.split(" ")[-1]
        for sm in re.findall(r"\W", last_sound):
            last_sound = last_sound.replace(sm, "")
        if last_sound not in finals:
            for i in initials:
                if i:
                    last_sound = last_sound.replace(i, "")
        return last_sound

    def _has(self, alias, tone, color):
        return self.singer.try_get_mapped_oto(alias, tone, color) is not None

    @staticmethod
    def _alt(p):
        return to_hiragana(alt_cv[p] if p in alt_cv else p)

    @staticmethod
    def _cond(p):
        return to_hiragana(conditional_alt[p] if p in conditional_alt else p)

    def _batchim(self, second_phoneme, final, tone, color):
        """the 'Adjust Result if note has batchim' block (c# repeats it four times)."""
        has = self._has
        if final == "n":
            if has(f"{second_phoneme} {to_hiragana(final)}", tone, color):
                second_phoneme += f" {to_hiragana(final)}"
            elif has(f"* {to_hiragana(final)}", tone, color):
                second_phoneme = f"* {to_hiragana(final)}"
            else:
                second_phoneme = f"{to_hiragana(final)}"
        else:
            if has(f"{second_phoneme} {final}", tone, color):
                second_phoneme += f" {final}"
            elif has(f"{second_phoneme} {self._alt(final)}", tone, color):
                second_phoneme += f" {self._alt(final)}"
            elif has(f"{self._alt(final)}", tone, color):
                second_phoneme = f"{self._alt(final)}"
            elif has(f"{second_phoneme} {self._cond(final)}", tone, color):
                second_phoneme += f" {self._cond(final)}"
            else:
                second_phoneme = f"{self._cond(final)}"
        return second_phoneme

    def process(self, notes, prev, next, prev_neighbour, next_neighbour, prev_neighbours):
        singer = self.singer
        has = self._has
        note = notes[0]

        def attrs(index):
            a = note.attr(index)
            return (a.voice_color if a.voice_color is not None else self.get_parent_voice_color(),
                    a.tone_shift if a.tone_shift is not None else self.get_parent_tone_shift(),
                    a.alternate if a.alternate is not None else self.get_parent_alternate(), a)

        color, shift, alt, attr = attrs(0)
        color1, shift1, alt1, attr1 = attrs(1)
        color2, shift2, alt2, attr2 = attrs(2)

        romaji2korean = self.convert_romaji_note_to_hangeul(notes, prev_neighbour, next_neighbour)
        if romaji2korean is not None:
            notes = romaji2korean.korean_lyric_notes
            note = notes[0]

        prev_lyric_raw = prev_neighbour.lyric if prev_neighbour is not None else None
        curr_romaji = ku.is_korean_romaji(note.lyric)
        prev_romaji = ku.is_korean_romaji(prev_lyric_raw)
        curr_rom_lyric = ku.try_parse_korean_romaji(note.lyric)
        prev_rom_lyric = ku.try_parse_korean_romaji(prev_lyric_raw)

        # R, -, end breaths
        if note.lyric in _END_SOUNDS:
            curr_phoneme = note.lyric
            if prev_neighbour is None:
                return [Phoneme(curr_phoneme)]
            if has(prev_neighbour.lyric, note.tone + shift, color):
                last_sound = self.get_last_sound_of_alias(prev_neighbour.lyric)
                if has(f"{last_sound} {curr_phoneme}", note.tone + shift, color):
                    curr_phoneme = f"{last_sound} {curr_phoneme}"
            else:
                if not prev_neighbour.phonetic_hint:
                    numval = _first_code(prev_neighbour.lyric)
                    if _utf16_len(prev_neighbour.lyric) == 1 and 44032 <= numval <= 55215:
                        prev_imf = self.get_imf(prev_neighbour.lyric)
                    elif prev_romaji and prev_rom_lyric is not None:
                        prev_imf = self.get_imf(prev_rom_lyric)
                    else:
                        return [Phoneme(curr_phoneme)]
                else:
                    prev_imf = self.get_imf_from_hint(prev_neighbour.phonetic_hint)

                if not prev_imf[2]:
                    m = prev_imf[1]
                    cand = f"{(m[1:] if (m[0] == 'w' or m[0] == 'y') else ('i' if m == 'wi' else m))} {curr_phoneme}"
                    curr_phoneme = cand  # the c# assigns inside the TryGetMappedOto call
                    has(curr_phoneme, note.tone + shift, color)
                elif prev_imf[2] == "n":
                    if has(f"{prev_imf[2]} {curr_phoneme}", note.tone + shift, color):
                        curr_phoneme = f"{prev_imf[2]} {curr_phoneme}"
            o = singer.try_get_mapped_oto(curr_phoneme + alt_str(alt), note.tone + shift, color)
            if o is not None:
                curr_phoneme = o.alias
            else:
                o = singer.try_get_mapped_oto(curr_phoneme, note.tone + shift, color)
                if o is not None:
                    curr_phoneme = o.alias
            return [Phoneme(curr_phoneme)]

        # IMF of the current note
        if not note.phonetic_hint:
            numval = _first_code(note.lyric)
            if _utf16_len(note.lyric) == 1 and 44032 <= numval <= 55215:
                curr_imf = self.get_imf(note.lyric)
            elif curr_romaji and curr_rom_lyric is not None:
                curr_imf = self.get_imf(curr_rom_lyric)
            else:
                return [Phoneme(note.lyric)]
        else:
            curr_imf = self.get_imf_from_hint(note.phonetic_hint)

        curr_phoneme = f"{curr_imf[0]}{curr_imf[1]}"
        A = self._alt
        C = self._cond
        tone = note.tone + shift

        if prev_neighbour is not None and prev_neighbour.lyric != "bre" and has(prev_neighbour.lyric, tone, color):
            last = self.get_last_sound_of_alias(prev_neighbour.lyric)
            p = curr_phoneme
            if has(f"{last} {A(p)}", tone, color):
                curr_phoneme = f"{last} {A(p)}"
            elif has(f"* {A(p)}", tone, color):
                curr_phoneme = f"* {A(p)}"
            elif has(f"- {A(p)}", tone, color):
                curr_phoneme = f"- {A(p)}"
            elif has(f"{A(p)}", tone, color):
                curr_phoneme = f"{A(p)}"
            elif has(f"{last} {C(p)}", tone, color):
                curr_phoneme = f"{last} {C(p)}"
            elif has(f"* {C(p)}", tone, color):
                curr_phoneme = f"* {C(p)}"
            elif has(f"- {C(p)}", tone, color):
                curr_phoneme = f"- {C(p)}"
            else:
                curr_phoneme = f"{C(p)}"
        else:
            if prev_neighbour is None or prev_neighbour.lyric in _END_SOUNDS:
                p = curr_phoneme
                if has(f"- {A(p)}", tone, color):
                    curr_phoneme = f"- {A(p)}"
                elif has(f"{A(p)}", tone, color):
                    curr_phoneme = f"{A(p)}"
                elif has(f"- {C(p)}", tone, color):
                    curr_phoneme = f"- {C(p)}"
                else:
                    curr_phoneme = f"{C(p)}"
            else:
                if not prev_neighbour.phonetic_hint:
                    numval = _first_code(prev_neighbour.lyric)
                    if _utf16_len(prev_neighbour.lyric) == 1 and 44032 <= numval <= 55215:
                        prev_imf = self.get_imf(prev_neighbour.lyric)
                    elif prev_romaji and prev_rom_lyric is not None:
                        prev_imf = self.get_imf(prev_rom_lyric)
                    else:
                        return [Phoneme(note.lyric)]
                else:
                    prev_imf = self.get_imf_from_hint(prev_neighbour.phonetic_hint)
                ptone = prev_neighbour.tone + shift
                prev_batchim = prev_imf[1][1:] if (prev_imf[1][0] == "w" or prev_imf[1][0] == "y") else prev_imf[1]
                if prev_imf[2]:
                    f = prev_imf[2]
                    if f == "n":
                        if has(f"{prev_batchim} {to_hiragana(f)}", ptone, color):
                            prev_batchim += f" {to_hiragana(f)}"
                        elif has(f"* {to_hiragana(f)}", ptone, color):
                            prev_batchim = f"* {to_hiragana(f)}"
                        else:
                            prev_batchim = f"{to_hiragana(f)}"
                    else:
                        if has(f"{prev_batchim} {f}", ptone, color):
                            prev_batchim += f" {f}"
                        elif has(f"{prev_batchim} {A(f)}", ptone, color):
                            prev_batchim += f" {A(f)}"
                        elif has(f"{A(f)}", ptone, color):
                            prev_batchim = f"{A(f)}"
                        elif has(f"{prev_batchim} {C(f)}", ptone, color):
                            prev_batchim += f" {C(f)}"
                        else:
                            prev_batchim = f"{C(f)}"
                p = curr_phoneme
                if prev_imf[2]:
                    if prev_imf[2] in sonorants:
                        if has(f"{prev_imf[2]} {A(p)}", tone, color) or has(f"{prev_imf[2]} {C(p)}", tone, color):
                            prev_connect = prev_imf[2]
                        else:
                            prev_connect = None
                    elif "く" in prev_batchim or "る" in prev_batchim or "む" in prev_batchim or "ぷ" in prev_batchim:
                        prev_connect = "u"
                    elif "と" in prev_batchim:
                        prev_connect = "o"
                    else:
                        if has(f"{A(p)}", tone, color) or has(f"{C(p)}", tone, color):
                            prev_connect = ""
                        elif has(f"- {A(p)}", tone, color) or has(f"- {C(p)}", tone, color):
                            prev_connect = "-"
                        else:
                            prev_connect = None
                else:
                    prev_connect = prev_imf[1][1:] if (prev_imf[1][0] == "w" or prev_imf[1][0] == "y") else prev_imf[1]

                pc = _s(prev_connect)
                if has(f"{pc} {A(p)}", tone, color):
                    curr_phoneme = f"{pc} {A(p)}"
                elif has(f"* {A(p)}", tone, color):
                    curr_phoneme = f"* {A(p)}"
                elif has(f"{A(p)}", tone, color):
                    curr_phoneme = f"{A(p)}"
                elif has(f"{pc} {C(p)}", tone, color):
                    curr_phoneme = f"{pc} {C(p)}"
                elif has(f"* {C(p)}", tone, color):
                    curr_phoneme = f"* {C(p)}"
                else:
                    curr_phoneme = f"{C(p)}"

                cp = curr_phoneme
                tone1 = note.tone + shift1
                if prev_neighbour is not None and (not prev_imf[2] or (prev_imf[2] and prev_imf[2] == "n")) \
                        and (has(f"{A(cp)}", tone1, color1) or has(f"{C(cp)}", tone1, color1)):
                    vc_length = 60
                    end_tick = notes[-1].position + notes[-1].duration
                    total_duration = prev_neighbour.duration
                    o = singer.try_get_mapped_oto(f"{A(cp)}", notes[0].tone + shift1, color1)
                    if o is not None:
                        if o.overlap < 0:
                            vc_length = -self.time_axis.ms_to_tick_at(-(o.preutter - o.overlap), end_tick)
                        else:
                            vc_length = -self.time_axis.ms_to_tick_at(-o.preutter, end_tick)
                    else:
                        o = singer.try_get_mapped_oto(f"{C(cp)}", notes[0].tone + shift1, color1)
                        if o is not None:
                            if o.overlap < 0:
                                vc_length = -self.time_axis.ms_to_tick_at(-(o.preutter - o.overlap), end_tick)
                            else:
                                vc_length = -self.time_axis.ms_to_tick_at(-o.preutter, end_tick)
                    ratio = attr1.consonant_stretch_ratio if attr1.consonant_stretch_ratio is not None else self.get_parent_consonant_stretch_ratio()
                    vc_length = int(round(min(cdiv(total_duration, 2), vc_length * ratio)))  # Convert.ToInt32: half to even

                    if not prev_imf[2]:
                        prev_connect = prev_imf[1][1:] if (prev_imf[1][0] == "w" or prev_imf[1][0] == "y") else prev_imf[1]
                    elif prev_imf[2] == "n":
                        prev_connect = prev_imf[2]

                    consonant = ""
                    a_h = A(cp)
                    c_h = C(cp)
                    con = consonant_lookup.get(a_h[:1] if a_h else "\0")
                    if con is None and len(a_h) >= 2:
                        con = consonant_lookup.get(a_h[:2])
                    if con is not None:
                        consonant = con
                    else:
                        con2 = consonant_lookup.get(c_h[:1] if c_h else "\0")
                        if con2 is not None:
                            consonant = con2
                        elif len(c_h) >= 2 and c_h[:2] in consonant_lookup:
                            consonant = None  # (sic) the c# matches into `con` but assigns `con2`, which is null
                    vc_phoneme = f"{_s(prev_connect)} {_s(consonant)}"
                    # (vcPhonemes / substituteLookup are computed in c# but never used: vcPhoneme is never null)

                    o = singer.try_get_mapped_oto(curr_phoneme + alt_str(alt1), tone1, color1)
                    if o is not None:
                        curr_phoneme = o.alias
                    else:
                        o = singer.try_get_mapped_oto(curr_phoneme, tone1, color1)
                        if o is not None:
                            curr_phoneme = o.alias
                    m = curr_imf[1]
                    second_phoneme = m[1:] if (m[0] == "w" or m[0] == "y") else m
                    if curr_imf[2]:
                        if next_neighbour is None:
                            second_phoneme = self._batchim(second_phoneme, curr_imf[2], tone, color)
                        elif curr_imf[2]:
                            second_phoneme = self._batchim(second_phoneme, curr_imf[2], tone, color)
                        note_length = sum(n.duration for n in notes)
                        second_position = max(note_length - (120 if next_neighbour is None else 180), cdiv(note_length, 2))
                        o = singer.try_get_mapped_oto(curr_phoneme + alt_str(alt1), tone1, color1)
                        if o is not None:
                            curr_phoneme = o.alias
                        else:
                            o = singer.try_get_mapped_oto(curr_phoneme, tone1, color1)
                            if o is not None:
                                curr_phoneme = o.alias
                        o = singer.try_get_mapped_oto(vc_phoneme, ptone, color)
                        if o is not None:
                            vc_phoneme = o.alias
                        o = singer.try_get_mapped_oto(second_phoneme + alt_str(alt2), note.tone + shift2, color2)
                        if o is not None:
                            second_phoneme = o.alias
                        else:
                            o = singer.try_get_mapped_oto(second_phoneme, note.tone + shift2, color2)
                            if o is not None:
                                second_phoneme = o.alias
                        if has(vc_phoneme, tone, color) and has(curr_phoneme, tone, color) and has(second_phoneme, tone, color):
                            return [Phoneme(vc_phoneme, position=-vc_length), Phoneme(curr_phoneme), Phoneme(second_phoneme, position=second_position)]
                    o = singer.try_get_mapped_oto(vc_phoneme, ptone, color)
                    if o is not None:
                        vc_phoneme = o.alias
                    if has(vc_phoneme, tone, color) and has(curr_phoneme, tone, color):
                        return [Phoneme(vc_phoneme, position=-vc_length), Phoneme(curr_phoneme)]

        if not curr_imf[2]:
            o = singer.try_get_mapped_oto(curr_phoneme + alt_str(alt), tone, color)
            if o is not None:
                curr_phoneme = o.alias
            else:
                o = singer.try_get_mapped_oto(curr_phoneme, tone, color)
                if o is not None:
                    curr_phoneme = o.alias
            return [Phoneme(curr_phoneme)]

        m = curr_imf[1]
        second_phoneme = m[1:] if (m[0] == "w" or m[0] == "y") else m
        if next_neighbour is None:
            second_phoneme = self._batchim(second_phoneme, curr_imf[2], tone, color)
        elif curr_imf[2]:
            second_phoneme = self._batchim(second_phoneme, curr_imf[2], tone, color)
        note_length = sum(n.duration for n in notes)
        second_position = max(note_length - (120 if next_neighbour is None else 180), cdiv(note_length, 2))
        o = singer.try_get_mapped_oto(curr_phoneme + alt_str(alt), tone, color)
        if o is not None:
            curr_phoneme = o.alias
        else:
            o = singer.try_get_mapped_oto(curr_phoneme, tone, color)
            if o is not None:
                curr_phoneme = o.alias
        o = singer.try_get_mapped_oto(second_phoneme + alt_str(alt1), note.tone + shift1, color1)
        if o is not None:
            second_phoneme = o.alias
        else:
            o = singer.try_get_mapped_oto(second_phoneme, note.tone + shift1, color1)
            if o is not None:
                second_phoneme = o.alias
        return [Phoneme(curr_phoneme), Phoneme(second_phoneme, position=second_position)]


def to_hiragana(romaji):
    """KOtoJAPhonemizer.ToHiragana: WanaKana.ToHiragana, then ゔ -> ヴ."""
    return _wanakana_to_hiragana(romaji).replace("ゔ", "ヴ")


# ---- wanakana (romaji -> hiragana, default options) ------------------------------------------------

def _build_romaji_tree():
    vowels5 = "aiueo"

    def row(kana):
        return {v: {"": k} for v, k in zip(vowels5, kana)}

    basic = {
        "a": {"": "あ"}, "i": {"": "い"}, "u": {"": "う"}, "e": {"": "え"}, "o": {"": "お"},
        "k": row("かきくけこ"), "s": row("さしすせそ"), "t": row("たちつてと"), "n": row("なにぬねの"), "h": row("はひふへほ"),
        "m": row("まみむめも"), "y": {"a": {"": "や"}, "u": {"": "ゆ"}, "o": {"": "よ"}}, "r": row("らりるれろ"),
        "w": {"a": {"": "わ"}, "i": {"": "ゐ"}, "e": {"": "ゑ"}, "o": {"": "を"}},
        "g": row("がぎぐげご"), "z": row("ざじずぜぞ"), "d": row("だぢづでど"), "b": row("ばびぶべぼ"), "p": row("ぱぴぷぺぽ"),
        "v": {"a": {"": "ゔぁ"}, "i": {"": "ゔぃ"}, "u": {"": "ゔ"}, "e": {"": "ゔぇ"}, "o": {"": "ゔぉ"}},
    }
    tree = basic

    def subtree_of(string):
        t = tree
        for ch in string:
            if ch not in t:
                t[ch] = {}
            t = t[ch]
        return t

    special_symbols = {".": "。", ",": "、", ":": "：", "/": "・", "!": "！", "?": "？", "~": "〜", "-": "ー", "‘": "「", "’": "」",
                       "“": "『", "”": "』", "[": "［", "]": "］", "(": "（", ")": "）", "{": "｛", "}": "｝"}
    consonants_ = {"k": "き", "s": "し", "t": "ち", "n": "に", "h": "ひ", "m": "み", "r": "り", "g": "ぎ", "z": "じ", "d": "ぢ",
                   "b": "び", "p": "ぴ", "v": "ゔ", "q": "く", "f": "ふ"}
    small_y = {"ya": "ゃ", "yi": "ぃ", "yu": "ゅ", "ye": "ぇ", "yo": "ょ"}
    small_vowels = {"a": "ぁ", "i": "ぃ", "u": "ぅ", "e": "ぇ", "o": "ぉ"}
    aliases = {"sh": "sy", "ch": "ty", "cy": "ty", "chy": "ty", "shy": "sy", "j": "zy", "jy": "zy",
               "shi": "si", "chi": "ti", "tsu": "tu", "ji": "zi", "fu": "hu"}
    small_letters = dict({"tu": "っ", "wa": "ゎ", "ka": "ヵ", "ke": "ヶ"}, **small_vowels, **small_y)
    special_cases = {"yi": "い", "wu": "う", "ye": "いぇ", "wi": "うぃ", "we": "うぇ", "kwa": "くぁ", "whu": "う",
                     "tha": "てゃ", "thu": "てゅ", "tho": "てょ", "dha": "でゃ", "dhu": "でゅ", "dho": "でょ"}
    aiueo_constructions = {"wh": "う", "qw": "く", "q": "く", "gw": "ぐ", "sw": "す", "ts": "つ", "th": "て", "tw": "と",
                           "dh": "で", "dw": "ど", "fw": "ふ", "f": "ふ"}

    for consonant, y_kana in consonants_.items():
        for roma, kana in small_y.items():
            subtree_of(consonant + roma)[""] = y_kana + kana
    for symbol, jsymbol in special_symbols.items():
        subtree_of(symbol)[""] = jsymbol
    for consonant, aiueo_kana in aiueo_constructions.items():
        for vowel, kana in small_vowels.items():
            subtree_of(consonant + vowel)[""] = aiueo_kana + kana
    for n_char in ["n", "n'", "xn"]:
        subtree_of(n_char)[""] = "ん"
    tree["c"] = copy.deepcopy(tree["k"])
    for string, alternative in aliases.items():
        parent = subtree_of(string[:-1])
        parent[string[-1]] = copy.deepcopy(subtree_of(alternative))

    def get_alternatives(string):
        out = []
        for alt, roma in list(aliases.items()) + [("c", "k")]:
            if string.startswith(roma):
                out.append(string.replace(roma, alt, 1))  # js String.replace: the first occurrence
        return out

    for kunrei_roma, kana in small_letters.items():
        x_subtree = subtree_of("x" + kunrei_roma)
        x_subtree[""] = kana
        parent = subtree_of("l" + kunrei_roma[:-1])
        parent[kunrei_roma[-1]] = x_subtree
        for alt_roma in get_alternatives(kunrei_roma):
            for prefix in ["l", "x"]:
                alt_parent = subtree_of(prefix + alt_roma[:-1])
                alt_parent[alt_roma[-1]] = subtree_of(prefix + kunrei_roma)
    for string, kana in special_cases.items():
        subtree_of(string)[""] = kana

    def add_tsu(t):
        out = {}
        for key, value in t.items():
            if not key:
                out[key] = f"っ{value}"
            else:
                out[key] = add_tsu(value)
        return out

    for consonant in list(consonants_.keys()) + ["c", "y", "w", "j"]:
        sub = tree[consonant]
        sub[consonant] = add_tsu(sub)
    del tree["n"]["n"]
    return copy.deepcopy(tree)


_ROMAJI_TREE = None


def _apply_mapping(string, root):
    """wanakana applyMapping with convertEnding = true -> list of (start, end, kana)."""
    out = []
    pos = 0
    n = len(string)
    while pos < n:
        first = string[pos]
        tree = dict(root.get(first, {}))
        tree.setdefault("", first)
        if "" not in root.get(first, {}):
            tree[""] = first
        cur = pos + 1
        while True:
            if cur >= n:
                out.append((pos, cur, tree[""]))
                pos = cur
                break
            if len(tree) == 1:
                out.append((pos, cur, tree[""]))
                pos = cur
                break
            ch = string[cur]
            sub = tree.get(ch)
            if sub is None:
                out.append((pos, cur, tree[""]))
                pos = cur
                break
            nxt = dict(sub)
            if "" not in sub:
                nxt[""] = string[pos:cur + 1]  # WanaKanaNet keeps the raw input for a node without a value
            tree = nxt
            cur += 1
    return out


def _to_kana(text):
    global _ROMAJI_TREE
    if _ROMAJI_TREE is None:
        _ROMAJI_TREE = _build_romaji_tree()
    return "".join(k for _, _, k in _apply_mapping(text, _ROMAJI_TREE) if k)


_ROMAJI_RE = re.compile("^[\u0000-\u007fĀāĒēĪīŌōŪū]+$")


def _is_kana(c):
    return "぀" <= c <= "ゟ" or "゠" <= c <= "ヿ"


def _katakana_to_hiragana(text):
    return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in text)


def _wanakana_to_hiragana(text):
    if not text:
        return ""
    has_kana = any(_is_kana(c) for c in text)
    has_romaji = any(_ROMAJI_RE.match(c) for c in text)
    if has_kana and has_romaji:
        return _to_kana(_katakana_to_hiragana(text).lower())
    if _ROMAJI_RE.match(text):
        return _to_kana(text.lower())
    return _katakana_to_hiragana(text)
