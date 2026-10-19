"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Plugin.Builtin/FrenchVCCVPhonemizer.cs

french vccv for m2RUg style banks (mim). like the french cvvc phonemizer its dictionary is the legacy
cmudict_fr.txt from openutau's Dictionaries folder, which a fresh install doesn't have, so in practice only
phonetic hints (and tails) give symbols. arpabet-like hint symbols (aa, ch, gn, ...) are converted to m2RUg.
"""

from .api import phonemizer
from .french_cvvc import _pairs
from .syllable_based import SyllableBasedPhonemizer, last


@phonemizer("French VCCV m2RUg Phonemizer", "FR VCCV", language="FR", openutau_class="OpenUtau.Plugin.Builtin.FrenchVCCVPhonemizer", author="Mim")
class FrenchVCCVPhonemizer(SyllableBasedPhonemizer):
    no_gap = True  # Endings has 50 ticks gap

    def __init__(self):
        super().__init__()
        self._fr_vowels = "A,E,e,2,9,i,o,O,u,y,a,U,0,A',E',e',2',9',i',o',O',u',y',a',U',0'".split(",")
        self._fr_consonants = "b,d,f,g,Z,k,l,m,n,p,R,s,S,t,v,w,j,z,J,H,h,4,r,_hh".split(",")
        self._fr_dictionary_replacements = _pairs(
            "aa=A;ai=E;ei=e;eu=2;ee=2;oe=9;ii=i;au=o;oo=O;ou=u;uu=y;an=a;in=U;un=U;on=0;uy=H;"
            "bb=b;dd=d;ff=f;gg=g;jj=Z;kk=k;ll=l;mm=m;nn=n;pp=p;rr=R;ss=s;ch=S;tt=t;vv=v;ww=w;yy=j;zz=z;gn=J;4=4;hh=h;")
        self.short_consonants = "R".split(",")
        self.long_consonants = "t,k,g,p,s,S,Z".split(",")
        self.hard_consonants = "t,k,g,p,d,b".split(",")

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

        # add vocal fry support
        if "'" in prev_v:
            prev_v = prev_v.replace("'", "")

        # --------------------------- STARTING V ------------------------------- //
        if syllable.is_starting_v:
            base_phoneme = f"- {v}"

        elif syllable.is_vv:  # if VV
            # (the c# has the alias extension commented out)
            base_phoneme = f"{prev_v} {v}"

        # --------------------------- STARTING CV ------------------------------- //
        elif syllable.is_starting_cv_with_one_consonant:
            base_phoneme = f"- {cc[0]}{v}"
            if not self.has_oto(base_phoneme, syllable.tone):
                self.try_add_phoneme(phonemes, syllable.tone, f"- {cc[0]}")
                base_phoneme = f"{cc[0]}{v}"

        # --------------------------- STARTING CCV ------------------------------- //
        elif syllable.is_starting_cv_with_more_than_one_consonant:
            if cc[0] not in self.hard_consonants:
                phonemes.append(f"- {cc[0]}")

            base_phoneme = f"{last(cc)}{v}"

            # CC + CCV support
            ccv = f"{cc[len(cc) - 2]}{last(cc)}{v}"
            if self.has_oto(ccv, syllable.tone):
                base_phoneme = ccv

                for i in range(len(cc) - 2):
                    cci = f"{cc[i]} {cc[i + 1]}"

                    if i == 0:
                        cci = f"- {cc[i]}{cc[i + 1]}_"
                    if not self.has_oto(cci, syllable.tone):
                        cci = f"{cc[i]}{cc[i + 1]}_"
                        if i + 1 == len(cc) - 2 and self.has_oto(f"_{ccv}", syllable.tone):
                            base_phoneme = f"_{ccv}"

                    self.try_add_phoneme(phonemes, syllable.tone, cci)
            else:
                # CC + CV support
                for i in range(len(cc) - 1):
                    cci = f"{cc[i]}{cc[i + 1]}_"

                    if i == 0:
                        cci = f"- {cc[i]}{cc[i + 1]}_"
                        if not self.has_oto(cci, syllable.tone):
                            cci = f"{cc[i]}{cc[i + 1]}_"

                    if self.has_oto(cci, syllable.tone):
                        phonemes.append(cci)
                        if i + 1 == len(cc) - 1 and self.has_oto(f"_{last(cc)}{v}", syllable.tone):
                            base_phoneme = f"_{last(cc)}{v}"
                    else:
                        cci = f"{cc[i]} {cc[i + 1]}"
                        self.try_add_phoneme(phonemes, syllable.tone, cci)

        # --------------------------- IS VCV ------------------------------- //
        elif syllable.is_vcv_with_one_consonant:
            # try VCV
            vc = f"{prev_v} {cc[0]}"
            phonemes.append(vc)

            base_phoneme = f"{cc[0]}{v}"

        else:
            # ------------- IS VCV WITH MORE THAN ONE CONSONANT --------------- //
            vc = f"{prev_v} {cc[0]}"
            phonemes.append(vc)

            base_phoneme = f"{last(cc)}{v}"

            # CC + CCV support
            ccv = f"{cc[len(cc) - 2]}{last(cc)}{v}"
            if self.has_oto(ccv, syllable.tone):
                base_phoneme = ccv

                for i in range(len(cc) - 2):
                    cci = f"{cc[i]} {cc[i + 1]}"

                    if not self.has_oto(cci, syllable.tone):
                        cci = f"{cc[i]}{cc[i + 1]}_"
                        if i + 1 == len(cc) - 2 and self.has_oto(f"_{ccv}", syllable.tone):
                            base_phoneme = f"_{ccv}"

                    self.try_add_phoneme(phonemes, syllable.tone, cci)
            else:
                # CC + CV support
                for i in range(len(cc) - 1):
                    cci = f"{cc[i]}{cc[i + 1]}_"

                    if self.has_oto(cci, syllable.tone):
                        phonemes.append(cci)
                        if i + 1 == len(cc) - 1 and self.has_oto(f"_{last(cc)}{v}", syllable.tone):
                            base_phoneme = f"_{last(cc)}{v}"
                    else:
                        cci = f"{cc[i]} {cc[i + 1]}"
                        if not self.has_oto(cci, syllable.tone):
                            cci = f"{cc[i]}{cc[i + 1]}"
                        self.try_add_phoneme(phonemes, syllable.tone, cci)

            # convert 'n + j' to 'J'
            if f"{last(cc)}" == "j" and f"{cc[len(cc) - 2]}" == "n":
                base_phoneme = f"J{v}"

        phonemes.append(base_phoneme)
        return phonemes

    def process_ending(self, ending):
        cc = ending.cc
        v = ending.prev_v

        phonemes = []

        # --------------------------- ENDING V ------------------------------- //
        if ending.is_ending_v:
            phonemes.append(f"{v} -")
        else:
            # --------------------------- ENDING VC ------------------------------- //
            if ending.is_ending_vc_with_one_consonant:
                # try 'VC -' else 'V C' + 'C -'
                vc = f"{v}{cc[0]} -"
                if self.has_oto(vc, ending.tone):
                    phonemes.append(vc)
                else:
                    vc = f"{v} {cc[0]}"
                    phonemes.append(vc)
                    phonemes.append(f"{cc[0]} -")
            else:
                # --------------------------- ENDING VCC ------------------------------- //
                vc = f"{v} {cc[0]}"
                phonemes.append(vc)
                has_ending = False

                for i in range(len(cc) - 1):
                    cci = f"{cc[i]} {cc[i + 1]}"

                    if i == len(cc) - 2:
                        cci = f"{cc[i]}{cc[i + 1]} -"
                        has_ending = True
                    if not self.has_oto(cci, ending.tone):
                        cci = f"{cc[i]}{cc[i + 1]}_"
                        has_ending = False
                    if not self.has_oto(cci, ending.tone):
                        cci = f"{cc[i]}{cc[i + 1]}"
                        has_ending = False

                    self.try_add_phoneme(phonemes, ending.tone, cci)

                if not has_ending:
                    self.try_add_phoneme(phonemes, ending.tone, f"{last(cc)} -")

        return phonemes

    def get_transition_basic_length_ms_with_attr(self, alias, tone, attr):
        oto_length = self.get_transition_basic_length_ms_by_oto(alias, tone, attr)
        return oto_length

    def get_symbols(self, note):
        original = super().get_symbols(note)
        if original is None:
            return None

        arpabet = "aa,ai,ei,eu,ee,oe,ii,au,oo,ou,uu,an,in,un,on,uy,bb,dd,ff,gg,jj,kk,ll,mm,nn,pp,rr,ss,ch,tt,vv,ww,yy,zz,gn".split(",")
        m2rug = "A,E,e,2,2,9,i,o,O,u,y,a,U,U,0,H,b,d,f,g,Z,k,l,m,n,p,R,s,S,t,v,w,j,z,J".split(",")

        convert = []
        for s in original:
            c = s
            for i in range(len(arpabet)):
                if s == arpabet[i]:
                    c = m2rug[i]
            convert.append(c)
        return convert
