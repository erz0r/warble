"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Plugin.Builtin/ChineseCVVPhonemizer.cs

chinese 十月式整音扩张 cvv phonemizer: splits "duang" into "duang" + "_ang" to produce the proper tail sound.

SetUp romanizes hanzi lyrics with BaseChinesePhonemizer.RomanizeNotes (the csharp-pinyin port in _pinyin.py)."""

from ...g2p import G2pDictionary, G2pFallbacks, IG2p
from .api import phonemizer
from .arpasing import singer_file, vowel_fallbacks
from .monophone import MonophonePhonemizer
from .phoneme_based import plugin_file, read_all_text

PINYINS = "a,ai,an,ang,ao,ba,bai,ban,bang,bao,bei,ben,beng,bi,bian,biao,bie,bin,bing,bo,bu,ca,cai,can,cang,cao,ce,cei,cen,ceng,cha,chai,chan,chang,chao,che,chen,cheng,chi,chong,chou,chu,chua,chuai,chuan,chuang,chui,chun,chuo,ci,cong,cou,cu,cuan,cui,cun,cuo,da,dai,dan,dang,dao,de,dei,den,deng,di,dia,dian,diao,die,ding,diu,dong,dou,du,duan,dui,dun,duo,e,ei,en,eng,er,fa,fan,fang,fei,fen,feng,fo,fou,fu,ga,gai,gan,gang,gao,ge,gei,gen,geng,gong,gou,gu,gua,guai,guan,guang,gui,gun,guo,ha,hai,han,hang,hao,he,hei,hen,heng,hong,hou,hu,hua,huai,huan,huang,hui,hun,huo,ji,jia,jian,jiang,jiao,jie,jin,jing,jiong,jiu,ju,jv,juan,jvan,jue,jve,jun,jvn,ka,kai,kan,kang,kao,ke,kei,ken,keng,kong,kou,ku,kua,kuai,kuan,kuang,kui,kun,kuo,la,lai,lan,lang,lao,le,lei,leng,li,lia,lian,liang,liao,lie,lin,ling,liu,lo,long,lou,lu,luan,lun,luo,lv,lve,ma,mai,man,mang,mao,me,mei,men,meng,mi,mian,miao,mie,min,ming,miu,mo,mou,mu,na,nai,nan,nang,nao,ne,nei,nen,neng,ni,nian,niang,niao,nie,nin,ning,niu,nong,nou,nu,nuan,nun,nuo,nv,nve,o,ou,pa,pai,pan,pang,pao,pei,pen,peng,pi,pian,piao,pie,pin,ping,po,pou,pu,qi,qia,qian,qiang,qiao,qie,qin,qing,qiong,qiu,qu,qv,quan,qvan,que,qve,qun,qvn,ran,rang,rao,re,ren,reng,ri,rong,rou,ru,rua,ruan,rui,run,ruo,sa,sai,san,sang,sao,se,sen,seng,sha,shai,shan,shang,shao,she,shei,shen,sheng,shi,shou,shu,shua,shuai,shuan,shuang,shui,shun,shuo,si,song,sou,su,suan,sui,sun,suo,ta,tai,tan,tang,tao,te,tei,teng,ti,tian,tiao,tie,ting,tong,tou,tu,tuan,tui,tun,tuo,wa,wai,wan,wang,wei,wen,weng,wo,wu,xi,xia,xian,xiang,xiao,xie,xin,xing,xiong,xiu,xu,xv,xuan,xvan,xue,xve,xun,xvn,ya,yan,yang,yao,ye,yi,yin,ying,yo,yong,you,yu,yv,yuan,yvan,yue,yve,yun,yvn,za,zai,zan,zang,zao,ze,zei,zen,zeng,zha,zhai,zhan,zhang,zhao,zhe,zhei,zhen,zheng,zhi,zhong,zhou,zhu,zhua,zhuai,zhuan,zhuang,zhui,zhun,zhuo,zi,zong,zou,zu,zuan,zui,zun"
TAILS = "_vn,_ing,_ong,_an,_ou,_er,_ao,_eng,_ang,_en,_en2,_ai,_iong,_in,_ei"

PINYIN_LIST = PINYINS.split(",")
TAIL_LIST = TAILS.split(",")


@phonemizer("Chinese CVV (十月式整音扩张) Phonemizer", "ZH CVV", language="ZH", openutau_class="OpenUtau.Plugin.Builtin.ChineseCVVMonophonePhonemizer")
class ChineseCVVMonophonePhonemizer(MonophonePhonemizer):
    consonant_length = 120  # ChineseCVVMonophonePhonemizer() { ConsonantLength = 120; }

    def load_g2p(self):
        g2ps = []

        # Load dictionary from plugin folder.
        path = plugin_file("zhcvv.yaml")
        if path is not None:
            g2ps.append(G2pDictionary.new_builder().load(read_all_text(path)).build())

        # Load dictionary from singer folder.
        file = singer_file(self.singer, "zhcvv.yaml")
        if file is not None:
            try:
                g2ps.append(G2pDictionary.new_builder().load(read_all_text(file)).build())
            except Exception:  # noqa: BLE001
                pass
        g2ps.append(ChineseCVVG2p())
        return G2pFallbacks(g2ps)

    def load_vowel_fallbacks(self):
        return vowel_fallbacks("_un=_en;_uai=_ai")

    def set_up(self, groups):
        super().set_up(groups)
        from .base_chinese import romanize_notes

        romanize_notes(groups)


class ChineseCVVG2p(IG2p):
    # The consonant table.
    consonants = "b,p,m,f,d,t,n,l,g,k,h,j,q,x,z,c,s,zh,ch,sh,r,y,w"
    # The vowel split table.
    vowels = "ai=_ai,uai=_uai,an=_an,ian=_en2,uan=_an,van=_en2,ang=_ang,iang=_ang,uang=_ang,ao=_ao,iao=_ao,ou=_ou,iu=_ou,ong=_ong,iong=_ong,ei=_ei,ui=_ei,uei=_ei,en=_en,un=_un,uen=_un,eng=_eng,in=_in,ing=_ing,vn=_vn"

    c_set = set(consonants.split(","))
    v_dict = dict(s.split("=") for s in vowels.split(","))

    def is_vowel(self, phoneme):
        return not phoneme.startswith("_")

    def is_glide(self, phoneme):
        return False

    def query(self, lyric):
        # The overall logic is:
        # 1. Remove consonant: "duang" -> "uang".
        # 2. Lookup the trailing sound in vowel table: "uang" -> "_ang".
        consonant = ""
        vowel = ""
        if len(lyric) > 2 and lyric[0:2] in self.c_set:
            # First try to find consonant "zh", "ch" or "sh", and extract vowel.
            consonant = lyric[0:2]
            vowel = lyric[2:]
        elif len(lyric) > 1 and lyric[0:1] in self.c_set:
            # Then try to find single character consonants, and extract vowel.
            consonant = lyric[0:1]
            vowel = lyric[1:]
        else:
            # Otherwise the lyric is a vowel.
            vowel = lyric
        if (vowel == "un" or vowel == "uan") and (consonant in ("j", "q", "x", "y")):
            vowel = "v" + vowel[1:]

        if vowel == "an" and consonant == "y":
            vowel = "ian"
        tail = self.v_dict.get(vowel)
        if tail is not None:
            return [lyric, tail]
        return [lyric]

    def is_valid_symbol(self, symbol):
        return True

    def unpack_hint(self, hint, separator=" "):
        return hint.split(separator)
