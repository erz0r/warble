"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Plugin.Builtin/SimpleVoicevoxENtoJAPhonemizer.cs

simple voicevox english to japanese (tubs & roku10shi): cmudict (arpabet) symbols folded into a few romaji
vowels, every syllable spelled as plain kana (no vcv/vc), lone consonants as u/o morae. meant for voicevox
singers; on a classic bank (what warble and the parity harness load) the voicevox dictionary isn't loaded and the
only voicevox part left is VoicevoxUtils.phoneme_List.paus, the pause lyrics (R pau AP SP -> R)."""

from ...g2p import ArpabetG2p
from .api import phonemizer
from .estoja import _adjust_cc
from .kotoja import _wanakana_to_hiragana
from .syllable_based import SyllableBasedPhonemizer

# VoicevoxUtils.phoneme_List.paus (Phoneme_list's constructor)
_PAUS = {g: "R" for g in "R pau AP SP".split()}

_VOWELS = "a i u e o ay ey oy ow aw".split()
_CONSONANTS = "b by ch d dh f g gy h hy j k ky l ly m my n ny ng p py r ry s sh t ts th v w y z zh".split()

_DICTIONARY_PHONEMES_REPLACEMENT = {
    "aa": "a", "ae": "e", "ah": "a", "ao": "o", "aw": "aw", "ay": "ay", "b": "b", "ch": "ch", "d": "d", "dh": "dh",
    "eh": "e", "er": "o", "ey": "ey", "f": "f", "g": "g", "hh": "h", "ih": "e", "iy": "i", "jh": "j", "k": "k", "l": "l",
    "m": "m", "n": "n", "ng": "ng", "ow": "ow", "oy": "oy", "p": "p", "r": "r", "s": "s", "sh": "sh", "t": "t",
    "th": "th", "uh": "o", "uw": "u", "v": "v", "w": "w", "y": "y", "z": "z", "zh": "zh",
}

_STARTING_CONSONANT = {
    "": "", "b": "b", "by": "by", "ch": "ch", "d": "d", "dh": "d", "f": "f", "g": "g", "gy": "gy", "h": "h", "hy": "hy",
    "j": "j", "k": "k", "ky": "ky", "l": "r", "ly": "ry", "m": "m", "my": "my", "n": "n", "ny": "ny", "ng": "n",
    "p": "p", "py": "py", "r": "rr", "ry": "ry", "s": "s", "sh": "sh", "t": "t", "ts": "ts", "th": "s", "v": "v",
    "w": "w", "y": "y", "z": "z", "zh": "sh",
}

_SOLO_CONSONANT = {
    "b": "ぶ", "by": "び", "ch": "ちゅ", "d": "ど", "dh": "ず", "f": "ふ", "g": "ぐ", "gy": "ぎ", "h": "ほ", "hy": "ひ",
    "j": "じゅ", "k": "く", "ky": "き", "l": "う", "ly": "り", "m": "む", "my": "み", "n": "ん", "ny": "に", "ng": "ん",
    "p": "ぷ", "py": "ぴ", "r": "う", "ry": "り", "s": "す", "sh": "しゅ", "t": "と", "ts": "つ", "th": "す", "v": "ヴ",
    "w": "う", "y": "い", "z": "ず", "zh": "しゅ",
}

_SPECIAL_CLUSTERS = "ky gy ts ny hy by py my ry ly".split()

_ALT_CV = {
    "si": "suli", "zi": "zuli", "ti": "teli", "tu": "tolu", "di": "deli", "du": "dolu", "hu": "holu", "yi": "i",
    "wu": "u", "wo": "ulo", "rra": "wa", "rri": "wi", "rru": "ru", "rre": "we", "rro": "ulo",
}

_CONDITIONAL_ALT = {"ulo": "wo", "va": "fa", "vi": "fi", "vu": "fu", "ヴ": "ふ", "ve": "fe", "vo": "fo"}

_EXTRA_CV = {
    "kye": ["ki", "e"], "gye": ["gi", "e"], "suli": ["se", "i"], "she": ["si", "e"], "zuli": ["ze", "i"],
    "je": ["ji", "e"], "teli": ["te", "i"], "tolu": ["to", "u"], "che": ["chi", "e"], "tsa": ["tsu", "a"],
    "tsi": ["tsu", "i"], "tse": ["tsu", "e"], "tso": ["tsu", "o"], "deli": ["de", "i"], "dolu": ["do", "u"],
    "nye": ["ni", "e"], "hye": ["hi", "e"], "holu": ["ho", "u"], "fa": ["fu", "a"], "fi": ["fu", "i"],
    "fe": ["fu", "e"], "fo": ["fu", "o"], "bye": ["bi", "e"], "pye": ["pi", "e"], "mye": ["mi", "e"],
    "ye": ["i", "e"], "rye": ["ri", "e"], "wi": ["u", "i"], "we": ["u", "e"], "ulo": ["u", "o"],
}


@phonemizer("Simple Voicevox ENtoJA Phonemizer", "S-VOICEVOX EN to JA", language="EN", openutau_class="OpenUtau.Core.Voicevox.SimpleVoicevoxENtoJAPhonemizer", author="TUBS & ROKU10SHI")
class SimpleVoicevoxENtoJAPhonemizer(SyllableBasedPhonemizer):
    # (SetSinger also keeps the singer as a VoicevoxSinger and loads its dictionary; a classic bank isn't one)

    def get_vowels(self):
        return _VOWELS

    def get_consonants(self):
        return _CONSONANTS

    def get_dictionary_name(self):
        return "cmudict-0_7b.txt"

    def get_dictionary_phonemes_replacement(self):
        return _DICTIONARY_PHONEMES_REPLACEMENT

    def load_base_dictionary(self):
        return ArpabetG2p()

    def get_symbols(self, note):
        modified = []
        if note.lyric in _PAUS:
            modified.append(_PAUS[note.lyric])
        else:
            original = super().get_symbols(note)
            if original is None:
                return None
            diphthongs = ["ay", "ey", "oy", "ow", "aw"]
            for s in original:
                if s in diphthongs:
                    modified.extend([s[0], s[1]])
                else:
                    modified.append(s)
        return modified

    def process_syllable(self, syllable):
        # skip processing if this note extends the prevous syllable
        if self.can_make_alias_extension(syllable):
            return [None]

        cc = syllable.cc
        v = syllable.v
        phonemes = []
        if v in _PAUS:
            phonemes.append(_PAUS[v])
            return phonemes

        cc = _adjust_cc(cc, _SPECIAL_CLUSTERS)

        # separate CCs and main CV
        final_cons = ""
        if len(cc) > 0:
            final_cons = cc[-1]
            for i in range(0, len(cc) - 1):
                cons = _SOLO_CONSONANT[cc[i]]
                if self.has_oto(cons, syllable.tone):
                    phonemes.append(cons)

        # convert to hiragana
        cv = f"{_STARTING_CONSONANT[final_cons]}{v}"
        cv = _ALT_CV[cv] if cv in _ALT_CV else cv
        hiragana = _wanakana_to_hiragana(cv)

        # check for nonstandard CV
        split = False
        if self.has_oto(hiragana, syllable.vowel_tone):
            phonemes.append(hiragana)
        else:
            split = True
        # handle nonstandard CV
        if split and cv in _EXTRA_CV:
            for part in _EXTRA_CV[cv]:
                phonemes.append(_wanakana_to_hiragana(part))

        return phonemes

    def process_ending(self, ending):
        cc = _adjust_cc(ending.cc, _SPECIAL_CLUSTERS)
        phonemes = []
        # convert to hiragana
        for symbol in cc:
            solo = _SOLO_CONSONANT[symbol]
            if self.has_oto(solo, ending.tone):
                phonemes.append(solo)
            elif solo in _CONDITIONAL_ALT:
                solo = _CONDITIONAL_ALT[solo]
                phonemes.append(solo)
        return phonemes
