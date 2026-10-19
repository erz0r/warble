"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Plugin.Builtin/BaseKoreanPhonemizer.cs

base for the korean phonemizers: phoneme variation via korean_phonemizer_util, FindInOto with
voice color / alternate, phonetic hint rendering and romaji -> hangeul conversion.

the c# GenerateResult overloads get distinct names. c# overload resolution prefers the candidate
that needs no default arguments, so a call site maps like this:
  GenerateResult(a)                                -> generate_result(a)
  GenerateResult(a, b, total)                      -> generate_result2(a, b, total)            (divider 3)
  GenerateResult(a, b, total, x)                   -> generate_result2(a, b, total, x)         (x = divider)
  GenerateResult(a, b, total, pos, div)            -> generate_result2p(a, b, total, pos, div)
  GenerateResult(a, b, c, total)                   -> generate_result3(a, b, c, total)
  GenerateResult(a, b, c, total, x, y)             -> generate_result3(a, b, c, total, x, y)   (both dividers)
  GenerateResult(a, b, c, total, pos, x, y)        -> generate_result3p(a, b, c, total, pos, x, y)
"""

import dataclasses

from . import korean_phonemizer_util as ku
from .api import Phoneme, Phonemizer


def cdiv(a, b):
    """c# integer division (truncates toward zero)."""
    q = abs(a) // abs(b)
    return -q if (a < 0) != (b < 0) else q


class ProcessResult:
    def __init__(self, notes, prev_note, next_note):
        self.korean_lyric_notes = notes
        self.korean_lyric_prev_note = prev_note
        self.korean_lyric_next_note = next_note


class BaseKoreanPhonemizer(Phonemizer):
    vc_length_short = 90

    PLAIN_VOWELS = ["ㅏ", "ㅣ", "ㅜ", "ㅔ", "ㅗ", "ㅡ", "ㅓ", "ㅢ"]
    SOFT_BATCHIMS = ["ㄴ", "ㄹ", "ㅇ"]
    HARD_BATCHIMS = ["ㄱ", "ㄷ", "ㅂ", "ㅁ"]

    def additional_test(self, lyric):
        return False

    def find_in_oto(self, singer, phoneme, note, null_if_not_found=False):
        attr = note.attr(0)
        color = attr.voice_color if attr.voice_color is not None else self.get_parent_voice_color()
        tone_shift = attr.tone_shift if attr.tone_shift is not None else self.get_parent_tone_shift()
        alt = attr.alternate if attr.alternate is not None else self.get_parent_alternate()
        if phoneme == "":
            return phoneme
        o = singer.try_get_mapped_oto(phoneme + ("" if alt is None else str(alt)), note.tone + tone_shift, color)
        if o is not None:
            return o.alias
        o = singer.try_get_mapped_oto(phoneme, note.tone + tone_shift, color)
        if o is not None:
            return o.alias
        o = singer.try_get_mapped_oto(phoneme, note.tone, color)
        if o is not None:
            return o.alias
        if null_if_not_found:
            return None
        return phoneme

    def convert_phonemes(self, notes, prev, next, prev_neighbour, next_neighbour, prev_neighbours):
        return [Phoneme("")]

    def generate_end_sound(self, notes, prev, next, prev_neighbour, next_neighbour, prev_neighbours):
        return [Phoneme("")]

    # ---- GenerateResult overloads -------------------------------------------------------------
    @staticmethod
    def generate_result(first_phoneme):
        return [Phoneme(first_phoneme)]

    @staticmethod
    def generate_result2(first_phoneme, second_phoneme, total_duration, total_duration_divider=3):
        return [Phoneme(first_phoneme), Phoneme(second_phoneme, position=total_duration - cdiv(total_duration, total_duration_divider))]

    @staticmethod
    def generate_result2p(first_phoneme, second_phoneme, total_duration, second_phoneme_position, total_duration_divider=3):
        return [Phoneme(first_phoneme),
                Phoneme(second_phoneme, position=total_duration - min(cdiv(total_duration, total_duration_divider), second_phoneme_position))]

    @staticmethod
    def generate_result3(first_phoneme, second_phoneme, third_phoneme, total_duration, second_total_duration_divider=3, third_total_duration_divider=8):
        return [Phoneme(first_phoneme),
                Phoneme(second_phoneme, position=total_duration - cdiv(total_duration, second_total_duration_divider)),
                Phoneme(third_phoneme, position=total_duration - cdiv(total_duration, third_total_duration_divider))]

    @staticmethod
    def generate_result3p(first_phoneme, second_phoneme, third_phoneme, total_duration, second_phoneme_position,
                          second_total_duration_divider=3, third_total_duration_divider=8):
        return [Phoneme(first_phoneme),
                Phoneme(second_phoneme, position=total_duration - min(cdiv(total_duration, second_total_duration_divider), second_phoneme_position)),
                Phoneme(third_phoneme, position=total_duration - cdiv(total_duration, third_total_duration_divider))]

    # ---- romaji -> hangeul ----------------------------------------------------------------------
    @staticmethod
    def convert_romaji_note_to_hangeul(notes, prev_note, next_note):
        note = notes[0]
        lyric = note.lyric
        if ku.is_korean_romaji(lyric):
            # like c#, this replaces the note in the caller's group array
            notes[0] = dataclasses.replace(note, lyric=ku.try_parse_korean_romaji(lyric))
            prev_note_new = prev_note
            next_note_new = next_note
            if prev_note is not None:
                ku.is_hangeul(prev_note.lyric)  # c# tests IsHangeul(...) != null, which is always true
                prev_note_new = dataclasses.replace(prev_note, lyric=ku.try_parse_korean_romaji(prev_note.lyric))
                if next_note is not None:
                    next_note_new = dataclasses.replace(next_note, lyric=ku.try_parse_korean_romaji(next_note.lyric))
            return ProcessResult(notes, prev_note_new, next_note_new)
        return None

    # ---- phonetic hints ----------------------------------------------------------------------
    def render_phonetic_hint(self, singer, note, total_duration):
        phonetic_hint = note.phonetic_hint
        if phonetic_hint is None:
            return None
        phonetic_hints = phonetic_hint.split(",")
        n = len(phonetic_hints)
        phonemes = [None] * n

        vv = {}
        vv_source = ["a", "i", "u", "e", "o", "eo", "eu"]
        for i in range(7):
            for j in range(6, -1, -1):
                vv[f"{vv_source[i]} {vv_source[j]}"] = f"{vv_source[j]}"
                vv[f"{vv_source[j]}"] = f"{vv_source[i]} {vv_source[j]}"

        for i in range(n):
            h = phonetic_hints[i].strip()
            alias = self.find_in_oto(singer, h, note, True)
            if alias is not None:
                if i == 0:
                    phonemes[i] = Phoneme(alias)
                elif i == n - 1 and (h.endswith("-") or h.endswith("R")):
                    phonemes[i] = Phoneme(alias, position=total_duration - min(self.vc_length_short, cdiv(total_duration, 8)))
                elif n == 2:
                    phonemes[i] = Phoneme(alias, position=total_duration - cdiv(total_duration, 3))
                else:
                    phonemes[i] = Phoneme(alias, position=total_duration - (cdiv(total_duration, n) * (n - i)))
            elif h in vv:
                if n == 2:
                    phonemes[i] = Phoneme(self.find_in_oto(singer, vv[h], note), position=total_duration - cdiv(total_duration, 3))
                else:
                    phonemes[i] = Phoneme(self.find_in_oto(singer, vv[h], note), position=total_duration - (cdiv(total_duration, n) * (n - i)))
            else:
                phonemes[i] = Phoneme(h, position=total_duration - (cdiv(total_duration, n) * (n - i)))
        return phonemes

    def process(self, notes, prev, next, prev_neighbour, next_neighbour, prev_neighbours):
        note = notes[0]
        lyric = note.lyric
        total_duration = sum(n.duration for n in notes)

        phonetic_hint = self.render_phonetic_hint(self.singer, note, total_duration)
        if phonetic_hint is not None:
            return phonetic_hint

        romaji2korean = self.convert_romaji_note_to_hangeul(notes, prev_neighbour, next_neighbour)
        if romaji2korean is not None:
            return self.convert_phonemes(romaji2korean.korean_lyric_notes, prev, next, romaji2korean.korean_lyric_prev_note,
                                         romaji2korean.korean_lyric_next_note, prev_neighbours)

        if ku.is_hangeul(lyric) or (not ku.is_hangeul(lyric) and self.additional_test(lyric)):
            return self.convert_phonemes(notes, prev, next, prev_neighbour, next_neighbour, prev_neighbours)
        return self.generate_end_sound(notes, prev, next, prev_neighbour, next_neighbour, prev_neighbours)
