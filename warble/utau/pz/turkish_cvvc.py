"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Plugin.Builtin/TurkishCVVCPhonemizer.cs"""

import copy
import unicodedata

from .api import Phoneme, Phonemizer, alt_str, phonemizer

# Contributed by ise with the help of Japanese CVVC phonemizer by TUBS
GLOTTAL_STOPS = ["?", "q"]
VOWELS = ["a", "e", "ae", "eu", "i", "o", "oe", "u", "ue"]
SUSTAINED_CONSONANTS = ["Y", "L", "LY", "M", "N", "NG"]
CONSONANTS = "9,b,c,ch,d,f,g,h,j,k,l,m,n,ng,p,r,rr,r',s,sh,t,v,w,y,z,by,dy,gy,hy,ky,ly,my,ny,py,ry,ty,Y,L,LY,M,N,NG,-,?,q".split(",")


class SegmentedLyric:
    """a c# struct: copied on assignment and when passed to a method (use copy.copy)."""

    def __init__(self, original_lyric=None, phonemes=None, has9_before_vow=False):
        if phonemes is None:
            self.lyric = ""
            self.start_c1 = self.start_c2 = self.vow = self.end_c1 = self.end_c2 = ""
        else:
            self.lyric = original_lyric
            self.start_c1 = phonemes[0]
            self.start_c2 = phonemes[1]
            self.vow = phonemes[2]
            self.end_c1 = phonemes[3]
            self.end_c2 = phonemes[4]
        self.has9_before_vow = has9_before_vow

    def has_consonant_before_vowel(self):
        return self.start_c1 != ""

    def has_consonant_after_vowel(self):
        return self.end_c1 != ""


@phonemizer("Turkish CVVC Phonemizer", "TR CVVC", language="TR", openutau_class="OpenUtau.Plugin.Builtin.TurkishCVVCPhonemizer", author="ise")
class TurkishCVVCPhonemizer(Phonemizer):
    # make it quicker to check multiple oto occurrences at once rather than spamming if else if
    def _check_oto_until_hit(self, input, note):
        attr = note.attr(0)
        color = attr.voice_color if attr.voice_color is not None else self.get_parent_voice_color()
        shift = attr.tone_shift if attr.tone_shift is not None else self.get_parent_tone_shift()
        alt = attr.alternate if attr.alternate is not None else self.get_parent_alternate()

        otos = []
        for test in input:
            oto_alt = self.singer.try_get_mapped_oto(test + alt_str(alt), note.tone + shift, color)
            if oto_alt is not None:
                otos.append(oto_alt)
                continue
            oto_candidacy = self.singer.try_get_mapped_oto(test, note.tone + shift, color)
            if oto_candidacy is not None:
                otos.append(oto_candidacy)

        if otos:
            match = next((o for o in otos if (o.color or "") == color), None)
            if match is not None:
                return match
            return otos[0]
        return None

    def _get_note_start(self, phonemes_current, phonemes_prev):
        note_start = phonemes_current.start_c1 + phonemes_current.start_c2 + phonemes_current.vow
        has_no_prev_neighbour = phonemes_prev.start_c1 == "" and phonemes_prev.vow == ""
        result = ["- " + note_start, note_start, phonemes_current.lyric]

        if has_no_prev_neighbour:
            return result

        if phonemes_current.start_c1 == "":
            if phonemes_prev.has_consonant_after_vowel():  # vc + V
                if phonemes_prev.end_c1.upper() in SUSTAINED_CONSONANTS:
                    result[0] = phonemes_prev.end_c1.upper() + " " + phonemes_current.vow
            elif phonemes_prev.vow != "":  # v + V
                if phonemes_current.has9_before_vow:
                    result[0] = phonemes_prev.vow + " 9" + phonemes_current.vow
                else:
                    result[0] = phonemes_prev.vow + " " + phonemes_current.vow
            return result

        return [note_start, phonemes_current.lyric]

    def _get_alternative_consonant(self, consonant, vow):
        if vow == "e" or vow == "i" or vow == "ue" or vow == "oe":
            y = "y"
            if consonant.upper() == consonant:
                y = "Y"
            if consonant + y in CONSONANTS:
                return consonant + y
        return consonant

    def _get_consonant_ending(self, current, has_next, next):
        current = copy.copy(current)  # struct passed by value
        v_ = current.vow + " "

        if current.end_c1 in GLOTTAL_STOPS:
            return [v_ + current.end_c1]

        if has_next:
            if current.end_c1 != "" and current.end_c1 == next.start_c1:
                return [v_ + self._get_alternative_consonant(current.end_c1, current.vow)]

            if next.start_c1 == "g" or next.start_c1 == "k":
                if current.end_c1 == "n":
                    current.end_c1 = "ng"
                elif current.end_c1 == "N":
                    current.end_c1 = "NG"

        if not current.has_consonant_after_vowel():
            if not has_next:
                return [v_ + "-"]
            elif next.has_consonant_before_vowel():  # V + c
                return [v_ + self._get_alternative_consonant(next.start_c1, next.vow)]
            else:  # V + v
                return [""]

        return [v_ + current.end_c1 + "-", v_ + current.end_c1]

    @staticmethod
    def _check_pchtk(c):
        if c == "p" or c == "ch" or c == "t" or c == "k":
            return ""
        return "-"

    @staticmethod
    def _convert_to_oto_styled_lyric(lyric):
        lyric = lyric.replace("ç", "ch")
        lyric = lyric.replace("ş", "sh")
        lyric = lyric.replace("ğ", "9")
        lyric = lyric.replace("æ", "ae")
        lyric = lyric.replace("E", "ae")
        lyric = lyric.replace("ı", "eu")
        lyric = lyric.replace("ö", "oe")
        lyric = lyric.replace("ü", "ue")
        return lyric

    def _get_segmented_phonemes(self, lyric):  # CCVCC
        lyric = self._convert_to_oto_styled_lyric(lyric)
        phonemes = ["", "", "", "", ""]
        has9_before_vow = False
        char_index = 0

        i = 0
        while i < 5:
            two_char_phoneme = ""
            if char_index + 2 <= len(lyric):
                two_char_phoneme = lyric[char_index:char_index + 2]
            if char_index + 1 > len(lyric):
                raise IndexError("ArgumentOutOfRangeException: Substring")  # c# Substring(charIndex, 1)
            one_char_phoneme = lyric[char_index:char_index + 1]

            if i < 2 and one_char_phoneme == "9":
                has9_before_vow |= True
                char_index += 1
            elif two_char_phoneme in VOWELS:
                i = 2
                phonemes[i] = two_char_phoneme
                char_index += 2
            elif one_char_phoneme in VOWELS:
                i = 2
                phonemes[i] = one_char_phoneme
                char_index += 1
            elif two_char_phoneme in CONSONANTS and i != 2:
                phonemes[i] = two_char_phoneme
                char_index += 2
            elif one_char_phoneme in CONSONANTS and i != 2:
                phonemes[i] = one_char_phoneme
                char_index += 1
            else:  # not found
                i -= 1
                char_index += 1

            if char_index == len(lyric):
                break
            i += 1
        return SegmentedLyric(lyric, phonemes, has9_before_vow)

    def process(self, notes, prev, next, prev_neighbour, next_neighbour, prev_neighbours):
        note = notes[0]
        current_lyric = unicodedata.normalize("NFC", note.lyric)

        if current_lyric[0] == ".":
            return [Phoneme(current_lyric[1:])]

        phonemes_current = self._get_segmented_phonemes(current_lyric)
        phonemes_prev = SegmentedLyric()
        phonemes_next = SegmentedLyric()

        if prev_neighbour is not None:
            phonemes_prev = self._get_segmented_phonemes(unicodedata.normalize("NFC", prev_neighbour.lyric))
        if next_neighbour is not None:
            phonemes_next = self._get_segmented_phonemes(unicodedata.normalize("NFC", next_neighbour.lyric))

        note_start_input = self._get_note_start(phonemes_current, phonemes_prev)
        note_end_input = self._get_consonant_ending(phonemes_current, next_neighbour is not None, phonemes_next)
        note_start, note_end, note_end_cc = "", "", ""

        if phonemes_current.end_c2 != "":  # + VCC
            note_end_input = [phonemes_current.vow + " " + phonemes_current.end_c1 + self._check_pchtk(phonemes_current.end_c1)]
            note_end_cc = phonemes_current.end_c1 + phonemes_current.end_c2 + " -"

        o1 = self._check_oto_until_hit(note_start_input, note)
        if o1 is not None:
            note_start = o1.alias

        o2 = self._check_oto_until_hit(note_end_input, note)
        note_end = o2.alias if o2 is not None else ""

        o3 = self._check_oto_until_hit([note_end_cc], note)
        note_end_cc = o3.alias if o3 is not None else ""

        if note_start != "" and note_end == "" and note_end_cc == "":
            return [Phoneme(note_start)]
        elif note_start != "" and note_end != "":
            total_duration = sum(n.duration for n in notes)
            last_length_from_oto = 120
            is_cv_coeff = 1.0
            if phonemes_current.has_consonant_after_vowel():
                is_cv_coeff = 1.8
            is_end_coeff = 2
            if next_neighbour is not None:
                is_end_coeff = 1
                attr0 = next_neighbour.attr(0)  # next first
                shift0 = attr0.tone_shift if attr0.tone_shift is not None else self.get_parent_tone_shift()
                color0 = attr0.voice_color if attr0.voice_color is not None else self.get_parent_voice_color()
                oto0 = self.singer.try_get_mapped_oto(self._get_note_start(phonemes_next, phonemes_current)[0], note.tone + shift0, color0)
                if oto0 is not None:
                    # If overlap is a negative value, vcLength is longer than Preutter
                    if oto0.overlap < 0:
                        last_length_from_oto = self.time_axis.ms_pos_to_tick_pos(oto0.preutter - oto0.overlap)
                    else:
                        last_length_from_oto = self.time_axis.ms_pos_to_tick_pos(oto0.preutter)
            # vcLength depends on the Vel of the note
            attr1 = note.attr(1)  # current last (noteEnd)
            ratio1 = attr1.consonant_stretch_ratio if attr1.consonant_stretch_ratio is not None else self.get_parent_consonant_stretch_ratio()
            # Convert.ToInt32 rounds half to even, like python's round
            vc_length = int(round(min(total_duration // (2 * is_end_coeff), last_length_from_oto * is_cv_coeff * ratio1)))

            if note_end_cc == "":
                return [Phoneme(note_start), Phoneme(note_end, position=total_duration - vc_length)]
            else:
                cc_length_from_oto = 60
                attr2 = note.attr(2)
                shift2 = attr2.tone_shift if attr2.tone_shift is not None else self.get_parent_tone_shift()
                color2 = attr2.voice_color if attr2.voice_color is not None else self.get_parent_voice_color()
                if next_neighbour is not None:
                    oto1 = self.singer.try_get_mapped_oto(note_end_cc, note.tone + shift2, color2)
                    if oto1 is not None:
                        # If overlap is a negative value, vcLength is longer than Preutter
                        if oto1.overlap < 0:
                            cc_length_from_oto = self.time_axis.ms_pos_to_tick_pos(oto1.preutter - oto1.overlap)
                        else:
                            cc_length_from_oto = self.time_axis.ms_pos_to_tick_pos(oto1.preutter)
                ratio2 = attr2.consonant_stretch_ratio if attr2.consonant_stretch_ratio is not None else self.get_parent_consonant_stretch_ratio()
                vc_length = int(round(min(total_duration // 3, cc_length_from_oto * ratio1)))
                cc_length = int(round(min(total_duration // 3, last_length_from_oto * ratio2)))

                exp = [{"abbr": "vol", "value": 70}]
                return [
                    Phoneme(note_start),
                    Phoneme(note_end, position=total_duration - vc_length - cc_length),
                    Phoneme(note_end_cc, position=total_duration - cc_length, expressions=exp),
                ]

        return [Phoneme(current_lyric)]
