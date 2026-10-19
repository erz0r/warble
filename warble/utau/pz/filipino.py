"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Plugin.Builtin/FilipinoPhonemizer.cs

filipino vcv & cvvc (cadlaxa): arpasing+ with filipino vowels, the plugin-folder filipino.yaml as its only
dictionary (no g2p model), and words the dictionary doesn't know split greedily into the yaml's consonants and
vowels (a leading or trailing apostrophe becomes a glottal stop "q")."""

from ...g2p._cs import to_lower_invariant
from .api import phonemizer
from .arpasing_plus import ArpasingPlusPhonemizer


@phonemizer("Filipino Phonemizer", "FIL VCV & CVVC", language="FIL", openutau_class="OpenUtau.Plugin.Builtin.FilipinoPhonemizer", author="Cadlaxa")
class FilipinoPhonemizer(ArpasingPlusPhonemizer):
    yaml_file_name = "filipino.yaml"
    yaml_template = "filipino-template.yaml"
    no_gap = True  # endings have a 50 ticks gap

    def __init__(self):
        super().__init__()
        self.vowels = ["a", "e", "i", "o", "u", "ay", "ey", "oy", "uy", "aw", "ew", "ow", "iw"]
        self.consonants = []
        self.diphthong_tails = {"ay": "y", "ey": "y", "oy": "y", "uy": "y", "aw": "w", "ew": "w", "ow": "w", "iw": "w"}

    def get_vowels(self):
        return self.vowels

    def get_consonants(self):
        return self.consonants

    def get_dictionary_name(self):
        return ""

    def get_symbols(self, note):
        original = super().get_symbols(note)
        if note.phonetic_hint:
            return [s for s in note.phonetic_hint.split(" ") if s]

        if original is None or len(original) == 0:
            lyric = to_lower_invariant(note.lyric)
            fallback_split = []
            vowels = self.get_vowels()
            consonants = self.get_consonants()

            # handle apostrophes at the start or end
            has_leading = lyric.startswith("'")
            has_trailing = lyric.endswith("'")
            if has_leading:
                lyric = lyric[1:]
            if has_trailing and len(lyric) > 0:
                lyric = lyric[:-1]

            cons_sorted = sorted(consonants, key=len, reverse=True)
            vow_sorted = sorted(vowels, key=len, reverse=True)
            ii = 0
            while ii < len(lyric):
                match = None
                for cons in cons_sorted:
                    if lyric[ii:].startswith(cons):
                        match = cons
                        break
                if match is None:
                    for vow in vow_sorted:
                        if lyric[ii:].startswith(vow):
                            match = vow
                            break
                if match is not None:
                    fallback_split.append(match)
                    ii += len(match)
                else:
                    fallback_split.append(lyric[ii])
                    ii += 1
            # add "q" at the beginning or end if needed
            if has_leading:
                fallback_split.insert(0, "q")
            if has_trailing:
                fallback_split.append("q")
            original = fallback_split

        return list(original)

    def get_base_g2ps(self):
        return []
