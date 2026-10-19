"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Plugin.Builtin/SpanishSyllableBasedPhonemizer.cs

Spanish syllable-based phonemizer.
I tried to make this phonemizer as compatible with many different methods as possible.
Supports both CVVC and VCV if the voicebank has it.
Supports seseo ("s" instead of "z" if the voicebank doesn't have the latter).
It also substitutes "nh" for "ny" if the voicebank doesn't have the first.
It now also uses "i" instead of "y" and "u" instead of "w" depending on what the voicebank supports.
Now with full VCV support, including "consonant VCV" if the voicebank has either of them (ex. "l ba", "n da" but
also "m bra" etc.).

c# quirks kept: the seseo / semivowel / eñe switches are instance flags that only ever turn on (they stay set
for the rest of the phonemizer's life), and the semivowel probe interpolates cc.Length ("{cc.Length}y{v}").
"""

import os

from ...g2p import G2pFallbacks, SpanishG2p
from .api import phonemizer
from .syllable_based import SyllableBasedPhonemizer, last, skip, take


def cs_pairs_dict(spec):
    """spec.Split(';').Select(Split('=')).Where(len == 2).Where(a != b).ToDictionary() (throws on a duplicate key)."""
    out = {}
    for entry in spec.split(";"):
        parts = entry.split("=")
        if len(parts) != 2 or parts[0] == parts[1]:
            continue
        if parts[0] in out:
            raise ValueError("An item with the same key has already been added. Key: " + parts[0])
        out[parts[0]] = parts[1]
    return out


@phonemizer("Spanish Syllable-Based Phonemizer", "ES SYL", language="ES", openutau_class="OpenUtau.Plugin.Builtin.SpanishSyllableBasedPhonemizer", author="Lotte V")
class SpanishSyllableBasedPhonemizer(SyllableBasedPhonemizer):
    no_gap = True  # Endings has 50 ticks gap

    def __init__(self):
        super().__init__()
        self._es_vowels = "a,e,i,o,u".split(",")
        self._es_consonants = "b,ch,d,dz,f,g,h,hh,j,k,l,ll,m,n,nh,p,r,rr,s,sh,t,ts,w,y,z,zz,zh,I,U".split(",")
        self._es_dictionary_replacements = cs_pairs_dict(
            "a=a;e=e;i=i;o=o;u=u;" + "b=b;ch=ch;d=d;f=f;g=g;gn=nh;k=k;l=l;ll=j;m=m;n=n;p=p;r=r;rr=rr;s=s;t=t;w=w;x=h;y=y;z=z;I=I;U=U;B=b;D=d;G=g;Y=y")
        self.long_consonants = "ch,dz,h,s,sh,k,p,rr,t,ts,z".split(",")
        self.initial_cc = ("bl,bly,blw,br,bry,brw,by,bw,dr,dry,drw,dy,dw,fl,fly,flw,fr,fry,frw,fy,fw,gl,gly,glw,gr,gry,grw,gy,gw,kl,kly,klw,"
                           "kr,kry,krw,ky,kw,pl,ply,plw,pr,pry,prw,py,pw,tl,tly,tlw,tr,try,trw,ty,tw,chy,chw,hy,hw,jy,jw,ly,lw,my,mw,ny,nw,"
                           "ry,rw,sy,sw,vy,vw,zy,zw,nhy,nhw,rry,rrw,ts").split(",")
        self.not_clusters = "dz,hh,ll,nh,sh,zz,zh,th,ng".split(",")
        self.burst_consonants = "ch,dz,j,k,p,t,ts,r".split(",")

        # For banks with a seseo accent
        self.seseo = cs_pairs_dict("z=s")
        self.is_seseo = False
        # For banks with alternate semivowel aliases
        self.semi_vowel_fallback = cs_pairs_dict(
            "jya=ja;jye=je;jyo=jo;jyu=ju;chya=cha;chye=che;chyo=cho;chyu=chu;nhya=nha;nhye=nhe;nhyo=nho;nhyu=nhu;nhwa=nua;nhwe=nue;"
            "nhwi=nui;nhwo=nuo;ya=ia;ye=ie;yo=io;yu=iu;wa=ua;we=ue;wi=ui;wo=uo")
        self.is_semi_vowel_fallback = False
        # For banks with alternate alias for "ñ"
        self.ene_fallback = cs_pairs_dict(
            "nhya=nya;nhye=nye;nhyo=nyo;nhyu=nyu;nhwa=nwa;nhwe=nwe;nhwi=nwi;nhwo=nwo;nha=nya;nhe=nye;nyi=ni;nhi=nyi;nho=nyo;nhu=nyu;"
            "a nh=a n;e nh=e n;i nh=i n;o nh=o n;u nh=u n;n nh=n n;l nh=l n;m nh=m n")
        self.is_ene_fallback = False

    def get_vowels(self):
        return self._es_vowels

    def get_consonants(self):
        return self._es_consonants

    def get_dictionary_name(self):
        return "cmudict_es.txt"

    def load_base_dictionary(self):
        g2ps = []
        # Load dictionary from singer folder.
        if self.singer is not None:
            file = os.path.join(self.singer.location, "es-syl.yaml")
            if os.path.isfile(file):
                try:
                    g2ps.append(self._g2p_dictionary_from(file))
                except Exception:  # noqa: BLE001 - Log.Error(e, $"Failed to load {file}")
                    pass
        g2ps.append(SpanishG2p())
        return G2pFallbacks(g2ps)

    def get_dictionary_phonemes_replacement(self):
        return self._es_dictionary_replacements

    def process_syllable(self, syllable):
        prev_v = syllable.prev_v
        cc = syllable.cc
        v = syllable.v
        has_oto = self.has_oto
        va = self.validate_alias
        initial_cc = self.initial_cc
        not_clusters = self.not_clusters

        phonemes = []

        last_c = len(cc) - 1
        first_c = 0

        rv = f"- {v}"
        vv1 = f"{prev_v} {v}"
        vv2 = f"{prev_v}{v}"

        # Switch between phonetic systems, depending on certain aliases in the bank
        if not has_oto(f"z{v}", syllable.tone) and not has_oto(f"- z{v}", syllable.tone):
            self.is_seseo = True
        if not has_oto(f"{len(cc)}y{v}", syllable.vowel_tone) and not has_oto(f"- {len(cc)}y{v}", syllable.vowel_tone):
            self.is_semi_vowel_fallback = True
        if not has_oto(f"nh{v}", syllable.vowel_tone) and not has_oto(f"- nh{v}", syllable.vowel_tone):
            self.is_ene_fallback = True

        if syllable.is_starting_v:
            base_phoneme = rv
            if not has_oto(rv, syllable.vowel_tone):
                base_phoneme = f"{v}"
        elif syllable.is_vv:
            if not self.can_make_alias_extension(syllable):
                if has_oto(vv1, syllable.vowel_tone):
                    base_phoneme = vv1
                elif not has_oto(vv1, syllable.vowel_tone) and has_oto(vv2, syllable.vowel_tone):
                    base_phoneme = vv2
                else:
                    base_phoneme = v
            else:
                # the previous alias will be extended
                base_phoneme = None
        elif syllable.is_starting_cv_with_one_consonant:
            # TODO: move to config -CV or -C CV
            rcv = f"- {cc[0]}{v}"
            if has_oto(rcv, syllable.vowel_tone) or has_oto(va(rcv), syllable.vowel_tone):
                base_phoneme = rcv
            else:
                base_phoneme = f"{cc[0]}{v}"
        elif syllable.is_starting_cv_with_more_than_one_consonant:
            # try RCCV
            joined = "".join(cc)
            rccv = f"- {joined}{v}"
            ccv = joined + v
            crv = f"{last(cc)} {v}"
            if (has_oto(rccv, syllable.vowel_tone) or has_oto(va(rccv), syllable.vowel_tone)) and (joined in initial_cc or va(joined) in initial_cc):
                base_phoneme = rccv
                last_c = 0
            elif (not has_oto(rccv, syllable.vowel_tone) and not has_oto(va(rccv), syllable.vowel_tone)
                  and (has_oto(ccv, syllable.vowel_tone) or has_oto(va(ccv), syllable.vowel_tone))
                  and (joined in initial_cc or va(joined) in initial_cc)):
                base_phoneme = ccv
                last_c = 0
            else:
                base_phoneme = va(crv)
                if not has_oto(va(crv), syllable.vowel_tone):
                    base_phoneme = f"{last(cc)}{v}"
                # try RCC
                for i in range(len(cc), 1, -1):
                    rcc = f"- {''.join(take(cc, i))}"
                    cc1 = "".join(take(cc, i))
                    if "".join(take(cc, i)) in initial_cc or va("".join(take(cc, i))) in initial_cc:
                        if self.try_add_phoneme(phonemes, syllable.tone, rcc, va(rcc), cc1, va(cc1)):
                            first_c = i - 1
                            break
                if len(phonemes) == 0:
                    self.try_add_phoneme(phonemes, syllable.tone, f"- {cc[0]}", va(f"- {cc[0]}"))
        else:  # VCV
            vcv = f"{prev_v} {cc[0]}{v}"
            vccv = f"{prev_v} {''.join(cc)}{v}"
            if (has_oto(vcv, syllable.vowel_tone) or has_oto(va(vcv), syllable.vowel_tone)) and syllable.is_vcv_with_one_consonant:
                base_phoneme = vcv
            elif ((has_oto(vccv, syllable.vowel_tone) or has_oto(va(vccv), syllable.vowel_tone))
                  and syllable.is_vcv_with_more_than_one_consonant
                  and ("".join(cc) in initial_cc or va("".join(cc)) in initial_cc)):
                base_phoneme = vccv
                last_c = 0
            else:
                cv = last(cc) + v
                crv = f"{last(cc)} {v}"
                base_phoneme = cv
                if not has_oto(cv, syllable.vowel_tone) and not has_oto(va(cv), syllable.vowel_tone):
                    base_phoneme = crv

                # try CCV
                if len(cc) - first_c > 1:
                    for i in range(first_c, last_c):
                        sk = "".join(skip(cc, i))
                        ccv = f"{sk}{v}"
                        ccv2 = f"{' '.join(skip(cc, i))}{v}"
                        ccv3 = f"{cc[0]} {sk}{v}"
                        if (has_oto(ccv, syllable.vowel_tone) or has_oto(va(ccv), syllable.vowel_tone)) and (sk in initial_cc or va(sk) in initial_cc):
                            last_c = i
                            base_phoneme = ccv
                            break
                        elif has_oto(ccv2, syllable.vowel_tone) or has_oto(va(ccv2), syllable.vowel_tone):
                            last_c = i
                            base_phoneme = ccv2
                            break
                        elif (has_oto(ccv3, syllable.vowel_tone) or has_oto(va(ccv3), syllable.vowel_tone)) and (sk in initial_cc or va(sk) in initial_cc):
                            last_c = i
                            base_phoneme = ccv3
                            break
                        else:
                            continue
                # try vcc or vc
                for i in range(last_c + 1, -1, -1):
                    vc1 = f"{prev_v} {cc[0]}"
                    vc2 = f"{prev_v}{cc[0]}"
                    t2 = "".join(take(cc, 2))
                    vcc = f"{prev_v} {t2}"
                    vcc2 = f"{prev_v}{t2}"
                    if (has_oto(va(vcc), syllable.tone) or has_oto(va(vcc), syllable.tone)) and (t2 not in not_clusters and va(t2) not in not_clusters):
                        phonemes.append(vcc)
                        first_c = 1
                        break
                    elif (has_oto(vcc2, syllable.tone) or has_oto(va(vcc2), syllable.tone)) and (t2 not in not_clusters and va(t2) not in not_clusters):
                        phonemes.append(vcc2)
                        first_c = 1
                        break
                    elif has_oto(vc1, syllable.tone) or has_oto(va(vc1), syllable.tone):
                        phonemes.append(vc1)
                        break
                    elif has_oto(vc2, syllable.tone) or has_oto(va(vc2), syllable.tone):
                        phonemes.append(vc2)
                        break
        for i in range(first_c, last_c):
            # we could use some CCV, so lastC is used
            # we could use -CC so firstC is used
            cc1 = f"{cc[i]}{cc[i + 1]}"

            # Use [C1C2]
            if not has_oto(cc1, syllable.tone):
                cc1 = va(cc1)
            # Use [C1 C2]
            if not has_oto(cc1, syllable.tone):
                cc1 = f"{cc[i]} {cc[i + 1]}"
            if not has_oto(cc1, syllable.tone):
                cc1 = va(cc1)
            if i + 1 < last_c:
                cc2 = f"{cc[i + 1]}{cc[i + 2]}"

                # Use [C2C3]
                if not has_oto(cc2, syllable.tone):
                    cc2 = va(cc2)
                # Use [C2 C3]
                if not has_oto(cc2, syllable.tone):
                    cc2 = f"{cc[i + 1]} {cc[i + 2]}"
                if not has_oto(cc2, syllable.tone):
                    cc2 = va(cc2)
                if (has_oto(cc1, syllable.tone) or has_oto(va(cc1), syllable.tone)) and (has_oto(cc2, syllable.tone) or has_oto(va(cc2), syllable.tone)):
                    # like [V C1] [C1 C2] [C2 C3] [C3 ..]
                    phonemes.append(cc1)
                elif self.try_add_phoneme(phonemes, syllable.tone, cc1, va(cc1)):
                    # like [V C1] [C1 C2] [C2 ..]
                    pass
                else:
                    # like[V C1][C1][C2..]
                    self.try_add_phoneme(phonemes, syllable.tone, cc[i], va(cc[i]))
            else:
                # like [V C1] [C1 C2]  [C2 ..] or like [V C1] [C1 -] [C3 ..]
                self.try_add_phoneme(phonemes, syllable.tone, cc1, cc[i], va(cc[i]))

        phonemes.append(base_phoneme)
        return phonemes

    def process_ending(self, ending):
        cc = ending.cc
        v = ending.prev_v
        has_oto = self.has_oto
        va = self.validate_alias
        tone = ending.tone
        not_clusters = self.not_clusters
        tap = self.try_add_phoneme

        phonemes = []

        last_c = len(cc) - 1
        first_c = 0

        if ending.is_ending_v:  # ending V
            tap(phonemes, tone, f"{v} -", f"{v}-", f"{v} R")
        elif ending.is_ending_vc_with_one_consonant:  # ending VC
            vcr = f"{v} {cc[0]}-"
            vcr2 = f"{v}{cc[0]}-"
            vc = f"{v} {cc[0]}"
            vc2 = f"{v}{cc[0]}"
            if has_oto(vcr, tone) or has_oto(va(vcr), tone):
                phonemes.append(vcr)
            elif has_oto(vcr2, tone) or has_oto(va(vcr2), tone):
                phonemes.append(vcr2)
            else:
                if has_oto(vc, tone) or has_oto(va(vc), tone):
                    phonemes.append(vc)
                elif has_oto(vc2, tone) or has_oto(va(vc2), tone):
                    phonemes.append(vc2)
                if cc[0] in self.burst_consonants or va(cc[0]) in self.burst_consonants:
                    tap(phonemes, tone, f"{cc[0]} -", f"{va(cc[0])} -", cc[0], va(cc[0]))
                else:
                    tap(phonemes, tone, f"{cc[0]} -", f"{va(cc[0])} -", f"{cc[0]}-", f"{va(cc[0])}-", f"{cc[0]} R", f"{va(cc[0])} R")
        else:  # ending VCC (very rare, usually only occurs in words ending with "x")
            for i in range(last_c, -1, -1):
                t2 = "".join(take(cc, 2))
                vcc = f"{v} {t2}-"
                vcc3 = f"{v}{t2}"
                vcc2 = f"{v} {t2}"
                vcc4 = f"{v}{' '.join(take(cc, 2))}-"
                vc = f"{v} {cc[0]}"
                vc2 = f"{v}{cc[0]}"
                if (has_oto(vcc, tone) or has_oto(va(vcc), tone)) and last_c == 1 and t2 not in not_clusters and va(t2) not in not_clusters:
                    phonemes.append(vcc)
                    first_c = 1
                    break
                elif (has_oto(vcc2, tone) or has_oto(va(vcc2), tone)) and t2 not in not_clusters and va(t2) not in not_clusters:
                    phonemes.append(vcc2)
                    first_c = 1
                    break
                elif (has_oto(vcc3, tone) or has_oto(va(vcc3), tone)) and t2 not in not_clusters and va(t2) not in not_clusters:
                    phonemes.append(vcc3)
                    first_c = 1
                    break
                elif (has_oto(vcc4, tone) or has_oto(va(vcc4), tone)) and last_c == 1 and t2 not in not_clusters and va(t2) not in not_clusters:
                    phonemes.append(vcc4)
                    first_c = 1
                    break
                elif has_oto(vc, tone) or has_oto(va(vc), tone):
                    phonemes.append(vc)
                    break
                else:
                    tap(phonemes, tone, vc2, va(vc2))
                    break

            i = first_c
            while i < last_c:
                # all CCs except the first one are /C1C2/, the last one is /C1 C2-/
                # but if there is no /C1C2/, we try /C1 C2-/, vise versa for the last one
                cc1 = f"{cc[i]} {cc[i + 1]}"
                if i < len(cc) - 2:
                    cc2 = f"{cc[i + 1]} {cc[i + 2]}"
                    if not has_oto(cc1, tone):
                        cc1 = va(cc1)
                    if not has_oto(cc1, tone) and f"{cc[i]}{cc[i + 1]}" not in not_clusters and va(f"{cc[i]}{cc[i + 1]}") not in not_clusters:
                        cc1 = f"{cc[i]}{cc[i + 1]}"
                    if not has_oto(cc1, tone):
                        cc1 = va(cc1)
                    if not has_oto(cc2, tone):
                        cc2 = va(cc2)
                    if not has_oto(cc2, tone):
                        cc2 = f"{cc[i + 1]}{cc[i + 2]}"
                    if not has_oto(cc2, tone):
                        cc2 = va(cc2)
                    c23r = f"{cc[i + 1]} {cc[i + 2]}-"
                    c23r2 = f"{cc[i + 1]}{cc[i + 2]}-"
                    if ((has_oto(cc1, tone) and (has_oto(cc2, tone) or has_oto(c23r, tone) or has_oto(va(c23r), tone)))
                            or has_oto(c23r2, tone) or has_oto(va(c23r2), tone)):
                        # like [C1 C2][C2 ...]
                        phonemes.append(cc1)
                    elif (has_oto(cc[i], tone)
                          or (has_oto(va(cc[i]), tone)
                              and (has_oto(cc2, tone) or has_oto(c23r, tone) or has_oto(va(c23r), tone) or has_oto(c23r2, tone) or has_oto(va(c23r2), tone)))):
                        # like [C1 C2-][C3 ...]
                        phonemes.append(cc[i])
                    elif tap(phonemes, tone, c23r, va(c23r), c23r2, va(c23r2)):
                        # like [C1 C2-][C3 ...]
                        i += 1
                    elif tap(phonemes, tone, f"{cc[i + 1]}{cc[i + 2]}", va(f"{cc[i + 1]}{cc[i + 2]}")):
                        # like [C1C2][C2 ...]
                        i += 1
                    elif tap(phonemes, tone, cc1, va(cc1)):
                        i += 1
                    else:
                        # like [C1][C2 ...]
                        tap(phonemes, tone, cc[i], va(cc[i]), f"{cc[i]} -", va(f"{cc[i]} -"))
                        tap(phonemes, tone, cc[i + 1], va(cc[i + 1]), f"{cc[i + 1]} -", va(f"{cc[i + 1]} -"))
                        i += 1
                else:
                    if not has_oto(cc1, tone):
                        cc1 = va(cc1)
                    if not has_oto(cc1, tone):
                        cc1 = f"{cc[i]}{cc[i + 1]}"
                    if not has_oto(cc1, tone):
                        cc1 = va(cc1)
                    c12r = f"{cc[i]} {cc[i + 1]}-"
                    c12r2 = f"{cc[i]}{cc[i + 1]}-"
                    if tap(phonemes, tone, c12r, va(c12r), c12r2, va(c12r2)):
                        # like [C1 C2-]
                        i += 1
                    elif tap(phonemes, tone, cc1, va(cc1)):
                        # like [C1 C2][C2 -]
                        tap(phonemes, tone, f"{cc[i + 1]} -", va(f"{cc[i + 1]} -"), cc[i + 1], va(cc[i + 1]))
                        i += 1
                    elif tap(phonemes, tone, f"{cc[i]}{cc[i + 1]}", va(f"{cc[i]}{cc[i + 1]}")):
                        # like [C1C2][C2 -]
                        tap(phonemes, tone, f"{cc[i + 1]} -", va(f"{cc[i + 1]} -"), cc[i + 1], va(cc[i + 1]))
                        i += 1
                    else:
                        # like [C1][C2 -]
                        tap(phonemes, tone, cc[i], va(cc[i]), f"{cc[i]} -", va(f"{cc[i]} -"))
                        tap(phonemes, tone, f"{cc[i + 1]} -", va(f"{cc[i + 1]} -"), cc[i + 1], va(cc[i + 1]))
                        i += 1
                i += 1
        return phonemes

    def get_hardcoded_fallback(self, alias, tone, suppressed_tokens):
        candidate = alias

        def apply_dictionary(d):
            nonlocal candidate
            if d is None:
                return
            for key, value in sorted(d.items(), key=lambda kv: len(kv[0]), reverse=True):
                if suppressed_tokens is not None and key in suppressed_tokens:
                    continue
                candidate = candidate.replace(key, value)

        def try_replace(from_token, to_token):
            nonlocal candidate
            if suppressed_tokens is not None and from_token in suppressed_tokens:
                return
            candidate = candidate.replace(from_token, to_token)

        # Validate alias depending on method
        if self.is_seseo:
            apply_dictionary(self.seseo)
        if self.is_semi_vowel_fallback:
            apply_dictionary(self.semi_vowel_fallback)
        if self.is_ene_fallback:
            apply_dictionary(self.ene_fallback)

        try_replace("I", "i")
        try_replace("U", "u")
        try_replace("ks", "x")

        # Exact match replacements
        if candidate == "r" and (suppressed_tokens is None or "r" not in suppressed_tokens):
            candidate = "rr"
        if candidate == "ch" and (suppressed_tokens is None or "ch" not in suppressed_tokens):
            candidate = "tch"

        if candidate != alias and self.has_oto(candidate, tone):
            return candidate
        return None

    def get_transition_basic_length_ms_with_attr(self, alias, tone, attr):
        oto_length = self.get_transition_basic_length_ms_by_oto(alias, tone, attr)
        return oto_length
