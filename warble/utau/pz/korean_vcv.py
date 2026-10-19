"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Plugin.Builtin/KoreanVCVPhonemizer.cs"""

import re

from . import korean_phonemizer_util as ku
from .api import Phoneme, phonemizer
from .base_korean_phonemizer import BaseKoreanPhonemizer

# ㄱ ㄲ ㄴ ㄷ ㄸ ㄹ ㅁ ㅂ ㅃ ㅅ ㅆ ㅇ ㅈ ㅉ ㅊ ㅋ ㅌ ㅍ ㅎ
INITIALS = ["g", "gg", "n", "d", "dd", "r", "m", "b", "bb", "s", "ss", "", "j", "jj", "ch", "k", "t", "p", "h"]
# ㅏ ㅐ ㅑ ㅒ ㅓ ㅔ ㅕ ㅖ ㅗ ㅘ ㅙ ㅚ ㅛ ㅜ ㅝ ㅞ ㅟ ㅠ ㅡ ㅢ ㅣ
MEDIALS = ["a", "e", "ya", "ye", "eo", "e", "yeo", "ye", "o", "wa", "we", "we", "yo", "u", "weo", "we", "wi", "yu", "eu", "eui", "i"]
# - ㄱ ㄲ ㄳ ㄴ ㄵ ㄶ ㄷ ㄹ ㄺ ㄻ ㄼ ㄽ ㄾ ㄿ ㅀ ㅁ ㅂ ㅄ ㅅ ㅆ ㅇ ㅈ ㅊ ㅋ ㅌ ㅍ ㅎ H B bre
FINALS = ["", "k", "k", "k", "n", "n", "n", "t", "l", "l", "l", "l", "l", "l", "l", "l", "m", "p", "p", "t", "t", "ng", "t", "t", "k", "t", "p", "t", "", "", ""]
SONORANTS = ["n", "m", "ng", "l"]
EXTRAS = ["f", "v", "th", "dh", "z", "rr", "kk", "pp", "tt"]
END_LYRICS = ("R", "R2", "-", "H", "B", "bre")

_SYMBOL = re.compile(r"\W")


def _at(arr, i):
    if i < 0 or i >= len(arr):
        raise IndexError("Index was outside the bounds of the array.")
    return arr[i]


def _cdiv(a, b):
    q = abs(a) // abs(b)
    return -q if (a < 0) != (b < 0) else q


def _alt(alt):
    return "" if alt is None else str(alt)


@phonemizer("Korean VCV Phonemizer", "KO VCV", language="KO", openutau_class="OpenUtau.Plugin.Builtin.KoreanVCVPhonemizer", author="ldc")
class KoreanVCVPhonemizer(BaseKoreanPhonemizer):
    def set_up(self, groups):
        ku.romanize_notes(groups, False)

    @staticmethod
    def get_imf(syllable):
        numval = ord(syllable[0]) - 44032
        i = _cdiv(numval, 588)
        numval -= i * 588
        m = _cdiv(numval, 28)
        numval -= m * 28
        f = numval
        return [_at(INITIALS, i), _at(MEDIALS, m), _at(FINALS, f)]

    @staticmethod
    def get_imf_from_hint(hint):
        hint_split = hint.split(" ")
        i = hint_split[0] if hint_split[0] in INITIALS + EXTRAS else ""
        m = hint_split[0] if not i else _at(hint_split, 1)
        f = hint_split[-1] if (len(hint_split) > 2 or (len(hint_split) == 2 and not i)) else ""
        if i in ("kk", "pp", "tt"):
            i = i.replace("k", "g").replace("p", "b").replace("t", "d")
        if m in ("oe", "oi"):
            m = "we"
        if m == "ui":
            m = "eui"
        if m in ("ae", "wae", "yae"):
            m = m.replace("ae", "e")
        return [i, m, f]

    @staticmethod
    def get_last_sound_of_alias(lyric):
        last_sound = lyric.split(" ")[-1]
        for match in _SYMBOL.findall(last_sound):
            last_sound = last_sound.replace(match, "")
        if last_sound not in FINALS:
            for i in INITIALS:
                if i:
                    last_sound = last_sound.replace(i, "")
        return last_sound

    def _has(self, alias, tone, color):
        return self.singer.try_get_mapped_oto(alias, tone, color) is not None

    @staticmethod
    def _is_hangeul_syllable(lyric):
        numval = ord(_at(lyric, 0))
        return len(lyric) == 1 and 44032 <= numval <= 55215

    def process(self, notes, prev, next, prev_neighbour, next_neighbour, prev_neighbours):
        note = notes[0]
        attr = note.attr(0)
        color = attr.voice_color if attr.voice_color is not None else self.get_parent_voice_color()
        shift = attr.tone_shift if attr.tone_shift is not None else self.get_parent_tone_shift()
        alt = attr.alternate if attr.alternate is not None else self.get_parent_alternate()
        attr1 = note.attr(1)
        color1 = attr1.voice_color if attr1.voice_color is not None else self.get_parent_voice_color()
        shift1 = attr1.tone_shift if attr1.tone_shift is not None else self.get_parent_tone_shift()
        alt1 = attr1.alternate if attr1.alternate is not None else self.get_parent_alternate()
        singer = self.singer

        romaji2korean = self.convert_romaji_note_to_hangeul(notes, prev_neighbour, next_neighbour)
        if romaji2korean is not None:
            notes = romaji2korean.korean_lyric_notes
            note = notes[0]

        prev_lyric = prev_neighbour.lyric if prev_neighbour is not None else None
        prev_hint = prev_neighbour.phonetic_hint if prev_neighbour is not None else None
        curr_romaji = ku.is_korean_romaji(note.lyric)
        prev_romaji = ku.is_korean_romaji(prev_lyric)
        curr_rom_lyric = ku.try_parse_korean_romaji(note.lyric)
        prev_rom_lyric = ku.try_parse_korean_romaji(prev_lyric)

        if note.lyric in END_LYRICS:
            curr_phoneme = note.lyric
            if prev_neighbour is None:
                return [Phoneme(curr_phoneme)]
            if self._has(prev_lyric, note.tone, color):
                last_sound = self.get_last_sound_of_alias(prev_lyric)
                curr_phoneme = f"{last_sound.upper() if not self._has(f'{last_sound} {curr_phoneme}', note.tone, color) else last_sound} {curr_phoneme}"
            else:
                if not prev_hint:
                    if self._is_hangeul_syllable(prev_lyric):
                        prev_imf = self.get_imf(prev_lyric)
                    elif prev_romaji and prev_rom_lyric is not None:
                        prev_imf = self.get_imf(prev_rom_lyric)
                    else:
                        return [Phoneme(curr_phoneme)]
                else:
                    prev_imf = self.get_imf_from_hint(prev_hint)
                if not prev_imf[2]:
                    m = prev_imf[1]
                    v = m[1:] if (_at(m, 0) == "w" or m[0] == "y" or m == "oi") else ("i" if m in ("eui", "ui") else m)
                    curr_phoneme = f"{v} {curr_phoneme}"
                else:
                    f = prev_imf[2]
                    curr_phoneme = f"{f.upper() if not self._has(f'{f} {curr_phoneme}', note.tone, color) else f} {curr_phoneme}"
            o = singer.try_get_mapped_oto(curr_phoneme + _alt(alt), note.tone + shift, color)
            if o is not None:
                curr_phoneme = o.alias
            else:
                o = singer.try_get_mapped_oto(curr_phoneme, note.tone + shift, color)
                if o is not None:
                    curr_phoneme = o.alias
            return [Phoneme(curr_phoneme)]

        if not note.phonetic_hint:
            if self._is_hangeul_syllable(note.lyric):
                curr_imf = self.get_imf(note.lyric)
            elif curr_romaji and curr_rom_lyric is not None:
                curr_imf = self.get_imf(curr_rom_lyric)
            else:
                return [Phoneme(note.lyric)]
        else:
            curr_imf = self.get_imf_from_hint(note.phonetic_hint)

        curr_phoneme = f"{curr_imf[0]}{curr_imf[1]}"
        if curr_imf[0] in ("gg", "dd", "bb"):
            if not self._has(f"- {curr_imf[0]}{curr_imf[1]}", note.tone + shift, color):
                curr_phoneme = f"{curr_imf[0].replace('g', 'k').replace('d', 't').replace('b', 'p')}{curr_imf[1]}"
        if curr_imf[1] == "eui":
            if not self._has("- eui", note.tone + shift, color):
                curr_phoneme = f"{curr_imf[0]}ui"

        if prev_neighbour is not None and prev_lyric != "bre" and self._has(prev_lyric, note.tone + shift, color):
            curr_phoneme = f"{self.get_last_sound_of_alias(prev_lyric)} {curr_phoneme}"
        else:
            if prev_neighbour is None or prev_lyric in END_LYRICS:
                curr_phoneme = f"- {curr_phoneme}"
            else:
                if not prev_hint:
                    if self._is_hangeul_syllable(prev_lyric):
                        prev_imf = self.get_imf(prev_lyric)
                    elif prev_romaji and prev_rom_lyric is not None:
                        prev_imf = self.get_imf(prev_rom_lyric)
                    else:
                        return [Phoneme(note.lyric)]
                else:
                    prev_imf = self.get_imf_from_hint(prev_hint)

                if prev_imf[2]:
                    if prev_imf[2] in SONORANTS:
                        if self._has(f"{prev_imf[2]} {curr_phoneme}", note.tone + shift, color):
                            prev_connect = prev_imf[2]
                        else:
                            prev_connect = prev_imf[2].upper()
                    else:
                        prev_connect = "-"
                else:
                    m = prev_imf[1]
                    if _at(m, 0) == "w" or m[0] == "y" or m == "oe":
                        prev_connect = m[1:]
                    elif m == "eui":
                        prev_connect = "i"
                    else:
                        prev_connect = m
                curr_phoneme = f"{prev_connect} {curr_phoneme}"

        if not curr_imf[2]:
            o = singer.try_get_mapped_oto(curr_phoneme + _alt(alt), note.tone + shift, color)
            if o is not None:
                curr_phoneme = o.alias
            else:
                o = singer.try_get_mapped_oto(curr_phoneme, note.tone + shift, color)
                if o is not None:
                    curr_phoneme = o.alias
            return [Phoneme(curr_phoneme)]

        if curr_imf[1] == "eui":
            curr_imf[1] = "ui"
        m = curr_imf[1]
        second_phoneme = m[1:] if (_at(m, 0) == "w" or m[0] == "y" or m == "oe" or m == "ui") else m

        if next_neighbour is None:
            if not curr_imf[2]:
                second_phoneme += " R"
            else:
                if self._has(f"{second_phoneme} {curr_imf[2]}", note.tone + shift1, color1):
                    second_phoneme += f" {curr_imf[2]}"
                else:
                    second_phoneme += f" {curr_imf[2].upper()}"
        elif curr_imf[2]:
            if self._has(f"{second_phoneme} {curr_imf[2]}", note.tone + shift1, color1):
                second_phoneme += f" {curr_imf[2]}"
            else:
                second_phoneme += f" {curr_imf[2].upper()}"

        note_length = sum(n.duration for n in notes)
        second_position = max(note_length - (120 if next_neighbour is None else 180), _cdiv(note_length, 2))

        o = singer.try_get_mapped_oto(curr_phoneme + _alt(alt), note.tone + shift, color)
        if o is not None:
            curr_phoneme = o.alias
        else:
            o = singer.try_get_mapped_oto(curr_phoneme, note.tone + shift, color)
            if o is not None:
                curr_phoneme = o.alias
        o = singer.try_get_mapped_oto(second_phoneme + _alt(alt1), note.tone + shift1, color1)
        if o is not None:
            second_phoneme = o.alias
        else:
            o = singer.try_get_mapped_oto(second_phoneme, note.tone + shift1, color1)
            if o is not None:
                second_phoneme = o.alias

        return [Phoneme(curr_phoneme), Phoneme(second_phoneme, position=second_position)]
