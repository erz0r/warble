"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Plugin.Builtin/SpanishVCCVPhonemizer.cs

Based on the nJokis method.
Supports automatic consonant substitutes, such as seseo, through ValidateAlias.

the plugin-folder njokis_vccv.yaml is read from data/romance/njokis.template.yaml (see data/romance/SOURCE.md).
c# quirks kept: ProcessSyllable shadows the vowels field with a local list holding only the current vowel, the
"if (HasOto(x)) { ...; if (!HasOto(x)) ... }" dead branches, and the loop counter bumps inside the consonant loop.
"""

import os

from ...g2p import SpanishG2p
from .api import phonemizer
from .spanish_syllable_based import cs_pairs_dict
from .syllable_based import SyllableBasedPhonemizer, last, skip, take

_DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "romance")


@phonemizer("Spanish VCCV Phonemizer", "ES VCCV", language="ES", openutau_class="OpenUtau.Plugin.Builtin.SpanishVCCVPhonemizer", author="Lotte V")
class SpanishVCCVPhonemizer(SyllableBasedPhonemizer):
    yaml_file_name = "njokis_vccv.yaml"
    yaml_template = os.path.join(_DATA, "njokis.template.yaml")
    yaml_version = "1.0"
    no_gap = True

    def __init__(self):
        super().__init__()
        self.vowels = "a,e,i,o,u,BB,DD,ff,GG,ll,mm,nn,rrr,ss,xx".split(",")
        self.consonants = "b,B,ch,d,D,E,f,g,G,h,I,jj,k,l,L,m,n,nJ,p,r,rr,s,sh,t,U,w,x,y,z".split(",")
        self.dictionary_replacements = cs_pairs_dict(
            "a=a;e=e;i=i;o=o;u=u;" + "b=b;ch=ch;d=d;f=f;g=g;gn=nJ;k=k;l=l;ll=jj;m=m;n=n;p=p;r=r;rr=rr;s=s;t=t;w=w;x=x;y=y;z=z;I=I;U=U;B=B;D=D;G=G;Y=y")

    def get_vowels(self):
        return self.vowels

    def get_consonants(self):
        return self.consonants

    def get_dictionary_name(self):
        return "cmudict_es.txt"

    def get_base_g2ps(self):
        return [SpanishG2p()]

    def get_symbols(self, note):
        original = super().get_symbols(note)
        if original is None:
            return None
        for i in range(len(original)):
            if original[i] in self.dictionary_replacements:
                original[i] = self.dictionary_replacements[original[i]]
        final_processed_phonemes = []
        for s in original:
            final_processed_phonemes.append(s)
        return final_processed_phonemes

    def process_syllable(self, syllable):
        syllable.prev_v = "" if syllable.prev_v in self.tails else syllable.prev_v
        replaced_prev_v = self.replace_phoneme(syllable.prev_v, syllable.tone)
        prev_v = "" if not replaced_prev_v else replaced_prev_v
        cc = [self.replace_phoneme(c, syllable.tone) for c in syllable.cc]
        v = self.replace_phoneme(syllable.v, syllable.vowel_tone)
        vowels = [v]
        has_oto = self.has_oto
        va = self.validate_alias
        tap = self.try_add_phoneme
        tone = syllable.tone
        vtone = syllable.vowel_tone
        phonemes = []
        last_c = len(cc) - 1
        first_c = 0
        _current_word_cc = [self.replace_phoneme(c, syllable.tone) for c in syllable.current_word_cc]
        _previous_word_cc = [self.replace_phoneme(c, syllable.tone) for c in syllable.previous_word_cc]

        if syllable.is_starting_v:
            rcv = f"- {v}"
            rcv2 = f"-{v}"
            if has_oto(rcv, vtone):
                base_phoneme = rcv
            else:
                base_phoneme = rcv2
        elif syllable.is_vv:
            vv = f"{prev_v} {v}"
            vv2 = f"{prev_v}{v}"
            if not self.can_make_alias_extension(syllable):
                if has_oto(vv, vtone):
                    base_phoneme = vv
                elif not has_oto(vv, vtone) and has_oto(va(vv2), vtone):
                    base_phoneme = va(vv2)
                else:
                    base_phoneme = v
            else:
                # the previous alias will be extended
                base_phoneme = None
        elif syllable.is_starting_cv_with_one_consonant:
            # TODO: move to config -CV or -C CV
            rcv = f"-{cc[0]}{v}"
            cv = f"{cc[0]}{v}"
            if has_oto(rcv, vtone):
                base_phoneme = rcv
            else:
                base_phoneme = cv
                if cc[0] in self.consonants:
                    tap(phonemes, tone, f"-{cc[0]}", va(f"-{cc[0]}"))
        elif syllable.is_starting_cv_with_more_than_one_consonant:
            # try RCCV
            rccv = f"-{''.join(cc)}{v}"
            if has_oto(rccv, vtone):
                base_phoneme = rccv
            elif has_oto(va(rccv), vtone):
                base_phoneme = va(rccv)
            else:
                ccv = f"{''.join(cc)}{v}"
                _cv = f"_{last(cc)}{v}"
                if has_oto(ccv, vtone):
                    base_phoneme = ccv
                elif has_oto(va(ccv), tone) and not va(ccv).startswith("B") and not va(ccv).startswith("D") and not va(ccv).startswith("G"):
                    base_phoneme = va(ccv)
                elif not has_oto(va(ccv), tone) and not has_oto(va(va(ccv)), tone) and has_oto(_cv, tone):
                    base_phoneme = _cv
                else:
                    base_phoneme = f"{last(cc)}{v}"
                # try RCC
                for i in range(len(cc), 1, -1):
                    t = "".join(take(cc, i))
                    if has_oto(_cv, vtone):
                        tap(phonemes, tone, f"-{t}", va(f"-{t}"), f"-{cc[0]}", va(f"-{cc[0]}"))
                        if not has_oto(f"-{t}", tone) and not has_oto(va(f"-{t}"), tone) and not has_oto(ccv, vtone) and not has_oto(va(ccv), vtone):
                            tap(phonemes, tone, f"{t}", va(f"{t}"))
                        first_c = i
                    else:
                        tap(phonemes, tone, f"-{cc[0]}", va(f"-{cc[0]}"))
                        first_c = i
                        break
        else:
            cv = last(cc) + v
            base_phoneme = cv
            if not has_oto(cv, vtone):
                cv = va(cv)
                base_phoneme = cv
            # try CCV
            if len(cc) - first_c > 1:
                for i in range(first_c, len(cc)):
                    ccv = f"{''.join(skip(cc, i))}{v}"
                    rccv = f"-{''.join(cc)}{v}"
                    if has_oto(ccv, vtone):
                        last_c = i
                        base_phoneme = ccv
                        break
                    elif not has_oto(ccv, vtone) and has_oto(va(ccv), vtone):
                        ccv = va(ccv)
                        last_c = i
                        base_phoneme = ccv
                        break
                    elif not has_oto(va(ccv), vtone) and has_oto(rccv, vtone):
                        last_c = i
                        base_phoneme = rccv
                        break
                    elif not has_oto(rccv, vtone) and has_oto(va(rccv), vtone):
                        rccv = va(rccv)
                        last_c = i
                        base_phoneme = rccv
                        break
            for i in range(last_c + 1, -1, -1):
                vcc = f"{prev_v} {''.join(take(cc, i))}"
                vcc2 = f"{prev_v}{''.join(take(cc, i))}"
                vcc3 = f"{prev_v}{' '.join(take(cc, 2))}"
                vcc4 = f"{prev_v}{' '.join(take(cc, 1))}"
                vcc5 = f"{prev_v} {''.join(take(cc, 2))}"
                cc1 = f"{' '.join(take(cc, 2))}"
                cc2 = f"{''.join(take(cc, 2))}"
                vc = f"{prev_v} {cc[0]}"
                vc2 = f"{prev_v}{cc[0]}"
                if i == 0:
                    tap(phonemes, tone, va(vcc), va(vc))
                elif has_oto(vcc, tone):
                    phonemes.append(vcc)
                    break
                elif not has_oto(vcc, tone) and has_oto(va(vcc), tone):
                    vcc = va(vcc)
                    phonemes.append(vcc)
                    break
                elif has_oto(vcc2, tone):
                    phonemes.append(vcc2)
                    break
                elif not has_oto(vcc2, tone) and has_oto(va(vcc2), tone):
                    vcc2 = va(vcc2)
                    phonemes.append(vcc2)
                    break
                elif (has_oto(vcc3, tone) and not has_oto(cc1, tone) and not has_oto(va(cc1), tone) and not has_oto(cc2, tone)
                      and not has_oto(va(cc2), tone)):
                    phonemes.append(vcc3)
                    break
                elif (not has_oto(vcc3, tone) and has_oto(va(vcc3), tone) and not has_oto(cc1, tone) and not has_oto(va(cc1), tone)
                      and not has_oto(cc2, tone) and not has_oto(va(cc2), tone)):
                    vcc3 = va(vcc3)
                    phonemes.append(vcc3)
                    break
                elif has_oto(vcc4, tone):
                    phonemes.append(vcc4)
                    break
                elif not has_oto(vcc4, tone) and has_oto(va(vcc4), tone):
                    vcc4 = va(vcc4)
                    phonemes.append(vcc4)
                    break
                elif has_oto(vcc5, tone):
                    phonemes.append(vcc5)
                    break
                elif not has_oto(vcc5, tone) and has_oto(va(vcc5), tone):
                    vcc5 = va(vcc5)
                    phonemes.append(vcc5)
                    break
                elif has_oto(vc, tone):
                    phonemes.append(vc)
                    break
                elif not has_oto(vc, tone) and has_oto(va(vc), tone):
                    vc = va(vc)
                    phonemes.append(vc)
                    break
                elif has_oto(vc2, tone) and has_oto(va(vc2), tone):
                    phonemes.append(vc2)
                    break
                else:
                    continue
        i = first_c
        while i < last_c:
            # we could use some CCV, so lastC is used
            # we could use -CC so firstC is used
            cc1 = f"{''.join(skip(cc, i))}"
            ccv = "".join(skip(cc, i)) + v
            ucv = f"_{last(cc)}{v}"
            rccv = f"-{''.join(cc)}{v}"
            if not has_oto(rccv, vtone) and not has_oto(va(rccv), vtone) and cc1 not in vowels:
                if not has_oto(cc1, tone):
                    cc1 = va(cc1)
                if not has_oto(cc1, tone):
                    cc1 = f"_{cc[i]}{cc[i + 1]}_"
                if not has_oto(cc1, tone):
                    cc1 = va(cc1)
                if not has_oto(cc1, tone):
                    cc1 = f"{cc[i]} {cc[i + 1]}"
                if not has_oto(cc1, tone):
                    cc1 = va(cc1)
                if not has_oto(cc1, tone):
                    cc1 = f"{cc[i]}{cc[i + 1]}"
                if not has_oto(cc1, tone):
                    cc1 = va(cc1)
                if has_oto(ccv, vtone):
                    base_phoneme = ccv
                    if not has_oto(ccv, vtone):
                        ccv = va(ccv)
                        base_phoneme = ccv
                elif has_oto(ucv, vtone) and has_oto(cc1, vtone) and f"{cc[i]} {cc[i + 1]}" not in cc1:
                    base_phoneme = ucv
                    if not has_oto(ucv, vtone):
                        ucv = va(ucv)
                        base_phoneme = ucv
                cc2 = f"{''.join(skip(cc, i))}"
                if i + 1 < last_c and cc2 not in vowels:
                    if not has_oto(cc2, tone):
                        cc2 = va(cc2)
                    if not has_oto(cc2, tone):
                        cc2 = f"_{cc[i + 1]}{cc[i + 2]}_"
                    if not has_oto(cc2, tone):
                        cc2 = va(cc2)
                    if not has_oto(cc2, tone):
                        cc2 = f"{cc[i + 1]} {cc[i + 2]}"
                    if not has_oto(cc2, tone):
                        cc2 = va(cc2)
                    if not has_oto(cc2, tone):
                        cc2 = f"{cc[i + 1]}{cc[i + 2]}"
                    if not has_oto(cc2, tone):
                        cc2 = va(cc2)
                    if "".join(skip(cc, i)) in cc2 or va("".join(skip(cc, i))) in cc2:
                        i += 1
                    if has_oto(ccv, vtone):
                        base_phoneme = ccv
                        if not has_oto(ccv, vtone):
                            ccv = va(ccv)
                            base_phoneme = ccv
                    elif has_oto(ucv, vtone) and has_oto(cc2, vtone) and f"{cc[i + 1]} {cc[i + 2]}" not in cc2:
                        base_phoneme = ucv
                        if not has_oto(ucv, vtone):
                            ucv = va(ucv)
                            base_phoneme = ucv
                    if (has_oto(cc1, tone) and has_oto(cc2, tone) and "".join(skip(cc, i)) not in cc1
                            and va("".join(skip(cc, i))) not in cc1):
                        # like [V C1] [C1 C2] [C2 C3] [C3 ..]
                        phonemes.append(cc1)
                    elif tap(phonemes, tone, cc1):
                        # like [V C1] [C1 C2] [C2 ..]
                        if "".join(skip(cc, i)) in cc1 or va("".join(skip(cc, i))) in cc1:
                            i += 1
                else:
                    # like [V C1] [C1 C2]  [C2 ..] or like [V C1] [C1 -] [C3 ..]
                    tap(phonemes, tone, cc1)
                    if "".join(skip(cc, i)) in cc1 or va("".join(skip(cc, i))) in cc1:
                        i += 1
            i += 1
        phonemes.append(base_phoneme)
        return phonemes

    def process_ending(self, ending):
        cc = [self.replace_phoneme(c, ending.tone) for c in ending.cc]
        v = self.replace_phoneme(ending.prev_v, ending.tone)
        t = self.replace_phoneme(ending.tail, ending.tone) if ending.has_tail else "-"
        has_oto = self.has_oto
        va = self.validate_alias
        tap = self.try_add_phoneme
        tone = ending.tone

        phonemes = []
        if ending.is_ending_v:
            tap(phonemes, tone, f"{v}{t}", va(f"{v}{t}"))
        elif ending.is_ending_vc_with_one_consonant:
            vcr = f"{v}{cc[0]}{t}"
            if has_oto(vcr, tone):
                phonemes.append(vcr)
            else:
                phonemes.append(f"{v} {cc[0]}")
                tap(phonemes, tone, f"{cc[0]}{t}", va(f"{cc[0]}{t}"))
        else:
            vcc1 = f"{v} {''.join(cc)}"
            vcc2 = f"{v}{' '.join(cc)}"
            vc1 = f"{v}{cc[0]}"
            vc2 = f"{v} {cc[0]}"
            if has_oto(vcc1, tone):
                phonemes.append(vcc1)
            elif not has_oto(vcc1, tone) and has_oto(va(vcc1), tone):
                phonemes.append(va(vcc1))
            elif not has_oto(va(vcc1), tone) and has_oto(vcc2, tone):
                phonemes.append(vcc2)
            elif not has_oto(vcc2, tone) and has_oto(va(vcc2), tone):
                phonemes.append(va(vcc2))
            elif not has_oto(va(vcc2), tone) and has_oto(vc1, tone):
                phonemes.append(vc1)
            elif not has_oto(vc1, tone) and has_oto(va(vc1), tone):
                phonemes.append(va(vc1))
            elif not has_oto(va(vc1), tone) and has_oto(vc2, tone):
                phonemes.append(vc2)
            elif not has_oto(vc2, tone) and has_oto(va(vc2), tone):
                phonemes.append(va(vc2))
            for i in range(len(cc) - 1):
                cc1 = f"{cc[i]} {cc[i + 1]}"
                if not has_oto(cc1, tone):
                    cc1 = va(cc1)
                if not has_oto(cc1, tone):
                    cc1 = f"{cc[i]}{cc[i + 1]}"
                if not has_oto(cc1, tone):
                    cc1 = va(cc1)
                tap(phonemes, tone, cc1, va(cc1))
                tap(phonemes, tone, f"{last(cc)}{t}", va(f"{last(cc)}{t}"))
        return phonemes

    _RULES = [("I", "y"), ("U", "w"),
              ("BB", "B"), ("DD", "D"),
              ("ff", "f"),
              ("GG", "G"),
              ("ll", "l"), ("mm", "m"), ("nn", "n"),
              ("rrr", "rr"),
              ("ss", "s"),
              ("E", "e"),
              (" k", " t"), (" p", " t"), (" ch", " t"),
              ("b", "B"), ("d", "D"), ("g", "G"),
              ("z", "s"),
              ("jj", "sh"),
              ("x", "h")]

    def get_hardcoded_fallback(self, alias, tone, suppressed_tokens):
        candidate = alias

        # Apply dictionary substitutions while honoring YAML suppression
        for key, value in sorted(self._RULES, key=lambda r: len(r[0]), reverse=True):
            token_key = key.strip()
            if suppressed_tokens is not None and token_key in suppressed_tokens:
                continue
            candidate = candidate.replace(key, value)

        # Secondary adjustments
        if suppressed_tokens is None or "h" not in suppressed_tokens:
            candidate = candidate.replace("h", "x")
        candidate = candidate.replace("xx", "x")

        if suppressed_tokens is None or "jj" not in suppressed_tokens:
            candidate = candidate.replace("jj", "L")

        if candidate != alias and self.has_oto(candidate, tone):
            return candidate
        return None

    def get_transition_basic_length_ms_with_attr(self, alias, tone, attr):
        oto_length = self.get_transition_basic_length_ms_by_oto(alias, tone, attr)
        return oto_length
