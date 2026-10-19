"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Plugin.Builtin/CantoneseSyoPhonemizer.cs"""

from ._pinyin import CanTone, Jyutping, cs_len, to_str_list
from .api import Phoneme, Phonemizer, alt_str, phonemizer
from .base_chinese import change_lyric, zip_change

# the consonant table.
CONSONANTS = "b,p,m,f,d,t,n,l,g,k,ng,h,gw,kw,w,z,c,s,j"
# the vowel split table.
VOWELS = ("aap=aa p,aat=aa t,aak=aa k,aam=aa m,aan=aa n,aang=aa ng,aai=aa i,aau=aa u,ap=a p,at=a t,ak=a k,am=a m,an=a n,ang=a ng,"
          "ai=a i,au=a u,op=o p,ot=o t,ok=o k,om=o m,on=o n,ong=o ng,oi=o i,ou=o u,oet=oe t,oek=oe k,oeng=oe ng,oei=oe i,eot=eo t,"
          "eon=eo n,eoi=eo i,ep=e p,et=e t,ek=e k,em=e m,en=e n,eng=e ng,ei=e i,eu=e u,up=u p,ut=u t,uk=uu k,um=um,un=u n,ung=uu ng,"
          "ui=u i,yut=yu t,yun=yu n,ip=i p,it=i t,ik=ii k,im=i m,in=i n,ing=ii ng,iu=i u")
# check for vowel substitutes.
SUBSTITUTION = [
    "aap,aat,aak,aam,aan,aang,aai,aau=aa", "ap,at,ak,am,an,ang,ai,au=a", "op,ot,ok,om,on,ong,oi,ou=o", "oet,oek,oen,oeng,oei=oe", "eot,eon,eoi=eo",
    "ep,et,ek,em,en,eng,ei,eu=e", "uk,ung=uu", "up,ut,um,un,ui=u", "yut,yun=yu", "ik,ing=ii", "ip,it,im,in,iu=i",
]
# check for substitutes for finals.
FINAL_SUB = ["ii ng=i ng", "ii k=i k", "uu k=u k", "uu ng=u ng", "oe t=eo t", "oe i=eo i"]


def _to_dictionary(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise ValueError(f"duplicate key {k}")  # ToDictionary throws on duplicates
        out[k] = v
    return out


C_SET = set(CONSONANTS.split(","))
V_DICT = _to_dictionary((a[0], a[1]) for a in (s.split("=") for s in VOWELS.split(",")))
SUBSTITUTE_LOOKUP = _to_dictionary((orig, line.split("=")[1]) for line in SUBSTITUTION for orig in line.split("=")[0].split(","))
FINAL_SUB_LOOKUP = _to_dictionary((orig, line.split("=")[1]) for line in FINAL_SUB for orig in line.split("=")[0].split(","))


class JyutpingConversion:
    """converts hanzi to jyutping, based on g2p."""

    @staticmethod
    def romanize(lyrics):
        lyrics_array = list(lyrics)
        inst = Jyutping.instance()
        hanzi_lyrics = [l for l in lyrics_array if inst.is_hanzi(l)]
        jyutping_result = to_str_list(inst.hanzi_to_pinyin(hanzi_lyrics, CanTone.NORMAL, 0))
        idx = 0
        for i in range(len(lyrics_array)):
            if cs_len(lyrics_array[i]) == 1 and inst.is_hanzi(lyrics_array[i]):
                lyrics_array[i] = jyutping_result[idx]
                idx += 1
        return lyrics_array

    @staticmethod
    def romanize_notes(groups):
        result_lyrics = JyutpingConversion.romanize(g[0].lyric for g in groups)
        zip_change(groups, result_lyrics, change_lyric)


def _ends_ptk(lyric):
    return lyric.endswith("p") or lyric.endswith("t") or lyric.endswith("k")


@phonemizer("Cantonese Syo-Style Phonemizer", "ZH-YUE SYO", language="ZH-YUE", openutau_class="OpenUtau.Plugin.Builtin.CantoneseSyoPhonemizer", author="Lotte V")
class CantoneseSyoPhonemizer(Phonemizer):
    def set_up(self, groups):
        super().set_up(groups)
        JyutpingConversion.romanize_notes(groups)

    def process(self, notes, prev, next, prev_neighbour, next_neighbour, prev_neighbours):
        # 1. remove consonant: "jyut" -> "yut". 2. lookup the trailing sound: "yut" -> "yu t".
        # 3. split the total duration and return "jyut"/"jyu" and "yu t".
        note = notes[0]
        lyric = note.lyric
        consonant = ""
        vowel = ""
        if len(lyric) > 2 and lyric[:2] in C_SET:
            consonant = lyric[:2]
            vowel = lyric[2:]
        elif len(lyric) > 1 and lyric[:1] in C_SET and lyric != "ng":
            consonant = lyric[:1]
            vowel = lyric[1:]
        else:
            vowel = lyric

        phoneme0 = lyric
        fin = f"{vowel} -"
        total_duration = sum(n.duration for n in notes)
        phoneme1 = V_DICT.get(vowel)
        if phoneme1:
            length1 = 120
            if length1 > total_duration // 2:
                length1 = total_duration // 2
            lyrics = [lyric]
            sub = SUBSTITUTE_LOOKUP.get(vowel or "")
            if sub is not None:
                lyrics.append(f"{consonant}{sub}" if consonant else sub)
            if prev_neighbour is None or _ends_ptk(prev_neighbour.lyric):
                initial = f"- {lyric}"
                if len(lyrics) < 2:
                    raise IndexError("Index was out of range.")  # lyrics[1]
                initial2 = f"- {lyrics[1]}"
                tests = [initial, initial2, lyric, lyrics[1]]
                o = self._check(tests, note)
                if o is not None:
                    phoneme0 = o.alias
            else:
                o = self._check(lyrics, note)
                if o is not None:
                    phoneme0 = o.alias

            length2 = 60
            if length2 > total_duration // 2:
                length2 = total_duration // 2
            if next_neighbour is None and self.singer.try_get_mapped_oto(fin, note.tone) is not None:
                o = self._check_final([fin], note)
                if o is not None:
                    phoneme1 = o.alias
                return [Phoneme(phoneme0), Phoneme(phoneme1, position=total_duration - length2)]
            else:
                tails = [phoneme1]
                fs = FINAL_SUB_LOOKUP.get(phoneme1 or "")
                if fs is not None:
                    tails.append(fs)
                o = self._check_final(tails, note)
                if o is not None:
                    phoneme1 = o.alias
                else:
                    return [Phoneme(phoneme0)]
            return [Phoneme(phoneme0), Phoneme(phoneme1, position=total_duration - length1)]

        # check for vowel ending on open syllables. if a vowel ending does not exist, it will not be inserted.
        if next_neighbour is None and not phoneme1 and fin:
            length1 = 60
            if length1 > total_duration // 2:
                length1 = total_duration // 2
            lyrics = [lyric]
            if prev_neighbour is None or _ends_ptk(prev_neighbour.lyric):
                o = self._check([f"- {lyric}", lyric], note)
                if o is not None:
                    phoneme0 = o.alias
            else:
                o = self._check(lyrics, note)
                if o is not None:
                    phoneme0 = o.alias
                else:
                    return [Phoneme(phoneme0)]
            o = self._check_final([fin], note)
            if o is not None:
                fin = o.alias
            else:
                return [Phoneme(phoneme0)]
            return [Phoneme(phoneme0), Phoneme(fin, position=total_duration - length1)]

        if prev_neighbour is None or _ends_ptk(prev_neighbour.lyric):
            o = self._check([f"- {lyric}", lyric], note)
            if o is not None:
                phoneme0 = o.alias
            else:
                return [Phoneme(phoneme0)]
        else:
            o = self._check([lyric], note)
            if o is not None:
                phoneme0 = o.alias
            else:
                return [Phoneme(phoneme0)]
        return [Phoneme(phoneme0)]

    def _otos(self, inputs, note, index):
        attr = note.attr(index)
        color = attr.voice_color if attr.voice_color is not None else self.get_parent_voice_color()
        shift = attr.tone_shift if attr.tone_shift is not None else self.get_parent_tone_shift()
        alt = attr.alternate if attr.alternate is not None else self.get_parent_alternate()
        otos = []
        for test in inputs:
            o = self.singer.try_get_mapped_oto(test + alt_str(alt), note.tone + shift, color)
            if o is None:
                o = self.singer.try_get_mapped_oto(test, note.tone + shift, color)
            if o is not None:
                otos.append(o)
        return otos, color

    def _check(self, inputs, note):
        otos, color = self._otos(inputs, note, 0)
        if otos:
            return next((o for o in otos if o.is_color_match(color)), otos[0])
        return None

    def _check_final(self, inputs, note):
        """final consonant or vowel ending: only a color match counts."""
        otos, color = self._otos(inputs, note, 1)
        if otos:
            return next((o for o in otos if o.is_color_match(color)), None)
        return None
