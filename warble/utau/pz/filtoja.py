"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Plugin.Builtin/FILtoJAPhonemizer.cs

filipino to japanese (cadlaxa): the en-to-ja engine (entoja.py) with filipino vowels and the fil2ja.yaml template.
it has no dictionary at all (the base g2p list is empty), so every word is split greedily into the consonants and
vowels (a leading or trailing apostrophe becomes a glottal stop "q"); "ng" and "mga" are spelled out."""

import os

from ...g2p import G2pFallbacks
from ...g2p._cs import to_lower_invariant
from .api import phonemizer
from .entoja import DATA_DIR, ENtoJAPhonemizer


@phonemizer("Filipino to Japanese Phonemizer", "FIL to JA", language="FIL", openutau_class="OpenUtau.Plugin.Builtin.FILtoJAPhonemizer", author="Cadlaxa")
class FILtoJAPhonemizer(ENtoJAPhonemizer):
    yaml_file_name = "fil2ja.yaml"
    yaml_template = os.path.join(DATA_DIR, "fil2ja.template.yaml")
    yaml_version = "1.0"

    def __init__(self):
        super().__init__()
        self.vowels = ["a", "e", "i", "o", "u"]
        self.consonants = "b,ch,d,dh,dr,dx,f,g,hh,jh,k,l,m,n,ng,p,q,r,s,sh,t,th,tr,v,w,y,z".split(",")

    def get_dictionary_name(self):
        return ""

    def load_base_dictionary(self):
        g2ps = []
        # g2ps.Add(new ArpabetPlusG2p());
        return G2pFallbacks(g2ps)

    def get_symbols(self, note):
        original = super().get_symbols(note)
        if note.lyric == "ng":
            return ["n", "a", "ng"]
        if note.lyric == "mga":
            return ["m", "a", "ng", "a"]
        if original is None:
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
