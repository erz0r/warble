"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Plugin.Builtin/SpanishMakkusanPhonemizer.cs

Spanish phonemizer, based on Makkusan's Italian reclist.
Despite being based on an Italian reclist, this phonemizer is for Spanish, although it does support
Italian-exclusive sounds through phonetic input.
Please make sure that the voicebank you want to use contains extra sounds for Spanish.

c# quirks kept: the "if (HasOto(x)) { ...; if (!HasOto(x)) ... }" dead branches, and cc2 starting as
cc.Take(i) (not the next cluster) in the consonant loop.
"""

from ...g2p import SpanishG2p
from .api import phonemizer
from .spanish_syllable_based import cs_pairs_dict
from .syllable_based import SyllableBasedPhonemizer, last, skip, take


@phonemizer("Spanish Makkusan Phonemizer", "ES MAKKU", language="ES", openutau_class="OpenUtau.Plugin.Builtin.SpanishMakkusanPhonemizer", author="Lotte V")
class SpanishMakkusanPhonemizer(SyllableBasedPhonemizer):
    no_gap = True  # Endings has 50 ticks gap

    def __init__(self):
        super().__init__()
        self._mk_vowels = "a,e,i,o,u,3,0".split(",")
        self._mk_consonants = "b,d,dz,dZ,f,g,gn,j,k,l,m,M,n,N,p,r,rr,s,S,t,ts,tS,v,w,y,z,B,D,G,h,T,x,Y,'".split(",")
        self._mk_dictionary_replacements = cs_pairs_dict(
            "a=a;e=e;i=i;o=o;u=u;" + "b=b;ch=tS;d=d;f=f;g=g;gn=gn;k=k;l=l;ll=Y;m=m;n=n;p=p;r=r;rr=rr;s=s;t=t;w=w;x=x;y=y;z=T;I=i;U=u;B=B;D=D;G=G;Y=Y")

    def get_vowels(self):
        return self._mk_vowels

    def get_consonants(self):
        return self._mk_consonants

    def get_dictionary_name(self):
        return "cmudict_es.txt"

    def load_base_dictionary(self):
        return SpanishG2p()

    def get_dictionary_phonemes_replacement(self):
        return self._mk_dictionary_replacements

    def process_syllable(self, syllable):
        prev_v = syllable.prev_v
        cc = syllable.cc
        v = syllable.v
        has_oto = self.has_oto
        va = self.validate_alias

        phonemes = []
        last_c = len(cc) - 1
        first_c = 0

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
            cv = f"{cc[0]}{v}"
            if has_oto(rcv, syllable.vowel_tone):
                base_phoneme = rcv
                if not has_oto(rcv, syllable.vowel_tone):
                    rcv = va(rcv)
                    base_phoneme = rcv
            else:
                base_phoneme = cv
                if not has_oto(cv, syllable.vowel_tone):
                    cv = va(cv)
                    base_phoneme = cv
        elif syllable.is_starting_cv_with_more_than_one_consonant:
            # try RCCV
            rccv = f"-{''.join(cc)}{v}"
            if has_oto(rccv, syllable.vowel_tone) and "-bre" not in rccv:
                base_phoneme = rccv
                if not has_oto(rccv, syllable.vowel_tone):
                    rccv = va(rccv)
                    base_phoneme = rccv
            else:
                _cv = f"_{last(cc)}{v}"
                cv = f"{last(cc)}{v}"
                if has_oto(_cv, syllable.tone):
                    base_phoneme = _cv
                    if not has_oto(_cv, syllable.vowel_tone):
                        _cv = va(_cv)
                        base_phoneme = _cv
                else:
                    base_phoneme = cv
                    if not has_oto(cv, syllable.vowel_tone):
                        cv = va(cv)
                        base_phoneme = cv
                # try RCC
                for i in range(len(cc), 1, -1):
                    t = "".join(take(cc, i))
                    if self.try_add_phoneme(phonemes, syllable.tone, f"-{t}", va(f"-{t}"), f"{t}", va(f"{t}")):
                        first_c = i
                        break
        else:
            base_phoneme = last(cc) + v
            # try CCV
            if len(cc) - first_c > 1:
                for i in range(first_c, len(cc)):
                    ccv = f"{''.join(skip(cc, i))}{v}"
                    if has_oto(ccv, syllable.vowel_tone) and "bre" not in ccv:
                        last_c = i
                        base_phoneme = ccv
                        if not has_oto(ccv, syllable.vowel_tone):
                            ccv = va(ccv)
                            last_c = i
                            base_phoneme = ccv
                            break
                        break
            phonemes.append(f"{prev_v} {cc[0]}")
        i = first_c
        while i < last_c:
            rccv = f"-{''.join(cc)}{v}"
            if not has_oto(rccv, syllable.vowel_tone):
                # we could use some CCV, so lastC is used
                # we could use -CC so firstC is used
                _cv = f"_{last(cc)}{v}"
                cc1 = f"{''.join(skip(cc, i))}"
                if not has_oto(cc1, syllable.tone):
                    cc1 = va(cc1)
                if not has_oto(cc1, syllable.tone):
                    cc1 = f"{cc[i]}{cc[i + 1]}"
                if not has_oto(cc1, syllable.tone):
                    cc1 = va(cc1)
                if not has_oto(cc1, syllable.tone):
                    cc1 = f"{cc[i]} {cc[i + 1]}"
                if not has_oto(cc1, syllable.tone):
                    cc1 = va(cc1)
                if has_oto(_cv, syllable.vowel_tone) and f"{cc[i]} {cc[i + 1]}" not in cc1:
                    base_phoneme = _cv
                if i + 1 < last_c:
                    cc2 = f"{''.join(take(cc, i))}"
                    if not has_oto(cc2, syllable.tone):
                        cc2 = va(cc2)
                    if not has_oto(cc2, syllable.tone):
                        cc2 = f"{cc[i + 1]}{cc[i + 2]}"
                    if not has_oto(cc2, syllable.tone):
                        cc2 = va(cc2)
                    if not has_oto(cc2, syllable.tone):
                        cc2 = f"{cc[i + 1]} {cc[i + 2]}"
                    if not has_oto(cc2, syllable.tone):
                        cc2 = va(cc2)
                    if has_oto(_cv, syllable.vowel_tone) and has_oto(cc2, syllable.vowel_tone) and f"{cc[i + 1]} {cc[i + 2]}" not in cc2:
                        base_phoneme = _cv
                    if has_oto(cc1, syllable.tone) and has_oto(cc2, syllable.tone) and f"{''.join(skip(cc, i))}" not in cc1:
                        # like [V C1] [C1 C2] [C2 C3] [C3 ..]
                        phonemes.append(cc1)
                    elif self.try_add_phoneme(phonemes, syllable.tone, cc1, va(cc1)):
                        # like [V C1] [C1 C2] [C2 ..]
                        i += 1
                    elif self.try_add_phoneme(phonemes, syllable.tone, f"{cc[i]}{cc[i + 1]}-", va(f"{cc[i]}{cc[i + 1]}-")):
                        # like [V C1] [C1 C2-] [C3 ..]
                        pass
                else:
                    # like [V C1] [C1 C2]  [C2 ..] or like [V C1] [C1 -] [C3 ..]
                    self.try_add_phoneme(phonemes, syllable.tone, cc1, va(cc1))
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
                if not self.has_oto(vcr, ending.tone):
                    vcr = self.validate_alias(vcr)
                    phonemes.append(vcr)
            else:
                phonemes.append(f"{v} {cc[0]}")
        elif ending.is_ending_vc_with_more_than_one_consonant:
            phonemes.append(f"{v} {cc[0]}")
            for i in range(len(cc) - 1):
                cc1 = f"{cc[i]}{cc[i + 1]}-"
                if self.has_oto(cc1, ending.tone):
                    phonemes.append(cc1)
                    if not self.has_oto(cc1, ending.tone):
                        cc1 = self.validate_alias(cc1)
                        phonemes.append(cc1)
        return phonemes

    def get_hardcoded_fallback(self, alias, tone, suppressed_tokens):
        candidate = alias

        def try_replace(from_token, to_token):
            nonlocal candidate
            if suppressed_tokens is not None and from_token in suppressed_tokens:
                return
            candidate = candidate.replace(from_token, to_token)

        # Consonant normalizations & substitutions
        try_replace("B", "b")
        try_replace("D", "d")
        try_replace("G", "g")
        try_replace("T", "s")
        try_replace("Y", "y")
        try_replace("x", "h")
        try_replace("y", "i")
        try_replace("w", "u")

        if candidate != alias and self.has_oto(candidate, tone):
            return candidate
        return None

    def get_transition_basic_length_ms_with_attr(self, alias, tone, attr):
        oto_length = self.get_transition_basic_length_ms_by_oto(alias, tone, attr)
        return oto_length
