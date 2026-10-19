"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Plugin.Builtin/KoreanCVCPhonemizer.cs"""

from . import korean_phonemizer_util as ku
from .api import Phoneme, phonemizer, to_unicode_elements
from .base_korean_phonemizer import BaseKoreanPhonemizer, cdiv

naPlainVowels = ["a", "e", "a", "e", "eo", "e", "eo", "e", "o", "a", "e", "e", "o", "u", "eo", "e", "i", "u", "eu", "i", "i"]
naConsonants = ["ㄱ:g", "ㄲ:gg", "ㄴ:n", "ㄷ:d", "ㄸ:dd", "ㄹ:r", "ㅁ:m", "ㅂ:b", "ㅃ:bb", "ㅅ:s", "ㅆ:ss", "ㅇ:", "ㅈ:j", "ㅉ:jj", "ㅊ:ch", "ㅋ:k", "ㅌ:t", "ㅍ:p", "ㅎ:h"]
naVowels = ["ㅏ:a", "ㅐ:e", "ㅑ:ya", "ㅒ:ye", "ㅓ:eo", "ㅔ:e", "ㅕ:yeo", "ㅖ:ye", "ㅗ:o", "ㅘ:wa", "ㅙ:we", "ㅚ:we", "ㅛ:yo", "ㅜ:u", "ㅝ:weo", "ㅞ:we", "ㅟ:wi",
            "ㅠ:yu", "ㅡ:eu", "ㅢ:eui", "ㅣ:i"]
naFinals = [":", "ㄱ:k", "ㄲ:k", "ㄳ:k", "ㄴ:n", "ㄵ:n", "ㄶ:n", "ㄷ:t", "ㄹ:l", "ㄺ:k", "ㄻ:m", "ㄼ:l", "ㄽ:l", "ㄾ:l", "ㄿ:p", "ㅀ:l", "ㅁ:m", "ㅂ:p", "ㅄ:p", "ㅅ:t",
            "ㅆ:t", "ㅇ:ng", "ㅈ:t", "ㅊ:t", "ㅋ:k", "ㅌ:t", "ㅍ:p", "ㅎ:t"]
hangeulStartIndex = 0xAC00
hangeulEndIndex = 0xD7A3

plainVowels = ["eu", "eo", "a", "i", "u", "e", "o", "er"]
plainDiphthongs = ["ya", "yeo", "yo", "yu", "ye", "wa", "weo", "wi", "we", "eui"]

vowels = [
    "eu=geu,neu,deu,reu,leu,meu,beu,seu,eu,jeu,cheu,keu,teu,peu,heu,ggeu,ddeu,bbeu,sseu,jjeu,feu,veu,zeu,theu,rreu",
    "eo=geo,neo,deo,reo,leo,meo,beo,seo,eo,jeo,cheo,keo,teo,peo,heo,ggeo,ddeo,bbeo,sseo,jjeo,feo,veo,zeo,theo,rreo,gyeo,nyeo,dyeo,ryeo,lyeo,myeo,byeo,syeo,yeo,jyeo,chyeo,kyeo,tyeo,pyeo,hyeo,ggyeo,ddyeo,bbyeo,ssyeo,jjyeo,fyeo,vyeo,zyeo,thyeo,gweo,nweo,dweo,rweo,lweo,mweo,bweo,sweo,weo,jweo,chweo,kweo,tweo,pweo,hweo,ggweo,ddweo,bbweo,ssweo,jjweo,fweo,vweo,zweo,thweo",
    "a=ga,na,da,ra,la,ma,ba,sa,a,ja,cha,ka,ta,pa,ha,gga,dda,bba,ssa,jja,fa,va,za,tha,rra,gya,nya,dya,rya,lya,mya,bya,sya,ya,jya,chya,kya,tya,pya,hya,ggya,ddya,bbya,ssya,jjya,fya,vya,zya,thya,gwa,nwa,dwa,rwa,lwa,mwa,bwa,swa,wa,jwa,chwa,kwa,twa,pwa,hwa,ggwa,ddwa,bbwa,sswa,jjwa,fwa,vwa,zwa,thwa",
    "e=ge,ne,de,re,le,me,be,se,e,je,che,ke,te,pe,he,gge,dde,bbe,sse,jje,fe,ve,ze,the,rre,gye,nye,dye,rye,lye,mye,bye,sye,ye,jye,chye,kye,tye,pye,hye,ggye,ddye,bbye,ssye,jjye,fye,vye,zye,thye,gwe,nwe,dwe,rwe,lwe,mwe,bwe,swe,we,jwe,chwe,kwe,twe,pwe,hwe,ggwe,ddwe,bbwe,sswe,jjwe,fwe,vwe,zwe,thwe",
    "i=gi,ni,di,ri,li,mi,bi,si,i,ji,chi,ki,ti,pi,hi,ggi,ddi,bbi,ssi,jji,fi,vi,zi,thi,rri,gwi,nwi,dwi,rwi,lwi,mwi,bwi,swi,wi,jwi,chwi,kwi,twi,pwi,hwi,ggwi,ddwi,bbwi,sswi,jjwi,fwi,vwi,zwi,thwi",
    "o=go,no,do,ro,lo,mo,bo,so,o,jo,cho,ko,to,po,ho,ggo,ddo,bbo,sso,jjo,fo,vo,zo,tho,rro,gyo,nyo,dyo,ryo,lyo,myo,byo,syo,yo,jyo,chyo,kyo,tyo,pyo,hyo,ggyo,ddyo,bbyo,ssyo,jjyo,fyo,vyo,zyo,thyo",
    "u=gu,nu,du,ru,lu,mu,bu,su,u,ju,chu,ku,tu,pu,hu,ggu,ddu,bbu,ssu,jju,fu,vu,zu,thu,rru,gyu,nyu,dyu,ryu,lyu,myu,byu,syu,yu,jyu,chyu,kyu,tyu,pyu,hyu,ggyu,ddyu,bbyu,ssyu,jjyu,fyu,vyu,zyu,thyu",
    "ng=ang,ing,ung,eng,ong,eung,eong",
    "n=an,in,un,en,on,eun,eon",
    "m=am,im,um,em,om,eum,eom",
    "l=al,il,ul,el,ol,eul,eol",
    "p=ap,ip,up,ep,op,eup,eop",
    "t=at,it,ut,et,ot,eut,eot",
    "k=ak,ik,uk,ek,ok,euk,eok",
    "er=er",
]

consonants = [
    "gg=gg,gga,ggi,ggu,gge,ggo,ggeu,ggeo,ggya,ggyu,ggye,ggyo,ggyeo,ggwa,ggwi,ggwe,ggweo",
    "dd=dd,dda,ddi,ddu,dde,ddo,ddeu,ddeo,ddya,ddyu,ddye,ddyo,ddyeo,ddwa,ddwi,ddwe,ddweo",
    "bb=bb,bba,bbi,bbu,bbe,bbo,bbeu,bbeo,bbya,bbyu,bbye,bbyo,bbyeo,bbwa,bbwi,bbwe,bbweo",
    "ss=ss,ssa,ssi,ssu,sse,sso,sseu,sseo,ssya,ssyu,ssye,ssyo,ssyeo,sswa,sswi,sswe,ssweo",
    "f=f,fa,fi,fu,fe,fo,feu,feo,fya,fyu,fye,fyo,fyeo,fwa,fwi,fwe,fweo",
    "v=v,va,vi,vu,ve,vo,veu,veo,vya,vyu,vye,vyo,vyeo,vwa,vwi,vwe,vweo",
    "z=z,za,zi,zu,ze,zo,zeu,zeo,zya,zyu,zye,zyo,zyeo,zwa,zwi,zwe,zweo",
    "th=th,tha,thi,thu,the,tho,theu,theo,thya,thyu,thye,thyo,thyeo,thwa,thwi,thwe,thweo",
    "rr=rr,rra,rri,rru,rre,rro,rreu,rreo",
    "g=g,ga,gi,gu,ge,go,geu,geo,gya,gyu,gye,gyo,gyeo,gwa,gwi,gwe,gweo",
    "n=n,na,ni,nu,ne,no,neu,neo,nya,nyu,nye,nyo,nyeo,nwa,nwi,nwe,nweo",
    "d=d,da,di,du,de,do,deu,deo,dya,dyu,dye,dyo,dyeo,dwa,dwi,dwe,dweo",
    "r=r,ra,ri,ru,re,ro,reu,reo,rya,ryu,rye,ryo,ryeo,rwa,rwi,rwe,rweo",
    "m=m,ma,mi,mu,me,mo,meu,meo,mya,myu,mye,myo,myeo,mwa,mwi,mwe,mweo",
    "b=b,ba,bi,bu,be,bo,beu,beo,bya,byu,bye,byo,byeo,bwa,bwi,bwe,bweo",
    "s=s,sa,si,su,se,so,seu,seo,sya,syu,sye,syo,syeo,swa,swi,swe,sweo",
    "j=j,ja,ji,ju,je,jo,jeu,jeo,jya,jyu,jye,jyo,jyeo,jwa,jwi,jwe,jweo",
    "ch=ch,cha,chi,chu,che,cho,cheu,cheo,chya,chyu,chye,chyo,chyeo,chwa,chwi,chwe,chweo",
    "k=k,ka,ki,ku,ke,ko,keu,keo,kya,kyu,kye,kyo,kyeo,kwa,kwi,kwe,kweo",
    "t=t,ta,ti,tu,te,to,teu,teo,tya,tyu,tye,tyo,tyeo,twa,twi,twe,tweo",
    "p=p,pa,pi,pu,pe,po,peu,peo,pya,pyu,pye,pyo,pyeo,pwa,pwi,pwe,pweo",
    "h=h,ha,hi,hu,he,ho,heu,heo,hya,hyu,hye,hyo,hyeo,hwa,hwi,hwe,hweo",
]


def _lookup(lines):
    out = {}
    for line in lines:
        parts = line.split("=")
        for cv in parts[1].split(","):
            if cv in out:
                raise ValueError(f"duplicate key {cv}")  # ToDictionary throws on duplicates
            out[cv] = parts[0]
    return out


vowelLookup = _lookup(vowels)
consonantLookup = _lookup(consonants)

_ALPHA_CONS = ("gg", "dd", "bb", "ss", "f", "v", "z", "th", "rr", "g", "n", "d", "r", "m", "b", "s", "j", "ch", "k", "t", "p", "h")


def getConsonant(s):
    for c in "aiuewoy":
        s = s.replace(c, " ")
    return s.strip()


def isAlphaCon(s):
    return s in _ALPHA_CONS


def _ch(s, i):
    if s is None:
        raise TypeError("Object reference not set to an instance of an object.")
    if i >= len(s):
        raise IndexError("Index was outside the bounds of the array.")
    return s[i]


def _last(elems):
    return elems[-1] if elems else None


def _first(elems):
    return elems[0] if elems else None


@phonemizer("KoreanCVCPhonemizer", "KO CVC", language="KO", openutau_class="OpenUtau.Plugin.Builtin.KoreanCVCPhonemizer", author="NANA")
class KoreanCVCPhonemizer(BaseKoreanPhonemizer):
    def set_up(self, groups):
        # variate lyrics
        ku.romanize_notes(groups, False)

    def _shift_color(self, note):
        attr0 = note.attr(0)
        shift = attr0.tone_shift if attr0.tone_shift is not None else self.get_parent_tone_shift()
        color = attr0.voice_color if attr0.voice_color is not None else self.get_parent_voice_color()
        return note.tone + shift, color

    def check_oto_until_hit(self, tests, note):
        tone, color = self._shift_color(note)
        for test in tests:
            o = self.singer.try_get_mapped_oto(test, tone, color)
            if o is not None:
                return o
        return None

    def _mapped(self, alias, note):
        tone, color = self._shift_color(note)
        return self.singer.try_get_mapped_oto(alias, tone, color)

    def process(self, notes, prev, next, prev_neighbour, next_neighbour, prev_neighbours):
        note = notes[0]
        currentUnicode = to_unicode_elements(note.lyric)
        currentLyric = note.lyric
        totalDuration = sum(n.duration for n in notes)

        CLconsonant = CLvowel = CLfinal = 0
        TCLconsonant = TCLvowel = TCLfinal = TCLplainvowel = ""
        NLconsonant = NLvowel = NLfinal = 0
        TNLconsonant = TNLvowel = TNLfinal = TNLplainvowel = ""
        PLconsonant = PLvowel = PLfinal = 0
        TPLconsonant = TPLvowel = TPLfinal = TPLplainvowel = TPLplainfinal = ""
        currentHangeul = prevHangeul = nextHangeul = False
        prevExist = nextExist = False
        lCL = lPL = lNL = 0

        phoneticHint = self.render_phonetic_hint(self.singer, notes[0], totalDuration)
        if phoneticHint is not None:
            return phoneticHint

        firstCL = _ch(currentLyric, 0)
        if firstCL == "ㄹ":
            lCL = 1
            firstCL = _ch(currentLyric, 1)
        uCL = ord(firstCL)
        if hangeulStartIndex <= uCL <= hangeulEndIndex:
            currentHangeul = True
            CLconsonant = (uCL - hangeulStartIndex) // (21 * 28)
            CLvowel = (uCL - hangeulStartIndex) % (21 * 28) // 28
            CLfinal = (uCL - hangeulStartIndex) % 28
            TCLconsonant = naConsonants[CLconsonant].split(":")[1]
            TCLvowel = naVowels[CLvowel].split(":")[1]
            TCLplainvowel = naPlainVowels[CLvowel]
            TCLfinal = naFinals[CLfinal].split(":")[1]

        if prev_neighbour is not None:
            firstPL = _ch(prev_neighbour.lyric, 0)
            prevExist = True
            if firstPL == "ㄹ":
                lPL = 1
                firstPL = _ch(prev_neighbour.lyric, 1)
            uPL = ord(firstPL)
            if hangeulStartIndex <= uPL <= hangeulEndIndex:
                prevHangeul = True
                PLconsonant = (uPL - hangeulStartIndex) // (21 * 28)
                PLvowel = (uPL - hangeulStartIndex) % (21 * 28) // 28
                PLfinal = (uPL - hangeulStartIndex) % 28
                TPLconsonant = naConsonants[PLconsonant].split(":")[1]
                TPLvowel = naVowels[PLvowel].split(":")[1]
                TPLplainvowel = naPlainVowels[PLvowel]
                TPLfinal = naFinals[PLfinal].split(":")[1]
                TPLplainfinal = TPLfinal

        if next_neighbour is not None:
            firstNL = _ch(next_neighbour.lyric, 0)
            nextExist = True
            if firstNL == "ㄹ":
                lNL = 1
                firstNL = _ch(next_neighbour.lyric, 1)
            uNL = ord(firstNL)
            if hangeulStartIndex <= uNL <= hangeulEndIndex:
                nextHangeul = True
                NLconsonant = (uNL - hangeulStartIndex) // (21 * 28)
                NLvowel = (uNL - hangeulStartIndex) % (21 * 28) // 28
                NLfinal = (uNL - hangeulStartIndex) % 28
                TNLconsonant = naConsonants[NLconsonant].split(":")[1]
                TNLvowel = naVowels[NLvowel].split(":")[1]
                TNLplainvowel = naPlainVowels[NLvowel]
                TNLfinal = naFinals[NLfinal].split(":")[1]

        def con(i):
            return naConsonants[i].split(":")[1]

        if currentHangeul:
            # 1. 연음법칙
            tempTCLconsonant = ""
            tempTCLfinal = ""
            yeoneum = False
            yeoneum2 = False

            if prevExist and prevHangeul and CLconsonant == 11 and TPLfinal != "":
                temp = PLfinal
                m = {1: 0, 2: 1, 3: 10, 4: 2, 5: 12, 6: 18, 7: 3, 8: 5, 9: 0, 10: 6, 11: 7, 12: 9, 13: 16, 14: 17, 15: 18, 16: 6, 17: 7, 18: 9, 19: 9,
                     20: 10, 22: 12, 23: 14, 24: 15, 25: 16, 26: 17, 27: 18}
                if temp in m:
                    tempTCLconsonant = con(m[temp])
                    yeoneum = True
                elif temp == 21:
                    tempTCLconsonant = ""
                    yeoneum = True

            if nextExist and nextHangeul and TCLfinal != "" and TNLconsonant == "":
                temp = CLfinal
                moved = {1: 0, 2: 1, 4: 2, 7: 3, 8: 5, 16: 6, 17: 7, 19: 9, 20: 10, 22: 12, 23: 14, 24: 15, 25: 16, 26: 17, 27: 18}
                kept = {3: "k", 5: "n", 6: "n", 9: "l", 10: "l", 11: "l", 12: "l", 13: "l", 14: "l", 15: "l", 18: "p"}
                if temp in moved:
                    tempTCLfinal = con(moved[temp])
                    TCLfinal = ""
                    yeoneum2 = True
                elif temp in kept:
                    TCLfinal = kept[temp]
                    yeoneum2 = True
            if yeoneum:
                TCLconsonant = tempTCLconsonant
            if yeoneum2:
                TNLconsonant = tempTCLfinal

            # 2. 격음화/유기음화/거센소리되기
            if prevExist and prevHangeul and TPLfinal != "":
                if PLfinal in (27, 6, 15):
                    if CLconsonant == 0:
                        TCLconsonant = "k"
                    elif CLconsonant == 3:
                        TCLconsonant = "t"
                    elif CLconsonant == 12:
                        TCLconsonant = "ch"
                    elif CLconsonant == 9:
                        TCLconsonant = "ss"
                if PLfinal == 1 and CLconsonant == 18:
                    TCLconsonant = "k"
                elif PLfinal == 7 and CLconsonant == 18:
                    TCLconsonant = "t"
                elif PLfinal == 17 and CLconsonant == 18:
                    TCLconsonant = "p"
                elif PLfinal == 22 and CLconsonant == 18:
                    TCLconsonant = "ch"
            if nextExist and nextHangeul and TCLfinal != "":
                asp = {0: "k", 3: "t", 12: "ch", 9: "ss"}
                if NLconsonant in asp and CLfinal in (27, 6, 15):
                    TCLfinal = {27: "", 6: "n", 15: "l"}[CLfinal]
                    TNLconsonant = asp[NLconsonant]

                if NLconsonant == 2 and CLfinal == 27:
                    TCLfinal = "n"

                if NLconsonant == 18 and CLfinal == 1:
                    TCLfinal = ""
                    TNLconsonant = "k"
                elif NLconsonant == 18 and CLfinal == 7:
                    TCLfinal = ""
                    TNLconsonant = "t"
                elif NLconsonant == 18 and CLfinal == 17:
                    TCLfinal = ""
                    TNLconsonant = "p"
                elif NLconsonant == 18 and CLfinal == 22:
                    TCLfinal = ""
                    TNLconsonant = "ch"

            # 3. 음절의 끝소리 규칙 예외
            if nextExist and nextHangeul:
                if CLfinal == 9 and NLconsonant == 0:
                    TCLfinal = "l"

            # 4. 경음화/된소리되기
            if prevExist and prevHangeul and TPLfinal != "":
                if TPLfinal in ("k", "t", "p"):
                    fort = {0: "gg", 3: "dd", 7: "bb", 9: "ss", 12: "jj"}
                    if CLconsonant in fort:
                        TCLconsonant = fort[CLconsonant]
                if PLfinal == 8 and CLconsonant == 3:
                    TCLconsonant = "dd"
                elif PLfinal == 8 and CLconsonant == 9:
                    TCLconsonant = "ss"
                elif PLfinal == 8 and CLconsonant == 12:
                    TCLconsonant = "jj"
                if PLfinal in (11, 13):
                    fort = {0: "gg", 3: "dd", 9: "ss", 12: "jj"}
                    if CLconsonant in fort:
                        TCLconsonant = fort[CLconsonant]

            # 5. 구개음화
            if prevExist and prevHangeul and TPLfinal != "":
                if PLfinal == 7 and CLconsonant == 11 and CLvowel == 20:
                    TCLconsonant = "j"
                elif PLfinal == 25 and CLconsonant == 11 and CLvowel == 20:
                    TCLconsonant = "ch"
                elif PLfinal == 13 and CLconsonant == 11 and CLvowel == 20:
                    TCLconsonant = "ch"
                elif PLfinal == 7 and CLconsonant == 18 and CLvowel == 20:
                    TCLconsonant = "ch"
            if nextExist and nextHangeul and TCLfinal != "":
                if (CLfinal == 7 and NLconsonant == 11 and NLvowel == 20) or (CLfinal == 25 and NLconsonant == 11 and NLvowel == 20) \
                        or (CLfinal == 13 and NLconsonant == 11 and NLvowel == 20) or (CLfinal == 7 and NLconsonant == 18 and NLvowel == 20):
                    TCLfinal = ""

            # 6. 비음화
            if prevExist and prevHangeul and TPLfinal != "":
                if TPLfinal in ("m", "ng") and CLconsonant == 5:
                    TCLconsonant = "n"
                if TPLfinal in ("k", "t", "p") and CLconsonant == 5:
                    TCLconsonant = "n"
            if nextExist and nextHangeul and TCLfinal != "":
                if TCLfinal == "k" and TNLconsonant in ("n", "m"):
                    TCLfinal = "ng"
                elif TCLfinal == "t" and TNLconsonant in ("n", "m"):
                    TCLfinal = "n"
                elif TCLfinal == "p" and TNLconsonant in ("n", "m"):
                    TCLfinal = "m"
                if TCLfinal == "k" and NLconsonant == 5:
                    TCLfinal = "ng"
                elif TCLfinal == "t" and NLconsonant == 5:
                    TCLfinal = "n"
                elif TCLfinal == "p" and NLconsonant == 5:
                    TCLfinal = "m"

            # 7. 유음화
            if prevExist and prevHangeul and TPLfinal != "":
                if PLfinal in (8, 13, 15) and TCLconsonant == "n":
                    TCLconsonant = "r"
            if nextExist and nextHangeul and TCLfinal != "":
                if TCLfinal == "n" and TNLconsonant == "r":
                    TCLfinal = "l"

            # 8. 받침 + ㄹ = ㄹㄹ
            if prevExist and prevHangeul and TPLfinal != "":
                lCL = 1

            CV = TCLconsonant + TCLvowel
            VC = ""
            if nextExist and TCLfinal == "" and nextHangeul and TNLconsonant == "gg":
                VC = TCLplainvowel + "k"
            elif nextExist and TCLfinal == "" and nextHangeul and TNLconsonant in ("dd", "jj"):
                VC = TCLplainvowel + "t"
            elif nextExist and TCLfinal == "" and nextHangeul and TNLconsonant == "bb":
                VC = TCLplainvowel + "p"
            elif nextExist and TCLfinal == "" and nextHangeul:
                VC = TCLplainvowel + " " + TNLconsonant

            FC = ""
            if TCLfinal != "":
                FC = TCLplainvowel + TCLfinal

            if lCL == 1:
                CV = CV.replace("r", "l")

            if not prevExist and TCLconsonant == "r":
                oto = self.check_oto_until_hit([f"- {CV}", f"l{TCLvowel}", CV, currentLyric], note)
                if oto is not None:
                    CV = oto.alias
            elif not prevExist and TCLconsonant != "r":
                oto = self.check_oto_until_hit([f"- {CV}", CV, currentLyric], note)
                if oto is not None:
                    CV = oto.alias

            if prevExist and TCLconsonant == "" and TPLfinal == "":
                oto = self.check_oto_until_hit([f"{TPLplainvowel} {CV}", CV, currentLyric], note)
                if oto is not None:
                    CV = oto.alias

            if prevExist and TCLconsonant == "" and TPLfinal == "ng":
                oto = self.check_oto_until_hit([f"ng{CV}", CV, currentLyric], note)
                if oto is not None:
                    CV = oto.alias

            if prev_neighbour is not None and prevExist and not prevHangeul and TCLconsonant == "":
                prevUnicode = to_unicode_elements(prev_neighbour.lyric)
                prevLyric = "".join(prevUnicode)
                vow = vowelLookup.get(_last(prevUnicode) or "")
                if vow is not None:
                    mixVV = f"{vow} {CV}"
                    if prevLyric.endswith("eo"):
                        mixVV = f"eo {CV}"
                    elif prevLyric.endswith("eu"):
                        mixVV = f"eu {CV}"
                    elif prevLyric.endswith("er"):
                        mixVV = f"er {CV}"
                    oto = self.check_oto_until_hit([mixVV, CV, currentLyric], note)
                    if oto is not None:
                        CV = oto.alias

            if next_neighbour is not None:
                nextUnicode = to_unicode_elements(next_neighbour.lyric)
                nextLyric = "".join(nextUnicode)
                consonant = ""
                c = consonantLookup.get(_first(nextUnicode) or "")
                if c is not None:
                    consonant = getConsonant(next_neighbour.lyric)
                    if nextLyric.startswith("gg"):
                        consonant = "k"
                    elif nextLyric.startswith("dd"):
                        consonant = "t"
                    elif nextLyric.startswith("bb"):
                        consonant = "p"
                    elif nextLyric.startswith("jj"):
                        consonant = "t"
                    elif not isAlphaCon(consonant):
                        consonant = c
                elif nextExist and nextHangeul:
                    consonant = TNLconsonant
                elif nextLyric.startswith("ch"):
                    consonant = "ch"
                elif nextLyric.startswith("l"):
                    consonant = "l"

                if not nextHangeul and (nextLyric.startswith("gg") or nextLyric.startswith("dd") or nextLyric.startswith("bb") or nextLyric.startswith("jj")
                                        or nextLyric.startswith("l")):
                    VC = TCLplainvowel + consonant
                elif not nextHangeul:
                    VC = TCLplainvowel + " " + consonant

            # 만약 받침이 있다면
            if FC != "":
                fcLength = cdiv(totalDuration, 3)
                if TCLfinal in ("k", "p", "t"):
                    fcLength = cdiv(totalDuration, 2)
                oto1 = self._mapped(CV, note)
                oto2 = self._mapped(FC, note) if oto1 is not None else None
                if oto1 is not None and oto2 is not None:
                    return [Phoneme(oto1.alias), Phoneme(oto2.alias, position=totalDuration - fcLength)]

            # 만약 받침이 없다면
            if TCLfinal == "":
                if nextExist:
                    if _ch(next_neighbour.lyric, 0) == "ㄹ":
                        VC = TCLplainvowel + "l"
                if VC != "" and TNLconsonant != "":
                    vcLength = 60
                    if TNLconsonant in ("r", "h"):
                        vcLength = 30
                    elif TNLconsonant == "s":
                        vcLength = cdiv(totalDuration, 3)
                    elif TNLconsonant in ("k", "t", "p", "ch"):
                        vcLength = cdiv(totalDuration, 2)
                    elif TNLconsonant in ("gg", "dd", "bb", "ss", "jj"):
                        vcLength = cdiv(totalDuration, 2)
                    vcLength = min(cdiv(totalDuration, 2), vcLength)
                    oto1 = self._mapped(CV, note)
                    oto2 = self._mapped(VC, note) if oto1 is not None else None
                    if oto1 is not None and oto2 is not None:
                        return [Phoneme(oto1.alias), Phoneme(oto2.alias, position=totalDuration - vcLength)]
                elif VC != "" and TNLconsonant == "":
                    vcLength = 60
                    nextAttr = next_neighbour.attr(0)
                    nextLyric = "".join(to_unicode_elements(next_neighbour.lyric))
                    shift = nextAttr.tone_shift if nextAttr.tone_shift is not None else self.get_parent_tone_shift()
                    color = nextAttr.voice_color if nextAttr.voice_color is not None else self.get_parent_voice_color()
                    oto0 = self.singer.try_get_mapped_oto(nextLyric, next_neighbour.tone + shift, color)
                    if oto0 is not None:
                        vcLength = self.ms_to_tick(oto0.preutter)
                    vcLength = min(cdiv(totalDuration, 2), vcLength)
                    oto1 = self._mapped(CV, note)
                    oto2 = self._mapped(VC, note) if oto1 is not None else None
                    if oto1 is not None and oto2 is not None:
                        return [Phoneme(oto1.alias), Phoneme(oto2.alias, position=totalDuration - vcLength)]
                # 그 외(받침 없는 마지막 노트)
                oto = self._mapped(CV, note)
                if oto is not None:
                    return [Phoneme(oto.alias)]

        if prevHangeul:
            endBreath = "R"
            if prevExist and TPLfinal == "" and currentLyric in endBreath:
                endBreath = f"{TPLplainvowel} R"
            elif prevExist and TPLfinal != "" and currentLyric in endBreath:
                endBreath = f"{TPLplainfinal} R"
            oto = self._mapped(endBreath, note)
            if oto is not None:
                return [Phoneme(oto.alias)]

        # ======================================================================================

        if prev_neighbour is None:
            oto = self.check_oto_until_hit([f"- {currentLyric}", currentLyric], note)
            if oto is not None:
                currentLyric = oto.alias
        elif currentLyric in plainVowels or currentLyric in plainDiphthongs:
            prevUnicode = to_unicode_elements(prev_neighbour.lyric)
            prevLyric = "".join(prevUnicode)
            vow = vowelLookup.get(_last(prevUnicode) or "")
            if vow is not None:
                vowLyric = f"{vow} {currentLyric}"
                if prevLyric.endswith("eo"):
                    vowLyric = f"eo {currentLyric}"
                elif prevLyric.endswith("eu"):
                    vowLyric = f"eu {currentLyric}"
                elif prevLyric.endswith("er"):
                    vowLyric = f"er {currentLyric}"
                oto = self.check_oto_until_hit([vowLyric, currentLyric], note)
                if oto is not None:
                    currentLyric = oto.alias
            elif prevExist and prevHangeul and TPLfinal == "":
                oto = self.check_oto_until_hit([f"{TPLplainvowel} {currentLyric}", currentLyric], note)
                if oto is not None:
                    currentLyric = oto.alias
            elif prevExist and prevHangeul and TPLfinal == "ng":
                oto = self.check_oto_until_hit([f"ng{currentLyric}", currentLyric], note)
                if oto is not None:
                    currentLyric = oto.alias
            else:
                oto = self.check_oto_until_hit([currentLyric], note)
                if oto is not None:
                    currentLyric = oto.alias
        elif currentLyric in "R":
            prevUnicode = to_unicode_elements(prev_neighbour.lyric)
            prevLyric = "".join(prevUnicode)
            vow = vowelLookup.get(_last(prevUnicode) or "")
            if vow is not None:
                endBreath = f"{vow} R"
                if prevLyric.endswith("eo"):
                    endBreath = "eo R"
                elif prevLyric.endswith("eu"):
                    endBreath = "eu R"
                elif prevLyric.endswith("er"):
                    endBreath = "er R"
                oto = self.check_oto_until_hit([endBreath, currentLyric], note)
                if oto is not None:
                    currentLyric = oto.alias
            else:
                last = _last(prevUnicode)
                endBreath = f"{'' if last is None else last} R"
                if prevLyric.endswith("ng"):
                    endBreath = "ng R"
                oto = self.check_oto_until_hit([endBreath, currentLyric], note)
                if oto is not None:
                    currentLyric = oto.alias
        else:
            oto = self.check_oto_until_hit([currentLyric], note)
            if oto is not None:
                currentLyric = oto.alias

        if next_neighbour is not None:
            nextUnicode = to_unicode_elements(next_neighbour.lyric)
            nextLyric = "".join(nextUnicode)

            if (_first(nextUnicode) or "") in plainVowels:
                return [Phoneme(currentLyric)]

            vowel = ""
            vow = vowelLookup.get(_last(currentUnicode) or "")
            if vow is not None:
                vowel = vow
                if "e" in currentLyric and "eui" not in currentLyric:
                    vowel = "e" + vowel
                    vowel = vowel.replace("ee", "e")

            consonant = ""
            c = consonantLookup.get(_first(nextUnicode) or "")
            if c is not None:
                consonant = getConsonant(next_neighbour.lyric)
                if nextLyric.startswith("jj"):
                    consonant = "t"
                if not isAlphaCon(consonant):
                    consonant = c
            elif nextLyric.startswith("gg"):
                consonant = "k"
            elif nextLyric.startswith("dd"):
                consonant = "t"
            elif nextLyric.startswith("bb"):
                consonant = "p"
            elif nextLyric.startswith("l"):
                consonant = "l"
            elif nextExist and nextHangeul:
                consonant = TNLconsonant
                if TNLconsonant == "gg":
                    consonant = "k"
                elif TNLconsonant in ("dd", "jj"):
                    consonant = "t"
                elif TNLconsonant == "bb":
                    consonant = "p"
                elif nextLyric.startswith("ㄹ"):
                    consonant = "l"
                else:
                    consonant = TNLconsonant
            elif nextLyric.startswith("ch"):
                consonant = "ch"

            if consonant == "":
                return [Phoneme(currentLyric)]

            if TNLconsonant in ("gg", "dd", "bb", "jj") or nextLyric.startswith("ㄹ"):
                vcPhoneme = f"{vowel}{consonant}"
            elif nextLyric.startswith("gg") or nextLyric.startswith("dd") or nextLyric.startswith("bb") or nextLyric.startswith("jj") or nextLyric.startswith("l"):
                vcPhoneme = f"{vowel}{consonant}"
            else:
                vcPhoneme = f"{vowel} {consonant}"
            oto1 = self.check_oto_until_hit([vcPhoneme, ""], note)
            if oto1 is not None:
                vcPhoneme = oto1.alias
            else:
                return [Phoneme(currentLyric)]

            vcLength = 60
            nextAttr = next_neighbour.attr(0)
            shift = nextAttr.tone_shift if nextAttr.tone_shift is not None else self.get_parent_tone_shift()
            color = nextAttr.voice_color if nextAttr.voice_color is not None else self.get_parent_voice_color()
            oto = self.singer.try_get_mapped_oto(nextLyric, next_neighbour.tone + shift, color)
            if oto is not None:
                vcLength = self.ms_to_tick(oto.preutter)
            elif TNLconsonant in ("r", "h"):
                vcLength = 30
            elif TNLconsonant == "s":
                vcLength = cdiv(totalDuration, 3)
            elif TNLconsonant in ("k", "t", "p", "ch"):
                vcLength = cdiv(totalDuration, 2)
            elif TNLconsonant in ("gg", "dd", "bb", "ss", "jj"):
                vcLength = cdiv(totalDuration, 2)
            vcLength = min(cdiv(totalDuration, 2), vcLength)
            return [Phoneme(currentLyric), Phoneme(vcPhoneme, position=totalDuration - vcLength)]

        return [Phoneme(currentLyric)]
