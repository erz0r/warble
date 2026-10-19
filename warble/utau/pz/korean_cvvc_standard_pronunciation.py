"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Plugin.Builtin/KoreanCVVCStandardPronunciationPhonemizer.cs"""

from . import korean_phonemizer_util as ku
from .api import phonemizer
from .base_korean_phonemizer import BaseKoreanPhonemizer

FIRST_CONSONANTS = {
    "ㄱ": "g", "ㄲ": "kk", "ㄴ": "n", "ㄷ": "d", "ㄸ": "tt", "ㄹ": "r", "ㅁ": "m", "ㅂ": "b", "ㅃ": "pp", "ㅅ": "s", "ㅆ": "ss", "ㅇ": "",
    "ㅈ": "j", "ㅉ": "jj", "ㅊ": "ch", "ㅋ": "k", "ㅌ": "t", "ㅍ": "p", "ㅎ": "h", "null": "",
    # EN Phonemes
    "th": "th", "v": "v", "f": "f", "rr": "rr",
}

MIDDLE_VOWELS = {
    "ㅏ": ["a", "", "a"], "ㅐ": ["e", "", "e"], "ㅑ": ["ya", "y", "a"], "ㅒ": ["ye", "y", "e"], "ㅓ": ["eo", "", "eo"], "ㅔ": ["e", "", "e"],
    "ㅕ": ["yeo", "y", "eo"], "ㅖ": ["ye", "y", "e"], "ㅗ": ["o", "", "o"], "ㅘ": ["wa", "w", "a"], "ㅙ": ["we", "w", "e"], "ㅚ": ["we", "w", "e"],
    "ㅛ": ["yo", "y", "o"], "ㅜ": ["u", "", "u"], "ㅝ": ["weo", "w", "eo"], "ㅞ": ["we", "w", "e"], "ㅟ": ["wi", "w", "i"], "ㅠ": ["yu", "y", "u"],
    "ㅡ": ["eu", "", "eu"], "ㅢ": ["eui", "", "i"], "ㅣ": ["i", "", "i"], "null": ["", "", ""],
}

LAST_CONSONANTS = {
    "ㄱ": ["K", ""], "ㄲ": ["K", ""], "ㄳ": ["K", ""], "ㄴ": ["n", "2"], "ㄵ": ["n", "2"], "ㄶ": ["n", "2"], "ㄷ": ["T", "1"], "ㄹ": ["l", "4"],
    "ㄺ": ["K", ""], "ㄻ": ["m", "1"], "ㄼ": ["l", "4"], "ㄽ": ["l", "4"], "ㄾ": ["l", "4"], "ㄿ": ["P", "1"], "ㅀ": ["l", "4"], "ㅁ": ["m", "1"],
    "ㅂ": ["P", "1"], "ㅄ": ["P", "1"], "ㅅ": ["T", "1"], "ㅆ": ["T", "1"], "ㅇ": ["ng", "3"], "ㅈ": ["T", "1"], "ㅊ": ["T", "1"], "ㅋ": ["L", ""],
    "ㅌ": ["T", "1"], "ㅍ": ["P", "1"], "ㅎ": ["T", "1"], " ": ["", ""], "null": ["", ""],
}

BATCHIM_ROMAJ = {"K": "ㄱ", "k": "ㄱ", "T": "ㄷ", "t": "ㄷ", "P": "ㅂ", "p": "ㅂ", "ng": "ㅇ", "n": "ㄴ", "l": "ㄹ", "m": "ㅁ"}

EN_PHONEMES = [
    "theui=th,ㅢ theu=th,ㅡ theo=th,ㅓ tha=th,ㅏ thi=th,ㅣ thu=th,ㅜ the=th,ㅔ tho=th,ㅗ".split(),
    "thyeo=th,ㅕ thya=th,ㅑ thyu=th,ㅜ thye=th,ㅖ thyo=th,ㅛ".split(),
    "thweo=th,ㅝ thwa=th,ㅘ thwi=th,ㅟ thwe=th,ㅞ".split(),
    "veui=v,ㅢ veu=v,ㅡ veo=v,ㅓ va=v,ㅏ vi=v,ㅣ vu=v,ㅜ ve=v,ㅔ vo=v,ㅗ".split(),
    "vyeo=v,ㅕ vya=v,ㅑ vyu=v,ㅜ vye=v,ㅖ vyo=v,ㅛ".split(),
    "vweo=v,ㅝ vwa=v,ㅘ vwi=v,ㅟ vwe=v,ㅞ".split(),
    "feui=f,ㅢ feu=f,ㅡ feo=f,ㅓ fa=f,ㅏ fi=f,ㅣ fu=f,ㅜ fe=f,ㅔ fo=f,ㅗ".split(),
    "fyeo=f,ㅕ fya=f,ㅑ fyu=f,ㅜ fye=f,ㅖ fyo=f,ㅛ".split(),
    "fweo=f,ㅝ fwa=f,ㅘ fwi=f,ㅟ fwe=f,ㅞ".split(),
    "rreui=rr,ㅢ rreu=rr,ㅡ rreo=rr,ㅓ rra=rr,ㅏ rri=rr,ㅣ rru=rr,ㅜ rre=rr,ㅔ rro=rr,ㅗ".split(),
    "rryeo=rr,ㅕ rrya=rr,ㅑ rryu=rr,ㅜ rrye=rr,ㅖ rryo=rr,ㅛ".split(),
    "rrweo=rr,ㅝ rrwa=rr,ㅘ rrwi=rr,ㅟ rrwe=rr,ㅞ".split(),
]


@phonemizer("Korean CVVC Phonemizer", "KO CVVC", language="KO", openutau_class="OpenUtau.Plugin.Builtin.KoreanCVVCPhonemizer", author="RYUUSEI & EX3")
class KoreanCVVCPhonemizer(BaseKoreanPhonemizer):
    def additional_test(self, lyric):
        return self.is_en_phoneme(lyric)

    def _find(self, phoneme, note, null_if_not_found=False):
        return self.find_in_oto(self.singer, phoneme, note, null_if_not_found)

    def convert_for_cvvc(self, notes, prev_lyric, this_lyric, next_lyric, next_neighbour):
        total_duration = sum(n.duration for n in notes)
        note = notes[0]
        f = self._find

        sound_before_end_sound = this_lyric[1] if this_lyric[2] == " " else this_lyric[2]
        this_mid_vowel_for_end = MIDDLE_VOWELS[sound_before_end_sound][2] if sound_before_end_sound in MIDDLE_VOWELS else LAST_CONSONANTS[sound_before_end_sound][0]
        end_sound = f"{this_mid_vowel_for_end} R"

        is_it_needs_front_cv = prev_lyric[0] == "null" or prev_lyric[1] == "null"
        is_it_needs_end_sound = (next_lyric[0] == "null" or next_lyric[1] == "null") and next_neighbour is None
        this_mid_vowel_head = MIDDLE_VOWELS[this_lyric[1]][1]
        this_mid_vowel_tail = MIDDLE_VOWELS[this_lyric[1]][2]

        if this_lyric[0] == "ㄹ" and prev_lyric[2] == "ㄹ":  # ㄹㄹ = l
            cv = f"l{MIDDLE_VOWELS[this_lyric[1]][0]}"
        else:
            cv = f"{FIRST_CONSONANTS[this_lyric[0]]}{MIDDLE_VOWELS[this_lyric[1]][0]}"

        vc = f"{this_mid_vowel_tail} {FIRST_CONSONANTS[next_lyric[0]]}{MIDDLE_VOWELS[next_lyric[1]][1]}"
        vv = f"{MIDDLE_VOWELS[prev_lyric[1]][2]} {this_mid_vowel_head}{this_mid_vowel_tail}"
        vsv = f"{this_mid_vowel_tail} {MIDDLE_VOWELS[next_lyric[1]][1]}"

        is_it_needs_vv = prev_lyric[2] == " " and this_lyric[0] == "ㅇ"
        if prev_lyric[2] == "ㅇ" and this_lyric[0] == "ㅇ":
            is_it_needs_vv = True
            vv = f"{LAST_CONSONANTS['ㅇ'][0]} {this_mid_vowel_head}{this_mid_vowel_tail}"
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

        if is_it_needs_vv and f(vv, note, True) is not None:
            cv = vv
            if is_it_needs_vsv:
                is_it_needs_vsv = False

        if this_lyric[2] == " " and is_it_needs_vc:
            if is_it_needs_front_cv:
                return self.generate_result2p(f(front_cv, note), f(vc, note), total_duration, 120, 3)
            return self.generate_result2p(f(cv, note), f(vc, note), total_duration, 120, 3)

        if this_lyric[2] == " " and is_it_needs_vsv:
            if is_it_needs_front_cv:
                return self.generate_result2p(f(front_cv, note), f(vsv, note), total_duration, 120, 3)
            return self.generate_result2p(f(cv, note), f(vsv, note), total_duration, 120, 3)

        if this_lyric[2] == " ":
            if is_it_needs_front_cv:
                return (self.generate_result2(f(front_cv, note), f(end_sound, note), total_duration, 8) if is_it_needs_end_sound
                        else self.generate_result(f(front_cv, note)))
            return (self.generate_result2(f(cv, note), f(end_sound, note), total_duration, 8) if is_it_needs_end_sound
                    else self.generate_result(f(cv, note)))

        batchim = f"{this_mid_vowel_tail} {LAST_CONSONANTS[this_lyric[2]][0]}"
        if f(batchim, note, True) is None:
            batchim = batchim.lower()

        if next_lyric[0] == "null" or next_lyric[0] == "ㅇ":
            if is_it_needs_front_cv:
                return self.generate_result2(f(front_cv, note), f(batchim, note), total_duration, 8)
            return self.generate_result2(f(cv, note), f(batchim, note), total_duration, 8)
        cc = f"{LAST_CONSONANTS[this_lyric[2]][0]} {FIRST_CONSONANTS[next_lyric[0]]}{MIDDLE_VOWELS[next_lyric[1]][1]}"

        if f(cc, note, True) is None:
            if cc.endswith("w") or cc.endswith("y"):
                cc = cc[:-1]

        if f(cc, note, True) is not None:
            if is_it_needs_front_cv:
                return self.generate_result3p(f(front_cv, note), f(batchim, note), f(cc, note), total_duration, 120, 2, 3)
            return self.generate_result3p(f(cv, note), f(batchim, note), f(cc, note), total_duration, 120, 2, 3)
        if is_it_needs_front_cv:
            self.generate_result2p(f(front_cv, note), f(batchim, note), total_duration, 120, 5)  # (sic) result discarded in c#
        return self.generate_result2p(f(cv, note), f(batchim, note), total_duration, 120, 5)

    @staticmethod
    def is_en_phoneme(phoneme):
        return phoneme.startswith("rr") or phoneme.startswith("th") or phoneme.startswith("f") or phoneme.startswith("v")

    def convert_phonemes(self, notes, prev, next, prev_neighbour, next_neighbour, prev_neighbours):
        note = notes[0]
        prev_is_en = curr_is_en = next_is_en = False
        prev_en = ["", "", ""]
        curr_en = ["", "", ""]
        next_en = ["", "", ""]
        # exit_loop is shared by the three scans, like the c# local: a match in the last row leaves
        # it set, which makes the next scan stop before its first row
        state = {"exit": False}

        def scan(lyric, out, batchim_out):
            hit = False
            for row in EN_PHONEMES:
                if state["exit"]:
                    state["exit"] = False
                    break
                for p in row:
                    grapheme = p.split("=")[0]
                    if not lyric.startswith(grapheme):
                        continue
                    temp = p.split("=")[1].split(",")
                    out[0] = temp[0]
                    out[1] = temp[1]
                    if len(lyric) != len(grapheme):
                        batchim_out[2] = BATCHIM_ROMAJ[lyric[len(grapheme):]]
                    else:
                        batchim_out[2] = " "
                    hit = True
                    state["exit"] = True
                    break
            return hit

        if self.is_en_phoneme(note.lyric):
            curr_is_en = scan(note.lyric, curr_en, curr_en)
        if prev is not None and self.is_en_phoneme(prev.lyric):
            prev_is_en = scan(prev.lyric, prev_en, prev_en)
        if next is not None and self.is_en_phoneme(next.lyric):
            next_is_en = scan(next.lyric, next_en, prev_en)  # (sic) c# writes the batchim into prevENPhones

        if not ku.is_hangeul(note.lyric) and not prev_is_en and not curr_is_en and not next_is_en:
            return self.generate_result(self._find(notes[0].lyric, notes[0]))

        if ku.is_hangeul(note.lyric):
            lyrics = ku.variate(prev_neighbour, note, next_neighbour)
        else:
            lyrics = {i: "null" for i in range(9)}
            if prev_neighbour is not None and not self.is_en_phoneme(prev_neighbour.lyric):
                t = ku.variate(None, prev_neighbour, None)
                lyrics[0], lyrics[1], lyrics[2] = t[3], t[4], t[5]
            if next_neighbour is not None and not self.is_en_phoneme(next_neighbour.lyric):
                t = ku.variate(None, next_neighbour, None)
                lyrics[6], lyrics[7], lyrics[8] = t[3], t[4], t[5]

        prev_lyric = [prev_en[i] if prev_is_en else lyrics[i] for i in range(3)]
        this_lyric = [curr_en[i] if curr_is_en else lyrics[3 + i] for i in range(3)]
        next_lyric = [next_en[i] if next_is_en else lyrics[6 + i] for i in range(3)]

        if this_lyric[0] == "null":
            return self.generate_result(self._find(notes[0].lyric, notes[0]))
        if prev_lyric[2] != " " and prev_is_en and this_lyric[0] == "ㅇ":
            this_lyric[0] = prev_lyric[2]
            prev_lyric[2] = " "
        return self.convert_for_cvvc(notes, prev_lyric, this_lyric, next_lyric, next_neighbour)

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
