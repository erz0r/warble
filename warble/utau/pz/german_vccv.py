"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Plugin.Builtin/GermanVCCVPhonemizer.cs

german vccv (lotte v), based on utau felix's vccv voicebank. symbols come from de_vccv.yaml (singer folder,
then the plugin-folder template) and the german g2p, remapped to x-sampa; diphthongs aU/OY/aI are split into a
vowel and a "^" offglide (a consonant-like symbol), which the hardcoded fallbacks turn back into U/I/Y."""

import os

from ...g2p import GermanG2p
from .api import phonemizer
from .syllable_based import SyllableBasedPhonemizer, last, skip, take

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "romance")


def to_dictionary(spec, sep):
    """spec.Split(sep).Select(Split('=')).Where(len == 2).Where(a != b).ToDictionary() (throws on duplicate keys)."""
    out = {}
    for entry in spec.split(sep):
        parts = entry.split("=")
        if len(parts) != 2 or parts[0] == parts[1]:
            continue
        if parts[0] in out:
            raise ValueError(f"An item with the same key has already been added. Key: {parts[0]}")
        out[parts[0]] = parts[1]
    return out


@phonemizer("German VCCV Phonemizer", "DE VCCV", language="DE", openutau_class="OpenUtau.Plugin.Builtin.GermanVCCVPhonemizer", author="Lotte V")
class GermanVCCVPhonemizer(SyllableBasedPhonemizer):
    """German VCCV phonemizer. Based on UTAU Felix's VCCV voicebank."""

    yaml_file_name = "de_vccv.yaml"
    yaml_template = os.path.join(DATA_DIR, "de_vccv.template.yaml")
    no_gap = True

    def __init__(self):
        super().__init__()
        self.vowels = "a,6,e,E,2,9,i,I,y,Y,u,U,o,O,@,aU,OY,aI".split(",")
        self.consonants = "-,b,C,d,f,g,h,j,k,kh,l,m,n,N,p,ph,R;,s,S,t,th,v,x,z,Z,dZ,ks,pf,st,St,tS,w".split(",")
        self.dictionary_replacements = to_dictionary(
            "aa=a,ae=E,ah=@,ao=O,aw=aU,ax=@,ay=aI,"
            "b=b,cc=C,ch=tS,d=d,dh=z," + "ee=e,eh=E,er=6,ex=6," + "f=f,g=g,hh=h,ih=I,iy=i,jh=dZ,k=k,l=l,m=m,n=n,ng=N,"
            "oe=9,ohh=2,ooh=o,oy=OY," + "p=p,pf=pf,q=-,r=R;,rr=R;,s=s,sh=S,t=t," + "th=s,ts=ts," + "ue=y,uh=U,uw=u," + "v=v,w=w,x=x,y=j,"
            "yy=Y," + "z=z,zh=Z", ",")

    def get_vowels(self):
        return self.vowels

    def get_consonants(self):
        return self.consonants

    def get_dictionary_name(self):
        return "cmudict_de.txt"

    def get_base_g2ps(self):
        return [GermanG2p()]

    def get_symbols(self, note):
        original = super().get_symbols(note)
        if original is None:
            return None
        final_processed_phonemes = []

        for i in range(len(original)):
            if original[i] in self.dictionary_replacements:
                original[i] = self.dictionary_replacements[original[i]]

        diphthongs = ["aU", "OY", "aI"]
        for s in original:
            if s in diphthongs:
                final_processed_phonemes.extend([s[0], s[1] + "^"])
            else:
                final_processed_phonemes.append(s)
        return final_processed_phonemes

    def process_syllable(self, syllable):
        syllable.prev_v = "" if syllable.prev_v in self.tails else syllable.prev_v
        replaced_prev_v = self.replace_phoneme(syllable.prev_v, syllable.tone)
        prev_v = "" if not replaced_prev_v else replaced_prev_v
        cc = [self.replace_phoneme(c, syllable.tone) for c in syllable.cc]
        v = self.replace_phoneme(syllable.v, syllable.vowel_tone)
        phonemes = []
        last_c = len(cc) - 1
        first_c = 0
        # CurrentWordCc / PreviousWordCc are computed in c# but never used

        if syllable.is_starting_v:
            base_phoneme = f"- {v}"
        elif syllable.is_vv:
            vv = f"{prev_v} {v}"
            if not self.can_make_alias_extension(syllable):
                if self.has_oto(vv, syllable.vowel_tone) or self.has_oto(self.validate_alias(vv), syllable.vowel_tone):
                    base_phoneme = vv
                else:
                    base_phoneme = f"-{v}"
                    phonemes.append(f"{prev_v} -")
            else:
                # the previous alias will be extended
                base_phoneme = None
        elif syllable.is_starting_cv_with_one_consonant:
            rcv = f"- {cc[0]}{v}"
            if self.has_oto(rcv, syllable.vowel_tone):
                base_phoneme = rcv
            else:
                base_phoneme = f"{cc[0]} {v}"
        elif syllable.is_starting_cv_with_more_than_one_consonant:
            rccv = f"- {''.join(cc)}{v}"
            if self.has_oto(rccv, syllable.vowel_tone):
                base_phoneme = rccv
            else:
                base_phoneme = f"{last(cc)}{v}"
                # try RCC, with or without schwa
                for i in range(len(cc), 1, -1):
                    if self.try_add_phoneme(phonemes, syllable.tone, f"- {''.join(take(cc, i))}", f"- {''.join(take(cc, i))}@"):
                        first_c = i - 1
                        break
                if len(phonemes) == 0:
                    # try RC with schwa if no RCC
                    self.try_add_phoneme(phonemes, syllable.tone, f"- {cc[0]}@")
        else:
            crv = f"{last(cc)} {v}"
            if self.has_oto(crv, syllable.vowel_tone) or self.has_oto(self.validate_alias(crv), syllable.vowel_tone):
                base_phoneme = crv
            else:
                base_phoneme = f"{last(cc)}{v}"
            # try CCV
            if len(cc) - first_c > 1:
                for i in range(first_c, len(cc)):
                    ccv = f"{''.join(skip(cc, i))}{v}"
                    if self.has_oto(ccv, syllable.vowel_tone) or self.has_oto(self.validate_alias(ccv), syllable.vowel_tone):
                        last_c = i
                        base_phoneme = ccv
                        break
            # try vcc
            for i in range(last_c + 1, -1, -1):
                vcc = f"{prev_v} {''.join(take(cc, 3))}"
                vcc2 = f"{prev_v}{''.join(take(cc, 2))}"
                vc = f"{prev_v} {cc[0]}"
                vc2 = f"{prev_v}{cc[0]}"
                if i == 0:
                    phonemes.append(vc)
                elif self.has_oto(vcc, syllable.tone) or self.has_oto(self.validate_alias(vcc), syllable.tone):
                    phonemes.append(vcc)
                    first_c = 1
                    break
                elif self.has_oto(vcc2, syllable.tone) or self.has_oto(self.validate_alias(vcc2), syllable.tone):
                    phonemes.append(vcc2)
                    first_c = 1
                    break
                elif self.has_oto(vc2, syllable.tone) or self.has_oto(self.validate_alias(vc2), syllable.tone):
                    phonemes.append(vc2)
                    break
                elif self.has_oto(vc, syllable.tone) or self.has_oto(self.validate_alias(vc), syllable.tone):
                    phonemes.append(vc)
                    break
                else:
                    continue

        i = first_c
        while i < last_c:
            # we could use some CCV, so lastC is used
            # we could use -CC so firstC is used
            rccv = f"- {''.join(cc)}{v}"
            cc1 = "".join(skip(cc, i))
            ccv = "".join(skip(cc, i)) + v
            if not self.has_oto(rccv, syllable.vowel_tone):
                cc1 = self._cc_chain(cc1, cc[i], cc[i + 1], syllable.tone)
                if self.has_oto(ccv, syllable.vowel_tone):
                    base_phoneme = ccv
                if i + 1 < last_c:
                    cc2 = self._cc_chain("".join(skip(cc, i)), cc[i + 1], cc[i + 2], syllable.tone)
                    if self.has_oto(ccv, syllable.vowel_tone):
                        base_phoneme = ccv
                    if self.try_add_phoneme(phonemes, syllable.tone, f"{cc[i]}{cc[i + 1]}{cc[i + 2]} -"):
                        # if it exists, use [C1][C2][C3] -
                        i += 1
                    elif self.has_oto(cc1, syllable.tone) and self.has_oto(cc2, syllable.tone):
                        # like [V C1] [C1 C2] [C2 C3] [C3 ..]
                        phonemes.append(cc1)
                    elif self.try_add_phoneme(phonemes, syllable.tone, cc1):
                        # like [V C1] [C1 C2] [C2 ..]
                        pass
                else:
                    self.try_add_phoneme(phonemes, syllable.tone, cc1)
            i += 1
        phonemes.append(base_phoneme)
        return phonemes

    def _cc_chain(self, joined, c1, c2, tone):
        """the syllable's cc fallback chain: joined CC, [C1][C2] -, [C1][C2], [C1] [C2], [C1][C2]@ (each validated)."""
        x = joined
        if not self.has_oto(x, tone):
            # joined CC
            x = self.validate_alias(x)
        if not self.has_oto(x, tone):
            x = f"{c1}{c2} -"
        if not self.has_oto(x, tone):
            x = self.validate_alias(x)
        if not self.has_oto(x, tone):
            x = f"{c1}{c2}"
        if not self.has_oto(x, tone):
            x = self.validate_alias(x)
        if not self.has_oto(x, tone):
            x = f"{c1} {c2}"
        if not self.has_oto(x, tone):
            x = self.validate_alias(x)
        if not self.has_oto(x, tone):
            # use schwa when no CC
            x = f"{c1}{c2}@"
        if not self.has_oto(x, tone):
            x = self.validate_alias(x)
        return x

    def _ending_cc_chain(self, c1, c2, t, tone):
        """the ending's cc fallback chain: [C1][C2] -, [C1] [C2], [C1][C2], [C1][C2]@ (each validated)."""
        x = f"{c1}{c2} {t}"
        if not self.has_oto(x, tone):
            x = self.validate_alias(x)
        if not self.has_oto(x, tone):
            x = f"{c1} {c2}"
        if not self.has_oto(x, tone):
            x = self.validate_alias(x)
        if not self.has_oto(x, tone):
            x = f"{c1}{c2}"
        if not self.has_oto(x, tone):
            x = self.validate_alias(x)
        if not self.has_oto(x, tone):
            x = f"{c1}{c2}@"
        if not self.has_oto(x, tone):
            x = self.validate_alias(x)
        return x

    def process_ending(self, ending):
        cc = [self.replace_phoneme(c, ending.tone) for c in ending.cc]
        v = self.replace_phoneme(ending.prev_v, ending.tone)
        t = self.replace_phoneme(ending.tail, ending.tone) if ending.has_tail else "-"
        last_c = len(cc) - 1
        first_c = 0

        phonemes = []
        if ending.is_ending_v:
            vr = f"{v}{t}"
            if self.has_oto(vr, ending.tone):
                phonemes.append(vr)
            else:
                phonemes.append(f"{v} {t}")
        elif ending.is_ending_vc_with_one_consonant:
            phonemes.append(f"{v}{cc[0]}")
        else:
            for i in range(last_c, -1, -1):
                vcc = f"{v}{''.join(take(cc, 2))}"
                if self.has_oto(vcc, ending.tone):
                    phonemes.append(vcc)
                    first_c = 1
                    break
                else:
                    phonemes.append(f"{v}{cc[0]}")
                    break
            i = first_c
            while i < last_c:
                # all CCs except the first one are /C1C2/, the last one is /C1 C2-/
                # but if there is no /C1C2/, we try /C1 C2-/, vise versa for the last one
                cc1 = self._ending_cc_chain(cc[i], cc[i + 1], t, ending.tone)
                if i < len(cc) - 2:
                    cc2 = self._ending_cc_chain(cc[i + 1], cc[i + 2], t, ending.tone)
                    c3 = f"{cc[i]}{cc[i + 1]}{cc[i + 2]} {t}"
                    if self.try_add_phoneme(phonemes, ending.tone, c3, self.validate_alias(c3)):
                        # like [C1 C2-][C3 ...]
                        i += 1
                    elif self.has_oto(cc1, ending.tone) and self.has_oto(cc2, ending.tone):
                        # like [C1 C2][C2 ...]
                        phonemes.append(cc1)
                    elif self.try_add_phoneme(phonemes, ending.tone, f"{cc[i + 1]}{cc[i + 2]} {t}", self.validate_alias(f"{cc[i + 1]}{cc[i + 2]} {t}")):
                        # like [C1 C2-][C3 ...]
                        i += 1
                    elif self.try_add_phoneme(phonemes, ending.tone, f"{cc[i + 1]}{cc[i + 2]}", self.validate_alias(f"{cc[i + 1]}{cc[i + 2]}")):
                        # like [C1C2][C2 ...]
                        i += 1
                    elif self.try_add_phoneme(phonemes, ending.tone, f"{cc[i + 1]}{cc[i + 2]}@", self.validate_alias(f"{cc[i + 1]}{cc[i + 2]}@")):
                        # like [C1C2][C2 ...]
                        i += 1
                    elif self.try_add_phoneme(phonemes, ending.tone, cc1, self.validate_alias(cc1)):
                        i += 1
                else:
                    if self.try_add_phoneme(phonemes, ending.tone, cc1, self.validate_alias(cc1)):
                        # like [C1 C2-]
                        i += 1
                i += 1
        return phonemes

    def get_hardcoded_fallback(self, alias, tone, suppressed_tokens):
        candidate = alias

        # apply string replacements with strict casing and YAML suppression checks
        def try_replace(from_pattern, to_pattern, *source_tokens):
            nonlocal candidate
            if suppressed_tokens is not None and any(t in suppressed_tokens for t in source_tokens):
                return
            candidate = candidate.replace(from_pattern, to_pattern)

        # Vowel fallback (a 6 / a6 -> a a)
        try_replace("a 6", "a a", "6")
        try_replace("a6", "a a", "6")

        # Affricate epenthesis fallbacks (with uppercase S)
        try_replace("n S", "n tS", "S")
        try_replace("l S", "l tS", "S")
        try_replace("nS", "ntS", "S")
        try_replace("lS", "ltS", "S")

        # Affricate epenthesis fallbacks (with lowercase s)
        try_replace("n s", "n ts", "s")
        try_replace("l s", "l ts", "s")
        try_replace("ns", "nts", "s")
        try_replace("ls", "lts", "s")

        # Cluster adjustment
        try_replace("st", "tst", "s", "t")

        # Split diphthong adjusters
        try_replace("U^", "U", "U^")
        try_replace("I^", "I", "I^")
        try_replace("Y^", "Y", "Y^")

        if candidate != alias and self.has_oto(candidate, tone):
            return candidate
        return None

    def get_transition_basic_length_ms_with_attr(self, alias, tone, attr):
        oto_length = self.get_transition_basic_length_ms_by_oto(alias, tone, attr)
        return oto_length
