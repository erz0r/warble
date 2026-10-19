"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Plugin.Builtin/KoreanCVCCVPhonemizer.cs"""

from . import korean_phonemizer_util as ku
from .api import Phoneme, phonemizer
from .base_korean_phonemizer import BaseKoreanPhonemizer, cdiv

INITIAL_CONSONANTS_TABLE = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
VOWELS_TABLE = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
Y_VOWELS_TABLE = "ㅣㅑㅖㅛㅠㅕ"
LAST_CONSONANTS_TABLE = "　ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"

UNICODE_KOREAN_BASE = 0xAC00
UNICODE_KOREAN_LAST = 0xD79F

# TYPE_FLAG
(VC_CV, VRC_CV, VC_RCV, VC_NCV, VC_NRCV, VRC_NCV, VC_CV_ADDED_Y, VCC_CV, VCC_CV_ADDED_Y, VC_CCV, VC_CCV_ADDED_Y, _VCV, CV) = range(13)

TYPE_TABLE = [
    [_VCV, VRC_CV, _VCV, _VCV, VRC_CV, _VCV, _VCV, _VCV, VRC_CV, _VCV, VC_CV_ADDED_Y, _VCV, _VCV, VRC_CV, VRC_CV, VRC_CV, VRC_CV, VRC_CV, _VCV],  # 받침누락
    [VC_NCV, VC_CV, VC_NCV, VC_NCV, VC_CV, VC_NCV, VC_NCV, VC_NCV, VC_CV, VCC_CV_ADDED_Y, VCC_CV_ADDED_Y, CV, VC_NCV, VC_CV, VC_CV, VC_CV, VC_CV, VC_CV, VC_NCV],  # ㄱ
    [VC_NCV, VC_CV, VC_NCV, VC_NCV, VC_CV, VC_NCV, VC_NCV, VC_NCV, VC_CV, VCC_CV_ADDED_Y, VCC_CV_ADDED_Y, VC_RCV, VC_NCV, VC_CV, VC_CV, VC_CV, VC_CV, VC_CV, VC_NCV],  # ㄲ
    [VC_NCV, VC_CV, VC_NCV, VC_NCV, VC_CV, VC_NCV, VC_NCV, VC_NCV, VC_CV, VCC_CV_ADDED_Y, VCC_CV_ADDED_Y, VC_NRCV, VC_NCV, VC_CV, VC_CV, VC_CV, VC_CV, VC_CV, VC_NCV],  # ㄳ
    [VC_CCV, VCC_CV, VC_CCV, VC_CCV, VC_CCV, VC_CCV, VC_CCV, VC_CCV, VCC_CV, VC_CCV, VCC_CV_ADDED_Y, CV, VC_CCV, VCC_CV, VCC_CV, VCC_CV, VCC_CV, VCC_CV, VC_CCV],  # ㄴ
    [VC_CCV, VCC_CV, VC_CCV, VC_CCV, VC_CCV, VC_CCV, VC_CCV, VC_CCV, VCC_CV, VC_CCV, VCC_CV_ADDED_Y, CV, VC_CCV, VCC_CV, VCC_CV, VCC_CV, VCC_CV, VCC_CV, VC_CCV],  # ㄵ
    [VC_CCV, VCC_CV, VC_CCV, VC_CCV, VC_CCV, VC_CCV, VC_CCV, VC_CCV, VCC_CV, VC_CCV, VCC_CV_ADDED_Y, CV, VC_CCV, VCC_CV, VCC_CV, VCC_CV, VCC_CV, VCC_CV, VC_CCV],  # ㄶ
    [VC_NCV, VC_CV, VC_NCV, VC_NCV, VC_CV, VC_NCV, VC_NCV, VC_NCV, VC_CV, VC_CV, VC_CV_ADDED_Y, CV, VC_NCV, VC_CV, VC_CV, VC_CV, VC_CV, VC_CV, VC_NCV],  # ㄷ
    [VC_CCV, VCC_CV, VC_CCV, VC_CCV, VC_CCV, VC_CCV, VC_CCV, VC_CCV, VCC_CV, VC_CCV, VC_CCV_ADDED_Y, CV, VC_CCV, VCC_CV, VCC_CV, VCC_CV, VCC_CV, VCC_CV, VC_CCV],  # ㄹ
    [VC_CCV, VCC_CV, VC_CCV, VC_CCV, VC_CCV, VC_CCV, VC_CCV, VC_CCV, VCC_CV, VC_CCV, VC_CCV_ADDED_Y, VC_NRCV, VC_CCV, VCC_CV, VCC_CV, VCC_CV, VCC_CV, VCC_CV, VC_CCV],  # ㄺ
    [VC_CCV, VCC_CV, VC_CCV, VC_CCV, VC_CCV, VC_CCV, VC_CCV, VC_CCV, VCC_CV, VC_CCV, VC_CCV_ADDED_Y, VC_NRCV, VC_CCV, VCC_CV, VCC_CV, VCC_CV, VCC_CV, VCC_CV, VC_CCV],  # ㄼ
    [VC_CCV, VCC_CV, VC_CCV, VC_CCV, VC_CCV, VC_CCV, VC_CCV, VC_CCV, VCC_CV, VC_CCV, VC_CCV_ADDED_Y, VC_NRCV, VC_CCV, VCC_CV, VCC_CV, VCC_CV, VCC_CV, VCC_CV, VC_CCV],  # ㄻ
    [VC_CCV, VCC_CV, VC_CCV, VC_CCV, VC_CCV, VC_CCV, VC_CCV, VC_CCV, VCC_CV, VC_CCV, VC_CCV_ADDED_Y, VC_NRCV, VC_CCV, VCC_CV, VCC_CV, VCC_CV, VCC_CV, VCC_CV, VC_CCV],  # ㄽ
    [VC_CCV, VCC_CV, VC_CCV, VC_CCV, VC_CCV, VC_CCV, VC_CCV, VC_CCV, VCC_CV, VC_CCV, VC_CCV_ADDED_Y, VC_NRCV, VC_CCV, VCC_CV, VCC_CV, VCC_CV, VCC_CV, VCC_CV, VC_CCV],  # ㄾ
    [VC_CCV, VCC_CV, VC_CCV, VC_CCV, VC_CCV, VC_CCV, VC_CCV, VC_CCV, VCC_CV, VC_CCV, VC_CCV_ADDED_Y, VC_NRCV, VC_CCV, VCC_CV, VCC_CV, VCC_CV, VCC_CV, VCC_CV, VC_CCV],  # ㄿ
    [VC_CCV, VCC_CV, VC_CCV, VC_CCV, VC_CCV, VC_CCV, VC_CCV, VC_CCV, VCC_CV, VC_CCV, VC_CCV_ADDED_Y, VC_NRCV, VC_CCV, VCC_CV, VCC_CV, VCC_CV, VCC_CV, VCC_CV, VC_CCV],  # ㅀ
    [VC_CCV, VCC_CV, VC_CCV, VC_CCV, VC_CCV, VC_CCV, VC_CCV, VC_CCV, VCC_CV, VC_CCV, VC_CCV_ADDED_Y, CV, VC_CCV, VCC_CV, VCC_CV, VCC_CV, VCC_CV, VCC_CV, VC_CCV],  # ㅁ
    [VC_NCV, VC_CV, VC_NCV, VC_NCV, VC_CV, VC_NCV, VC_NCV, VC_NCV, VC_CV, VCC_CV, VCC_CV_ADDED_Y, CV, VC_NCV, VC_CV, VC_CV, VC_CV, VC_CV, VC_CV, VC_NCV],  # ㅂ
    [VC_NCV, VC_CV, VC_NCV, VC_NCV, VC_CV, VC_NCV, VC_NCV, VC_NCV, VC_CV, VCC_CV, VCC_CV_ADDED_Y, VC_NRCV, VC_NCV, VC_CV, VC_CV, VC_CV, VC_CV, VC_CV, VC_NCV],  # ㅄ
    [VC_NCV, VC_CV, VC_NCV, VC_NCV, VC_CV, VC_NCV, VC_NCV, VC_NCV, VC_CV, VC_CV, VC_CV_ADDED_Y, CV, VC_NCV, VC_CV, VC_CV, VC_CV, VC_CV, VC_CV, VC_NCV],  # ㅅ
    [VRC_NCV, VRC_NCV, VRC_NCV, VRC_NCV, VRC_NCV, VRC_NCV, VRC_NCV, VRC_NCV, VRC_NCV, VRC_NCV, VRC_NCV, VC_RCV, VRC_NCV, VRC_NCV, VRC_NCV, VRC_NCV, VRC_NCV, VRC_NCV, VRC_NCV],  # ㅆ
    [VC_CCV, VCC_CV, VCC_CV, VC_CCV, VC_CCV, VCC_CV, VC_CCV, VC_CCV, VC_CV, VCC_CV, VCC_CV_ADDED_Y, VC_CCV, VC_CCV, VC_CV, VCC_CV, VCC_CV, VCC_CV, VCC_CV, VC_CCV],  # ㅇ
    [VC_NCV, VC_CV, VC_NCV, VC_NCV, VC_CV, VC_NCV, VC_NCV, VC_NCV, VC_CV, VCC_CV, VC_CV_ADDED_Y, CV, VC_NCV, VC_CV, VC_CV, VC_CV, VC_CV, VC_CV, VC_NCV],  # ㅈ
    [VC_NCV, VC_CV, VC_NCV, VC_NCV, VC_CV, VC_NCV, VC_NCV, VC_NCV, VC_CV, VCC_CV, VC_CV_ADDED_Y, CV, VC_NCV, VC_CV, VC_CV, VC_CV, VC_CV, VC_CV, VC_NCV],  # ㅊ
    [VC_NCV, VC_CV, VC_NCV, VC_NCV, VC_CV, VC_NCV, VC_NCV, VC_NCV, VC_CV, VCC_CV, VC_CV_ADDED_Y, VC_NRCV, VC_NCV, VC_CV, VC_CV, VC_CV, VC_CV, VC_CV, VC_NCV],  # ㅋ
    [VC_NCV, VC_CV, VC_NCV, VC_NCV, VC_CV, VC_NCV, VC_NCV, VC_NCV, VC_CV, VCC_CV, VC_CV_ADDED_Y, VC_NRCV, VC_NCV, VC_CV, VC_CV, VC_CV, VC_CV, VC_CV, VC_NCV],  # ㅌ
    [VC_NCV, VC_CV, VC_NCV, VC_NCV, VC_CV, VC_NCV, VC_NCV, VC_NCV, VC_CV, VCC_CV, VCC_CV_ADDED_Y, VC_NRCV, VC_NCV, VC_CV, VC_CV, VC_CV, VC_CV, VC_CV, VC_NCV],  # ㅍ
    [VC_NCV, VC_CV, VC_NCV, VC_NCV, VC_CV, VC_NCV, VC_NCV, VC_NCV, VC_CV, VC_CV, VC_CV_ADDED_Y, CV, VC_NCV, VC_CV, VC_CV, VC_CV, VC_CV, VC_CV, VC_NCV],  # ㅎ
    # ㄱ ㄲ ㄴ ㄷ ㄸ ㄹ ㅁ ㅂ ㅃ ㅅ ㅆ ㅇ ㅈ ㅉ ㅊ ㅋ ㅌ ㅍ ㅎ
]

CONTINUOUS_INITIAL_CONSONANTS = ["g=ㄱ,ㄺ", "gg=ㄲ", "n=ㄴ,ㄵ,ㄶ", "d=ㄷ", "dd=ㄸ", "r=ㄹ", "m=ㅁ,ㄻ", "b=ㅂ,ㄼ", "bb=ㅃ", "s=ㅅ,ㅄ,ㄽ,ㄳ", "ss=ㅆ", "=ㅇ",
                                 "j=ㅈ", "jj=ㅉ", "ch=ㅊ", "k=ㅋ", "t=ㅌ", "p=ㅍ,ㄿ", "h=ㅎ,ㅀ"]
CCV_CONTINUOUS_INITIAL_CONSONANTS = ["g=ㄱ", "gg=ㄲ", "n=ㄴ", "d=ㄷ", "dd=ㄸ", "l=ㄹ,ㄺ,ㄼ,ㄻ,ㄽ,ㄾ,ㄿ,ㅀ", "m=ㅁ", "b=ㅂ", "bb=ㅃ", "s=ㅅ", "ss=ㅆ", "=ㅇ",
                                     "j=ㅈ", "jj=ㅉ", "ch=ㅊ", "k=ㅋ", "t=ㅌ", "p=ㅍ", "h=ㅎ"]
VRC_CONTINUOUS_INITIAL_CONSONANTS = ["gg=ㄱ,ㄲ", "n=ㄴ,ㄵ,ㄶ", "dd=ㄷ,ㄸ", "r=ㄹ", "m=ㅁ", "d=ㅎ", "bb=ㅂ,ㅃ", "ss=ㅅ,ㅆ", "=ㅇ", "jj=ㅈ,ㅉ", "ch=ㅊ",
                                     "k=ㅋ", "t=ㅌ", "p=ㅍ"]
VOWELS = ["a=ㅏ", "ya=ㅑ", "eo=ㅓ", "yeo=ㅕ", "o=ㅗ", "yo=ㅛ", "u=ㅜ", "yu=ㅠ", "eu=ㅡ", "i=ㅣ", "e=ㅔ,ㅐ", "ye=ㅖ,ㅒ", "eui=ㅢ", "wa=ㅘ", "weo=ㅝ",
          "we=ㅞ,ㅙ,ㅚ", "wi=ㅟ"]
SUBSEQUENT_VOWELS = ["a=ㅏ,ㅑ,ㅘ", "eo=ㅓ,ㅕ,ㅝ", "o=ㅗ,ㅛ", "u=ㅜ,ㅠ", "eu=ㅡ", "e=ㅔ,ㅐ,ㅞ,ㅙ,ㅚ,ㅖ,ㅒ", "i=ㅣ,ㅢ,ㅟ"]
LAST_CONSONANTS = ["K=ㄱ,ㅋ,ㄲ,ㄳ", "T=ㅅ,ㅈ,ㅌ,ㄷ,ㅆ,ㅎ,ㅊ,ㄸ", "P=ㅂ,ㅍ,ㅃ,ㅄ", "m=ㅁ", "n=ㄴ,ㄵ", "ng=ㅇ", "l=ㄹ,ㄺ,ㄻ,ㄼ,ㄽ,ㄾ,ㄿ,ㅀ", "-=　"]
VC_LAST_CONSONANTS = ["k=ㄱ,ㅋ,ㄲ,ㄳ", "t=ㅅ,ㅈ,ㅌ,ㄸ,ㅊ,ㅉ,ㄷ,ㅎ", "p=ㅍ,ㅃ,ㅂ,ㅄ", "m=ㅁ", "n=ㄴ,ㄵ,ㄶ", "ng=ㅇ", "l=ㄹ,ㄺ,ㄻ,ㄼ,ㄽ,ㄾ,ㄿ,ㅀ", "ss=ㅆ"]
VRC_LAST_CONSONANTS = ["k=ㄱ,ㅋ,ㄲ,ㄳ", "t=ㅅ,ㅈ,ㅌ,ㄸ,ㅊ,ㅉ,ㄷ,ㅎ,ㅆ", "p=ㅍ,ㅃ,ㅂ,ㅄ", "m=ㅁ", "n=ㄴ,ㄵ,ㄶ", "ng=ㅇ", "l=ㄹ,ㄺ,ㄻ,ㄼ,ㄽ,ㄾ,ㄿ,ㅀ"]


def _table(lines):
    out = {}
    for line in lines:
        parts = line.split("=")
        for cv in parts[1].split(","):
            if cv in out:
                raise ValueError(f"duplicate key {cv}")  # ToDictionary throws on duplicates
            out[cv] = parts[0]
    return out


initial_consonant_lookup = _table(CONTINUOUS_INITIAL_CONSONANTS)
ccv_continuous_initial_consonants_lookup = _table(CCV_CONTINUOUS_INITIAL_CONSONANTS)
vrc_initial_consonant_lookup = _table(VRC_CONTINUOUS_INITIAL_CONSONANTS)
vowel_lookup = _table(VOWELS)
subsequent_vowel_lookup = _table(SUBSEQUENT_VOWELS)
last_consonants_lookup = _table(LAST_CONSONANTS)
vc_last_consonants_lookup = _table(VC_LAST_CONSONANTS)
vrc_last_consonants_lookup = _table(VRC_LAST_CONSONANTS)


def _get(d, k):
    """TryGetValue(out var x) then $"{x}": a miss interpolates as ''."""
    v = d.get(k)
    return "" if v is None else v


def _ch(s, i):
    if i < 0 or i >= len(s):
        raise IndexError("Index was outside the bounds of the array.")
    return s[i]


def separate_hangul(letter):
    if letter == "\0":
        return ["　", "　", "　"]
    u16 = ord(letter)
    if u16 < UNICODE_KOREAN_BASE or u16 > UNICODE_KOREAN_LAST:
        return [letter]
    u16 -= UNICODE_KOREAN_BASE
    i = u16 // (21 * 28)
    u16 %= 21 * 28
    v = u16 // 28
    u16 %= 28
    l = u16
    return [INITIAL_CONSONANTS_TABLE[i], VOWELS_TABLE[v], LAST_CONSONANTS_TABLE[l]]


def _is_syllable(c):
    return "가" <= c <= "힣"


@phonemizer("Korean CVCCV Phonemizer", "KO CVCCV", language="KO", openutau_class="OpenUtau.Plugin.Builtin.KoreanCVCCVPhonemizer", author="RYUUSEI")
class KoreanCVCCVPhonemizer(BaseKoreanPhonemizer):
    legacy_mapping = True

    def set_up(self, groups):
        super().set_up(groups)
        ku.romanize_notes(groups, False)

    def process(self, notes, prev, next, prev_neighbour, next_neighbour, prevs):
        prev_lyric = prev_neighbour.lyric if prev_neighbour is not None else None
        next_lyric = next_neighbour.lyric if next_neighbour is not None else None
        total_duration = sum(n.duration for n in notes)

        phonetic_hint = self.render_phonetic_hint(self.singer, notes[0], total_duration)
        if phonetic_hint is not None:
            return phonetic_hint

        romaji2korean = self.convert_romaji_note_to_hangeul(notes, prev_neighbour, next_neighbour)
        if romaji2korean is not None:
            notes = romaji2korean.korean_lyric_notes
            prev_neighbour = romaji2korean.korean_lyric_prev_note
            next_neighbour = romaji2korean.korean_lyric_next_note
            prev_lyric = prev_neighbour.lyric if prev_neighbour is not None else None
            next_lyric = next_neighbour.lyric if next_neighbour is not None else None

        phonemes_arr = []
        current_lyric = notes[0].lyric
        current = separate_hangul(_ch(current_lyric, 0) if current_lyric is not None else "\0")

        if current_lyric is None:
            raise TypeError("Object reference not set to an instance of an object.")
        if not _is_syllable(_ch(current_lyric, 0)):
            return [Phoneme(current_lyric)]

        if prev_lyric is not None and _is_syllable(_ch(prev_lyric, 0)):
            prev_k = separate_hangul(prev_lyric[0])
            t = TYPE_TABLE[LAST_CONSONANTS_TABLE.find(_ch(prev_k, 2))][INITIAL_CONSONANTS_TABLE.find(current[0])]

            current_consonants = _get(initial_consonant_lookup, current[0])
            current_ccv_consonants = _get(ccv_continuous_initial_consonants_lookup, current[0])
            vrc_initial_consonants = _get(vrc_initial_consonant_lookup, current[0])
            current_vowel = _get(vowel_lookup, _ch(current, 1))
            prev_last_consonants = _get(last_consonants_lookup, prev_k[2])
            prev_subsequent_vowel = _get(subsequent_vowel_lookup, prev_k[1])
            prev_initial_consonants = _get(initial_consonant_lookup, prev_k[2])

            p = None
            if t == VCC_CV:
                p = f"{current_consonants}{current_vowel}"
            elif t == VCC_CV_ADDED_Y:
                p = f"ss{current_vowel}"
            elif t == VC_CCV:
                p = f"{prev_last_consonants} {current_ccv_consonants}{current_vowel}"
            elif t == VC_CCV_ADDED_Y:
                p = f"{current_ccv_consonants}{current_vowel}"
            elif t == VC_NCV:
                p = f"- {current_ccv_consonants}{current_vowel}"
            elif t == VC_NRCV:
                p = f"- {prev_initial_consonants}{current_vowel}"
            elif t in (VC_CV, VRC_CV, VC_CV_ADDED_Y):
                p = f"{current_consonants}{current_vowel}"
            elif t == VRC_NCV:
                p = f"- {vrc_initial_consonants}{current_vowel}"
            elif t == VC_RCV:
                p = f"{prev_initial_consonants}{current_vowel}"
            elif t == _VCV:
                p = f"{prev_subsequent_vowel} {current_consonants}{current_vowel}"
            elif t == CV:
                p = f"{prev_subsequent_vowel} {prev_initial_consonants}{current_vowel}"
            phonemes_arr.append(Phoneme(p))
        else:
            current_consonants = _get(initial_consonant_lookup, current[0])
            current_vowel = _get(vowel_lookup, _ch(current, 1))
            phonemes_arr.append(Phoneme(f"- {current_consonants}{current_vowel}"))

        if next_lyric is not None and _is_syllable(_ch(next_lyric, 0)):
            next_k = separate_hangul(next_lyric[0])
            t = TYPE_TABLE[LAST_CONSONANTS_TABLE.find(_ch(current, 2))][INITIAL_CONSONANTS_TABLE.find(next_k[0])]

            next_consonants = _get(initial_consonant_lookup, next_k[0])
            next_vcc_consonants = _get(vc_last_consonants_lookup, next_k[0])
            next_vrc_consonants = _get(vrc_last_consonants_lookup, next_k[0])
            cur_sub_vowel = _get(subsequent_vowel_lookup, current[1])
            cur_last = _get(last_consonants_lookup, current[2])
            cur_vc_last = _get(vc_last_consonants_lookup, current[2])
            pos3 = total_duration - min(cdiv(total_duration, 3), 120)
            y_next = Y_VOWELS_TABLE.find(_ch(next_k, 1)) > 0

            if t == VCC_CV:
                phonemes_arr.append(Phoneme(f"{cur_sub_vowel}{cur_last} {next_vcc_consonants}", position=pos3))
            elif t == VCC_CV_ADDED_Y:
                if y_next:
                    phonemes_arr.append(Phoneme(f"{cur_sub_vowel}{cur_vc_last} sy", position=pos3))
                else:
                    phonemes_arr.append(Phoneme(f"{cur_sub_vowel}{cur_vc_last} s", position=pos3))
            elif t == VC_CCV_ADDED_Y:
                if y_next:
                    phonemes_arr.append(Phoneme(f"{cur_sub_vowel} {next_consonants}y", position=pos3))
                else:
                    phonemes_arr.append(Phoneme(f"{cur_sub_vowel} {cur_vc_last}", position=pos3))
            elif t in (VC_CCV, VC_NCV, VC_NRCV, VC_CV, VC_RCV):
                phonemes_arr.append(Phoneme(f"{cur_sub_vowel} {cur_vc_last}", position=pos3))
            elif t == VRC_NCV:
                phonemes_arr.append(Phoneme(f"{cur_sub_vowel} {cur_last}", position=pos3))
            elif t == VRC_CV:
                phonemes_arr.append(Phoneme(f"{cur_sub_vowel} {next_vrc_consonants}", position=total_duration - min(cdiv(total_duration, 4), 100)))
            elif t == VC_CV_ADDED_Y:
                if y_next:
                    phonemes_arr.append(Phoneme(f"{cur_sub_vowel} {next_vcc_consonants}y", position=pos3))
                else:
                    phonemes_arr.append(Phoneme(f"{cur_sub_vowel} {next_vcc_consonants}", position=pos3))
            elif t == CV:
                pass
            # (_VCV adds nothing)
        else:
            cur_sub_vowel = _get(subsequent_vowel_lookup, current[1])
            cur_last = _get(last_consonants_lookup, current[2])
            phonemes_arr.append(Phoneme(f"{cur_sub_vowel} {cur_last}", position=total_duration - 60))

        return phonemes_arr
