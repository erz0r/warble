"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Plugin.Builtin/EnXSampaPhonemizer.cs

general english phonemizer for x-sampa voicebanks (lotte v): delta-style banks and other x-sampa english banks,
with extended phonemes for custom dictionaries and phonetic input. cmudict arpabet is mapped to x-sampa, and
the bank's own alias set switches on fallback tables (vocaloid-style sampa, 5-vowel delta, en+ja banks,
"true" x-sampa, salem's reclist, ...)."""

from ...g2p import ArpabetG2p
from .api import phonemizer
from .syllable_based import SyllableBasedPhonemizer, cs_regex_word_boundary_match, cs_replace, last

VOWELS = (r"a,A,@,{,V,O,aU,aI,E,3,eI,I,i,oU,OI,U,u,Q,Ol,Ql,aUn,e@,eN,IN,e,o,Ar,Qr,Er,Ir,Or,Ur,ir,ur,aIr,aUr,A@,Q@,E@,I@,O@,U@,i@,u@,"
          r"aI@,aU@,@r,@l,@m,@n,@N,1,e@m,e@n,y,I\,M,U\,Y,@\,@`,3`,A`,Q`,E`,I`,O`,U`,i`,u`,aI`,aU`,},2,3\,6,7,8,9,&,{~,I~,aU~,VI,VU,@U,"
          r"ai,ei,Oi,au,ou,Ou,@u,i:,u:,O:,e@0,E~,e~,3r,ar,or,{l,Al,al,El,Il,il,ol,ul,Ul,oUl,@5,u5,O5,A5,E5,I5,i5,mm,nn,ll,NN").split(",")
CONSONANTS = "b,tS,d,D,4,f,g,h,dZ,k,l,m,n,N,p,r,s,S,t,T,v,w,W,j,z,Z,t_},・,_".split(",")

DIPHTHONGS = ["aI", "eI", "OI", "aU", "oU", "VI", "VU", "@U", "ai", "ei", "Oi", "au", "ou", "Ou", "@u"]
AFFRICATES = ["dZ", "tS"]

VV_EXCEPTIONS = {"aI": "j", "eI": "j", "OI": "j", "aU": "w", "oU": "w", "VI": "j", "VU": "w", "@U": "w", "ai": "j", "Oi": "j",
                 "au": "w", "ou": "w", "Ou": "w", "@u": "w", "3": "r"}
DELTA5_VV_EXCEPTIONS = {"aI": "I", "eI": "I", "OI": "I", "aU": "U", "oU": "U", "VI": "I", "VU": "U", "@U": "U", "ai": "i", "Oi": "i",
                        "au": "u", "ou": "u", "Ou": "u", "@u": "u", "3": "r"}


def _dict(spec):
    """spec.Split(';').Select(e => e.Split('=')).Where(len 2).Where(p0 != p1).ToDictionary(...)"""
    out = {}
    for entry in spec.split(";"):
        parts = entry.split("=")
        if len(parts) != 2 or parts[0] == parts[1]:
            continue
        if parts[0] in out:
            raise ValueError(f"An item with the same key has already been added. Key: {parts[0]}")
        out[parts[0]] = parts[1]
    return out


@phonemizer("English X-SAMPA phonemizer", "EN X-SAMPA", language="EN", openutau_class="OpenUtau.Plugin.Builtin.EnXSampaPhonemizer", author="Lotte V")
class EnXSampaPhonemizer(SyllableBasedPhonemizer):
    yaml_file_name = "en-xsampa.yaml"
    yaml_template = "en-xsampa.template.yaml"
    no_gap = True  # endings have a 50 ticks gap

    def __init__(self):
        super().__init__()
        self.vowels = list(VOWELS)
        self.consonants = list(CONSONANTS)
        self.dictionary_replacements = _dict(
            "aa=A;ae={;ah=V;ao=O;aw=aU;ax=@;ay=aI;"
            "b=b;ch=tS;d=d;dh=D;" "dx=4;eh=E;el=@l;em=@m;en=@n;eng=@N;er=3;ey=eI;f=f;g=g;hh=h;ih=I;iy=i;jh=dZ;k=k;l=l;m=m;n=n;ng=N;ow=oU;oy=OI;"
            "p=p;q=・;r=r;s=s;sh=S;t=t;th=T;" "uh=U;uw=u;v=v;w=w;" "y=j;z=z;zh=Z")
        # for banks aliased with VOCALOID-style phonemes
        self.voca_sampa = _dict("A=Q;E=e;i=i:;u=u:;O=O:;3=@r;oU=@U;Ar=Q@;Qr=Q@;Er=e@;er=e@;Ir=I@;ir=I@;i:r=I@;Or=O@;O:r=O@;Ur=U@;ur=U@;u:r=U@")
        self.is_voca_sampa = False
        # for banks with slightly fewer vowels
        self.simple_delta = _dict("E=e;V=@;o=O")
        self.is_simple_delta = False
        self.canadian_raising = _dict("VI=aI;VU=aU")
        self.is_missing_canadian_raising = False
        # for banks with only minimal vowels
        self.mini_delta = _dict("I=i;U=u")
        self.is_mini_delta = False
        # for japanese-english combined banks
        self.en_plus_ja = _dict("j=y;dZ=j;r=r\\;tS=ch")
        self.is_en_plus_ja = False
        # for banks encoded in "true"/more accurate x-sampa
        self.true_x_sampa = _dict("r=r\\;3=@`")
        self.is_true_x_sampa = False
        # for banks using salem's reclist
        self.salem_list = _dict("3=@r;Ar=ar;aIr=ar;aUr=ar;Or=or;aIl=al")
        self.is_salem_list = False
        # velar nasal fallback
        self.velar_nasal_fallback = _dict("N g=n g;N k=n k")
        self.is_velar_nasal_fallback = False
        # for kasane teto's missing sample
        self.teto_exception = _dict("V=@")
        self.is_teto_exception = False
        # for dark l vowels (the c# splits this list on ';' while it is written with ',', so it stays empty)
        self.dark_l_vowel = _dict("@l=@5,ul=u5,Ol=O5,Al=A5,El=E5,Il=I5,il=i5,")
        self.is_dark_l_vowel = False

    def get_vowels(self):
        return self.vowels

    def get_consonants(self):
        return self.consonants

    def get_dictionary_name(self):
        return ""

    def get_base_g2ps(self):
        return [ArpabetG2p()]

    def get_symbols(self, note):
        original = super().get_symbols(note)
        if original is None:
            return None
        final = []
        for i in range(len(original)):
            if original[i] in self.dictionary_replacements:
                original[i] = self.dictionary_replacements[original[i]]
        H = self.has_oto
        V = self.validate_alias
        # splits diphthongs and affricates if not present in the bank
        for s in original:
            if s in DIPHTHONGS and not H(f"- {s}", note.tone) and not H(s, note.tone) and not H(V(f"- {s}"), note.tone) and not H(V(s), note.tone):
                final.extend([s[0], s[1] + "^"])
            elif s in AFFRICATES and not H(f"{s}A", note.tone) and not H(f"{s} A", note.tone) and not H(f"{s}Q", note.tone) and not H(f"{s} Q", note.tone):
                final.extend([s[0], s[1]])
            else:
                final.append(s)
        return final

    def process_syllable(self, syllable):
        H = self.has_oto
        V = self.validate_alias
        add = self.try_add_phoneme
        tone = syllable.tone
        vtone = syllable.vowel_tone

        syllable.prev_v = "" if syllable.prev_v in self.tails else syllable.prev_v
        replaced_prev_v = self.replace_phoneme(syllable.prev_v, tone)
        prev_v = "" if not replaced_prev_v else replaced_prev_v
        cc = [self.replace_phoneme(c, tone) for c in syllable.cc]
        v = self.replace_phoneme(syllable.v, vtone)
        phonemes = []
        last_c = len(cc) - 1
        first_c = 0
        current_word_cc = [self.replace_phoneme(c, tone) for c in syllable.current_word_cc]
        previous_word_cc = [self.replace_phoneme(c, tone) for c in syllable.previous_word_cc]
        prev_word_consonants_count = syllable.prev_word_consonants_count

        rv = f"- {v}"

        # switch between phonetic systems, depending on certain aliases in the bank
        if H("- i:", tone) or H("i:", tone) or (not H("- 3", tone) and not H("3", tone)):
            self.is_voca_sampa = True
        if not H("- VI", tone) or H("VI", tone) or (not H("- VU", tone) and not H("VU", tone)):
            self.is_missing_canadian_raising = True
        if not H("- V", vtone) and not H("V", vtone):
            self.is_simple_delta = True
        if not H("- bV", vtone) and not H("bV", vtone):
            self.is_teto_exception = True
        if (not H("- I", vtone) and not H("I", vtone)) or (not H("- U", vtone) and not H("U", vtone)):
            self.is_mini_delta = True
        if H("あ", vtone) or H("- あ", vtone):
            self.is_en_plus_ja = True
        if H(f"{prev_v} r\\", tone):
            self.is_true_x_sampa = True
        if not H("- 3", tone) and not H("3", tone) and not H("- @`", tone) and not H("@`", tone):
            self.is_salem_list = True
        if (not H("N g", tone) or not H("N g-", tone)) and (not H("N k", tone) or not H("N k-", tone)):
            self.is_velar_nasal_fallback = True
        if any(H(a, vtone) for a in ["@5", "u5", "O5", "A5", "E5", "I5", "i5", "- @5", "- u5", "- O5", "- A5", "- E5", "- I5", "- i5"]):
            self.is_dark_l_vowel = True

        if syllable.is_starting_v:
            if H(rv, vtone) or H(V(rv), vtone):
                base_phoneme = rv
            else:
                base_phoneme = v
        elif syllable.is_vv:
            if not self.can_make_alias_extension(syllable):
                if H(f"{prev_v} {v}", vtone) or H(V(f"{prev_v} {v}"), vtone):
                    base_phoneme = f"{prev_v} {v}"
                elif H(f"{prev_v}{v}", vtone) or H(V(f"{prev_v}{v}"), vtone):
                    base_phoneme = f"{prev_v}{v}"
                elif prev_v in VV_EXCEPTIONS or prev_v in DELTA5_VV_EXCEPTIONS:
                    table = VV_EXCEPTIONS if prev_v in VV_EXCEPTIONS else DELTA5_VV_EXCEPTIONS
                    tail = table[prev_v]
                    vc_space = f"{prev_v} {tail}"
                    vc_no_space = f"{prev_v}{tail}"
                    cv = f"{tail}{v}"
                    cv_space = f"{tail} {v}"
                    add(phonemes, tone, vc_space, V(vc_space), vc_no_space, V(vc_no_space))
                    if H(cv, vtone) or H(V(cv), vtone):
                        base_phoneme = cv
                    elif H(cv_space, vtone) or H(V(cv_space), vtone):
                        base_phoneme = cv_space
                    elif H(v, vtone) or H(V(v), vtone):
                        base_phoneme = v
                    else:
                        base_phoneme = V(f"- {v}")
                        phonemes.append(f"{prev_v} -")
                elif prev_v in self.diphthong_splits or prev_v in self.diphthong_tails:
                    # diphthong fallbacks
                    if prev_v in self.diphthong_splits:
                        split_override = self.diphthong_splits[prev_v]
                        vc = split_override[0].replace("{v}", v)
                        cv = split_override[1].replace("{v}", v)
                        add(phonemes, tone, vc, V(vc))
                    else:
                        # default yaml diphthong logic
                        tail = self.diphthong_tails[prev_v]
                        vc_space = f"{prev_v} {tail}"
                        vc_no_space = f"{prev_v}{tail}"
                        cv = f"{tail}{v}"
                        add(phonemes, tone, vc_space, V(vc_space), vc_no_space, V(vc_no_space))
                    if H(cv, vtone) or H(V(cv), vtone):
                        base_phoneme = cv
                    elif not H(cv, vtone) or not H(V(cv), vtone):
                        base_phoneme = f"{self.diphthong_tails[prev_v]} {v}"
                    elif H(v, vtone) or H(V(v), vtone):
                        base_phoneme = v
                    else:
                        base_phoneme = V(f"- {v}")
                        phonemes.append(f"{prev_v} -")
                else:
                    if H(v, vtone) or H(V(v), vtone):
                        base_phoneme = v
                    else:
                        base_phoneme = V(f"- {v}")
                        phonemes.append(f"{prev_v} -")
            else:
                base_phoneme = None
        elif syllable.is_starting_cv_with_one_consonant:
            rcv = f"- {cc[0]}{v}"
            crv = f"{cc[0]} {v}"
            cv = f"{cc[0]}{v}"
            if H(rcv, vtone) or H(V(rcv), vtone):
                base_phoneme = rcv
            elif (not H(rcv, vtone) and not H(V(rcv), vtone)) and (H(crv, vtone) or H(V(crv), vtone)):
                base_phoneme = crv
                add(phonemes, tone, f"- {cc[0]}", V(f"- {cc[0]}"))
            else:
                base_phoneme = cv
                add(phonemes, tone, f"- {cc[0]}", V(f"- {cc[0]}"))
        elif syllable.is_starting_cv_with_more_than_one_consonant:
            # try RCCV
            rccv = f"- {''.join(cc)}{v}"
            crv = f"{last(cc)} {v}"
            ucv = f"_{last(cc)}{v}"
            if H(rccv, vtone) or H(V(rccv), vtone):
                base_phoneme = rccv
                last_c = 0
            else:
                if H(ucv, vtone) or H(V(ucv), vtone):
                    base_phoneme = ucv
                elif H(crv, vtone) or H(V(crv), vtone):
                    base_phoneme = crv
                else:
                    base_phoneme = f"{last(cc)}{v}"
                # try RCC
                for i in range(len(cc), 1, -1):
                    a = f"- {''.join(cc[:i])}"
                    if add(phonemes, tone, a, V(a)):
                        first_c = i - 1
                        break
                if len(phonemes) == 0:
                    add(phonemes, tone, f"- {cc[0]}", V(f"- {cc[0]}"))
                # try CCV
                for i in range(first_c, len(cc) - 1):
                    ccv = "".join(cc[i:]) + v
                    if H(ccv, vtone) or H(V(ccv), vtone):
                        base_phoneme = ccv
                        last_c = i
                        break
                    else:
                        if H(ucv, vtone) or H(V(ucv), vtone):
                            base_phoneme = ucv
                            break
                        elif H(crv, vtone) or H(V(crv), vtone):
                            base_phoneme = crv
                            break
                        else:
                            base_phoneme = f"{last(cc)}{v}"
                            break
        else:  # VCV
            vcv = f"{prev_v} {cc[0]}{v}"
            vcv_end = f"{prev_v}{cc[0]} {v}"
            vccv = f"{prev_v} {''.join(cc)}{v}"
            crv = f"{last(cc)} {v}"
            one = syllable.is_vcv_with_one_consonant
            if one and (H(vcv, vtone) or H(V(vcv), vtone)) and prev_word_consonants_count == 0 and len(current_word_cc) == 1:
                # regular VCV if the current word starts with one consonant and the previous word ends with none
                base_phoneme = vcv
            elif one and prev_word_consonants_count == 1 and len(current_word_cc) == 0 and (H(vcv_end, vtone) or H(V(vcv_end), vtone)):
                # end VCV if the current word does not start with a consonant but the previous word ends with one
                base_phoneme = vcv_end
            elif one and not H(vcv_end, vtone) and not H(V(vcv_end), vtone) and (H(vcv, vtone) or H(V(vcv), vtone)):
                # regular VCV if end VCV does not exist
                base_phoneme = vcv
            elif syllable.is_vcv_with_more_than_one_consonant and (H(vccv, vtone) or H(V(vccv), vtone)) and prev_word_consonants_count == 0:
                # VCV with multiple consonants, only for current word onset and null previous word ending
                base_phoneme = vccv
                last_c = 0
            else:
                cv = last(cc) + v
                base_phoneme = cv
                if (not H(cv, vtone) and not H(V(cv), vtone)) and (H(crv, vtone) or H(V(crv), vtone)):
                    base_phoneme = crv
                # try CCV
                if len(cc) - first_c > 1 and len(current_word_cc) >= 2:
                    for i in range(first_c, len(cc)):
                        ccv = f"{''.join(cc)}{v}"
                        rccv = f"- {''.join(cc)}{v}"
                        ucv = f"_{last(cc)}{v}"
                        if H(ccv, vtone) or H(V(ccv), vtone):
                            last_c = 0
                            base_phoneme = ccv
                            break
                        elif not H(ccv, vtone) and not H(V(ccv), vtone) and (H(rccv, vtone) or H(V(rccv), vtone)):
                            last_c = 0
                            base_phoneme = rccv
                            break
                        elif (not H(rccv, vtone) or not H(V(rccv), vtone)) and (H(ucv, vtone) or H(V(ucv), vtone)):
                            base_phoneme = ucv
                            break
                # try vcc
                for i in range(last_c + 1, -1, -1):
                    vr = f"{prev_v} -"
                    vcc = f"{prev_v} {''.join(cc[:2])}"
                    vcc2 = f"{prev_v}{' '.join(cc[:2])}"
                    vc = f"{prev_v} {cc[0]}"
                    if i == 0:
                        if H(vr, tone) or H(V(vr), tone):
                            phonemes.append(vr)
                    elif (H(vcc, tone) or H(V(vcc), tone)) and "".join(cc[:2]) not in self.affricate:
                        phonemes.append(vcc)
                        first_c = 1
                        break
                    elif H(vcc2, tone) or H(V(vcc2), tone):
                        phonemes.append(vcc2)
                        first_c = 1
                        break
                    elif H(vc, tone) or H(V(vc), tone):
                        phonemes.append(vc)
                        break
                    else:
                        continue

        i = first_c
        while i < last_c:
            # we could use some CCV, so lastC is used; we could use -CC so firstC is used
            cc1 = f"{cc[i]} {cc[i + 1]}"
            ccv = "".join(cc[i + 1:]) + v
            rccv = f"- {''.join(cc[i + 1:]) + v}"
            ucv = f"_{last(cc)}{v}"
            crv = f"{last(cc)} {v}"
            cv = f"{last(cc)}{v}"
            # use [C1C2...] when current word starts with 2 consonants or more
            if not H(cc1, tone):
                cc1 = V(cc1)
            if len(current_word_cc) >= 2 and cc1 not in previous_word_cc:
                cc1 = "".join(cc[i:])
            if len(current_word_cc) >= 2:
                if last(cc) in self.liquid or last(cc) in self.semivowel or V(last(cc)) in self.liquid or V(last(cc)) in self.semivowel:
                    self.glides(cc1)
            if not H(cc1, tone):
                cc1 = V(cc1)
            # use [C1C2] when current word has 2 consonants or more and [C1C2C3...] does not exist
            if not H(cc1, tone) and len(current_word_cc) >= 2 and cc1 in current_word_cc:
                cc1 = f"{cc[i]}{cc[i + 1]}"
            if not H(cc1, tone):
                cc1 = V(cc1)
            # use [C1 C2] when either [C1C2] does not exist, or the previous word owns it
            if not H(cc1, tone) or cc1 in previous_word_cc:
                cc1 = f"{cc[i]} {cc[i + 1]}"
            if not H(cc1, tone):
                cc1 = V(cc1)
            # use UCV if it exists
            if (H(ucv, vtone) or H(V(ucv), vtone)) and f"{cc[i]} {cc[i + 1]}" not in cc1:
                base_phoneme = ucv
            if i + 1 < last_c:
                cc2 = f"{cc[i + 1]} {cc[i + 2]}"
                if not H(cc2, tone):
                    cc2 = V(cc2)
                # use [C2C3...] when current word starts with 2 consonants or more
                if len(current_word_cc) >= 2 and cc2 not in previous_word_cc:
                    cc2 = "".join(cc[i:])
                if not H(cc2, tone):
                    cc2 = V(cc2)
                if len(current_word_cc) >= 2:
                    if cc[i + 1] in self.liquid or cc[i + 1] in self.semivowel or V(cc[i + 1]) in self.liquid or V(cc[i + 1]) in self.semivowel:
                        self.glides(cc1)
                # use [C2C3] when current word has 2 consonants or more and [C2C3C4...] does not exist
                if not H(cc2, tone) and len(current_word_cc) >= 2 and cc2 in current_word_cc:
                    cc2 = f"{cc[i + 1]}{cc[i + 2]}"
                if not H(cc2, tone):
                    cc2 = V(cc2)
                # use [C2 C3] when either [C2C3] does not exist, or the previous word owns it
                if not H(cc2, tone) or cc2 in previous_word_cc:
                    cc2 = f"{cc[i + 1]} {cc[i + 2]}"
                if not H(cc2, tone):
                    cc2 = V(cc2)
                rest = "".join(cc[i + 1:])
                if (H(ccv, vtone) or H(V(ccv), vtone)) and len(current_word_cc) >= 2 and rest not in previous_word_cc:
                    # use CCV if it exists
                    last_c = i
                    base_phoneme = ccv
                elif (H(rccv, vtone) or H(V(rccv), vtone)) and len(current_word_cc) >= 2 and rest not in previous_word_cc:
                    # use RCCV if it exists
                    last_c = i
                    base_phoneme = rccv
                elif (H(ucv, vtone) or H(V(ucv), vtone)) and H(cc2, vtone) and f"{cc[i + 1]} {cc[i + 2]}" not in cc2 and len(current_word_cc) >= 2:
                    # use _CV if it exists
                    base_phoneme = ucv
                elif H(crv, vtone) or H(V(crv), vtone):
                    # use spaced CV if it exists
                    base_phoneme = crv
                else:
                    # use normal CV
                    base_phoneme = cv
                if H(cc1, tone) and H(cc2, tone) and "".join(cc[i:]) not in cc1:
                    # like [V C1] [C1 C2] [C2 C3] [C3 ..]
                    phonemes.append(cc1)
                elif add(phonemes, tone, cc1):
                    # like [V C1] [C1 C2] [C2 ..]
                    if "".join(cc[i:]) in cc1:
                        i += 1
                else:
                    # singular cc
                    if ((cc1 in previous_word_cc) == (cc1 in current_word_cc)) and cc1 not in self.affricate:
                        cc1 = V(cc1)
                    else:
                        add(phonemes, tone, cc1, cc[i], V(cc[i]))
            else:
                # like [V C1] [C1 C2]  [C2 ..] or like [V C1] [C1 -] [C3 ..]
                add(phonemes, tone, cc1, cc[i], V(cc[i]))
            i += 1

        phonemes.append(base_phoneme)
        return phonemes

    def process_ending(self, ending):
        H = self.has_oto
        V = self.validate_alias
        add = self.try_add_phoneme
        tone = ending.tone
        cc = [self.replace_phoneme(c, tone) for c in ending.cc]
        v = self.replace_phoneme(ending.prev_v, tone)
        t = self.replace_phoneme(ending.tail, tone) if ending.has_tail else "-"
        phonemes = []
        vr = f"{v} {t}"
        last_c = len(cc) - 1
        first_c = 0

        if ending.is_ending_v:
            add(phonemes, tone, vr, V(vr))
        elif ending.is_ending_vc_with_one_consonant:
            vc = f"{v} {cc[0]}"
            vcr = f"{v} {cc[0]}{t}"
            vcr2 = f"{v}{cc[0]} {t}"
            if H(vcr, tone) or H(V(vcr), tone):
                phonemes.append(vcr)
            elif (not H(vcr, tone) and not H(V(vcr), tone)) and (H(vcr2, tone) or H(V(vcr2), tone)):
                phonemes.append(vcr2)
            else:
                phonemes.append(vc)
                if cc[0] in self.affricate:
                    add(phonemes, tone, f"{cc[0]} {t}", cc[0])
                else:
                    add(phonemes, tone, f"{cc[0]} {t}", V(f"{cc[0]} {t}"))
        else:
            for i in range(last_c, -1, -1):
                vcc = f"{v} {''.join(cc[:2])}{t}"
                vcc2 = f"{v}{' '.join(cc[:2])}{t}"
                vcc3 = f"{v}{' '.join(cc[:2])}"
                vcc4 = f"{v} {''.join(cc[:2])}"
                vc = f"{v} {cc[0]}"
                if i == 0:
                    if H(vr, tone) or H(V(vr), tone):
                        phonemes.append(vr)
                elif (H(vcc, tone) or H(V(vcc), tone)) and last_c == 1:
                    phonemes.append(vcc)
                    first_c = 1
                    break
                elif (H(vcc2, tone) or H(V(vcc2), tone)) and last_c == 1:
                    phonemes.append(vcc2)
                    first_c = 1
                    break
                elif H(vcc3, tone) or H(V(vcc3), tone):
                    phonemes.append(vcc3)
                    if vcc3.endswith(last(cc)) and last_c == 1:
                        if last(cc) in self.affricate:
                            add(phonemes, tone, f"{last(cc)} {t}", V(f"{last(cc)} {t}"), last(cc), V(last(cc)))
                        else:
                            add(phonemes, tone, f"{last(cc)} {t}", V(f"{last(cc)} {t}"))
                    first_c = 1
                    break
                elif H(vcc4, tone) or H(V(vcc4), tone):
                    phonemes.append(vcc4)
                    if vcc4.endswith(last(cc)) and last_c == 1:
                        if last(cc) in self.affricate:
                            add(phonemes, tone, f"{last(cc)} {t}", V(f"{last(cc)} {t}"), last(cc), V(last(cc)))
                        else:
                            add(phonemes, tone, f"{last(cc)} {t}", V(f"{last(cc)} {t}"))
                    first_c = 1
                    break
                else:
                    phonemes.append(vc)
                    break

            i = first_c
            while i < last_c:
                # all CCs except the first one are /C1C2/, the last one is /C1 C2-/
                # but if there is no /C1C2/, we try /C1 C2-/, vise versa for the last one
                cc1 = f"{cc[i]} {cc[i + 1]}"
                if i < len(cc) - 2:
                    cc2 = f"{cc[i + 1]} {cc[i + 2]}"
                    if not H(cc1, tone):
                        cc1 = V(cc1)
                    if not H(cc1, tone):
                        cc1 = f"{cc[i]}{cc[i + 1]}"
                    if not H(cc1, tone):
                        cc1 = V(cc1)
                    if not H(cc2, tone):
                        cc2 = V(cc2)
                    if not H(cc2, tone):
                        cc2 = f"{cc[i + 1]}{cc[i + 2]}"
                    if not H(cc2, tone):
                        cc2 = V(cc2)
                    c2c3t = f"{cc[i + 1]} {cc[i + 2]}{t}"
                    if add(phonemes, tone, f"{cc[i]} {cc[i + 1]}{cc[i + 2]}{t}", V(f"{cc[i]} {cc[i + 1]}{cc[i + 2]}{t}")):
                        # like [C1 C2-][C3 ...]
                        i += 1
                    elif H(cc1, tone) and (H(cc2, tone) or H(c2c3t, tone) or H(V(c2c3t), tone)):
                        # like [C1 C2][C2 ...]
                        phonemes.append(cc1)
                    elif H(cc[i], tone) or H(V(cc[i]), tone) and (H(cc2, tone) or H(c2c3t, tone) or H(V(c2c3t), tone)):
                        # like [C1 C2-][C3 ...]
                        phonemes.append(cc[i])
                    elif add(phonemes, tone, c2c3t, V(c2c3t)):
                        # like [C1 C2-][C3 ...]
                        i += 1
                    elif add(phonemes, tone, f"{cc[i + 1]}{cc[i + 2]}", V(f"{cc[i + 1]}{cc[i + 2]}")):
                        # like [C1C2][C2 ...]
                        i += 1
                    elif add(phonemes, tone, cc1, V(cc1)):
                        i += 1
                    else:
                        # like [C1][C2 ...]
                        add(phonemes, tone, cc[i], V(cc[i]), f"{cc[i]} {t}", V(f"{cc[i]} {t}"))
                        add(phonemes, tone, cc[i + 1], V(cc[i + 1]), f"{cc[i + 1]} {t}", V(f"{cc[i + 1]} {t}"))
                        i += 1
                else:
                    if not H(cc1, tone):
                        cc1 = V(cc1)
                    if not H(cc1, tone):
                        cc1 = f"{cc[i]}{cc[i + 1]}"
                    if not H(cc1, tone):
                        cc1 = V(cc1)
                    if add(phonemes, tone, f"{cc[i]} {cc[i + 1]}{t}", V(f"{cc[i]} {cc[i + 1]}{t}")):
                        # like [C1 C2-]
                        i += 1
                    elif add(phonemes, tone, cc1, V(cc1)):
                        # like [C1 C2][C2 -]
                        add(phonemes, tone, f"{cc[i + 1]} {t}", V(f"{cc[i + 1]} {t}"), cc[i + 1], V(cc[i + 1]))
                        i += 1
                    elif add(phonemes, tone, f"{cc[i]}{cc[i + 1]}", V(f"{cc[i]}{cc[i + 1]}")):
                        # like [C1C2][C2 -]
                        add(phonemes, tone, f"{cc[i + 1]} {t}", V(f"{cc[i + 1]} {t}"), cc[i + 1], V(cc[i + 1]))
                        i += 1
                    else:
                        # like [C1][C2 -]
                        add(phonemes, tone, cc[i], V(cc[i]), f"{cc[i]} {t}", V(f"{cc[i]} {t}"))
                        add(phonemes, tone, f"{cc[i + 1]} {t}", V(f"{cc[i + 1]} {t}"), cc[i + 1], V(cc[i + 1]))
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
                candidate = cs_replace(candidate, key, value)

        if self.is_voca_sampa:
            apply_dictionary(self.voca_sampa)
        if self.is_simple_delta:
            apply_dictionary(self.simple_delta)
        if self.is_mini_delta:
            apply_dictionary(self.mini_delta)
        if self.is_en_plus_ja:
            apply_dictionary(self.en_plus_ja)
        if self.is_true_x_sampa:
            apply_dictionary(self.true_x_sampa)
        if self.is_salem_list:
            apply_dictionary(self.salem_list)
        if self.is_velar_nasal_fallback:
            apply_dictionary(self.velar_nasal_fallback)
        if self.is_teto_exception:
            apply_dictionary(self.teto_exception)
        if self.is_missing_canadian_raising:
            apply_dictionary(self.canadian_raising)
        if self.is_dark_l_vowel:
            apply_dictionary(self.dark_l_vowel)

        # split diphthongs adjuster
        candidate = candidate.replace("U^", "U").replace("I^", "I").replace("u^", "u").replace("i^", "i")

        # other validations
        if "@r" not in candidate and "3r" not in candidate:
            if self.consonants is not None:
                for consonant1 in ["r ", "r\\ "]:
                    for consonant2 in self.consonants:
                        candidate = cs_replace(candidate, consonant1 + consonant2, "3 " + consonant2)

        if candidate != alias and self.has_oto(candidate, tone):
            return candidate
        return None

    def get_transition_basic_length_ms_with_attr(self, alias, tone, attr):
        oto_length = self.get_transition_basic_length_ms_by_oto(alias, tone, attr)
        for symbol, value in sorted(self.phoneme_overrides.items(), key=lambda kv: len(kv[0]), reverse=True):
            if cs_regex_word_boundary_match(alias, symbol):
                return self.get_transition_basic_length_ms_by_constant() * value
        return oto_length
