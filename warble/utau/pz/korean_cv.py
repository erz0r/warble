"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Plugin.Builtin/KoreanCVPhonemizer.cs

settings: openutau reads `<data>/Plugins/kocv.yaml` (writing it from kocv.template.yaml when it is
missing) and lets the bank's own `kocv.yaml` override it. here the packaged template stands in for
the plugin-folder file, and the bank's kocv.yaml still wins. (openutau's very first run, before the
plugin file exists, has no settings at all and returns plain lyrics; that transient state is not
reproduced.)
"""

import os

import yaml

from . import korean_phonemizer_util as ku
from .api import phonemizer
from .base_korean_phonemizer import BaseKoreanPhonemizer, cdiv

TEMPLATE = os.path.join(os.path.dirname(__file__), "data", "korean", "kocv.template.yaml")

_BOOL_SETTINGS = ["use_rentan", "use_shi_phoneme", "use_ax_batchim_phoneme", "use_ax_batchim_phoneme_only", "use_capital_batchim",
                  "use_capital_batchim_only", "attach_empty_phoneme_after_batchims", "use_batchim_c", "use_batchim_c_only"]


class KoreanCVSetting:
    """KoreanCVSetting as YamlDotNet fills it (underscored names, unmatched keys ignored)."""

    class Settings:
        def __init__(self, d):
            for k in _BOOL_SETTINGS:
                v = d.get(k, False)
                if not isinstance(v, bool):
                    if str(v).lower() not in ("true", "false"):
                        raise ValueError(f"bad bool {v!r}")
                    v = str(v).lower() == "true"
                setattr(self, k, v)
            v = d.get("eui_fallback")
            self.eui_fallback = None if v is None else str(v)

    class BatchimConnection:
        def __init__(self, d):
            g = lambda k: None if d.get(k) is None else str(d.get(k))  # noqa: E731
            self.if_prev_batchim_is = g("if_prev_batchim_is")
            self.if_current_consonant = g("if_current_consonant")
            self.use_current_consonant_phoneme_as = g("use_current_consonant_phoneme_as")

    def __init__(self, d):
        d = d or {}
        self.version = d.get("version")
        self.settings = None if d.get("settings") is None else KoreanCVSetting.Settings(d["settings"])
        bc = d.get("batchim_connections")
        self.batchim_connections = None if bc is None else [KoreanCVSetting.BatchimConnection(x or {}) for x in bc]


def _load_setting(path):
    with open(path, encoding="utf-8-sig") as f:
        return KoreanCVSetting(yaml.safe_load(f.read()))


FIRST_CONSONANTS = {
    "ㄱ": "g", "ㄲ": "gg", "ㄴ": "n", "ㄷ": "d", "ㄸ": "dd", "ㄹ": "r", "ㅁ": "m", "ㅂ": "b", "ㅃ": "bb", "ㅅ": "s", "ㅆ": "ss", "ㅇ": "",
    "ㅈ": "j", "ㅉ": "jj", "ㅊ": "ch", "ㅋ": "k", "ㅌ": "t", "ㅍ": "p", "ㅎ": "h", "null": "",
}
MIDDLE_VOWELS = {
    "ㅏ": ["a", "", "a"], "ㅐ": ["e", "", "e"], "ㅑ": ["ya", "y", "a"], "ㅒ": ["ye", "y", "e"], "ㅓ": ["eo", "", "eo"], "ㅔ": ["e", "", "e"],
    "ㅕ": ["yeo", "y", "eo"], "ㅖ": ["ye", "y", "e"], "ㅗ": ["o", "", "o"], "ㅘ": ["wa", "w", "a"], "ㅙ": ["we", "w", "e"],
    "ㅚ": ["we", "w", "e"], "ㅛ": ["yo", "y", "o"], "ㅜ": ["u", "", "u"], "ㅝ": ["weo", "w", "eo"], "ㅞ": ["we", "w", "e"],
    "ㅟ": ["wi", "w", "i"], "ㅠ": ["yu", "y", "u"], "ㅡ": ["eu", "", "eu"], "ㅢ": ["eui", "eu", "i"], "ㅣ": ["i", "", "i"],
    "null": ["", "", ""],
}
LAST_CONSONANTS = {
    "ㄱ": ["k", ""], "ㄲ": ["k", ""], "ㄳ": ["k", ""], "ㄴ": ["n", "2"], "ㄵ": ["n", "2"], "ㄶ": ["n", "2"], "ㄷ": ["t", "1"],
    "ㄹ": ["l", "4"], "ㄺ": ["k", ""], "ㄻ": ["m", "1"], "ㄼ": ["l", "4"], "ㄽ": ["l", "4"], "ㄾ": ["l", "4"], "ㄿ": ["p", "1"],
    "ㅀ": ["l", "4"], "ㅁ": ["m", "1"], "ㅂ": ["p", "1"], "ㅄ": ["p", "1"], "ㅅ": ["t", "1"], "ㅆ": ["t", "1"], "ㅇ": ["ng", "3"],
    "ㅈ": ["t", "1"], "ㅊ": ["t", "1"], "ㅋ": ["k", ""], "ㅌ": ["t", "1"], "ㅍ": ["p", "1"], "ㅎ": ["t", "1"], " ": [""],
    "null": ["", ""],
}


def _contains_key(d, key):
    if key is None:
        raise ValueError("Value cannot be null. (Parameter 'key')")  # Dictionary.ContainsKey(null) throws
    return key in d


@phonemizer("Korean CV Phonemizer", "KO CV", language="KO", openutau_class="OpenUtau.Plugin.Builtin.KoreanCVPhonemizer", author="EX3")
class KoreanCVPhonemizer(BaseKoreanPhonemizer):
    def __init__(self):
        super().__init__()
        self.kocv_s = None

    def set_singer(self, singer):
        if self.singer is singer:
            return
        self.singer = singer
        if self.singer is None:
            return
        self.load_kocv_setting()

    def load_kocv_setting(self):
        try:
            self.kocv_s = _load_setting(TEMPLATE)
        except Exception:  # noqa: BLE001
            pass
        f = os.path.join(self.singer.location, "kocv.yaml")
        if os.path.isfile(f):
            try:
                self.kocv_s = _load_setting(f)
            except Exception:  # noqa: BLE001 - keeps the plugin-folder settings
                pass

    def check_this_phoneme_exists(self, phoneme, note):
        return self._find(phoneme, note, True) is not None

    def _find(self, phoneme, note, null_if_not_found=False):
        return self.find_in_oto(self.singer, phoneme, note, null_if_not_found)

    def convert_for_cv(self, notes, prev_lyric, this_lyric, next_lyric):
        s = self.kocv_s
        if s is None:
            return self.generate_result(self._find(notes[0].lyric, notes[0]))

        total_duration = sum(n.duration for n in notes)
        note = notes[0]
        is_it_needs_front_cv = prev_lyric[0] == "null" or prev_lyric[1] == "null" or (
            prev_lyric[2] != "null" and prev_lyric[2] in self.HARD_BATCHIMS and prev_lyric[2] != "ㅁ")
        is_relaxed_vc = next_lyric[0] == "null" or next_lyric[1] == "null"

        first_consonant = FIRST_CONSONANTS[this_lyric[0]]
        if all(p is None for p in this_lyric):
            return self.generate_result(self._find(note.lyric, note))
        this_mid_vowel_head = MIDDLE_VOWELS[this_lyric[1]][1]
        this_mid_vowel_tail = MIDDLE_VOWELS[this_lyric[1]][2]
        if s.settings.use_shi_phoneme:
            if this_lyric[1][0] == "ㅅ" and this_lyric[1][1] == "ㅣ":  # never true: [1] is a vowel
                if self.check_this_phoneme_exists("shi", note):
                    first_consonant = "sh"

        cv = f"{first_consonant}{this_mid_vowel_head}{this_mid_vowel_tail}"

        if self._find(cv, note, True) is None:
            if this_lyric[1] == "ㅢ":
                if _contains_key(MIDDLE_VOWELS, s.settings.eui_fallback):
                    this_mid_vowel_head = MIDDLE_VOWELS[s.settings.eui_fallback][1]
                    this_mid_vowel_tail = MIDDLE_VOWELS[s.settings.eui_fallback][2]
                else:
                    this_mid_vowel_head = MIDDLE_VOWELS["ㅔ"][1]
                    this_mid_vowel_tail = MIDDLE_VOWELS["ㅔ"][2]
            cv = f"{first_consonant}{this_mid_vowel_head}{this_mid_vowel_tail}"
        if s.batchim_connections is None:
            raise AttributeError("Object reference not set to an instance of an object.")
        for bc in s.batchim_connections:
            if prev_lyric[2] == bc.if_prev_batchim_is and this_lyric[0] == bc.if_current_consonant:
                cv_ = f"{bc.use_current_consonant_phoneme_as or ''}{this_mid_vowel_head}{this_mid_vowel_tail}"
                if self.check_this_phoneme_exists(cv_, note):
                    cv = cv_
                break

        if s.settings.use_rentan:
            front_cv = f"- {cv}"
            if not self.check_this_phoneme_exists(front_cv, note):
                front_cv = f"-{cv}"
                if not self.check_this_phoneme_exists(front_cv, note):
                    front_cv = cv
        else:
            front_cv = cv

        if this_lyric[2] == " ":
            if is_it_needs_front_cv:
                return self.generate_result(self._find(front_cv, note))
            return self.generate_result(self._find(cv, note))

        last = LAST_CONSONANTS[this_lyric[2]][0]
        _batchim = f"{this_mid_vowel_tail} {last}"

        def set_if_exists(cur, cand):
            return cand if self.check_this_phoneme_exists(cand, note) else cur

        if s.settings.use_ax_batchim_phoneme:
            if s.settings.use_ax_batchim_phoneme_only:
                _batchim = set_if_exists(_batchim, f"{this_mid_vowel_tail}{last}")
            if not self.check_this_phoneme_exists(_batchim, note):
                _batchim = set_if_exists(_batchim, f"{this_mid_vowel_tail}{last}")

        if s.settings.use_capital_batchim:
            if s.settings.use_capital_batchim_only:
                _batchim = set_if_exists(_batchim, f"{this_mid_vowel_tail} {last.upper()}")
            else:
                _batchim = set_if_exists(_batchim, f"{this_mid_vowel_tail}{last.upper()}")

        if s.settings.use_batchim_c:
            if s.settings.use_batchim_c_only:
                if s.settings.use_capital_batchim:
                    __batchim = f"{last}"
                    if s.settings.use_capital_batchim_only or self.check_this_phoneme_exists(__batchim, note):
                        _batchim = set_if_exists(_batchim, f"{last.upper()}")
                else:
                    _batchim = set_if_exists(_batchim, f"{last}")

        batchim = _batchim
        head = front_cv if is_it_needs_front_cv else cv
        mid = max(cdiv(total_duration, 2), 120)

        if this_lyric[2] == "ㅁ" or this_lyric[2] not in self.HARD_BATCHIMS:
            if is_relaxed_vc:
                return self.generate_result2p(self._find(head, note), self._find(batchim, note), total_duration, 120, 8)
            if s.settings.attach_empty_phoneme_after_batchims:
                return self.generate_result3p(self._find(head, note), self._find(batchim, note), "", total_duration, mid, 3, 5)
            return self.generate_result2p(self._find(head, note), self._find(batchim, note), total_duration, mid, 2 if is_it_needs_front_cv else 3)
        if is_relaxed_vc:
            return self.generate_result2p(self._find(head, note), self._find(batchim, note), total_duration, 120, 8)
        return self.generate_result2p(self._find(head, note), self._find(batchim, note), total_duration, mid, 3)

    def convert_phonemes(self, notes, prev, next, prev_neighbour, next_neighbour, prev_neighbours):
        note = notes[0]
        lyrics = ku.variate(prev_neighbour, note, next_neighbour)
        prev_lyric = [lyrics[0], lyrics[1], lyrics[2]]
        this_lyric = [lyrics[3], lyrics[4], lyrics[5]]
        next_lyric = [lyrics[6], lyrics[7], lyrics[8]]
        if this_lyric[0] == "null":
            return self.generate_result(self._find(notes[0].lyric, notes[0]))
        return self.convert_for_cv(notes, prev_lyric, this_lyric, next_lyric)

    def generate_end_sound(self, notes, prev, next, prev_neighbour, next_neighbour, prev_neighbours):
        note = notes[0]
        if prev_neighbour is None:
            return self.generate_result(self._find(note.lyric, note))
        lyrics = ku.separate(prev_neighbour.lyric)
        prev_lyric = [lyrics[0], lyrics[1], lyrics[2]]
        sound_before_end_sound = prev_lyric[1] if prev_lyric[2] == " " else prev_lyric[2]
        end_sound = note.lyric
        if prev_lyric[1] == "ㅢ":
            eui_exists = self.check_this_phoneme_exists("eui", note)
            if self.kocv_s is None or self.kocv_s.settings is None:
                raise AttributeError("Object reference not set to an instance of an object.")
            if not eui_exists and _contains_key(MIDDLE_VOWELS, self.kocv_s.settings.eui_fallback):
                prev_mid_vowel = MIDDLE_VOWELS[self.kocv_s.settings.eui_fallback][2]
            elif not eui_exists:
                prev_mid_vowel = MIDDLE_VOWELS["ㅔ"][2]
            else:
                prev_mid_vowel = MIDDLE_VOWELS["ㅢ"][2]
        else:
            prev_mid_vowel = MIDDLE_VOWELS[sound_before_end_sound][2] if sound_before_end_sound in MIDDLE_VOWELS else LAST_CONSONANTS[sound_before_end_sound][0]

        if self._find(f"{prev_mid_vowel} {end_sound}", note, True) is None:
            if self._find(f"{prev_mid_vowel}{end_sound}", note, True) is None:
                return self.generate_result(self._find(f"{end_sound}", note))
            return self.generate_result(self._find(f"{prev_mid_vowel}{end_sound}", note, True))
        return self.generate_result(self._find(f"{prev_mid_vowel} {end_sound}", note))
