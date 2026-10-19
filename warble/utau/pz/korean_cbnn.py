"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Plugin.Builtin/KoreanCBNNPhonemizer.cs"""

from . import korean_phonemizer_util as ku
from .api import phonemizer
from .base_korean_phonemizer import BaseKoreanPhonemizer

FIRST_CONSONANTS = {
    "ㄱ": "g", "ㄲ": "gg", "ㄴ": "n", "ㄷ": "d", "ㄸ": "dd", "ㄹ": "r", "ㅁ": "m", "ㅂ": "b", "ㅃ": "bb", "ㅅ": "s", "ㅆ": "ss", "ㅇ": "",
    "ㅈ": "j", "ㅉ": "jj", "ㅊ": "ch", "ㅋ": "k", "ㅌ": "t", "ㅍ": "p", "ㅎ": "h", "null": "",
}
MIDDLE_VOWELS = {
    "ㅏ": ["a", "", "a"], "ㅐ": ["e", "", "e"], "ㅑ": ["ya", "y", "a"], "ㅒ": ["ye", "y", "e"], "ㅓ": ["eo", "", "eo"], "ㅔ": ["e", "", "e"],
    "ㅕ": ["yeo", "y", "eo"], "ㅖ": ["ye", "y", "e"], "ㅗ": ["o", "", "o"], "ㅘ": ["wa", "w", "a"], "ㅙ": ["we", "w", "e"],
    "ㅚ": ["we", "w", "e"], "ㅛ": ["yo", "y", "o"], "ㅜ": ["u", "", "u"], "ㅝ": ["weo", "w", "eo"], "ㅞ": ["we", "w", "e"],
    "ㅟ": ["wi", "w", "i"], "ㅠ": ["yu", "y", "u"], "ㅡ": ["eu", "", "eu"], "ㅢ": ["i", "", "i"], "ㅣ": ["i", "", "i"], "null": ["", "", ""],
}
LAST_CONSONANTS = {
    "ㄱ": ["k", ""], "ㄲ": ["k", ""], "ㄳ": ["k", ""], "ㄴ": ["n", "2"], "ㄵ": ["n", "2"], "ㄶ": ["n", "2"], "ㄷ": ["t", "1"],
    "ㄹ": ["l", "4"], "ㄺ": ["k", ""], "ㄻ": ["m", "1"], "ㄼ": ["l", "4"], "ㄽ": ["l", "4"], "ㄾ": ["l", "4"], "ㄿ": ["p", "1"],
    "ㅀ": ["l", "4"], "ㅁ": ["m", "1"], "ㅂ": ["p", "1"], "ㅄ": ["p", "1"], "ㅅ": ["t", "1"], "ㅆ": ["t", "1"], "ㅇ": ["ng", "3"],
    "ㅈ": ["t", "1"], "ㅊ": ["t", "1"], "ㅋ": ["k", ""], "ㅌ": ["t", "1"], "ㅍ": ["p", "1"], "ㅎ": ["t", "1"], " ": ["", ""], "null": ["", ""],
}


@phonemizer("Korean CBNN Phonemizer", "KO CBNN", language="KO", openutau_class="OpenUtau.Plugin.Builtin.KoreanCBNNPhonemizer", author="EX3")
class KoreanCBNNPhonemizer(BaseKoreanPhonemizer):
    def _find(self, phoneme, note, null_if_not_found=False):
        return self.find_in_oto(self.singer, phoneme, note, null_if_not_found)

    def convert_for_cbnn(self, notes, prev_lyric, this_lyric, next_lyric, next_neighbour):
        total_duration = sum(n.duration for n in notes)
        note = notes[0]
        f = self._find
        g1, g2p, g2 = self.generate_result, self.generate_result2p, self.generate_result2

        sound_before_end_sound = this_lyric[1] if this_lyric[2] == " " else this_lyric[2]
        this_mid_vowel_for_end = MIDDLE_VOWELS[sound_before_end_sound][2] if sound_before_end_sound in MIDDLE_VOWELS else LAST_CONSONANTS[sound_before_end_sound][0]
        end_sound = f"{this_mid_vowel_for_end} -"

        is_it_needs_vv = prev_lyric[2] == " " and this_lyric[0] == "ㅇ" and this_lyric[1] in self.PLAIN_VOWELS
        is_it_needs_front_cv = prev_lyric[0] == "null" or prev_lyric[1] == "null" or (
            prev_lyric[2] != "null" and prev_lyric[2] in self.HARD_BATCHIMS and prev_lyric[2] != "ㅁ")
        is_relaxed_vc = next_lyric[0] == "null" or next_lyric[1] == "null" or (
            this_lyric[2] == next_lyric[0] and (this_lyric[2] in ku.nasal_sounds or this_lyric[2] == "ㄹ"))
        is_it_needs_end_sound = (next_lyric[0] == "null" or next_lyric[1] == "null") and next_neighbour is None

        this_mid_vowel_head = MIDDLE_VOWELS[this_lyric[1]][1]
        this_mid_vowel_tail = MIDDLE_VOWELS[this_lyric[1]][2]

        cv = f"{FIRST_CONSONANTS[this_lyric[0]]}{this_mid_vowel_head}{this_mid_vowel_tail}{LAST_CONSONANTS[this_lyric[2]][1]}"
        if f(cv, note, True) is None:
            cv = cv[:-1]
        vc = f"{this_mid_vowel_tail} {FIRST_CONSONANTS[next_lyric[0]]}{MIDDLE_VOWELS[next_lyric[1]][1]}"
        vv = f"{MIDDLE_VOWELS[prev_lyric[1]][2]} {this_mid_vowel_tail}"
        vsv = f"{this_mid_vowel_tail} {MIDDLE_VOWELS[next_lyric[1]][1]}"
        is_it_needs_vsv = this_lyric[2] == " " and next_lyric[0] == "ㅇ" and next_lyric[1] not in self.PLAIN_VOWELS and f(vsv, note, True) is not None
        is_it_needs_vc = this_lyric[2] == " " and next_lyric[0] != "ㅇ" and next_lyric[0] != "null"

        front_cv = f"- {cv}"
        if f(front_cv, note, True) is None:
            front_cv = f"-{cv}"
            if f(front_cv, note, True) is None:
                front_cv = cv

        if f(vc, note, True) is None:
            if vc.endswith("w") or vc.endswith("y"):
                vc = vc[:-1]
            if f(vc, note, True) is None:
                is_it_needs_vc = False

        if is_it_needs_vv:
            cv = vv

        if this_lyric[2] == " " and is_it_needs_vc:
            if is_it_needs_front_cv:
                return g2p(f(front_cv, note), f(vc, note), total_duration, 120, 3)
            return g2p(f(cv, note), f(vc, note), total_duration, 120, 3)

        if this_lyric[2] == " " and is_it_needs_vsv:
            if is_it_needs_front_cv:
                return g2p(f(front_cv, note), f(vsv, note), total_duration, 120, 3)
            return g2p(f(cv, note), f(vsv, note), total_duration, 120, 3)

        if this_lyric[2] == " ":
            if is_it_needs_front_cv:
                return g2(f(front_cv, note), f(end_sound, note), total_duration, 8) if is_it_needs_end_sound else g1(f(front_cv, note))
            return g2(f(cv, note), f(end_sound, note), total_duration, 8) if is_it_needs_end_sound else g1(f(cv, note))

        batchim = f"{this_mid_vowel_tail}{LAST_CONSONANTS[this_lyric[2]][0]}"

        head = front_cv if is_it_needs_front_cv else cv
        if this_lyric[2] == "ㅁ" or this_lyric[2] not in self.HARD_BATCHIMS:
            # GenerateResult(a, b, c, total, 120, 2, 3): 7 arguments -> the overload with secondPhonemePosition
            return g2p(f(head, note), f(batchim, note), total_duration, 120, 8) if is_relaxed_vc \
                else self.generate_result3p(f(head, note), f(batchim, note), f(end_sound, note), total_duration, 120, 2, 3)
        return g2p(f(head, note), f(batchim, note), total_duration, 120, 8) if is_relaxed_vc \
            else g2p(f(head, note), f(batchim, note), total_duration, 120, 5)

    def convert_phonemes(self, notes, prev, next, prev_neighbour, next_neighbour, prev_neighbours):
        note = notes[0]
        lyrics = ku.variate(prev_neighbour, note, next_neighbour)
        prev_lyric = [lyrics[0], lyrics[1], lyrics[2]]
        this_lyric = [lyrics[3], lyrics[4], lyrics[5]]
        next_lyric = [lyrics[6], lyrics[7], lyrics[8]]
        if this_lyric[0] == "null":
            return self.generate_result(self._find(notes[0].lyric, notes[0]))
        return self.convert_for_cbnn(notes, prev_lyric, this_lyric, next_lyric, next_neighbour)

    def generate_end_sound(self, notes, prev, next, prev_neighbour, next_neighbour, prev_neighbours):
        note = notes[0]
        if prev_neighbour is None:
            return self.generate_result(self._find(note.lyric, note))
        lyrics = ku.separate(prev_neighbour.lyric)
        prev_lyric = [lyrics[0], lyrics[1], lyrics[2]]
        sound_before_end_sound = prev_lyric[1] if prev_lyric[2] == " " else prev_lyric[2]
        end_sound = note.lyric
        prev_mid_vowel = MIDDLE_VOWELS[sound_before_end_sound][2] if sound_before_end_sound in MIDDLE_VOWELS else LAST_CONSONANTS[sound_before_end_sound][0]
        if self._find(f"{prev_mid_vowel} {end_sound}", note, True) is None:
            if self._find(f"{prev_mid_vowel}{end_sound}", note, True) is None:
                return self.generate_result(self._find(f"{end_sound}", note))
            return self.generate_result(self._find(f"{prev_mid_vowel}{end_sound}", note, True))
        return self.generate_result(self._find(f"{prev_mid_vowel} {end_sound}", note))
