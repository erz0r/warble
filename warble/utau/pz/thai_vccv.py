"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Plugin.Builtin/ThaiVCCVPhonemizer.cs"""

import re
import unicodedata

from .api import Phoneme, Phonemizer, phonemizer

VOWELS = ["a", "i", "u", "e", "o", "@", "Q", "3", "6", "1", "ia", "ua", "I", "8"]

DIPHTHONGS = ["r", "l", "w"]

CONSONANTS = ["b", "ch", "d", "f", "g", "h", "j", "k", "kh", "l", "m", "n", "p", "ph", "r", "s", "t", "th", "w", "y"]

ENDING_CONSONANTS = ["b", "ch", "d", "f", "g", "h", "j", "k", "kh", "l", "m", "n", "p", "ph", "r", "s", "t", "th", "w", "y"]

# c: the initial consonant (cluster), x: the final consonant. iterated in this order.
VOWEL_MAPPING = {
    "เcือะ": "6", "เcือx": "6", "แcะ": "@", "แcx": "@", "เcอะ": "3", "เcอ": "3", "ไc": "I", "ใc": "I", "เcาะ": "Q", "cอx": "Q",
    "cืx": "1", "cึx": "1", "cือ": "1", "cะ": "a", "cัx": "a", "cาx": "a", "เcา": "8", "เcะ": "e", "เcx": "e", "cิx": "i", "cีx": "i",
    "เcียะ": "ia", "เcียx": "ia", "โcะ": "o", "โcx": "o", "cุx": "u", "cูx": "u", "cัวะ": "ua", "cัว": "ua", "cำ": "am", "เcิx": "3", "เcิ": "3",
}

C_MAPPING = {
    "ก": "k", "ข": "kh", "ค": "kh", "ฆ": "kh", "ฅ": "kh", "ฃ": "kh",
    "จ": "j", "ฉ": "ch", "ช": "ch", "ฌ": "ch",
    "ฎ": "d", "ด": "d",
    "ต": "t", "ฏ": "t",
    "ถ": "th", "ฐ": "th", "ฑ": "th", "ธ": "th", "ท": "th",
    "บ": "b", "ป": "p", "พ": "ph", "ผ": "ph", "ภ": "ph", "ฟ": "f", "ฝ": "f",
    "ห": "h", "ฮ": "h",
    "ม": "m", "น": "n", "ณ": "n", "ร": "r", "ล": "l", "ฤ": "r",
    "ส": "s", "ศ": "s", "ษ": "s", "ซ": "s",
    "ง": "g", "ย": "y", "ญ": "y", "ว": "w", "ฬ": "r",
}

X_MAPPING = {
    "บ": "b", "ป": "b", "พ": "b", "ฟ": "b", "ภ": "b",
    "ด": "d", "จ": "d", "ช": "d", "ซ": "d", "ฎ": "d", "ฏ": "d", "ฐ": "d",
    "ฑ": "d", "ฒ": "d", "ต": "d", "ถ": "d", "ท": "d", "ธ": "d", "ศ": "d", "ษ": "d", "ส": "d",
    "ก": "k", "ข": "k", "ค": "k", "ฆ": "k",
    "ว": "w",
    "ย": "y",
    "น": "n", "ญ": "n", "ณ": "n", "ร": "n", "ล": "n", "ฬ": "n",
    "ง": "g",
    "ม": "m",
}


def _nfc(s):
    return unicodedata.normalize("NFC", s)


@phonemizer("Thai VCCV Phonemizer", "TH VCCV", language="TH", openutau_class="OpenUtau.Plugin.Builtin.ThaiVCCVPhonemizer", author="PRINTmov")
class ThaiVCCVPhonemizer(Phonemizer):
    def _check_oto_until_hit(self, input, note):
        attr = note.attr(0)
        shift = attr.tone_shift if attr.tone_shift is not None else self.get_parent_tone_shift()
        color = attr.voice_color if attr.voice_color is not None else self.get_parent_voice_color()
        for test in input:
            oto_candidacy = self.singer.try_get_mapped_oto(test, note.tone + shift, color)
            if oto_candidacy is not None:
                return oto_candidacy
        return None

    def process(self, notes, prev, next, prev_neighbour, next_neighbour, prev_neighbours):
        note = notes[0]
        current_lyric = _nfc(note.lyric)
        if note.phonetic_hint:
            current_lyric = _nfc(note.phonetic_hint)

        phonemes = []

        tests = []

        prev_temp = ""
        if prev_neighbour is not None:
            prev_temp = prev_neighbour.lyric
        prev_th = self.parse_input(prev_temp)

        note_th = self.parse_input(current_lyric)
        n_con, n_dip, n_vow, n_end = note_th

        if n_con is not None and n_dip is None and n_vow is not None:
            temp_oto = self._check_oto_until_hit([n_con + n_vow], note)
            if temp_oto is not None:
                tests.append(temp_oto.alias)
        elif n_con is not None and n_dip is not None and n_vow is not None:
            temp_oto = self._check_oto_until_hit([n_con + n_dip + n_vow], note)
            if temp_oto is not None:
                tests.append(temp_oto.alias)
            else:
                temp_oto = self._check_oto_until_hit([n_con + n_dip], note)
                if temp_oto is not None:
                    tests.append(temp_oto.alias)
                temp_oto = self._check_oto_until_hit([n_dip + n_vow], note)
                if temp_oto is not None:
                    tests.append(temp_oto.alias)

        if n_con is None and n_vow is not None:
            temp_oto = None
            if prev_th[3] is not None:
                temp_oto = self._check_oto_until_hit([prev_th[3] + n_vow], note)
            if temp_oto is not None:
                tests.append(temp_oto.alias)
            else:
                if prev_th[2] is not None:
                    temp_oto = self._check_oto_until_hit([prev_th[2] + n_vow], note)
                if temp_oto is not None:
                    tests.append(temp_oto.alias)
                else:
                    temp_oto = self._check_oto_until_hit([n_vow], note)
                    if temp_oto is not None:
                        tests.append(temp_oto.alias)

        if n_end is not None and n_vow is not None:
            temp_oto = self._check_oto_until_hit([n_vow + n_end], note)
            if temp_oto is not None:
                tests.append(temp_oto.alias)
        elif next_neighbour is not None and n_vow is not None:
            next_th = self.parse_input(next_neighbour.lyric)
            temp_oto = self._check_oto_until_hit([n_vow + " " + (next_th[0] or "")], note)
            if temp_oto is not None:
                tests.append(temp_oto.alias)

        if prev_neighbour is None and len(tests) >= 1:
            temp_oto = self._check_oto_until_hit(["-" + tests[0]], note)
            if temp_oto is not None:
                tests[0] = temp_oto.alias

        if next_neighbour is None and len(tests) >= 1:
            if n_end is None:
                temp_oto = self._check_oto_until_hit([(n_vow or "") + "-"], note)
                if temp_oto is not None:
                    tests.append(temp_oto.alias)
            else:
                temp_oto = self._check_oto_until_hit([tests[-1] + "-"], note)
                if temp_oto is not None:
                    tests[-1] = temp_oto.alias

        if len(tests) <= 0:
            temp_oto = self._check_oto_until_hit([current_lyric], note)
            if temp_oto is not None:
                tests.append(current_lyric)

        oto = self._check_oto_until_hit(tests, note)
        if oto is not None:
            note_duration = sum(n.duration for n in notes)

            for i in range(len(tests)):
                position = 0
                vc_position = note_duration - 120

                if next_neighbour is not None and " " in tests[i]:
                    next_lyric = _nfc(next_neighbour.lyric)
                    if next_neighbour.phonetic_hint:
                        next_lyric = _nfc(next_neighbour.phonetic_hint)
                    nx_con, nx_dip, nx_vow, _ = self.parse_input(next_lyric)
                    next_check = nx_vow
                    if nx_con is not None:
                        next_check = nx_con + (nx_vow or "")
                    if nx_dip is not None:
                        next_check = (nx_con or "") + nx_dip + (nx_vow or "")
                    next_attr = next_neighbour.attr(0)
                    shift = next_attr.tone_shift if next_attr.tone_shift is not None else self.get_parent_tone_shift()
                    color = next_attr.voice_color if next_attr.voice_color is not None else self.get_parent_voice_color()
                    if next_check is None:
                        # c# TryGetMappedOto(null, ...) ends in otoMap.TryGetValue(null), which throws
                        raise ValueError("ArgumentNullException: Value cannot be null. (Parameter 'key')")
                    next_oto = self.singer.try_get_mapped_oto(next_check, next_neighbour.tone + shift, color)
                    if next_oto is not None:
                        if oto.overlap > 0:
                            vc_position = note_duration - self.ms_to_tick(next_oto.overlap) - self.ms_to_tick(next_oto.preutter)

                if n_dip is None or len(tests) <= 2:
                    if i == 1:
                        position = max(int(note_duration * 0.75), vc_position)
                else:
                    if i == 1:
                        position = min(int(note_duration * 0.1), 60)
                    elif i == 2:
                        position = max(int(note_duration * 0.75), vc_position)

                phonemes.append(Phoneme(tests[i], position=position))

        return phonemes

    def parse_input(self, input):
        """-> (consonant, dipthong, vowel, ending_consonant)"""
        input = self.word_to_phonemes(input)

        consonant = None
        diphthong = None
        vowel = None
        ending_consonant = None

        if input is None:
            return (None, None, None, None)

        for con in CONSONANTS:
            if input.startswith(con):
                if consonant is None or len(consonant) < len(con):
                    consonant = con

        start_idx = len(consonant) if consonant is not None else 0
        for dip in DIPHTHONGS:
            if input[start_idx:].startswith(dip):
                if diphthong is None or len(diphthong) < len(dip):
                    diphthong = dip

        start_idx += len(diphthong) if diphthong is not None else 0
        for vow in VOWELS:
            if input[start_idx:].startswith(vow):
                if vowel is None or len(vowel) < len(vow):
                    vowel = vow

        for con in ENDING_CONSONANTS:
            if input.endswith(con):
                if ending_consonant is None or len(ending_consonant) < len(con):
                    ending_consonant = con

        return (consonant, diphthong, vowel, ending_consonant)

    def word_to_phonemes(self, input):
        input = input.replace(" ", "")
        input = self._remove_invalid_letters(input)
        if not re.search("[ก-ฮ]", input):
            return input
        for key, value in VOWEL_MAPPING.items():
            pattern = "^" + key.replace("c", "([ก-ฮ][ลรว]?|อ[ย]?|ห[ก-ฮ]?)").replace("x", "([ก-ฮ]?)") + "$"

            match = re.search(pattern, input)
            if match:
                c = match.group(1)
                x = (match.group(2) or "") if len(match.groups()) >= 2 else ""
                if len(c) >= 2 and (c.startswith("ห") or c.startswith("อ")):
                    c = c[1:]
                c_converted = self._convert_c(c)
                x_converted = self._convert_x(x)
                if value == "a" and "ั" in input and x == "ว":
                    return c_converted + "ua"
                if value == "e" and x == "ย":
                    return c_converted + "3" + x_converted
                return c_converted + value + x_converted
        if len(input) == 1:
            return self._convert_c(input) + "Q"
        elif len(input) == 2:
            return self._convert_c(input[0]) + "o" + self._convert_x(input[1])
        elif len(input) == 3:
            if input[1] == "ว":
                return self._convert_c(input[0]) + "ua" + self._convert_x(input[2])
            else:
                return self._convert_c(input[0:2]) + "o" + self._convert_x(input[1])
        elif len(input) == 4:
            if input[2] == "ว":
                return self._convert_c(input[0:2]) + "ua" + self._convert_x(input[3])
        return input

    def _convert_c(self, input):
        if not input:
            return input
        first_char = input[0]
        second_char = input[1] if len(input) > 1 else None
        if first_char in C_MAPPING:
            first_char_converted = C_MAPPING[first_char]
            if second_char is not None and second_char in C_MAPPING:
                return first_char_converted + C_MAPPING[second_char]
            return first_char_converted
        return input

    def _convert_x(self, input):
        if not input:
            return input
        first_char = input[0]
        if first_char in X_MAPPING:
            return X_MAPPING[first_char]
        return input

    def _remove_invalid_letters(self, input):
        input = re.sub(".์", "", input)
        input = re.sub("[่้๊๋็]", "", input)
        return input
