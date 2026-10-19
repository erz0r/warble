"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Plugin.Builtin/RussianVCCVPhonemizer.cs

russian vccv (Heiden.BZR): RussianG2p (LoadBaseDictionary is overridden, so cmudict_ru.txt is never read),
"- CV" / "V C" / "C C" / "VC -" aliases, timing from the oto. private c# fields that hide the base ones are
kept apart from the base fields (see russian_cvc.py).
"""

from ...g2p import RussianG2p
from .api import phonemizer
from .russian_cvc import _to_dictionary
from .syllable_based import SyllableBasedPhonemizer, cs_replace, last


@phonemizer("Russian VCCV Phonemizer", "RU VCCV", language="RU", openutau_class="OpenUtau.Plugin.Builtin.RussianVCCVPhonemizer", author="Heiden.BZR")
class RussianVCCVPhonemizer(SyllableBasedPhonemizer):
    no_gap = True  # Endings has 50 ticks gap

    def __init__(self):
        super().__init__()
        self._ru_vowels = "a,e,o,u,y,i,M,N,ex,ax,x".split(",")
        self._ru_consonants = "sh',sh,zh,j,ts,ch,b',b,v',v,g',g,d',d,z',z,k',k,l',l,m',m,n',n,p',p,r',r,s',s,t',t,f',f,h',h".split(",")
        self.burst_consonants = "t,t',k,k',p,p',ch,ts,b,b',g,g',d,d'".split(",")
        self._ru_dictionary_replacements = _to_dictionary(
            "a=ax;aa=a;ay=a;b=b;bb=b';c=ts;ch=ch;d=d;dd=d';ee=e;"
            "f=f;ff=f';g=g;gg=g';h=h;hh=h';i=x;ii=i;j=j;ja=a;je=e;jo=o;ju=u;k=k;kk=k';l=l;ll=l';m=m;mm=m';n=n;nn=n';oo=o;ae=e;"
            "p=p;pp=p';r=r;rr=r';s=s;sch=sh';sh=sh;ss=s';t=t;tt=t';u=u;uj=u;uu=u;v=v;vv=v';y=ex;yy=y;z=z;zh=zh;zz=z'", ";", "=", drop_same=True)
        self.no_start_consonants = "t,t',k,k',p,p',ch,ts".split(",")
        self.hard_consonants = "b,v,g,d,z,k,l,m,n,p,r,s,t,f,h,sh,ts".split(",")
        self.short_consonants = "r,r'".split(",")
        self.long_consonants = "sh,sh',ch,ts,ts".split(",")

    def get_vowels(self):
        return self._ru_vowels

    def get_consonants(self):
        return self._ru_consonants

    def get_dictionary_name(self):
        return "cmudict_ru.txt"

    def load_base_dictionary(self):
        return RussianG2p()

    def get_dictionary_phonemes_replacement(self):
        return self._ru_dictionary_replacements

    def process_syllable(self, syllable):
        prev_v = syllable.prev_v
        cc = syllable.cc
        v = syllable.v

        phonemes = []
        if syllable.is_starting_v:
            base_phoneme = f"- {v}"
        elif syllable.is_vv:
            if not self.can_make_alias_extension(syllable):
                base_phoneme = f"{prev_v} {v}"
            else:
                # the previous alias will be extended
                base_phoneme = None
        elif syllable.is_starting_cv_with_one_consonant:
            # TODO: move to config -CV or -C CV
            rcv = f"- {cc[0]}{v}"
            if self.has_oto(rcv, syllable.tone):
                base_phoneme = rcv
            else:
                base_phoneme = f"{cc[0]}{v}"
                if cc[0] not in self.no_start_consonants:
                    phonemes.append(f"- {cc[0]}")
        elif syllable.is_starting_cv_with_more_than_one_consonant:
            base_phoneme = f"{last(cc)}{v}"
            if cc[0] not in self.no_start_consonants:
                phonemes.append(f"- {cc[0]}")
        else:  # VCV
            base_phoneme = f"{last(cc)}{v}"
            phonemes.append(f"{prev_v} {cc[0]}")
        for i in range(len(cc) - 1):
            # same for any transition
            current_cc = f"{cc[i]} {cc[i + 1]}"
            if not self.has_oto(current_cc, syllable.tone):
                continue
            phonemes.append(current_cc)
        phonemes.append(base_phoneme)
        return phonemes

    def process_ending(self, ending):
        cc = ending.cc
        v = ending.prev_v

        phonemes = []
        if ending.is_ending_v:
            phonemes.append(f"{v} -")
        elif ending.is_ending_vc_with_one_consonant:
            # TODO: move to config VC- or VC C-
            vcr = f"{v}{cc[0]} -"
            if self.has_oto(vcr, ending.tone):
                phonemes.append(vcr)
            else:
                phonemes.append(f"{v} {cc[0]}")
                phonemes.append(f"{cc[0]} -")
        else:  # VCmR
            phonemes.append(f"{v} {cc[0]}")
            for i in range(len(cc) - 1):
                current_cc = f"{cc[i]} {cc[i + 1]}"
                if not self.has_oto(current_cc, ending.tone):
                    continue
                phonemes.append(current_cc)
            if last(cc) in self.burst_consonants:
                phonemes.append(f"{last(cc)} -")
        return phonemes

    def validate_alias(self, alias, tone=0):
        if self.has_oto(alias, tone):
            return alias

        base_resolved = super().validate_alias(alias, tone)
        if base_resolved and base_resolved != alias:
            if self.has_oto(base_resolved, tone):
                return base_resolved
            alias = base_resolved
        for consonant in ["'", "ch", "j"]:
            for vowel in ["ax", "ex"]:
                alias = cs_replace(alias, consonant + vowel, consonant + "x")
            alias = cs_replace(alias, consonant + "y", consonant + "i")
        for consonant in self.hard_consonants:
            alias = cs_replace(alias, consonant + "i", consonant + "y")
        return alias

    def get_transition_basic_length_ms_with_attr(self, alias, tone, attr):
        oto_length = self.get_transition_basic_length_ms_by_oto(alias, tone, attr)
        return oto_length
