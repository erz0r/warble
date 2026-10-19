"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Plugin.Builtin/BrazilianPortugueseCVCPhonemizer.cs

Brazilian Portuguese CVC Phonemizer by HAI-D. Connotation: BRAPA, main accent: neutral.
supported aliases: -C, -V, C-, V-, -CV, VC-, CV, VC, V, VV, _V. PortugueseG2p (LoadBaseDictionary is
overridden, so cmudict_ptbr.txt is never read). private c# fields that hide the base ones are kept apart from
the base fields (see russian_cvc.py).
"""

from ...g2p import PortugueseG2p
from .api import phonemizer
from .russian_cvc import _to_dictionary
from .syllable_based import SyllableBasedPhonemizer, cs_replace, last


@phonemizer("Brazilian Portuguese CVC Phonemizer", "PT-BR CVC", language="PT", openutau_class="OpenUtau.Plugin.Builtin.BrazilianPortugueseCVCPhonemizer", author="HAI-D")
class BrazilianPortugueseCVCPhonemizer(SyllableBasedPhonemizer):

    def __init__(self):
        super().__init__()
        self._pt_vowels = "a,oa,ah,ahn,ax,an,e,en,eh,ehn,ae,aen,i,in,i0,o,on,oh,ohn,u,un,u0".split(",")
        self._pt_consonants = "b,bv,ch,d,dj,f,g,gv,h,hr,k,l,l0,lh,m,n,ng,nh,p,r,rr,rw,s,sh,t,v,w,x,y,z,rh".split(",")
        self.burst_consonants = "b,ch,d,dj,g,k,p,t".split(",")
        self._pt_dictionary_replacements = _to_dictionary(
            "a=a;e=e;i=i;o=o;u=u;E=eh;O=oh;a~=an;e~=en;i~=in;o~=on;u~=un;"
            "b=b;tS=ch;d=d;dZ=dj;f=f;g=g;h=h;X=h;R=h;Z=j;k=k;l=l;L=lh;m=m;n=n;J=nh;p=p;r=r;s=s;S=sh;t=t;v=v;w=w;w~=w;j=y;j~=y;z=z",
            ";", "=", drop_same=True)
        self.short_consonants = "r".split(",")
        self.long_consonants = "s,sh".split(",")

    def get_vowels(self):
        return self._pt_vowels

    def get_consonants(self):
        return self._pt_consonants

    def get_dictionary_name(self):
        return "cmudict_ptbr.txt"

    def load_base_dictionary(self):
        return PortugueseG2p()

    def get_dictionary_phonemes_replacement(self):
        return self._pt_dictionary_replacements

    def process_syllable(self, syllable):
        prev_v = syllable.prev_v
        cc = syllable.cc
        v = syllable.v

        phonemes = []
        if syllable.is_starting_v:
            base_phoneme = f"- {v}"
        elif syllable.is_vv:  # if VV
            if not self.can_make_alias_extension(syllable):
                # try VV
                base_phoneme = f"{prev_v} {v}"
                # if no VV -> _V
                if not self.has_oto(base_phoneme, syllable.vowel_tone):
                    base_phoneme = f"_{v}"
                    # if no _V -> V
                    if not self.has_oto(base_phoneme, syllable.vowel_tone):
                        base_phoneme = v
            else:
                # the previous alias will be extended
                base_phoneme = None
        elif syllable.is_starting_cv:
            base_phoneme = f"-{last(cc)} {v}"
            for i in range(len(cc) - 1):
                phonemes.append(f"- {cc[i]}")
        else:  # VCV
            if len(cc) == 1 or self.is_short(syllable) or last(cc) == "`":
                base_phoneme = f"{last(cc)} {v}"
            else:
                base_phoneme = f"-{last(cc)} {v}"
            phonemes.append(f"{prev_v} {cc[0]}")
            offset = 0 if cc[0] in self.burst_consonants else 1
            for i in range(offset, len(cc) - 1):
                cr = f"{cc[i]} -"
                phonemes.append(cr if self.has_oto(cr, syllable.tone) else cc[i])
        phonemes.append(base_phoneme)
        return phonemes

    def process_ending(self, ending):
        cc = ending.cc
        v = ending.prev_v

        phonemes = []
        if ending.is_ending_v:
            phonemes.append(f"{v} -")
        else:
            phonemes.append(f"{v} {cc[0]}-")
            for i in range(1, len(cc)):
                cr = f"{cc[i]} -"
                phonemes.append(cr if self.has_oto(cr, ending.tone) else cc[i])
        return phonemes

    # change rh V -> r V
    # since rh is a VC only alias, r is used as their natural approximant to make CV connections, if it happens
    def validate_alias(self, alias, tone=0):
        if self.has_oto(alias, tone):
            return alias

        base_resolved = super().validate_alias(alias, tone)
        if base_resolved and base_resolved != alias:
            if self.has_oto(base_resolved, tone):
                return base_resolved
            alias = base_resolved
        for vowel in self._pt_vowels:
            alias = cs_replace(alias, "rh" + " " + vowel, "r" + " " + vowel)
        return alias

    def get_transition_basic_length_ms(self, alias=""):
        for c in self.short_consonants:
            if alias.endswith(c):
                return super().get_transition_basic_length_ms() * 0.75
        for c in self.long_consonants:
            if alias.endswith(c):
                return super().get_transition_basic_length_ms() * 1.5
        return super().get_transition_basic_length_ms()
