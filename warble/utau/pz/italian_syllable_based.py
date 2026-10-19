"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Plugin.Builtin/ItalianSyllableBasedPhonemizer.cs

italian syllable-based (lotte v), dictionary based and built on makkusan's list: an optional it-syl.yaml in
the singer folder, then the italian g2p. extra spanish consonants are only reachable through phonetic hints.

the affricate fallback (dz/ts/dZ/tS -> d/t) switches on for good once a syllable has a consonant with no
"<c> dz|dZ|ts|tS" alias; like the c# field, the flag lives on the instance and is never reset."""

import os

from ...g2p import G2pDictionary, G2pFallbacks, ItalianG2p
from .api import phonemizer
from .german_vccv import to_dictionary
from .syllable_based import SyllableBasedPhonemizer, g2p_data_from_raw, last, load_raw_yaml, skip, take


@phonemizer("Italian Syllable-Based Phonemizer", "IT SYL", language="IT", openutau_class="OpenUtau.Plugin.Builtin.ItalianSyllableBasedPhonemizer", author="Lotte V")
class ItalianSyllableBasedPhonemizer(SyllableBasedPhonemizer):
    """Italian syllable-based phonemizer. As opposed to the already existing Italian phonemizer, this one is
    dictionary-based. Similarly to that one, it's based on Makkusan's list. It also has support for extra
    Spanish consonants, but only through phonetic input."""

    no_gap = True  # Endings has 50 ticks gap

    def __init__(self):
        super().__init__()
        self._it_vowels = "a,e,i,o,u,3,0".split(",")
        self._it_consonants = "b,d,dz,dZ,f,g,gn,j,k,l,m,M,n,N,p,r,rr,s,S,t,ts,tS,v,w,y,z,B,D,G,h,T,x,Y,'".split(",")
        self._it_dictionary_replacements = to_dictionary(
            "a=a;e=e;i=i;o=o;u=u;EE=3;OO=0;"
            "b=b;d=d;dz=dz;dZZ=dZ;f=f;g=g;j=y;" + "JJ=gn;k=k;l=l;LL=j;m=m;n=n;nf=M;ng=N;p=p;r=r;s=s;SS=S;t=t;ts=ts;tSS=tS;v=v;w=w;z=z", ";")
        self._fall_backs = to_dictionary("dz=d;ts=t;dZ=d;tS=t", ";")
        self._is_fall_back = False

    def get_vowels(self):
        return self._it_vowels

    def get_consonants(self):
        return self._it_consonants

    def get_dictionary_name(self):
        return "cmudict_it.txt"

    def get_dictionary_phonemes_replacement(self):
        return self._it_dictionary_replacements

    def load_base_dictionary(self):
        g2ps = []
        # Load dictionary from singer folder.
        if self.singer is not None and getattr(self.singer, "location", None):
            file = os.path.join(self.singer.location, "it-syl.yaml")
            if os.path.isfile(file):
                try:
                    g2ps.append(G2pDictionary.new_builder().load(g2p_data_from_raw(load_raw_yaml(file))).build())
                except Exception:  # noqa: BLE001 - Log.Error(e, $"Failed to load {file}")
                    pass
        g2ps.append(ItalianG2p())
        return G2pFallbacks(g2ps)

    def process_syllable(self, syllable):
        prev_v = syllable.prev_v
        cc = syllable.cc
        v = syllable.v

        phonemes = []
        last_c = len(cc) - 1
        first_c = 0

        for cn in cc:
            if not self.has_oto(f"{cn} dz", syllable.tone) and not self.has_oto(f"{cn} dZ", syllable.tone) \
                    and not self.has_oto(f"{cn} ts", syllable.tone) and not self.has_oto(f"{cn} tS", syllable.tone):
                self._is_fall_back = True

        if syllable.is_starting_v:
            base_phoneme = f"-{v}"
        elif syllable.is_vv:
            if not self.can_make_alias_extension(syllable):
                base_phoneme = f"{prev_v} {v}"
            else:
                # the previous alias will be extended
                base_phoneme = None
        elif syllable.is_starting_cv_with_one_consonant:
            # TODO: move to config -CV or -C CV
            rcv = f"-{cc[0]}{v}"
            if self.has_oto(rcv, syllable.vowel_tone):
                base_phoneme = rcv
            else:
                base_phoneme = f"{cc[0]}{v}"
        elif syllable.is_starting_cv_with_more_than_one_consonant:
            # try RCCV
            rccv = f"-{''.join(cc)}{v}"
            if self.has_oto(rccv, syllable.vowel_tone) and "-bre" not in rccv:
                base_phoneme = rccv
            else:
                _cv = f"_{last(cc)}{v}"
                if self.has_oto(_cv, syllable.tone):
                    base_phoneme = _cv
                else:
                    base_phoneme = f"{last(cc)}{v}"
                # try RCC
                for i in range(len(cc), 1, -1):
                    if self.try_add_phoneme(phonemes, syllable.tone, f"-{''.join(take(cc, i))}"):
                        first_c = i
                        break
        else:
            base_phoneme = last(cc) + v
            # try CCV
            if len(cc) - first_c > 1:
                for i in range(first_c, len(cc)):
                    ccv = f"{''.join(skip(cc, i))}{v}"
                    if self.has_oto(ccv, syllable.vowel_tone) and "bre" not in ccv:
                        last_c = i
                        base_phoneme = ccv
                        break

            for i in range(last_c + 1, -1, -1):
                vcc = f"{prev_v} {''.join(take(cc, 2))}"
                vc = f"{prev_v} {cc[0]}"
                if self.has_oto(vcc, syllable.tone) or self.has_oto(self.validate_alias(vcc), syllable.tone):
                    phonemes.append(vcc)
                    first_c = 1
                    break
                else:
                    phonemes.append(vc)
                    break

        i = first_c
        while i < last_c:
            rccv = f"-{''.join(cc)}{v}"
            if not self.has_oto(rccv, syllable.vowel_tone):
                # we could use some CCV, so lastC is used
                # we could use -CC so firstC is used
                _cv = f"_{last(cc)}{v}"
                cc1 = "".join(skip(cc, i))
                if not self.has_oto(cc1, syllable.tone):
                    cc1 = f"{cc[i]}{cc[i + 1]}"
                if not self.has_oto(f"{cc[i]}{cc[i + 1]}", syllable.tone) and not self.has_oto("".join(skip(cc, i)), syllable.tone):
                    cc1 = self.validate_alias(f"{cc[i]} {cc[i + 1]}")
                if self.has_oto(_cv, syllable.vowel_tone) and self.has_oto(cc1, syllable.tone) and f"{cc[i]} {cc[i + 1]}" not in cc1:
                    base_phoneme = _cv
                if i + 1 < last_c:
                    cc2 = "".join(take(cc, i))
                    if not self.has_oto(cc2, syllable.tone):
                        cc2 = f"{cc[i + 1]}{cc[i + 2]}"
                    if not self.has_oto(f"{cc[i + 1]}{cc[i + 2]}", syllable.tone) and not self.has_oto("".join(skip(cc, i)), syllable.tone):
                        cc2 = self.validate_alias(f"{cc[i + 1]} {cc[i + 2]}")
                    if self.has_oto(f"_{last(cc)}{v}", syllable.vowel_tone) and self.has_oto(cc2, syllable.vowel_tone) \
                            and f"{cc[i + 1]} {cc[i + 2]}" not in cc2:
                        base_phoneme = f"_{last(cc)}{v}"
                    if self.has_oto(cc1, syllable.tone) and self.has_oto(cc2, syllable.tone) and "".join(skip(cc, i)) not in cc1:
                        # like [V C1] [C1 C2] [C2 C3] [C3 ..]
                        phonemes.append(cc1)
                    elif self.try_add_phoneme(phonemes, syllable.tone, cc1):
                        # like [V C1] [C1 C2] [C2 ..]
                        i += 1
                    elif self.try_add_phoneme(phonemes, syllable.tone, f"{cc[i]}{cc[i + 1]}-"):
                        # like [V C1] [C1 C2-] [C3 ..]
                        pass
                else:
                    # like [V C1] [C1 C2]  [C2 ..] or like [V C1] [C1 -] [C3 ..]
                    self.try_add_phoneme(phonemes, syllable.tone, cc1)
            i += 1
        phonemes.append(base_phoneme)
        return phonemes

    def process_ending(self, ending):
        cc = ending.cc
        v = ending.prev_v

        phonemes = []
        if ending.is_ending_v:
            phonemes.append(f"{v} R")
        elif ending.is_ending_vc_with_one_consonant:
            vcr = f"{v}{cc[0]}-"
            if self.has_oto(vcr, ending.tone):
                phonemes.append(vcr)
            else:
                phonemes.append(f"{v} {cc[0]}")
        elif ending.is_ending_vc_with_more_than_one_consonant:
            phonemes.append(f"{v} {cc[0]}")
            for i in range(len(cc) - 1):
                cc1 = f"{cc[i]}{cc[i + 1]}-"
                if self.has_oto(cc1, ending.tone):
                    phonemes.append(cc1)
        return phonemes

    def validate_alias(self, alias, tone=0):
        if self.has_oto(alias, tone):
            return alias

        base_resolved = super().validate_alias(alias, tone)
        if base_resolved and base_resolved != alias:
            if self.has_oto(base_resolved, tone):
                return base_resolved
            alias = base_resolved
        if self._is_fall_back:
            for k, val in self._fall_backs.items():
                alias = alias.replace(k, val)
        return alias

    def get_transition_basic_length_ms_with_attr(self, alias, tone, attr):
        oto_length = self.get_transition_basic_length_ms_by_oto(alias, tone, attr)
        return oto_length
