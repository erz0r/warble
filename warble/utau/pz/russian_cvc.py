"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Plugin.Builtin/RussianCVCPhonemizer.cs

russian cvc (Heiden.BZR): RussianG2p (the cmudict_ru.txt name is never read: LoadBaseDictionary is
overridden), "-CV" / "VC" / "VC-" aliases, timing from the oto.

the c# class declares private vowels/consonants/dictionaryReplacements fields that hide the base ones; the
port keeps them apart from the base fields too (the base dictionary_replacements stays empty, which is what
the base GetSymbols reads).
"""

from ...g2p import RussianG2p
from .api import phonemizer
from .syllable_based import SyllableBasedPhonemizer, cs_replace, last


def _to_dictionary(spec, sep, kv, drop_same=False):
    """spec.Split(sep).Select(e => e.Split(kv))[.Where(len == 2).Where(p0 != p1)].ToDictionary(p0, p1)."""
    out = {}
    for entry in spec.split(sep):
        parts = entry.split(kv)
        if drop_same:
            if len(parts) != 2 or parts[0] == parts[1]:
                continue
        if parts[0] in out:
            raise ValueError("An item with the same key has already been added.")
        out[parts[0]] = parts[1]  # IndexOutOfRange in c# for a part without '=' (none here)
    return out


@phonemizer("Russian CVC Phonemizer", "RU CVC", language="RU", openutau_class="OpenUtau.Plugin.Builtin.RussianCVCPhonemizer", author="Heiden.BZR")
class RussianCVCPhonemizer(SyllableBasedPhonemizer):
    no_gap = True  # Endings has 50 ticks gap

    def __init__(self):
        super().__init__()
        self._ru_vowels = "a,e,o,u,y,i,M,N".split(",")
        self._ru_consonants = "b',b,v',v,g',g,d',d,z',z,k',k,l',l,m',m,n',n,p',p,r',r,s',s,t',t,f',f,h',h,w',w,j,~,c,4',".split(",")
        self.aliases_fallback = _to_dictionary("ic=yc;y4'=i4';ij=yj;ic-=yc-;y4'-=i4'-;ij-=yj-", ";", "=")
        self.burst_consonants = "t,t',k,k',p,p',4',c,b,b',g,g',d,d'".split(",")
        self._ru_dictionary_replacements = _to_dictionary(
            "a=a;aa=a;ay=a;b=b;bb=b';c=c;ch=4';d=d;dd=d';ee=e;f=f;ff=f';"
            "g=g;gg=g';h=h;hh=h';i=i;ii=i;j=~;ja=a;je=e;jo=o;ju=u;k=k;kk=k';l=l;ll=l';m=m;mm=m';n=n;nn=n';oo=o;p=p;pp=p';r=r;rr=r';ae=e;"
            "s=s;sch=w';sh=w;ss=s';t=t;tt=t';u=u;uj=u;uu=u;v=v;vv=v';y=y;yy=y;z=z;zh=j;zz=z'", ";", "=", drop_same=True)
        self.hard_consonants = "b,v,g,d,z,k,l,m,n,p,r,s,t,f,h,w,c".split(",")
        self.short_consonants = "r,r'".split(",")
        self.long_consonants = "w,w',4',ts,t'".split(",")

    def get_vowels(self):
        return self._ru_vowels

    def get_consonants(self):
        return self._ru_consonants

    def get_dictionary_name(self):
        return "cmudict_ru.txt"

    def load_base_dictionary(self):
        return RussianG2p()

    def get_aliases_fallback(self):
        return self.aliases_fallback

    def get_dictionary_phonemes_replacement(self):
        return self._ru_dictionary_replacements

    def process_syllable(self, syllable):
        prev_v = syllable.prev_v
        cc = syllable.cc
        v = syllable.v

        phonemes = []
        if syllable.is_starting_v:
            base_phoneme = f"-{v}"
        elif syllable.is_vv:
            if not self.can_make_alias_extension(syllable):
                base_phoneme = v
            else:
                # the previous alias will be extended
                base_phoneme = None
        elif syllable.is_starting_cv:
            base_phoneme = f"-{last(cc)}{v}"
            for i in range(len(cc) - 1):
                phonemes.append(f"-{cc[i]}")
        else:  # VCV
            if len(cc) == 1 or self.is_short(syllable) or last(cc) == "`":
                base_phoneme = f"{last(cc)}{v}"
            else:
                base_phoneme = f"-{last(cc)}{v}"
            phonemes.append(f"{prev_v}{cc[0]}")
            offset = 0 if cc[0] in self.burst_consonants else 1
            for i in range(offset, len(cc) - 1):
                cr = f"{cc[i]}-"
                phonemes.append(cr if self.has_oto(cr, syllable.tone) else cc[i])
        phonemes.append(base_phoneme)
        return phonemes

    def process_ending(self, ending):
        cc = ending.cc
        v = ending.prev_v

        phonemes = []
        if ending.is_ending_v:
            phonemes.append(f"{v}-")
        else:
            phonemes.append(f"{v}{cc[0]}-")
            for i in range(1, len(cc)):
                cr = f"{cc[i]}-"
                phonemes.append(cr if self.has_oto(cr, ending.tone) else cc[i])
        return phonemes

    # russian specific replacements
    def validate_alias(self, alias, tone=0):
        if self.has_oto(alias, tone):
            return alias

        base_resolved = super().validate_alias(alias, tone)
        if base_resolved and base_resolved != alias:
            if self.has_oto(base_resolved, tone):
                return base_resolved
            alias = base_resolved
        for consonant in ["'", "~"]:
            alias = cs_replace(alias, consonant + "y", consonant + "i")
        for consonant in self.hard_consonants:
            alias = cs_replace(alias, consonant + "i", consonant + "y")
        return self.aliases_fallback[alias] if alias in self.aliases_fallback else alias

    def get_transition_basic_length_ms_with_attr(self, alias, tone, attr):
        oto_length = self.get_transition_basic_length_ms_by_oto(alias, tone, attr)
        return oto_length
