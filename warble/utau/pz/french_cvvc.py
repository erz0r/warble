"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Plugin.Builtin/FrenchCVVCPhonemizer.cs

french cvvc (mim, with the help of heiden.bzr's & nago's phonemizers), with "fraloids" voicebank support (a
bank with an "a" alias switches the vowels to fraloids names).

the dictionary is the legacy cmudict_fr.txt from openutau's Dictionaries folder, which a fresh install
doesn't have, so in practice only phonetic hints (and tails) give symbols; other lyrics end in "word not
found" (or the lyric itself when the bank has it as an alias).

c# quirks kept: usesFraloids is an instance field that is only ever set (never reset) by process_syllable
and read by process_ending / validate_alias; ValidateAlias(v) is called with the default tone 0; out of range
cc indexes throw (c# arrays don't wrap), which openutau turns into an error phoneme.
"""

from .api import phonemizer
from .syllable_based import SyllableBasedPhonemizer, at, last


def _pairs(spec):
    out = {}
    for entry in spec.split(";"):
        parts = entry.split("=")
        if len(parts) != 2 or parts[0] == parts[1]:
            continue
        if parts[0] in out:
            raise ValueError(f"An item with the same key has already been added. Key: {parts[0]}")
        out[parts[0]] = parts[1]
    return out


@phonemizer("French CVVC Phonemizer", "FR CVVC", language="FR", openutau_class="OpenUtau.Plugin.Builtin.FrenchCVVCPhonemizer", author="Mim")
class FrenchCVVCPhonemizer(SyllableBasedPhonemizer):
    no_gap = True  # Endings has 50 ticks gap

    def __init__(self):
        super().__init__()
        self._fr_vowels = "ah,ae,eh,ee,oe,ih,oh,oo,ou,uh,en,in,on,oi,ui,a,ai,e,i,o,u,eu".split(",")
        self._fr_consonants = "b,d,f,g,j,k,l,m,n,p,r,s,sh,t,v,w,y,z,gn,.,-,R,BR,_hh".split(",")
        self._fr_dictionary_replacements = _pairs(
            "aa=ah;ai=ae;ei=eh;eu=ee;ee=ee;oe=oe;ii=ih;au=oh;oo=oo;ou=ou;uu=uh;an=en;in=in;un=in;on=on;uy=ui;"
            "bb=b;dd=d;ff=f;gg=g;jj=j;kk=k;ll=l;mm=m;nn=n;pp=p;rr=r;ss=s;ch=sh;tt=t;vv=v;ww=w;yy=y;zz=z;gn=gn;4=l;hh=h;")
        self.short_consonants = "r".split(",")
        self.long_consonants = "t,k,g,p,s,sh,j".split(",")
        self.fraloids_replacement = _pairs("ah=a;ae=ai;ee=e;ih=i;oh=o;uh=u;oe=eu;")
        self.uses_fraloids = False

    def get_vowels(self):
        return self._fr_vowels

    def get_consonants(self):
        return self._fr_consonants

    def get_dictionary_name(self):
        return "cmudict_fr.txt"

    def get_dictionary_phonemes_replacement(self):
        return self._fr_dictionary_replacements

    def process_syllable(self, syllable):
        prev_v = syllable.prev_v
        cc = syllable.cc
        v = syllable.v

        phonemes = []

        if prev_v == "ui":
            prev_v = "ih"

        # Convert to Fraloids
        if self.has_oto("a", syllable.tone):
            self.uses_fraloids = True
            v = self.validate_alias(v)
            prev_v = self.validate_alias(prev_v)

        # --------------------------- STARTING V ------------------------------- //
        if syllable.is_starting_v:
            # try -V, - V then defaults to V
            base_phoneme = self._check_alias_formatting(v, "cv", syllable.vowel_tone, "")

        # --------------------------- is VV ------------------------------- //
        elif syllable.is_vv:
            if not self.can_make_alias_extension(syllable):
                vv_check = prev_v + v
                # TODO clean exception of fraloids ai/a + i conflict
                if self.uses_fraloids and vv_check == "ai":
                    base_phoneme = self._check_alias_formatting(v, "vvFr", syllable.vowel_tone, prev_v)
                else:
                    base_phoneme = self._check_alias_formatting(v, "vv", syllable.vowel_tone, prev_v)
                    if base_phoneme == v:
                        # TODO clean exception part below
                        if prev_v == "ih" or prev_v == "i":
                            base_phoneme = f"y{v}"
                        if prev_v == "ou":
                            base_phoneme = f"w{v}"
                        if not self.has_oto(base_phoneme, syllable.tone):
                            base_phoneme = v
            else:
                # the previous alias will be extended
                base_phoneme = None

        # --------------------------- STARTING CV ------------------------------- //
        elif syllable.is_starting_cv_with_one_consonant:
            cv = f"{cc[0]}{v}"
            base_phoneme = self._check_alias_formatting(cv, "cv", syllable.tone, "")

            if "-" not in base_phoneme:
                self.try_add_phoneme(phonemes, syllable.tone, self._check_alias_formatting(f"{cc[0]}", "rcv", syllable.tone, ""))

        # --------------------------- STARTING CCV ------------------------------- //
        elif syllable.is_starting_cv_with_more_than_one_consonant:
            rccv = f"{''.join(cc)}{v}"

            rccv = self._check_alias_formatting(rccv, "rcv", syllable.tone, "")
            if self.has_oto(rccv, syllable.vowel_tone):
                base_phoneme = rccv
            else:
                base_phoneme = f"{last(cc)}{v}"

                max_ = len(cc)
                min_ = 0

                # try -CC of all lengths
                for i in range(len(cc)):
                    rcc = ""
                    for k in range(max_):
                        rcc += f"{at(cc, k)}"
                    rcc = self._check_alias_formatting(rcc, "rcv", syllable.tone, "")
                    if self.has_oto(rcc, syllable.tone):
                        phonemes.append(rcc)
                        break
                    max_ -= 1

                if self._find_last_valid_alias(phonemes, cc) == len(cc) - 1:
                    pass  # GOOD JOB :)
                else:
                    min_ = len(cc) - self._find_last_valid_alias(phonemes, cc)
                    max_ = len(cc)
                    # try CCV of all lengths
                    for i in range(min_):
                        rccv = ""
                        for k in range(i, len(cc)):
                            rccv += f"{cc[k]}"
                        rccv += f"{v}"

                        if not self.has_oto(rccv, syllable.tone):
                            rccv = self.validate_alias(rccv)

                        if self.has_oto(rccv, syllable.vowel_tone):
                            base_phoneme = rccv
                            break
                        max_ -= 1

                    # try _CV else add CV
                    if self.has_oto(f"_{last(cc)}{v}", syllable.vowel_tone) and max_ == len(cc) - min_:
                        base_phoneme = f"_{last(cc)}{v}"

                    # try CC of all lengths
                    for i in range(len(cc) - max_):
                        rcc = ""
                        for k in range(min_):
                            rcc += f"{at(cc, k)}"
                        if self.has_oto(rcc, syllable.tone):
                            phonemes.append(rcc)
                            break
                        min_ -= 1

                    if self._find_last_valid_alias(phonemes, cc) == len(cc) - 1:
                        pass  # GOOD JOB :)
                    else:
                        min_ = self._find_last_valid_alias(phonemes, cc)

                        # add remaining CC
                        for i in range(min_, len(cc) - max_):
                            ccc = f"{at(cc, i)}"
                            ccc = self._check_alias_formatting(ccc, "endccOe", syllable.tone, f"{at(cc, i)}")

                            # exception of y sound
                            if f"{at(cc, i + 1)}" == "y" and self._check_coe_ending(ccc, syllable.tone) in ccc:
                                if self.uses_fraloids:
                                    ccc = f"{at(cc, i)}i"
                                else:
                                    ccc = f"{at(cc, i)}ih"
                            phonemes.append(ccc)

        # --------------------------- IS VCV ------------------------------- //
        elif syllable.is_vcv_with_one_consonant:
            # try VCV
            vcv = f"{prev_v} {cc[0]}{v}"
            if self.has_oto(vcv, syllable.vowel_tone):
                base_phoneme = vcv
            else:
                cv = f"{cc[0]}{v}"
                base_phoneme = cv

                # Fraloids "Vn"/"V n" conflict solve
                vc = ""
                if self.uses_fraloids:
                    vc = f"{prev_v} {cc[0]}"
                    vc = self._replace_fraloids_conflict(vc, syllable.tone)
                    if self.has_oto(vc, syllable.tone):
                        phonemes.append(vc)
                    else:
                        vc = f"{prev_v}{cc[0]}"
                        if self.has_oto(vc, syllable.tone):
                            phonemes.append(vc)
                if len(phonemes) == 0:
                    vc = self._check_alias_formatting(cc[0], "vc", syllable.tone, prev_v)
                    if self.has_oto(vc, syllable.tone):
                        phonemes.append(vc)
        else:
            # ------------- IS VCV WITH MORE THAN ONE CONSONANT --------------- //
            base_phoneme = f"{last(cc)}{v}"

            max_ = len(cc)
            min_ = 0

            # Fraloids "Vn"/"V n" conflict solve
            vc = ""
            if self.uses_fraloids:
                vc = f"{prev_v} {cc[0]}"
                vc = self._replace_fraloids_conflict(vc, syllable.tone)
                if self.has_oto(vc, syllable.tone):
                    phonemes.append(vc)

            if len(phonemes) == 0:
                # try VCC of all lengths
                for i in range(len(cc)):
                    vcc = ""
                    for k in range(len(cc) - i):
                        vcc += f"{cc[k]}"
                    vcc = self._check_alias_formatting(vcc, "vc", syllable.tone, prev_v)
                    if self.has_oto(vcc, syllable.tone):
                        phonemes.append(vcc)
                        break

            min_ = len(cc) - self._find_last_valid_alias(phonemes, cc)
            max_ = len(cc)
            # try CCV of all lengths
            for i in range(min_):
                ccv = ""
                for k in range(i, len(cc)):
                    ccv += f"{cc[k]}"
                ccv += f"{v}"

                if not self.has_oto(ccv, syllable.tone):
                    ccv = self.validate_alias(ccv)

                if self.has_oto(ccv, syllable.vowel_tone):
                    base_phoneme = ccv
                    break
                max_ -= 1

            # try _CV else add CV
            if self.has_oto(f"_{last(cc)}{v}", syllable.vowel_tone) and max_ == len(cc) - min_:
                base_phoneme = f"_{last(cc)}{v}"

            min_ = self._find_last_valid_alias(phonemes, cc)

            if min_ == len(cc):
                pass  # GOOD JOB :)
            else:
                min_ -= 1
                # add remaining CC
                for i in range(min_, len(cc) - max_):
                    ccc = f"{at(cc, i)}"

                    if i + 1 >= len(cc):
                        break

                    ccc = self._check_alias_formatting(ccc, "endccOe", syllable.tone, f"{cc[i + 1]}")

                    if self._check_coe_ending(ccc, syllable.tone) in ccc or ccc == f"{cc[i]}":
                        if cc[i] == cc[i + 1]:
                            break
                        if i == 0 and f"{cc[i + 1]}" != "y":
                            continue

                    # exception of y sound
                    if f"{cc[i + 1]}" == "y" and self._check_coe_ending(ccc, syllable.tone) in ccc:
                        if self.uses_fraloids:
                            ccc = f"{cc[i]}i"
                        else:
                            ccc = f"{cc[i]}ih"

                    if ccc == f"{cc[i]}":
                        if i + 2 <= len(cc):
                            break

                    phonemes.append(ccc)

        phonemes.append(base_phoneme)
        return phonemes

    def process_ending(self, ending):
        cc = ending.cc
        v = ending.prev_v

        phonemes = []

        # Convert to Fraloids
        if self.has_oto("a", ending.tone):
            v = self.validate_alias(v)

        # --------------------------- ENDING V ------------------------------- //
        if ending.is_ending_v:
            # try V- else no ending
            end_v = self._check_alias_formatting(v, "end", ending.tone, "")
            self.try_add_phoneme(phonemes, ending.tone, end_v)

            # TODO: clean exceptions
            if len(phonemes) == 0:
                end_v = v + " R"
                self.try_add_phoneme(phonemes, ending.tone, end_v)
                if len(phonemes) == 0:
                    end_v = v + " BR"
                    self.try_add_phoneme(phonemes, ending.tone, end_v)
                    if len(phonemes) == 0:
                        end_v = v + "_hh"
                        self.try_add_phoneme(phonemes, ending.tone, end_v)
        else:
            # --------------------------- ENDING VC ------------------------------- //
            if ending.is_ending_vc_with_one_consonant:
                vc = ""

                # Fraloids "Vn"/"V n" conflict solve
                if self.uses_fraloids:
                    vc = f"{v} {cc[0]}"
                    vc = self._replace_fraloids_conflict(vc, ending.tone)
                    if self.has_oto(vc, ending.tone):
                        phonemes.append(vc)
                if len(phonemes) == 0:
                    vc = self._check_alias_formatting(f"{v}{cc[0]}", "endVc", ending.tone, "")
                    if self.has_oto(vc, ending.tone):
                        phonemes.append(vc)
                    else:
                        vc = self._check_alias_formatting(cc[0], "vc", ending.tone, v)
                        phonemes.append(vc)

                if "-" not in vc:
                    self.try_add_phoneme(phonemes, ending.tone, self._check_alias_formatting(f"{cc[0]}", "end", ending.tone, ""))
            else:
                # --------------------------- ENDING VCC ------------------------------- //
                max_ = len(cc)

                # Fraloids "Vn"/"V n" conflict solve
                vc = ""
                if self.uses_fraloids:
                    vc = f"{v} {cc[0]}"
                    vc = self._replace_fraloids_conflict(vc, ending.tone)
                    if self.has_oto(vc, ending.tone):
                        phonemes.append(vc)
                if len(phonemes) == 0:
                    # try VCC of all lengths
                    for i in range(len(cc)):
                        type_ = "endVc"
                        if i > 0:
                            type_ = "blank"

                        vcc = ""
                        for k in range(len(cc) - i):
                            vcc += f"{cc[k]}"
                        temp = f"{v}{vcc}"
                        temp = self._check_alias_formatting(temp, type_, ending.tone, "")

                        if self.has_oto(temp, ending.tone):
                            vcc = temp
                            phonemes.append(vcc)
                            break
                        else:
                            temp = f"{v} {vcc}"
                            temp = self._check_alias_formatting(temp, type_, ending.tone, "")
                            if self.has_oto(temp, ending.tone):
                                vcc = temp
                                phonemes.append(vcc)
                                break
                        max_ -= 1

                if self._find_last_valid_alias(phonemes, cc) == len(cc):
                    end = self._check_alias_formatting(f"{last(cc)}", "end", ending.tone, "")
                    self.try_add_phoneme(phonemes, ending.tone, end)
                else:
                    # add remaining CC
                    for i in range(max_ - 1, len(cc)):
                        ccc = f"{at(cc, i)}"

                        # if last C & it has CC- then break the loop
                        if i + 1 == len(cc) - 1:
                            ccc = f"{at(cc, i)}{cc[i + 1]}"
                            ccc = self._check_alias_formatting(ccc, "end", ending.tone, "")
                            if self.has_oto(ccc, ending.tone):
                                phonemes.append(ccc)
                                break
                        # else try CC
                        if i + 1 < len(cc):
                            ccc = f"{at(cc, i)}"
                            ccc = self._check_alias_formatting(ccc, "endcc", ending.tone, f"{cc[i + 1]}")
                            if self.has_oto(ccc, ending.tone):
                                phonemes.append(ccc)
                                continue

                        if i > 0:
                            ccc = f"{cc[i]}"
                            ccc = self._check_alias_formatting(ccc, "endcOe", ending.tone, "")

                        if self.has_oto(ccc, ending.tone):
                            phonemes.append(ccc)

        return phonemes

    # TODO: add "oi" exception
    def validate_alias(self, alias, tone=0):
        if self.has_oto(alias, tone):
            return alias

        base_resolved = super().validate_alias(alias, tone)
        if base_resolved and base_resolved != alias:
            if self.has_oto(base_resolved, tone):
                return base_resolved
            alias = base_resolved

        # fraloids conversion
        if self.uses_fraloids:
            for key, value in self.fraloids_replacement.items():
                alias = alias.replace(key, value)

        for oi in ("wah", "wa"):
            alias = alias.replace(oi, "oi")

        return alias

    def _replace_fraloids_conflict(self, vc, tone):
        fraloids_vcs = {"o n": "on2", "e n": "en2", "i n": "in2", "u n": "un2"}

        if self.has_oto(vc, tone) or vc == "ai n":
            return vc

        for key, value in fraloids_vcs.items():
            vc = vc.replace(key, value)
        return vc

    def _check_coe_ending(self, cv, tone):
        # TODO: Improve cOe check
        if self.has_oto(cv, tone) and "oe" in cv:
            return "oe"
        elif "eu" in cv:
            return "eu"
        return "no Coe Ending"

    def get_transition_basic_length_ms_with_attr(self, alias, tone, attr):
        oto_length = self.get_transition_basic_length_ms_by_oto(alias, tone, attr)
        return oto_length

    def _check_alias_formatting(self, alias, type_, tone, prev_v):
        alias_formats = ["-", "- ", "", "-", " -", "", prev_v, prev_v + " ", "_", "", prev_v, " " + prev_v, "", "oe", "eu"]
        starting_i = 0
        ending_i = len(alias_formats)

        # ---- TODO: CLEAN THIS //
        if type_ == "end":
            starting_i = 3
            ending_i = starting_i + 1
        if type_ == "endC":
            starting_i = 2
            ending_i = starting_i + 1
        if type_ == "endVc":
            starting_i = 3
            ending_i = starting_i + 2
        if type_ == "vc":
            starting_i = 6
            ending_i = starting_i + 1
        if type_ == "endcc":
            starting_i = 6
            ending_i = starting_i + 1
        if type_ == "rcv":
            starting_i = 0
            ending_i = starting_i + 1
        if type_ == "vv":
            starting_i = 6
            ending_i = starting_i + 3
        if type_ == "vvFr":
            starting_i = 7
            ending_i = starting_i + 3
        if type_ == "cc":
            starting_i = 6
            ending_i = starting_i + 1
        if type_ == "endccOe":
            starting_i = 10
            ending_i = starting_i + 4
        if type_ == "endcOe":
            starting_i = 12
            ending_i = starting_i + 2
        if type_ == "blank":
            starting_i = 2
            ending_i = starting_i
        if type_ == "cv":
            starting_i = 0
            ending_i = starting_i + 2
        # ---- TODO: CLEAN THIS ^^^^^^ //

        for i in range(starting_i, ending_i + 1):
            if "end" in type_:
                alias_format = alias + alias_formats[i]
            else:
                alias_format = alias_formats[i] + alias
            if self.has_oto(alias_format, tone):
                return alias_format

        return "no alias found"

    @staticmethod
    def _find_last_valid_alias(input_phonemes, word_phonemes):
        last_alias_index = 0
        for i in range(len(input_phonemes)):
            last_alias_index = 0
            for k in range(len(word_phonemes)):
                if f"{word_phonemes[k]}" not in input_phonemes[i]:
                    break
                last_alias_index += 1
        return last_alias_index

    def get_symbols(self, note):
        original = super().get_symbols(note)
        if original is None:
            return None

        arpabet = "aa,ai,ei,eu,ii,au,uu,an,un,uy,bb,dd,ff,gg,jj,kk,ll,mm,nn,pp,rr,ss,ch,tt,vv,ww,yy,zz".split(",")
        petitmot = "ah,ae,eh,ee,ih,oh,uh,en,in,ui,b,d,f,g,j,k,l,m,n,p,r,s,sh,t,v,w,y,z".split(",")

        convert = []
        for s in original:
            c = s
            for i in range(len(arpabet)):
                if s == arpabet[i]:
                    c = petitmot[i]
            convert.append(c)

        modified = []
        for s in convert:
            if s == "gn":
                modified.extend(["n", "y"])
            else:
                modified.append(s)
        return modified
