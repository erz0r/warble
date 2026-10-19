"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Plugin.Builtin/EStoJAPhonemizer.cs

spanish to japanese (lotte v): spanish g2p symbols spelled with japanese kana (always seseo), closely based on
tubs' older english-to-japanese phonemizer: vc ("a k") when the bank has it, else vcv ("a か") or plain cv, lone
consonants as u/o morae (k -> く), and alt/extra cv tables for syllables japanese doesn't have (ti -> て + い)."""

from ...g2p import SpanishG2p
from .api import phonemizer
from .entoja import _last_char, to_romaji
from .kotoja import to_hiragana as _wanakana_to_hiragana_vu
from .syllable_based import SyllableBasedPhonemizer

_VOWELS = "a i u e o".split()
_CONSONANTS = "b by B By ch d dy D Dy f g gy G Gy h hh hy I j k ky l ly m my n ny p py r ry rr rry s sh t ty ts U w x y Y z".split()

_DICTIONARY_PHONEMES_REPLACEMENT = {
    "a": "a", "b": "b", "B": "b", "ch": "ch", "d": "d", "D": "d", "e": "e", "f": "f", "g": "g", "G": "g", "hh": "hh",
    "i": "i", "I": "y", "ll": "j", "k": "k", "l": "l", "m": "m", "n": "n", "gn": "ny", "o": "o", "p": "p", "r": "r",
    "rr": "rr", "s": "s", "t": "t", "u": "u", "U": "w", "w": "w", "x": "h", "y": "y", "Y": "y", "z": "z",
}

_STARTING_CONSONANT = {
    "": "", "b": "b", "by": "by", "bw": "bw", "B": "b", "By": "by", "Bw": "bw", "ch": "ch", "chy": "chy", "chw": "chw",
    "d": "d", "dy": "dy", "dw": "dw", "D": "d", "Dy": "dy", "Dw": "dw", "f": "f", "fy": "fy", "fw": "fw", "g": "g",
    "gy": "gy", "gw": "gw", "G": "g", "Gy": "gy", "Gw": "gw", "h": "h", "hy": "hy", "hw": "hw", "j": "j", "jy": "j",
    "jw": "jw", "k": "k", "ky": "ky", "kw": "kw", "l": "r", "ly": "ry", "lw": "rw", "m": "m", "my": "my", "mw": "mw",
    "n": "n", "ny": "ny", "nw": "nw", "p": "p", "py": "py", "pw": "pw", "r": "r", "ry": "ry", "rw": "rw", "rr": "rr",
    "rry": "rry", "rrw": "rrw", "s": "s", "sy": "sy", "sw": "sw", "t": "t", "ty": "ty", "tw": "tw", "w": "w", "y": "y",
    "z": "s", "zy": "sy", "zw": "sw",
}

_SOLO_CONSONANT = {
    "b": "ぶ", "by": "び", "bw": "ぶ", "B": "ぶ", "By": "ヴぃ", "Bw": "ぶ", "ch": "ちゅ", "chy": "ち", "chw": "ちゅ",
    "d": "ど", "dy": "でぃ", "dw": "どぅ", "D": "ど", "Dy": "でぃ", "Dw": "どぅ", "f": "ふ", "fy": "ふぃ", "fw": "ふ",
    "g": "ぐ", "gy": "ぎ", "gw": "ぐ", "G": "ぐ", "Gy": "ぎ", "Gw": "ぐ", "h": "ほ", "hy": "ひ", "hw": "ほ", "hh": "息",
    "I": "い", "j": "じゅ", "jy": "じ", "jw": "じゅ", "k": "く", "ky": "き", "kw": "く", "l": "る", "ly": "り", "lw": "る",
    "m": "ん", "my": "み", "mw": "む", "n": "ん", "ny": "に", "nw": "ぬ", "p": "ぷ", "py": "ぴ", "pw": "ぷ", "r": "る",
    "ry": "り", "rw": "る", "rr": "る", "rry": "り", "rrw": "る", "s": "す", "sy": "すぃ", "sw": "す", "t": "と",
    "ty": "てぃ", "tw": "とぅ", "U": "う", "w": "う", "y": "い", "z": "す", "zy": "すぃ", "zw": "す",
}

_SPECIAL_CLUSTERS = ("ky kw gy gw Gy Gw sy sw zy zw jy jw ty tw chy chw dy dw Dy Dw ny nw nyw hy hw by bw By Bw py pw my mw "
                     "ry rw rry rrw ly lw").split()

_ALT_CV = {
    "kwa": "kula", "kwi": "kuli", "kwe": "kule", "kwo": "kulo",
    "gwa": "gula", "gwi": "guli", "gwe": "gule", "gwo": "gulo",
    "Gwa": "gula", "Gwi": "guli", "Gwe": "gule", "Gwo": "gulo",
    "si": "suli", "sya": "sulya", "syu": "sulyu", "sye": "sulile", "syo": "sulyo",
    "swa": "sula", "swi": "sui", "swe": "sule", "swo": "sulo",
    "zi": "suli", "zya": "sulya", "zyu": "sulyu", "zye": "sulile", "zyo": "sulyo",
    "zwa": "sula", "zwi": "sui", "zwe": "sule", "zwo": "sulo",
    "ti": "teli", "tya": "telya", "tyu": "telyu", "tye": "tele", "tyo": "telyo",
    "tu": "tolu", "twa": "tola", "twi": "toli", "twe": "tole", "two": "tolo",
    "di": "deli", "dya": "delya", "dyu": "delyu", "dye": "dele", "dyo": "delyo",
    "du": "dolu", "dwa": "dola", "dwi": "doli", "dwe": "dole", "dwo": "dolo",
    "Di": "deli", "Dya": "delya", "Dyu": "delyu", "Dye": "dele", "Dyo": "delyo",
    "Du": "dolu", "Dwa": "dola", "Dwi": "doli", "Dwe": "dole", "Dwo": "dolo",
    "nwa": "nula", "nwi": "nuli", "nwe": "nule", "nwo": "nulo",
    "hwa": "hola", "hwi": "holi", "hwe": "hole", "hwo": "holo",
    "fwa": "fua", "fwi": "fui", "fwe": "fue", "fwo": "fuo",
    "bwa": "bula", "bwi": "buli", "bwe": "bule", "bwo": "bulo",
    "Bwa": "bula", "Bwi": "buli", "Bwe": "bule", "Bwo": "bulo",
    "pwa": "pula", "pwi": "puli", "pwe": "pule", "pwo": "pulo",
    "hu": "holu",
    "mwa": "mula", "mwi": "muli", "mwe": "mule", "mwo": "mulo",
    "yi": "i",
    "rwa": "rula", "rwi": "ruli", "rwe": "rule", "rwo": "rulo",
    "wu": "u", "wi": "uli", "we": "ule", "wo": "ulo",
}

_CONDITIONAL_ALT = {"uli": "wi", "ule": "we", "ulo": "wo"}

_EXTRA_CV = {
    "rr": ["ru", "ru", "ru"], "rra": ["ra", "ra", "ra"], "rri": ["ri", "ri", "ri"], "rru": ["ru", "ru", "ru"],
    "rre": ["re", "re", "re"], "rro": ["ro", "ro", "ro"], "rrya": ["ri", "ri", "rya"], "rryu": ["ri", "ri", "ryu"],
    "rrye": ["ri", "ri", "rye"], "rryo": ["ri", "ri", "ryo"], "rrwa": ["ru", "ru", "wa"], "rrwi": ["ru", "ru", "uli"],
    "rrwe": ["ru", "ru", "ule"], "rrwo": ["ru", "ru", "ulo"],
    "kye": ["ki", "e"], "kula": ["ku", "wa"], "kuli": ["ku", "uli"], "kule": ["ku", "ule"], "kulo": ["ku", "ulo"],
    "gye": ["gi", "e"], "gula": ["gu", "wa"], "guli": ["gu", "uli"], "gule": ["gu", "ule"], "gulo": ["gu", "ulo"],
    "suli": ["se", "i"], "sulya": ["suli", "ya"], "sulyu": ["suli", "yu"], "sulile": ["suli", "ye"],
    "sulyo": ["suli", "yo"], "sula": ["su", "wa"], "sui": ["su", "uli"], "sule": ["su", "ule"], "sulo": ["su", "ulo"],
    "je": ["ji", "e"], "jya": ["ji", "ya"], "jye": ["ji", "e"], "jyo": ["ji", "yo"], "jyu": ["ji", "yu"],
    "jwa": ["ju", "wa"], "jwi": ["ju", "uli"], "jwe": ["ju", "ule"], "jwo": ["ju", "ulo"],
    "teli": ["te", "i"], "telya": ["teli", "ya"], "telyu": ["teli", "yu"], "tele": ["teli", "ye"],
    "telyo": ["teli", "yo"], "tolu": ["to", "u"], "tola": ["tolu", "wa"], "toli": ["tolu", "uli"],
    "tole": ["tolu", "ule"], "tolo": ["tolu", "ulo"],
    "che": ["chi", "e"], "chya": ["chi", "ya"], "chye": ["chi", "e"], "chyo": ["chi", "yo"], "chyu": ["chi", "yu"],
    "chwa": ["chu", "wa"], "chwi": ["chu", "uli"], "chwe": ["chu", "ule"], "chwo": ["chu", "ulo"],
    "deli": ["de", "i"], "delya": ["deli", "ya"], "delyu": ["deli", "yu"], "dele": ["deli", "ye"],
    "delyo": ["deli", "yo"], "dolu": ["do", "u"], "dola": ["dolu", "wa"], "doli": ["dolu", "uli"],
    "dole": ["dolu", "ule"], "dolo": ["dolu", "ulo"],
    "nye": ["ni", "e"], "nula": ["nu", "wa"], "nuli": ["nu", "uli"], "nule": ["nu", "ule"], "nulo": ["nu", "ulo"],
    "hye": ["hi", "e"], "holu": ["ho", "u"], "hola": ["ho", "wa"], "holi": ["ho", "uli"], "hole": ["ho", "ule"],
    "holo": ["ho", "ulo"],
    "fa": ["fu", "a"], "fi": ["fu", "i"], "fe": ["fu", "e"], "fo": ["fu", "o"], "fua": ["fu", "wa"],
    "fui": ["fu", "uli"], "fue": ["fu", "ule"], "fuo": ["fu", "ulo"], "fya": ["fi", "ya"], "fyu": ["fi", "yu"],
    "fye": ["fi", "ye"], "fyo": ["fi", "yo"],
    "bye": ["bi", "e"], "bula": ["bu", "wa"], "buli": ["bu", "uli"], "bule": ["bu", "ule"], "bulo": ["bu", "ulo"],
    "pye": ["pi", "e"], "pula": ["pu", "wa"], "puli": ["pu", "uli"], "pule": ["pu", "ule"], "pulo": ["pu", "ulo"],
    "mye": ["mi", "e"], "mula": ["mu", "wa"], "muli": ["mu", "uli"], "mule": ["mu", "ule"], "mulo": ["mu", "ulo"],
    "ye": ["i", "e"],
    "rye": ["ri", "e"], "rula": ["ru", "wa"], "ruli": ["ru", "uli"], "rule": ["ru", "ule"], "rulo": ["ru", "ulo"],
    "uli": ["u", "i"], "ule": ["u", "e"], "ulo": ["u", "o"],
}

_AFFRICATES = "ch j".split()


def _adjust_cc(cc, special_clusters):
    """check CCs for special clusters"""
    adjusted = []
    i = 0
    while i < len(cc):
        if i == len(cc) - 1:
            adjusted.append(cc[i])
        else:
            if cc[i] == cc[i + 1]:
                adjusted.append(cc[i])
                i += 2
                continue
            diphone = f"{cc[i]}{cc[i + 1]}"
            if diphone in special_clusters:
                adjusted.append(diphone)
                i += 1
            else:
                adjusted.append(cc[i])
        i += 1
    return adjusted


@phonemizer("Spanish to Japanese Phonemizer", "ES to JA", language="ES", openutau_class="OpenUtau.Plugin.Builtin.EStoJAPhonemizer", author="Lotte V")
class EStoJAPhonemizer(SyllableBasedPhonemizer):
    no_gap = True  # endings have a 50 ticks gap

    def get_vowels(self):
        return _VOWELS

    def get_consonants(self):
        return _CONSONANTS

    def get_dictionary_name(self):
        return "cmudict_es.txt"

    def get_dictionary_phonemes_replacement(self):
        return _DICTIONARY_PHONEMES_REPLACEMENT

    def load_base_dictionary(self):
        return SpanishG2p()

    def process_syllable(self, syllable):
        # skip processing if this note extends the prevous syllable
        if self.can_make_alias_extension(syllable):
            return [None]

        prev_v = syllable.prev_v
        cc = syllable.cc
        v = syllable.v
        phonemes = []
        using_vc = False

        if len(prev_v) == 0:
            prev_v = "-"

        cc = _adjust_cc(cc, _SPECIAL_CLUSTERS)

        # separate CCs and main CV
        final_cons = ""
        if len(cc) > 0:
            final_cons = cc[-1]

            start = 0
            has_vc, vc_phonemes = self._has_vc(prev_v, cc[0], syllable.tone, len(cc))
            using_vc = has_vc
            phonemes.extend(vc_phonemes)

            if using_vc:
                start = 1

            for i in range(start, len(cc) - 1):
                cons = _SOLO_CONSONANT[cc[i]]
                if not using_vc:
                    cons = self._try_vcv(prev_v, cons, syllable.tone)
                else:
                    using_vc = False
                if self.has_oto(cons, syllable.tone):
                    phonemes.append(cons)
                elif cons in _CONDITIONAL_ALT:
                    cons = _CONDITIONAL_ALT[cons]
                    phonemes.append(self._try_vcv(prev_v, cons, syllable.tone))
                prev_v = _last_char(to_romaji(cons))

        # convert to hiragana
        cv = f"{_STARTING_CONSONANT[final_cons]}{v}"
        cv = _ALT_CV[cv] if cv in _ALT_CV else cv
        hiragana = self._to_hiragana(cv)
        if not using_vc:
            hiragana = self._try_vcv(prev_v, hiragana, syllable.vowel_tone)
        else:
            hiragana = self._fix_cv(hiragana, syllable.vowel_tone)

        # check for nonstandard CV
        split = False
        if self.has_oto(hiragana, syllable.vowel_tone):
            phonemes.append(hiragana)
        elif cv in _CONDITIONAL_ALT:
            cv = _CONDITIONAL_ALT[cv]
            hiragana = self._try_vcv(prev_v, self._to_hiragana(cv), syllable.vowel_tone)
            if self.has_oto(hiragana, syllable.vowel_tone):
                phonemes.append(hiragana)
            else:
                split = True
        else:
            split = True

        # handle nonstandard CV
        if split and cv in _EXTRA_CV:
            split_cv = _EXTRA_CV[cv]
            for part in split_cv:
                if part != prev_v:
                    converted = self._to_hiragana(part)
                    phonemes.append(self._try_vcv(prev_v, converted, syllable.vowel_tone))
                    prev_v = _last_char(part)

        return phonemes

    def process_ending(self, ending):
        prev_v = ending.prev_v
        cc = ending.cc
        phonemes = []

        cc = _adjust_cc(cc, _SPECIAL_CLUSTERS)

        using_vc = False
        # convert to hiragana
        for i in range(len(cc)):
            symbol = cc[i]

            if i == 0:
                has_vc, vc_phonemes = self._has_vc(prev_v, symbol, ending.tone, len(cc) + 1)
                using_vc = has_vc
                phonemes.extend(vc_phonemes)
                if using_vc:
                    continue

            solo = _SOLO_CONSONANT[symbol]
            if not using_vc:
                solo = self._try_vcv(prev_v, solo, ending.tone)
            else:
                using_vc = False
                solo = self._fix_cv(solo, ending.tone)

            if self.has_oto(solo, ending.tone):
                phonemes.append(solo)
            elif solo in _CONDITIONAL_ALT:
                solo = _CONDITIONAL_ALT[solo]
                if not using_vc:
                    solo = self._try_vcv(prev_v, solo, ending.tone)
                else:
                    solo = self._fix_cv(solo, ending.tone)
                phonemes.append(solo)

            if "ん" in solo:
                if ending.is_ending_vc_with_one_consonant:
                    self.try_add_phoneme(phonemes, ending.tone, "n R", "n -", "n-")
                elif (ending.is_ending_vc_with_more_than_one_consonant and cc[-1] == "n") or cc[-1] == "m":
                    self.try_add_phoneme(phonemes, ending.tone, "n R", "n -", "n-")

            prev_v = _last_char(to_romaji(solo))

        if ending.is_ending_v:
            self.try_add_phoneme(phonemes, ending.tone, f"{prev_v} R", f"{prev_v} -", f"{prev_v}-")

        return phonemes

    def _has_vc(self, vowel, cons, tone, cc):
        if vowel == "" or vowel == "-":
            return False, []

        phonemes = []
        if cons == "rr":
            cons = "r"
        elif cons == "rry":
            cons = "ry"
        elif cons == "l":
            cons = "r"
        elif cons == "ly":
            cons = "ry"
        else:
            cons = _STARTING_CONSONANT[cons]

        vc = f"{vowel} {cons}"
        alt_vc = f"{vowel} {cons[0]}"

        if self.has_oto(vc, tone):
            phonemes.append(vc)
        elif self.has_oto(alt_vc, tone):
            phonemes.append(alt_vc)
        else:
            return False, []

        if cons in _AFFRICATES and cc > 1:
            phonemes.append(self._fix_cv(_SOLO_CONSONANT[cons], tone))

        return len(phonemes) > 0, phonemes

    def _try_vcv(self, vowel, cv, tone):
        vcv = f"{vowel} {cv}"
        return vcv if self.has_oto(vcv, tone) else self._fix_cv(cv, tone)

    def _fix_cv(self, cv, tone):
        alt = f"- {cv}"
        return cv if self.has_oto(cv, tone) else alt if self.has_oto(alt, tone) else cv

    @staticmethod
    def _to_hiragana(romaji):
        # WanaKana.ToHiragana(romaji), then ゔ -> ヴ
        return _wanakana_to_hiragana_vu(romaji)

    def get_transition_basic_length_ms_with_attr(self, alias, tone, attr):
        oto_length = self.get_transition_basic_length_ms_by_oto(alias, tone, attr)
        parts = [p for p in alias.split(" ") if p]
        is_vcv = False
        if len(parts) == 2:
            starting_vowels = ["a", "i", "u", "e", "o", "n", "N", "-"]
            ending_vowels = _VOWELS
            # first part must be a vowel (or a rest)
            if parts[0] in starting_vowels:
                cv = parts[1]
                # second part must end in a vowel (romaji CV) OR be japanese (hiragana/katakana)
                is_romaji_vcv = cv[-1] in ending_vowels
                is_japanese_vcv = any(ord(c) > 0xFF for c in cv)
                if is_romaji_vcv or is_japanese_vcv:
                    is_vcv = True
        if is_vcv:
            return self.get_transition_basic_length_ms_by_constant() * 1.0
        return oto_length
