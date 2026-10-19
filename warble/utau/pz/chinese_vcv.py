"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Plugin.Builtin/ChineseVCVPhonemizer.cs"""

import unicodedata

from .api import Phoneme, Phonemizer, phonemizer
from .base_chinese import romanize_notes

# pinyin -> tail final. format: tail=pinyin1,pinyin2,...
TAIL_MAP = [
    "a=a,ba,pa,ma,fa,da,ta,na,la,ga,ka,ha,zha,cha,sha,za,ca,sa,ya,lia,jia,qia,xia,wa,gua,kua,hua,zhua,shua,dia",
    "ang=ang,bang,pang,mang,fang,dang,tang,nang,lang,gang,kang,hang,zhang,chang,shang,rang,zang,cang,sang,yang,liang,jiang,qiang,xiang,wang,guang,kuang,huang,zhuang,chuang,shuang,niang",
    "ao=ao,bao,pao,mao,dao,tao,nao,lao,gao,kao,hao,zhao,chao,shao,rao,zao,cao,sao,yao,biao,piao,miao,diao,tiao,niao,liao,jiao,qiao,xiao",
    "ai=ai,bai,pai,mai,dai,tai,nai,lai,gai,kai,hai,zhai,chai,shai,zai,cai,sai,wai,guai,kuai,huai,zhuai,chuai,shuai",
    "an=an,ban,pan,man,fan,dan,tan,nan,lan,gan,kan,han,zhan,chan,shan,ran,zan,can,san,wan,duan,tuan,nuan,luan,guan,kuan,huan,zhuan,chuan,shuan,ruan,zuan,cuan,suan",
    "o=o,bo,po,mo,fo,wo,duo,tuo,nuo,luo,guo,kuo,huo,zhuo,chuo,shuo,ruo,zuo,cuo,suo",
    "ong=ong,dong,tong,nong,long,gong,kong,hong,zhong,chong,rong,zong,cong,song,yong,jiong,qiong,xiong",
    "ou=ou,pou,mou,fou,dou,tou,lou,gou,kou,hou,zhou,chou,shou,rou,zou,cou,sou,you,miu,diu,niu,liu,jiu,qiu,xiu",
    "e=e,me,de,te,ne,le,ge,ke,he,zhe,che,she,re,ze,ce,se",
    "en=en,ben,pen,men,fen,nen,gen,ken,hen,zhen,chen,shen,ren,zen,cen,sen,wen,dun,tun,lun,gun,kun,hun,zhun,chun,shun,run,zun,cun,sun",
    "eng=eng,beng,peng,meng,feng,deng,teng,neng,leng,geng,keng,heng,weng,zheng,cheng,sheng,reng,zeng,ceng,seng",
    "ei=ei,bei,pei,mei,fei,dei,tei,nei,lei,gei,kei,hei,zhei,shei,zei,wei,dui,tui,gui,kui,hui,zhui,chui,shui,rui,zui,cui,sui",
    "ie=ye,bie,pie,mie,die,tie,nie,lie,jie,qie,xie",
    "ue=yue,nue,lue,jue,que,xue",
    "u=u,bu,pu,mu,fu,du,tu,nu,lu,gu,ku,hu,zhu,chu,shu,ru,zu,cu,su,wu",
    "v=yu,nv,lv,ju,qu,xu",
    "vn=yun,jun,qun,xun",
    "i=i,bi,pi,mi,di,ti,ni,li,ji,qi,xi,yi",
    "in=yin,bin,pin,min,nin,lin,jin,qin,xin",
    "ing=ying,bing,ping,ming,ding,ting,ning,ling,jing,qing,xing",
    "ir=zhi,chi,shi,ri",
    "iz=zi,ci,si",
    "er=er",
    "ian=yan,bian,pian,mian,dian,tian,nian,lian,jian,qian,xian,yuan,juan,quan,xuan",
]


def _tail_lookup():
    out = {}
    for line in TAIL_MAP:
        tail, pinyins = line.split("=")[0], line.split("=")[1]
        for p in pinyins.split(","):
            if p in out:
                raise ValueError(f"duplicate key {p}")  # ToDictionary throws on duplicates
            out[p] = tail
    return out


TAIL_LOOKUP = _tail_lookup()


def nfc(s):
    return unicodedata.normalize("NFC", s)


def _is_null_or_white_space(s):
    return s is None or s.strip() == ""


@phonemizer("Chinese VCV Phonemizer", "ZH VCV", language="ZH", openutau_class="OpenUtau.Plugin.Builtin.ChineseVCVPhonemizer", author="樗儿")
class ChineseVCVPhonemizer(Phonemizer):
    """chinese vcv: hanzi become toneless pinyin, then vcv aliases; ending "R" from the tail-final table."""

    def set_up(self, groups):
        romanize_notes(groups)

    def process(self, notes, prev, next, prev_neighbour, next_neighbour, prevs):
        note = notes[0]
        current_lyric = nfc(note.lyric)
        total_duration = sum(n.duration for n in notes)

        # 1. phonetic hint wins
        if note.phonetic_hint:
            hint = nfc(note.phonetic_hint)
            ph = self._check_oto_until_hit([hint], note, 0)
            if ph is not None:
                return [Phoneme(ph.alias)]
            return [Phoneme(hint)]

        # 2. pure pinyin
        current_pure = self._extract_pure_pinyin(current_lyric)

        # 3. extension passes through
        if current_pure == "+":
            return [Phoneme("+")]

        # 4. candidates by priority
        candidates = []
        if prev_neighbour is not None:
            prev_lyric = nfc(prev_neighbour.lyric)
            if prev_neighbour.phonetic_hint:
                prev_lyric = nfc(prev_neighbour.phonetic_hint)
            prev_pure = self._extract_pure_pinyin(prev_lyric)
            tail = TAIL_LOOKUP.get(prev_pure)
            if tail:
                candidates.append(f"{tail} {current_pure}")
                candidates.append(f"* {current_pure}")
        candidates.append(f"- {current_pure}")
        candidates.append(current_pure)

        # 5. match oto
        oto = self._check_oto_until_hit(candidates, note, 0)
        if oto is not None:
            return self._make_result_with_tail_r(oto.alias, note, current_pure, total_duration, next_neighbour)
        # 6. fall back to the plain pinyin
        return self._make_result_with_tail_r(current_pure, note, current_pure, total_duration, next_neighbour)

    def _make_result_with_tail_r(self, main_phoneme, note, current_pure, total_duration, next_neighbour):
        if next_neighbour is not None:
            return [Phoneme(main_phoneme)]
        tail = TAIL_LOOKUP.get(current_pure)
        if tail:
            tail_oto = self._check_oto_until_hit([f"{tail} R"], note, 1)
            if tail_oto is not None:
                return [Phoneme(main_phoneme), Phoneme(tail_oto.alias, position=total_duration - min(total_duration // 6, 60))]
        return [Phoneme(main_phoneme)]

    @staticmethod
    def _extract_pure_pinyin(lyric):
        if _is_null_or_white_space(lyric):
            return ""
        result = lyric.strip()
        if result.startswith("-"):
            result = result[1:].strip()
        if " " in result:
            result = result.split(" ")[-1].strip()
        return result

    def _check_oto_until_hit(self, inputs, note, index):
        if self.singer is None:
            return None
        attr = note.attr(index)
        color = attr.voice_color if attr.voice_color is not None else ""
        tone_shift = attr.tone_shift if attr.tone_shift is not None else 0
        alt = attr.alternate
        results = []
        for inp in inputs:
            if alt is not None:
                o = self.singer.try_get_mapped_oto(inp + str(alt), note.tone + tone_shift, color)
                if o is not None:
                    results.append(o)
            o = self.singer.try_get_mapped_oto(inp, note.tone + tone_shift, color)
            if o is not None:
                results.append(o)
        if not results:
            return None
        return next((o for o in results if o.is_color_match(color)), results[0])
