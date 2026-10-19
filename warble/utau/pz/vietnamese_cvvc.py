"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Plugin.Builtin/VietnameseCVVCPhonemizer.cs

the Process body was translated statement by statement from the c# (same branches, same names), so the two
can be diffed. c# integer division is written // (all operands are non-negative here).
"""

import copy

from .api import Phoneme, Phonemizer, alt_str, phonemizer, to_unicode_elements

# The lookup table to convert a hiragana to its tail vowel.
VOWELS = [
    "a=a,à,á,ả,ã,ạ,ă,ằ,ắ,ẳ,ẵ,ặ,A,À,Á,Ả,Ã,Ạ,Ă,Ằ,Ắ,Ẳ,Ẵ,Ặ",
    "A=â,ầ,ấ,ẩ,ẫ,ậ,Â,Ầ,Ấ,Ẩ,Ẫ,Ậ",
    "@=ơ,ờ,ớ,ở,ỡ,ợ,Ơ,Ờ,Ớ,Ở,Ỡ,Ợ,@",
    "i=i,y,ì,í,ỉ,ĩ,ị,ỳ,ý,ỷ,ỹ,ỵ,I,Y,Ì,Í,Ỉ,Ĩ,Ị,Ỳ,Ý,Ỷ,Ỹ,Ỵ",
    "e=e,è,é,ẻ,ẽ,ẹ,E,È,É,Ẻ,Ẽ,Ẹ",
    "E=ê,ề,ế,ể,ễ,ệ,Ê,Ề,Ế,Ể,Ễ,Ệ",
    "o=o,ò,ó,ỏ,õ,ọ,O,Ò,Ó,Ỏ,Õ,Ọ",
    "O=ô,ồ,ố,ổ,ỗ,ộ,Ô,Ồ,Ố,Ổ,Ỗ,Ộ",
    "u=u,ù,ú,ủ,ũ,ụ,U,Ù,Ú,Ủ,Ũ,Ụ",
    "U=ư,ừ,ứ,ử,ữ,ự,Ư,Ừ,Ứ,Ử,Ữ,Ự",
    "m=m,M",
    "n=n,N",
    "ng=g,G",
    "nh=h,H",
    "-=c,C,t,T,-,p,P,R,1,2,3,4,5",
]


def _table(lines):
    out = {}
    for line in lines:
        parts = line.split("=")
        for cv in parts[1].split(","):
            if cv in out:
                raise ValueError(f"duplicate key {cv}")  # c# ToDictionary throws on duplicates
            out[cv] = parts[0]
    return out


VOWEL_LOOKUP = _table(VOWELS)


@phonemizer("Vietnamese CVVC Phonemizer", "VIE CVVC", language="VI", openutau_class="OpenUtau.Plugin.Builtin.VietnameseCVVCPhonemizer", author="Jani Tran")
class VietnameseCVVCPhonemizer(Phonemizer):
    # Legacy mapping. Might adjust later to new mapping style.
    legacy_mapping = True

    def process(self, notes, prev, next, prev_neighbour, next_neighbour, prev_neighbours):
        note = copy.copy(notes[0])
        if note.phonetic_hint:
            return [Phoneme(note.phonetic_hint)]
        totalDuration = sum(n.duration for n in notes)
        Short = 0
        Long = 0
        Medium = 0
        VCP = 0
        End = 0
        ViTri = 0
        if totalDuration < 350:
            Short = totalDuration * 4 // 7
            Long = totalDuration // 6
            Medium = totalDuration // 3
            VCP = -90
            End = totalDuration * 4 // 5
            ViTri = Short
        else:
            Short = totalDuration - 170
            Long = 90
            Medium = 180
            VCP = -90
            End = totalDuration - 50
            ViTri = Short
        NoNext = next_neighbour is None and note.lyric != "R"
        loi = note.lyric
        if note.lyric.startswith("?"):
            pass
        else:
            if note.lyric != "R":
                loi = note.lyric.lower()
                note.lyric = note.lyric.lower()
        note.lyric = note.lyric.replace("à", "a").replace("á", "a").replace("ả", "a").replace("ã", "a").replace("ạ", "a")
        note.lyric = note.lyric.replace("ằ", "ă").replace("ắ", "ă").replace("ẳ", "ă").replace("ẵ", "ă").replace("ặ", "ă")
        note.lyric = note.lyric.replace("ầ", "â").replace("ấ", "â").replace("ẩ", "â").replace("ẫ", "â").replace("ậ", "â")
        note.lyric = note.lyric.replace("ờ", "ơ").replace("ớ", "ơ").replace("ở", "ơ").replace("ỡ", "ơ").replace("ợ", "ơ")
        note.lyric = note.lyric.replace("ì", "i").replace("í", "i").replace("ỉ", "i").replace("ĩ", "i").replace("ị", "i")
        note.lyric = note.lyric.replace("ỳ", "y").replace("ý", "y").replace("ỷ", "y").replace("ỹ", "y").replace("ỵ", "y")
        note.lyric = note.lyric.replace("è", "e").replace("é", "e").replace("ẻ", "e").replace("ẽ", "e").replace("ẹ", "e")
        note.lyric = note.lyric.replace("ề", "ê").replace("ế", "ê").replace("ể", "ê").replace("ễ", "ê").replace("ệ", "ê")
        note.lyric = note.lyric.replace("ò", "o").replace("ó", "o").replace("ỏ", "o").replace("õ", "o").replace("ọ", "o")
        note.lyric = note.lyric.replace("ồ", "ô").replace("ố", "ô").replace("ổ", "ô").replace("ỗ", "ô").replace("ộ", "ô")
        note.lyric = note.lyric.replace("ù", "u").replace("ú", "u").replace("ủ", "u").replace("ũ", "u").replace("ụ", "u")
        note.lyric = note.lyric.replace("ừ", "ư").replace("ứ", "ư").replace("ử", "ư").replace("ữ", "ư").replace("ự", "ư")
        if note.lyric == "quôc":
            note.lyric = "quâc"
        if (note.lyric != "gi" and note.lyric != "gin" and note.lyric != "gim" and note.lyric != "ginh"
            and note.lyric != "ging" and note.lyric != "git" and note.lyric != "gip" and note.lyric != "gic"
            and note.lyric != "gich"):
            loi = note.lyric.replace("à", "a").replace("á", "a").replace("ả", "a").replace("ã", "a").replace("ạ", "a")
            loi = note.lyric.replace("ằ", "ă").replace("ắ", "ă").replace("ẳ", "ă").replace("ẵ", "ă").replace("ặ", "ă")
            loi = note.lyric.replace("ầ", "â").replace("ấ", "â").replace("ẩ", "â").replace("ẫ", "â").replace("ậ", "â")
            loi = note.lyric.replace("ờ", "ơ").replace("ớ", "ơ").replace("ở", "ơ").replace("ỡ", "ơ").replace("ợ", "ơ")
            loi = note.lyric.replace("ì", "i").replace("í", "i").replace("ỉ", "i").replace("ĩ", "i").replace("ị", "i")
            loi = note.lyric.replace("ỳ", "y").replace("ý", "y").replace("ỷ", "y").replace("ỹ", "y").replace("ỵ", "y")
            loi = note.lyric.replace("è", "e").replace("é", "e").replace("ẻ", "e").replace("ẽ", "e").replace("ẹ", "e")
            loi = note.lyric.replace("ề", "ê").replace("ế", "ê").replace("ể", "ê").replace("ễ", "ê").replace("ệ", "ê")
            loi = note.lyric.replace("ò", "o").replace("ó", "o").replace("ỏ", "o").replace("õ", "o").replace("ọ", "o")
            loi = note.lyric.replace("ồ", "ô").replace("ố", "ô").replace("ổ", "ô").replace("ỗ", "ô").replace("ộ", "ô")
            loi = note.lyric.replace("ù", "u").replace("ú", "u").replace("ủ", "u").replace("ũ", "u").replace("ụ", "u")
            loi = note.lyric.replace("ừ", "ư").replace("ứ", "ư").replace("ử", "ư").replace("ữ", "ư").replace("ự", "ư")
            loi = (note.lyric.replace("ch", "C").replace("d", "z").replace("đ", "d").replace("ph", "f").replace("ch", "C")
                .replace("gi", "z").replace("gh", "g").replace("c", "k").replace("kh", "K").replace("ng", "N")
                .replace("ngh", "N").replace("nh", "J").replace("x", "s").replace("tr", "Z").replace("th", "T")
                .replace("q", "k").replace("r", "z"))
        else:
            loi = note.lyric.replace("ì", "i").replace("í", "i").replace("ỉ", "i").replace("ĩ", "i").replace("ị", "i")
            loi = loi.replace("gi", "zi").replace("ng", "N").replace("nh", "J").replace("ch", "C").replace("c", "k")
        tontaiVVC = (loi.endswith("iên") or loi.endswith("iêN") or loi.endswith("iêm") or loi.endswith("iêt") or loi.endswith("iêk")
            or loi.endswith("iêp") or loi.endswith("iêu") or loi.endswith("yên") or loi.endswith("yêN")
            or loi.endswith("yêm") or loi.endswith("yêt") or loi.endswith("yêk") or loi.endswith("yêp")
            or loi.endswith("yêu") or loi.endswith("uôn") or loi.endswith("uôN") or loi.endswith("uôm")
            or loi.endswith("uôt") or loi.endswith("uôk") or loi.endswith("uôi") or loi.endswith("ươn")
            or loi.endswith("ươN") or loi.endswith("ươm") or loi.endswith("ươt") or loi.endswith("ươk")
            or loi.endswith("ươp") or loi.endswith("ươi"))
        if tontaiVVC == True:
            koVVCchia = False
        else:
            koVVCchia = True
        tontaiCcuoi = (loi.endswith("k") or loi.endswith("t") or loi.endswith("C") or loi.endswith("p"))
        tontaiC = (loi.startswith("b") or loi.startswith("C") or loi.startswith("d") or loi.startswith("f") or loi.startswith("g")
            or loi.startswith("h") or loi.startswith("k") or loi.startswith("K") or loi.startswith("l")
            or loi.startswith("m") or loi.startswith("n") or loi.startswith("N") or loi.startswith("J")
            or loi.startswith("r") or loi.startswith("s") or loi.startswith("t") or loi.startswith("T")
            or loi.startswith("Z") or loi.startswith("v") or loi.startswith("w") or loi.startswith("z")
            or loi.startswith("p"))
        x = prev_neighbour.duration if prev_neighbour is not None else 0
        if x < 160 and prev_neighbour is not None:
            VCP = -(x * 4 // 8)
        elif (loi.startswith("b") or loi.startswith("d") or loi.startswith("g") or loi.startswith("d") or loi.startswith("k")
            or loi.startswith("l") or loi.startswith("m") or loi.startswith("n") or loi.startswith("nh")
            or loi.startswith("ng") or loi.startswith("t") or loi.startswith("th") or loi.startswith("v")
            or loi.startswith("w") or loi.startswith("y")):
            VCP = -70
        else:
            VCP = -110
        if tontaiC == True:
            kocoC = False
        else:
            kocoC = True
        BR = note.lyric.startswith("breath")
        tontaiVV = (loi.endswith("ai") or loi.endswith("ơi") or loi.endswith("oi") or loi.endswith("ôi") or loi.endswith("ui")
            or loi.endswith("ưi") or loi.endswith("ao") or loi.endswith("eo") or loi.endswith("êu") or loi.endswith("iu")
            or loi.endswith("an") or loi.endswith("ơn") or loi.endswith("in") or loi.endswith("en") or loi.endswith("ên")
            or loi.endswith("on") or loi.endswith("ôn") or loi.endswith("un") or loi.endswith("ưn") or loi.endswith("am")
            or loi.endswith("ơm") or loi.endswith("im") or loi.endswith("em") or loi.endswith("êm") or loi.endswith("om")
            or loi.endswith("ôm") or loi.endswith("um") or loi.endswith("ưm") or loi.endswith("aN") or loi.endswith("ơN")
            or loi.endswith("iN") or loi.endswith("eN") or loi.endswith("êN") or loi.endswith("ưN") or loi.endswith("aJ")
            or loi.endswith("iJ") or loi.endswith("êJ") or loi.endswith("at") or loi.endswith("ơt") or loi.endswith("it")
            or loi.endswith("et") or loi.endswith("êt") or loi.endswith("ot") or loi.endswith("ôt") or loi.endswith("ut")
            or loi.endswith("ưt") or loi.endswith("aC") or loi.endswith("iC") or loi.endswith("êC") or loi.endswith("ak")
            or loi.endswith("ơk") or loi.endswith("ik") or loi.endswith("ek") or loi.endswith("êk") or loi.endswith("ok")
            or loi.endswith("ôk") or loi.endswith("uk") or loi.endswith("ưk") or loi.endswith("ap") or loi.endswith("ơp")
            or loi.endswith("ip") or loi.endswith("ep") or loi.endswith("êp") or loi.endswith("op") or loi.endswith("ôp")
            or loi.endswith("up") or loi.endswith("ưp") or loi.endswith("ia") or loi.endswith("ua") or loi.endswith("ưa")
            or loi.endswith("ay") or loi.endswith("ây") or loi.endswith("uy") or loi.endswith("au") or loi.endswith("âu")
            or loi.endswith("oa") or loi.endswith("oe") or loi.endswith("uê"))
        ViTriNgan = (loi.endswith("ai") or loi.endswith("ơi") or loi.endswith("oi") or loi.endswith("ôi") or loi.endswith("ui")
            or loi.endswith("ưi") or loi.endswith("ao") or loi.endswith("eo") or loi.endswith("êu") or loi.endswith("iu")
            or loi.endswith("an") or loi.endswith("ơn") or loi.endswith("in") or loi.endswith("en") or loi.endswith("ên")
            or loi.endswith("on") or loi.endswith("ôn") or loi.endswith("un") or loi.endswith("ưn") or loi.endswith("am")
            or loi.endswith("ơm") or loi.endswith("im") or loi.endswith("em") or loi.endswith("êm") or loi.endswith("om")
            or loi.endswith("ôm") or loi.endswith("um") or loi.endswith("ưm") or loi.endswith("aN") or loi.endswith("ơN")
            or loi.endswith("iN") or loi.endswith("eN") or loi.endswith("êN") or loi.endswith("ưN") or loi.endswith("at")
            or loi.endswith("ơt") or loi.endswith("it") or loi.endswith("et") or loi.endswith("êt") or loi.endswith("ot")
            or loi.endswith("ôt") or loi.endswith("ut") or loi.endswith("ưt") or loi.endswith("ak") or loi.endswith("ơk")
            or loi.endswith("ik") or loi.endswith("ek") or loi.endswith("êk") or loi.endswith("ok") or loi.endswith("ôk")
            or loi.endswith("uk") or loi.endswith("ưk") or loi.endswith("ap") or loi.endswith("ơp") or loi.endswith("ip")
            or loi.endswith("ep") or loi.endswith("êp") or loi.endswith("op") or loi.endswith("ôp") or loi.endswith("up")
            or loi.endswith("ưp") or loi.endswith("ia") or loi.endswith("ua") or loi.endswith("ưa") or loi.endswith("uôN")
            or loi.endswith("yt") or loi.endswith("yn") or loi.endswith("ym") or loi.endswith("yC") or loi.endswith("yp")
            or loi.endswith("yk") or loi.endswith("yN") or loi.endswith("uya") and (note.lyric != "qua"))
        ViTriDai = (loi.endswith("ay") or loi.endswith("ây") or loi.endswith("uy") or loi.endswith("au") or loi.endswith("âu")
            or loi.endswith("oa") or loi.endswith("oe") or loi.endswith("uê") or note.lyric.endswith("qua"))
        ViTriTB = (loi.endswith("ăt") or loi.endswith("ât") or loi.endswith("ăk") or loi.endswith("âk") or loi.endswith("ăp")
            or loi.endswith("âp") or loi.endswith("ăn") or loi.endswith("ân") or loi.endswith("ăN") or loi.endswith("âN")
            or loi.endswith("ăm") or loi.endswith("âm") or loi.endswith("aJ") or loi.endswith("iJ") or loi.endswith("êJ")
            or loi.endswith("yJ") or loi.endswith("ôN") or loi.endswith("uN") or loi.endswith("oN") or loi.endswith("aC")
            or loi.endswith("iC") or loi.endswith("êC") or loi.endswith("yC"))
        XO = False
        if ViTriTB:
            ViTri = Medium
        if ViTriNgan:
            ViTri = Short
        if ViTriDai:
            ViTri = Long
        if loi.endswith("uôN"):
            ViTri = Short
        dem = len(loi)
        phoneme = ""
        phonemes = []
        # 1 kí tự
        if note.lyric.startswith("?"):
            phoneme = note.lyric[1:]
        else:
            if dem == 1:
                N = loi
                N = (N.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                    .replace("ô", "O").replace("ư", "U").replace("C", "ch").replace("K", "kh").replace("N", "ng")
                    .replace("J", "nh").replace("Z", "tr").replace("T", "th"))
                if NoNext:
                    if prev_neighbour is None:
                        phonemes.append(Phoneme(f"-{N}"))
                        phonemes.append(Phoneme(f"{N}-", position=End))
                elif prev_neighbour is None:
                    phonemes.append(Phoneme(f"-{N}"))
            # 2 kí tự CV, ví dụ: "ba"
            if (dem == 2) and tontaiC:
                N = loi
                N2 = loi[1:2]
                N = (N.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                    .replace("ô", "O").replace("ư", "U").replace("C", "ch").replace("K", "kh").replace("N", "ng")
                    .replace("J", "nh").replace("Z", "tr").replace("T", "th"))
                N2 = (N2.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                    .replace("ô", "O").replace("ư", "U"))
                if NoNext:
                    if prev_neighbour is None:
                        phonemes.append(Phoneme(f"{N}"))
                        phonemes.append(Phoneme(f"{N2}-", position=End))
                elif prev_neighbour is None:
                    phonemes.append(Phoneme(f"{N}"))
            # 2 kí tự VV, ví dụ: "oa"
            if (dem == 2) and kocoC:
                V1 = loi[0:1]
                V2 = loi[1:2]
                if loi.endswith("oa") or loi.endswith("oe"):
                    V1 = "u"
                V1 = (V1.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                    .replace("ô", "O").replace("ư", "U"))
                V2 = (V2.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                    .replace("ô", "O").replace("ư", "U").replace("C", "ch").replace("N", "ng").replace("J", "nh"))
                a = (loi.endswith("ia") or loi.endswith("ua") or loi.endswith("ưa"))
                if a:
                    V2 = "A"
                if note.lyric == "ao" or note.lyric == "eo":
                    V2 = "u"
                N = V2
                if V1 + V2 == "Ong" or V1 + V2 == "ung" or V1 + V2 == "ong":
                    N = "m"
                if NoNext and tontaiCcuoi:
                    if prev_neighbour is None:
                        phonemes.append(Phoneme(f"-{V1}"))
                        phonemes.append(Phoneme(f"{V1}{V2}", position=ViTri))
                elif NoNext:
                    if prev_neighbour is None:
                        phonemes.append(Phoneme(f"-{V1}"))
                        phonemes.append(Phoneme(f"{V1}{V2}", position=ViTri))
                        phonemes.append(Phoneme(f"{N}-", position=End))
                elif prev_neighbour is None:
                    phonemes.append(Phoneme(f"-{V1}"))
                    phonemes.append(Phoneme(f"{V1}{V2}", position=ViTri))
            # 3 kí tự VVC/VVV chia 3 nốt, ví dụ: "oát" "oan" "oai"
            if (dem == 3) and koVVCchia and kocoC:
                V1 = loi[0:1]
                V2 = loi[1:2]
                V3 = loi[2:3]
                if loi.startswith("oa") or loi.startswith("oe"):
                    V1 = "u"
                V1 = (V1.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                    .replace("ô", "O").replace("ư", "U"))
                V2 = (V2.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                    .replace("ô", "O").replace("ư", "U"))
                V3 = (V3.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                    .replace("ô", "O").replace("ư", "U").replace("C", "ch").replace("N", "ng").replace("J", "nh"))
                N = V3
                if V2 + V3 == "Ong" or V2 + V3 == "ung" or V2 + V3 == "ong":
                    N = "m"
                if ViTriDai:
                    ViTri = Medium
                if NoNext and tontaiCcuoi:
                    if prev_neighbour is None:
                        phonemes.append(Phoneme(f"-{V1}"))
                        phonemes.append(Phoneme(f"{V1}{V2}", position=Long))
                        phonemes.append(Phoneme(f"{V2}{V3}", position=ViTri))
                elif NoNext:
                    if prev_neighbour is None:
                        phonemes.append(Phoneme(f"-{V1}"))
                        phonemes.append(Phoneme(f"{V1}{V2}", position=Long))
                        phonemes.append(Phoneme(f"{V2}{V3}", position=ViTri))
                        phonemes.append(Phoneme(f"{N}-", position=End))
                elif prev_neighbour is None:
                    phonemes.append(Phoneme(f"-{V1}"))
                    phonemes.append(Phoneme(f"{V1}{V2}", position=Long))
                    phonemes.append(Phoneme(f"{V2}{V3}", position=ViTri))
            # 3 kí tự VVV/VVC chia 2 nốt, ví dụ: "yên" "ướt"
            if (dem == 3) and tontaiVVC and kocoC:
                V1 = loi[0:1]
                VVC = loi[0:]
                C = loi[2:]
                V1 = (V1.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                    .replace("ô", "O").replace("ư", "U"))
                VVC = (VVC.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                    .replace("ô", "O").replace("ư", "U").replace("C", "ch").replace("N", "ng").replace("J", "nh"))
                C = C.replace("C", "ch").replace("N", "ng").replace("J", "nh")
                if NoNext and tontaiCcuoi:
                    if prev_neighbour is None:
                        phonemes.append(Phoneme(f"-{V1}"))
                        phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                elif NoNext:
                    if prev_neighbour is None:
                        phonemes.append(Phoneme(f"-{V1}"))
                        phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                        phonemes.append(Phoneme(f"{C}-", position=End))
                elif prev_neighbour is None:
                    phonemes.append(Phoneme(f"-{V1}"))
                    phonemes.append(Phoneme(f"{VVC}", position=ViTri))
            # 3 kí tự CVV/CVC, ví dụ: "hoa" "hang" "hát"
            if dem == 3 and tontaiC:
                C = loi[0:1]
                V1 = loi[1:2]
                V2 = loi[2:]
                if loi.endswith("oa") or loi.endswith("oe"):
                    V1 = "u"
                C = (C.replace("C", "ch").replace("K", "kh").replace("N", "ng").replace("J", "nh").replace("Z", "tr")
                    .replace("T", "th"))
                V1 = (V1.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                    .replace("ô", "O").replace("ư", "U"))
                V2 = (V2.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                    .replace("ô", "O").replace("ư", "U").replace("C", "ch").replace("N", "ng").replace("J", "nh"))
                a = (loi.endswith("ia") or loi.endswith("ua") or loi.endswith("ưa"))
                if a and note.lyric != "qua":
                    V2 = "A"
                if note.lyric.endswith("ao") or note.lyric.endswith("eo"):
                    V2 = "u"
                N = V2
                if V1 + V2 == "Ong" or V1 + V2 == "ung" or V1 + V2 == "ong":
                    N = "m"
                if NoNext and tontaiCcuoi:
                    if prev_neighbour is None:
                        phonemes.append(Phoneme(f"{C}{V1}"))
                        phonemes.append(Phoneme(f"{V1}{V2}", position=ViTri))
                elif NoNext:
                    if prev_neighbour is None:
                        phonemes.append(Phoneme(f"{C}{V1}"))
                        phonemes.append(Phoneme(f"{V1}{V2}", position=ViTri))
                        phonemes.append(Phoneme(f"{N}-", position=End))
                elif prev_neighbour is None:
                    phonemes.append(Phoneme(f"{C}{V1}"))
                    phonemes.append(Phoneme(f"{V1}{V2}", position=ViTri))
            # 4 kí tự VVVC có VVC liền, chia 3 nốt, ví dụ "uyết" "uyên"
            if dem == 4 and kocoC and tontaiVVC:
                V1 = loi[0:1]
                V2 = loi[1:2]
                VVC = loi[1:]
                C = loi[3:]
                V1 = (V1.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                    .replace("ô", "O").replace("ư", "U"))
                V2 = (V2.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                    .replace("ô", "O").replace("ư", "U"))
                VVC = (VVC.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                    .replace("ô", "O").replace("ư", "U").replace("C", "ch").replace("N", "ng").replace("J", "nh"))
                C = C.replace("C", "ch").replace("N", "ng").replace("J", "nh")
                if ViTriNgan:
                    ViTri = Short
                else:
                    ViTri = Medium
                if NoNext and tontaiCcuoi:
                    if prev_neighbour is None:
                        phonemes.append(Phoneme(f"-{V1}"))
                        phonemes.append(Phoneme(f"{V1}{V2}", position=Long))
                        phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                elif NoNext:
                    if prev_neighbour is None:
                        phonemes.append(Phoneme(f"-{V1}"))
                        phonemes.append(Phoneme(f"{V1}{V2}", position=Long))
                        phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                        phonemes.append(Phoneme(f"{C}-", position=End))
                elif prev_neighbour is None:
                    phonemes.append(Phoneme(f"-{V1}"))
                    phonemes.append(Phoneme(f"{V1}{V2}", position=Long))
                    phonemes.append(Phoneme(f"{VVC}", position=ViTri))
            # 4 kí tự CVVC, có VVC liền, chia 2 nốt, ví dụ "thiết" "tiên"
            if dem == 4 and tontaiVVC and tontaiC:
                C = loi[0:1]
                V1 = loi[1:2]
                VVC = loi[1:]
                C2 = loi[3:]
                C = (C.replace("C", "ch").replace("K", "kh").replace("N", "ng").replace("J", "nh").replace("Z", "tr")
                    .replace("T", "th"))
                V1 = (V1.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                    .replace("ô", "O").replace("ư", "U"))
                VVC = (VVC.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                    .replace("ô", "O").replace("ư", "U").replace("C", "ch").replace("N", "ng").replace("J", "nh"))
                C2 = C2.replace("C", "ch").replace("N", "ng").replace("J", "nh")
                if NoNext and tontaiCcuoi:
                    if prev_neighbour is None:
                        phonemes.append(Phoneme(f"{C}{V1}"))
                        phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                elif NoNext:
                    if prev_neighbour is None:
                        phonemes.append(Phoneme(f"{C}{V1}"))
                        phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                        phonemes.append(Phoneme(f"{C2}-", position=End))
                elif prev_neighbour is None:
                    phonemes.append(Phoneme(f"{C}{V1}"))
                    phonemes.append(Phoneme(f"{VVC}", position=ViTri))
            else:
                XO = True
            # 4 kí tự CVVC/CVVV, chia 3 nốt, ví dụ "thoát" "toan" "toại"
            if dem == 4 and tontaiC and XO:
                C = loi[0:1]
                V1 = loi[1:2]
                V2 = loi[2:3]
                VC = loi[2:]
                N = loi[3:]
                if V1 + V2 == "oa" or V1 + V2 == "oe":
                    V1 = "u"
                C = (C.replace("C", "ch").replace("K", "kh").replace("N", "ng").replace("J", "nh").replace("Z", "tr")
                    .replace("T", "th"))
                V1 = (V1.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                    .replace("ô", "O").replace("ư", "U"))
                V2 = (V2.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                    .replace("ô", "O").replace("ư", "U"))
                VC = (VC.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                    .replace("ô", "O").replace("ư", "U").replace("C", "ch").replace("N", "ng").replace("J", "nh"))
                N = (N.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                    .replace("ô", "O").replace("ư", "U").replace("C", "ch").replace("N", "ng").replace("J", "nh"))
                if ViTriNgan:
                    ViTri = Short
                else:
                    ViTri = Medium
                if NoNext and tontaiCcuoi:
                    if prev_neighbour is None:
                        phonemes.append(Phoneme(f"{C}{V1}"))
                        phonemes.append(Phoneme(f"{V1}{V2}", position=Long))
                        phonemes.append(Phoneme(f"{VC}", position=ViTri))
                elif NoNext:
                    if prev_neighbour is None:
                        phonemes.append(Phoneme(f"{C}{V1}"))
                        phonemes.append(Phoneme(f"{V1}{V2}", position=Long))
                        phonemes.append(Phoneme(f"{VC}", position=ViTri))
                        phonemes.append(Phoneme(f"{N}-", position=End))
                elif prev_neighbour is None:
                    phonemes.append(Phoneme(f"{C}{V1}"))
                    phonemes.append(Phoneme(f"{V1}{V2}", position=Long))
                    phonemes.append(Phoneme(f"{VC}", position=ViTri))
            # 5 kí tự CVVVC, có VVC liền, chia 3 nốt, ví dụ "thuyết"
            if dem == 5 and tontaiVVC and tontaiC:
                C = loi[0:1]
                V1 = loi[1:2]
                V2 = loi[2:3]
                VVC = loi[2:]
                N = loi[4:]
                C = (C.replace("C", "ch").replace("K", "kh").replace("N", "ng").replace("J", "nh").replace("Z", "tr")
                    .replace("T", "th"))
                V1 = (V1.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                    .replace("ô", "O").replace("ư", "U"))
                V2 = (V2.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                    .replace("ô", "O").replace("ư", "U"))
                VVC = (VVC.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                    .replace("ô", "O").replace("ư", "U").replace("C", "ch").replace("N", "ng").replace("J", "nh"))
                N = N.replace("N", "ng").replace("J", "nh")
                if ViTriNgan:
                    ViTri = Short
                else:
                    ViTri = Medium
                if NoNext and tontaiCcuoi:
                    if prev_neighbour is None:
                        phonemes.append(Phoneme(f"{C}{V1}"))
                        phonemes.append(Phoneme(f"{V1}{V2}", position=Long))
                        phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                elif NoNext:
                    if prev_neighbour is None:
                        phonemes.append(Phoneme(f"{C}{V1}"))
                        phonemes.append(Phoneme(f"{V1}{V2}", position=Long))
                        phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                        phonemes.append(Phoneme(f"{N}-", position=End))
                elif prev_neighbour is None:
                    phonemes.append(Phoneme(f"{C}{V1}"))
                    phonemes.append(Phoneme(f"{V1}{V2}", position=Long))
                    phonemes.append(Phoneme(f"{VVC}", position=ViTri))
            if BR:
                num = loi[5:]
                if num == "":
                    num = "1"
                if prev_neighbour is None:
                    phonemes.append(Phoneme(f"breath{num}"))
        if prev_neighbour is not None:
            lyric = prev_neighbour.phonetic_hint if prev_neighbour.phonetic_hint is not None else prev_neighbour.lyric
            unicode = to_unicode_elements(lyric)
            vow = VOWEL_LOOKUP.get(unicode[-1] if unicode else "")
            if vow is not None:
                PR = prev_neighbour.lyric
                if PR.startswith("?"):
                    vow = PR[len(PR) - 1:len(PR) - 1 + 1]
                    if PR.endswith("nh"):
                        vow = "nh"
                    if PR.endswith("ng"):
                        vow = "ng"
                    if PR.endswith("ch") or PR.endswith("t") or PR.endswith("k") or PR.endswith("p"):
                        vow = "-"
                if PR != "R":
                    PR = PR.lower()
                if PR == "gi":
                    PR = "zi"
                PR = PR.replace("à", "a").replace("á", "a").replace("ả", "a").replace("ã", "a").replace("ạ", "a")
                PR = PR.replace("ằ", "ă").replace("ắ", "ă").replace("ẳ", "ă").replace("ẵ", "ă").replace("ặ", "ă")
                PR = PR.replace("ầ", "â").replace("ấ", "â").replace("ẩ", "â").replace("ẫ", "â").replace("ậ", "â")
                PR = PR.replace("ờ", "ơ").replace("ớ", "ơ").replace("ở", "ơ").replace("ỡ", "ơ").replace("ợ", "ơ")
                PR = PR.replace("ì", "i").replace("í", "i").replace("ỉ", "i").replace("ĩ", "i").replace("ị", "i")
                PR = PR.replace("ỳ", "y").replace("ý", "y").replace("ỷ", "y").replace("ỹ", "y").replace("ỵ", "y")
                PR = PR.replace("è", "e").replace("é", "e").replace("ẻ", "e").replace("ẽ", "e").replace("ẹ", "e")
                PR = PR.replace("ề", "ê").replace("ế", "ê").replace("ể", "ê").replace("ễ", "ê").replace("ệ", "ê")
                PR = PR.replace("ò", "o").replace("ó", "o").replace("ỏ", "o").replace("õ", "o").replace("ọ", "o")
                PR = PR.replace("ồ", "ô").replace("ố", "ô").replace("ổ", "ô").replace("ỗ", "ô").replace("ộ", "ô")
                PR = PR.replace("ù", "u").replace("ú", "u").replace("ủ", "u").replace("ũ", "u").replace("ụ", "u")
                PR = PR.replace("ừ", "ư").replace("ứ", "ư").replace("ử", "ư").replace("ữ", "ư").replace("ự", "ư")
                PR = (PR.replace("ch", "C").replace("d", "z").replace("đ", "d").replace("ph", "f").replace("ch", "C")
                    .replace("gi", "z").replace("gh", "g").replace("c", "k").replace("kh", "K").replace("ng", "N")
                    .replace("ngh", "N").replace("nh", "J").replace("x", "s").replace("tr", "Z").replace("th", "T")
                    .replace("qu", "w"))
                a = (PR.endswith("ua") or PR.endswith("ưa") or PR.endswith("ia") or PR.endswith("uya"))
                if a:
                    vow = "A"
                a = (PR.endswith("uN") or PR.endswith("ôN") or PR.endswith("oN"))
                if PR.endswith("uôN"):
                    vow = "ng"
                elif a:
                    vow = "m"
                a = PR.endswith("breaT")
                if a:
                    vow = "-"
                if PR.endswith("ao") or PR.endswith("eo"):
                    vow = "u"
                XO = False
                prevtontaiCcuoi = (PR.endswith("t") or PR.endswith("C") or PR.endswith("p") or PR.endswith("k") or PR.endswith("breaT"))
                Cvoiced = PR.endswith("J") or PR.endswith("n") or PR.endswith("m") or PR.endswith("N")
                if prevtontaiCcuoi == True:
                    prevkocoCcuoi = False
                else:
                    prevkocoCcuoi = True
                if note.lyric.startswith("?"):
                    phoneme = note.lyric[1:]
                else:
                    # 1 kí tự
                    if dem == 1:
                        if NoNext:
                            N = loi
                            N = (N.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                                .replace("ô", "O").replace("ư", "U").replace("C", "ch").replace("K", "kh").replace("N", "ng")
                                .replace("J", "nh").replace("Z", "tr").replace("T", "th"))
                            if Cvoiced and note.lyric != "-":
                                phonemes.append(Phoneme(f"{vow} {N}"))
                                phonemes.append(Phoneme(f"{N}-", position=End))
                            else:
                                phonemes.append(Phoneme(f"{vow}{N}"))
                                phonemes.append(Phoneme(f"{N}-", position=End))
                        elif Cvoiced and note.lyric != "-":
                            phoneme = f"{vow} {loi}"
                            phoneme = (phoneme.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i")
                                .replace("ê", "E").replace("ô", "O").replace("ư", "U").replace("C", "ch").replace("K", "kh")
                                .replace("N", "ng").replace("J", "nh").replace("Z", "tr").replace("T", "th"))
                            phonemes.append(Phoneme(phoneme))
                        else:
                            phoneme = f"{vow}{loi}"
                            phoneme = (phoneme.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i")
                                .replace("ê", "E").replace("ô", "O").replace("ư", "U").replace("C", "ch").replace("K", "kh")
                                .replace("N", "ng").replace("J", "nh").replace("Z", "tr").replace("T", "th"))
                            phonemes.append(Phoneme(phoneme))
                    # R
                    if loi == "R":
                        phonemes.append(Phoneme(f"{vow} R"))
                    # 2 kí tự CV, ví dụ: "ba"
                    if (dem == 2) and tontaiC:
                        C = loi[0:1]
                        V = loi[1:2]
                        C = (C.replace("C", "ch").replace("K", "kh").replace("N", "ng").replace("J", "nh").replace("Z", "tr")
                            .replace("T", "th"))
                        V = (V.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                            .replace("ô", "O").replace("ư", "U"))
                        if prevkocoCcuoi and NoNext:
                            phonemes.append(Phoneme(f"{vow} {C}", position=VCP))
                            phonemes.append(Phoneme(f"{C}{V}"))
                            phonemes.append(Phoneme(f"{V}-", position=End))
                        elif prevkocoCcuoi:
                            phonemes.append(Phoneme(f"{vow} {C}", position=VCP))
                            phonemes.append(Phoneme(f"{C}{V}"))
                        elif NoNext:
                            phonemes.append(Phoneme(f"{C}{V}"))
                            phonemes.append(Phoneme(f"{V}-", position=End))
                        else:
                            phonemes.append(Phoneme(f"{C}{V}"))
                    # 2 kí tự VV/VC, ví dụ: "oa" "át"
                    if (dem == 2) and kocoC:
                        V1 = loi[0:1]
                        V2 = loi[1:2]
                        V1 = (V1.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                            .replace("ô", "O").replace("ư", "U"))
                        V2 = (V2.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                            .replace("ô", "O").replace("ư", "U").replace("C", "ch").replace("N", "ng").replace("J", "nh"))
                        a = (loi.endswith("ia") or loi.endswith("ua") or loi.endswith("ưa"))
                        if a:
                            V2 = "A"
                        if loi.endswith("oa") or loi.endswith("oe"):
                            V1 = "u"
                        if note.lyric == "ao" or note.lyric == "eo":
                            V2 = "u"
                        N = V2
                        if V1 + V2 == "Ong" or V1 + V2 == "ung" or V1 + V2 == "ong":
                            N = "m"
                        if NoNext and Cvoiced and tontaiCcuoi:
                            phonemes.append(Phoneme(f"{vow} {V1}"))
                            phonemes.append(Phoneme(f"{V1}{V2}", position=ViTri))
                        elif NoNext and tontaiCcuoi:
                            phonemes.append(Phoneme(f"{vow}{V1}"))
                            phonemes.append(Phoneme(f"{V1}{V2}", position=ViTri))
                        elif NoNext and Cvoiced:
                            phonemes.append(Phoneme(f"{vow} {V1}"))
                            phonemes.append(Phoneme(f"{V1}{V2}", position=ViTri))
                            phonemes.append(Phoneme(f"{N}-", position=End))
                        elif NoNext:
                            phonemes.append(Phoneme(f"{vow}{V1}"))
                            phonemes.append(Phoneme(f"{V1}{V2}", position=ViTri))
                            phonemes.append(Phoneme(f"{N}-", position=End))
                        elif Cvoiced and tontaiCcuoi:
                            phonemes.append(Phoneme(f"{vow} {V1}"))
                            phonemes.append(Phoneme(f"{V1}{V2}", position=ViTri))
                        elif Cvoiced:
                            phonemes.append(Phoneme(f"{vow} {V1}"))
                            phonemes.append(Phoneme(f"{V1}{V2}", position=ViTri))
                        else:
                            phonemes.append(Phoneme(f"{vow}{V1}"))
                            phonemes.append(Phoneme(f"{V1}{V2}", position=ViTri))
                    # 3 kí tự VVC chia 3 nốt, ví dụ: "oát" "oan" "oai"
                    if (dem == 3) and koVVCchia and kocoC:
                        V1 = loi[0:1]
                        V2 = loi[1:2]
                        VC = loi[1:]
                        N = loi[2:]
                        if loi.startswith("oa") or loi.startswith("oe"):
                            V1 = "u"
                        V1 = (V1.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                            .replace("ô", "O").replace("ư", "U"))
                        V2 = (V2.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                            .replace("ô", "O").replace("ư", "U"))
                        VC = (VC.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                            .replace("ô", "O").replace("ư", "U").replace("C", "ch").replace("N", "ng").replace("J", "nh"))
                        N = (N.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                            .replace("ô", "O").replace("ư", "U").replace("C", "ch").replace("N", "ng").replace("J", "nh"))
                        if ViTriDai:
                            ViTri = Medium
                        if NoNext and Cvoiced and tontaiCcuoi:
                            phonemes.append(Phoneme(f"{vow} {V1}"))
                            phonemes.append(Phoneme(f"{V1}{V2}", position=Long))
                            phonemes.append(Phoneme(f"{VC}", position=ViTri))
                        elif NoNext and tontaiCcuoi:
                            phonemes.append(Phoneme(f"{vow}{V1}"))
                            phonemes.append(Phoneme(f"{V1}{V2}", position=Long))
                            phonemes.append(Phoneme(f"{VC}", position=ViTri))
                        elif NoNext and Cvoiced:
                            phonemes.append(Phoneme(f"{vow} {V1}"))
                            phonemes.append(Phoneme(f"{V1}{V2}", position=Long))
                            phonemes.append(Phoneme(f"{VC}", position=ViTri))
                            phonemes.append(Phoneme(f"{N}-", position=End))
                        elif NoNext:
                            phonemes.append(Phoneme(f"{vow}{V1}"))
                            phonemes.append(Phoneme(f"{V1}{V2}", position=Long))
                            phonemes.append(Phoneme(f"{VC}", position=ViTri))
                            phonemes.append(Phoneme(f"{N}-", position=End))
                        elif Cvoiced and tontaiCcuoi:
                            phonemes.append(Phoneme(f"{vow} {V1}"))
                            phonemes.append(Phoneme(f"{V1}{V2}", position=Long))
                            phonemes.append(Phoneme(f"{VC}", position=ViTri))
                        elif Cvoiced:
                            phonemes.append(Phoneme(f"{vow} {V1}"))
                            phonemes.append(Phoneme(f"{V1}{V2}", position=Long))
                            phonemes.append(Phoneme(f"{VC}", position=ViTri))
                        else:
                            phonemes.append(Phoneme(f"{vow}{V1}"))
                            phonemes.append(Phoneme(f"{V1}{V2}", position=Long))
                            phonemes.append(Phoneme(f"{VC}", position=ViTri))
                    # 3 kí tự VVV/VVC chia 2 nốt, ví dụ: "yên" "ướt"
                    if (dem == 3) and tontaiVVC and kocoC:
                        V1 = loi[0:1]
                        VVC = loi[0:]
                        N = loi[2:]
                        V1 = (V1.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                            .replace("ô", "O").replace("ư", "U"))
                        VVC = (VVC.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                            .replace("ô", "O").replace("ư", "U").replace("C", "ch").replace("N", "ng").replace("J", "nh"))
                        N = N.replace("C", "ch").replace("N", "ng").replace("J", "nh")
                        if NoNext and Cvoiced and tontaiCcuoi:
                            phonemes.append(Phoneme(f"{vow} {V1}"))
                            phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                        elif NoNext and tontaiCcuoi:
                            phonemes.append(Phoneme(f"{vow}{V1}"))
                            phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                        elif NoNext and Cvoiced:
                            phonemes.append(Phoneme(f"{vow} {V1}"))
                            phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                            phonemes.append(Phoneme(f"{N}-", position=End))
                        elif NoNext:
                            phonemes.append(Phoneme(f"{vow}{V1}"))
                            phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                            phonemes.append(Phoneme(f"{N}-", position=End))
                        elif Cvoiced and tontaiCcuoi:
                            phonemes.append(Phoneme(f"{vow} {V1}"))
                            phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                        elif Cvoiced:
                            phonemes.append(Phoneme(f"{vow} {V1}"))
                            phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                        else:
                            phonemes.append(Phoneme(f"{vow}{V1}"))
                            phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                    # 3 kí tự CVC/CVV, ví dụ: "hát" "hoa"
                    if dem == 3 and tontaiC:
                        C = loi[0:1]
                        V1 = loi[1:2]
                        V2 = loi[2:]
                        a = (loi.endswith("ia") or loi.endswith("ua") or loi.endswith("ưa"))
                        if a and note.lyric != "qua":
                            V2 = "A"
                        if loi.endswith("oa") or loi.endswith("oe"):
                            V1 = "u"
                        if note.lyric.endswith("ao") or note.lyric.endswith("eo"):
                            V2 = "u"
                        C = (C.replace("C", "ch").replace("K", "kh").replace("N", "ng").replace("J", "nh").replace("Z", "tr")
                            .replace("T", "th"))
                        V1 = (V1.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                            .replace("ô", "O").replace("ư", "U"))
                        V2 = (V2.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                            .replace("ô", "O").replace("ư", "U").replace("C", "ch").replace("N", "ng").replace("J", "nh"))
                        N = V2
                        if V1 + V2 == "Ong" or V1 + V2 == "ung" or V1 + V2 == "ong":
                            N = "m"
                        if NoNext and prevkocoCcuoi and tontaiCcuoi:
                            phonemes.append(Phoneme(f"{vow} {C}", position=VCP))
                            phonemes.append(Phoneme(f"{C}{V1}"))
                            phonemes.append(Phoneme(f"{V1}{V2}", position=ViTri))
                        elif NoNext and prevkocoCcuoi:
                            phonemes.append(Phoneme(f"{vow} {C}", position=VCP))
                            phonemes.append(Phoneme(f"{C}{V1}"))
                            phonemes.append(Phoneme(f"{V1}{V2}", position=ViTri))
                            phonemes.append(Phoneme(f"{N}-", position=End))
                        elif NoNext and tontaiCcuoi:
                            phonemes.append(Phoneme(f"{C}{V1}"))
                            phonemes.append(Phoneme(f"{V1}{V2}", position=ViTri))
                        elif prevkocoCcuoi and tontaiCcuoi:
                            phonemes.append(Phoneme(f"{vow} {C}", position=VCP))
                            phonemes.append(Phoneme(f"{C}{V1}"))
                            phonemes.append(Phoneme(f"{V1}{V2}", position=ViTri))
                        elif prevkocoCcuoi:
                            phonemes.append(Phoneme(f"{vow} {C}", position=VCP))
                            phonemes.append(Phoneme(f"{C}{V1}"))
                            phonemes.append(Phoneme(f"{V1}{V2}", position=ViTri))
                        elif NoNext:
                            phonemes.append(Phoneme(f"{C}{V1}"))
                            phonemes.append(Phoneme(f"{V1}{V2}", position=ViTri))
                            phonemes.append(Phoneme(f"{N}-", position=End))
                        else:
                            phonemes.append(Phoneme(f"{C}{V1}"))
                            phonemes.append(Phoneme(f"{V1}{V2}", position=ViTri))
                    # 4 kí tự VVVC có VVC liền, chia 3 nốt, ví dụ "uyết" "uyên"
                    if dem == 4 and kocoC and tontaiVVC:
                        V1 = loi[0:1]
                        V2 = loi[1:2]
                        VVC = loi[1:]
                        N = loi[3:]
                        V1 = (V1.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                            .replace("ô", "O").replace("ư", "U"))
                        V2 = (V2.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                            .replace("ô", "O").replace("ư", "U"))
                        VVC = (VVC.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                            .replace("ô", "O").replace("ư", "U").replace("C", "ch").replace("N", "ng").replace("J", "nh"))
                        N = N.replace("C", "ch").replace("N", "ng").replace("J", "nh")
                        if ViTriNgan:
                            ViTri = Short
                        else:
                            ViTri = Medium
                        if NoNext and Cvoiced and tontaiCcuoi:
                            phonemes.append(Phoneme(f"{vow} {V1}"))
                            phonemes.append(Phoneme(f"{V1}{V2}", position=Long))
                            phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                        elif NoNext and Cvoiced:
                            phonemes.append(Phoneme(f"{vow} {V1}"))
                            phonemes.append(Phoneme(f"{V1}{V2}", position=Long))
                            phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                            phonemes.append(Phoneme(f"{N}-", position=End))
                        elif NoNext and tontaiCcuoi:
                            phonemes.append(Phoneme(f"{vow}{V1}"))
                            phonemes.append(Phoneme(f"{V1}{V2}", position=Long))
                            phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                        elif Cvoiced and tontaiCcuoi:
                            phonemes.append(Phoneme(f"{vow} {V1}"))
                            phonemes.append(Phoneme(f"{V1}{V2}", position=Long))
                            phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                        elif NoNext:
                            phonemes.append(Phoneme(f"{vow}{V1}"))
                            phonemes.append(Phoneme(f"{V1}{V2}", position=Long))
                            phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                            phonemes.append(Phoneme(f"{N}-", position=End))
                        elif Cvoiced:
                            phonemes.append(Phoneme(f"{vow} {V1}"))
                            phonemes.append(Phoneme(f"{V1}{V2}", position=Long))
                            phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                        else:
                            phonemes.append(Phoneme(f"{vow}{V1}"))
                            phonemes.append(Phoneme(f"{V1}{V2}", position=Long))
                            phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                    # 4 kí tự CVVC, có VVC liền, chia 2 nốt, ví dụ "thiết" "tiên"
                    if dem == 4 and tontaiVVC and tontaiC:
                        C = loi[0:1]
                        V1 = loi[1:2]
                        VVC = loi[1:]
                        N = loi[3:]
                        C = (C.replace("C", "ch").replace("K", "kh").replace("N", "ng").replace("J", "nh").replace("Z", "tr")
                            .replace("T", "th"))
                        V1 = (V1.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                            .replace("ô", "O").replace("ư", "U"))
                        VVC = (VVC.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                            .replace("ô", "O").replace("ư", "U").replace("C", "ch").replace("N", "ng").replace("J", "nh"))
                        N = N.replace("C", "ch").replace("N", "ng").replace("J", "nh")
                        if NoNext and prevkocoCcuoi and tontaiCcuoi:
                            phonemes.append(Phoneme(f"{vow} {C}", position=VCP))
                            phonemes.append(Phoneme(f"{C}{V1}"))
                            phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                        elif NoNext and prevkocoCcuoi:
                            phonemes.append(Phoneme(f"{vow} {C}", position=VCP))
                            phonemes.append(Phoneme(f"{C}{V1}"))
                            phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                            phonemes.append(Phoneme(f"{N}-", position=End))
                        elif NoNext and tontaiCcuoi:
                            phonemes.append(Phoneme(f"{C}{V1}"))
                            phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                        elif prevkocoCcuoi and tontaiCcuoi:
                            phonemes.append(Phoneme(f"{vow} {C}", position=VCP))
                            phonemes.append(Phoneme(f"{C}{V1}"))
                            phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                        elif prevkocoCcuoi:
                            phonemes.append(Phoneme(f"{vow} {C}", position=VCP))
                            phonemes.append(Phoneme(f"{C}{V1}"))
                            phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                        elif NoNext:
                            phonemes.append(Phoneme(f"{C}{V1}"))
                            phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                            phonemes.append(Phoneme(f"{N}-", position=End))
                        else:
                            phonemes.append(Phoneme(f"{C}{V1}"))
                            phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                    else:
                        XO = True
                    # 4 kí tự CVVC/CVVV, chia 3 nốt, ví dụ "thoát" "thoai"
                    if dem == 4 and tontaiC and XO:
                        C = loi[0:1]
                        V1 = loi[1:2]
                        V2 = loi[2:3]
                        VC = loi[2:]
                        N = loi[3:]
                        if V1 + V2 == "oa" or V1 + V2 == "oe":
                            V1 = "u"
                        C = (C.replace("C", "ch").replace("K", "kh").replace("N", "ng").replace("J", "nh").replace("Z", "tr")
                            .replace("T", "th"))
                        V1 = (V1.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                            .replace("ô", "O").replace("ư", "U"))
                        V2 = (V2.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                            .replace("ô", "O").replace("ư", "U"))
                        VC = (VC.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                            .replace("ô", "O").replace("ư", "U").replace("C", "ch").replace("N", "ng").replace("J", "nh"))
                        N = (N.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                            .replace("ô", "O").replace("ư", "U").replace("C", "ch").replace("N", "ng").replace("J", "nh"))
                        if ViTriNgan:
                            ViTri = Short
                        else:
                            ViTri = Medium
                        if NoNext and prevkocoCcuoi and tontaiCcuoi:
                            phonemes.append(Phoneme(f"{vow} {C}", position=VCP))
                            phonemes.append(Phoneme(f"{C}{V1}"))
                            phonemes.append(Phoneme(f"{V1}{V2}", position=Long))
                            phonemes.append(Phoneme(f"{VC}", position=ViTri))
                        elif NoNext and prevkocoCcuoi:
                            phonemes.append(Phoneme(f"{vow} {C}", position=VCP))
                            phonemes.append(Phoneme(f"{C}{V1}"))
                            phonemes.append(Phoneme(f"{V1}{V2}", position=Long))
                            phonemes.append(Phoneme(f"{VC}", position=ViTri))
                            phonemes.append(Phoneme(f"{N}-", position=End))
                        elif NoNext and tontaiCcuoi:
                            phonemes.append(Phoneme(f"{C}{V1}"))
                            phonemes.append(Phoneme(f"{V1}{V2}", position=Long))
                            phonemes.append(Phoneme(f"{VC}", position=ViTri))
                        elif tontaiCcuoi and prevkocoCcuoi:
                            phonemes.append(Phoneme(f"{vow} {C}", position=VCP))
                            phonemes.append(Phoneme(f"{C}{V1}"))
                            phonemes.append(Phoneme(f"{V1}{V2}", position=Long))
                            phonemes.append(Phoneme(f"{VC}", position=ViTri))
                        elif prevkocoCcuoi:
                            phonemes.append(Phoneme(f"{vow} {C}", position=VCP))
                            phonemes.append(Phoneme(f"{C}{V1}"))
                            phonemes.append(Phoneme(f"{V1}{V2}", position=Long))
                            phonemes.append(Phoneme(f"{VC}", position=ViTri))
                        elif NoNext:
                            phonemes.append(Phoneme(f"{C}{V1}"))
                            phonemes.append(Phoneme(f"{V1}{V2}", position=Long))
                            phonemes.append(Phoneme(f"{VC}", position=ViTri))
                            phonemes.append(Phoneme(f"{N}-", position=End))
                        else:
                            phonemes.append(Phoneme(f"{C}{V1}"))
                            phonemes.append(Phoneme(f"{V1}{V2}", position=Long))
                            phonemes.append(Phoneme(f"{VC}", position=ViTri))
                    # 5 kí tự CVVVC, có VVC liền, chia 3 nốt, ví dụ "thuyết"
                    if dem == 5 and tontaiVVC and tontaiC:
                        C = loi[0:1]
                        V1 = loi[1:2]
                        V2 = loi[2:3]
                        VVC = loi[2:]
                        N = loi[4:]
                        C = (C.replace("C", "ch").replace("K", "kh").replace("N", "ng").replace("J", "nh").replace("Z", "tr")
                            .replace("T", "th"))
                        V1 = (V1.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                            .replace("ô", "O").replace("ư", "U"))
                        V2 = (V2.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                            .replace("ô", "O").replace("ư", "U"))
                        VVC = (VVC.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                            .replace("ô", "O").replace("ư", "U").replace("C", "ch").replace("N", "ng").replace("J", "nh"))
                        N = N.replace("C", "ch").replace("N", "ng").replace("J", "nh")
                        if ViTriNgan:
                            ViTri = Short
                        else:
                            ViTri = Medium
                        if NoNext and prevkocoCcuoi and tontaiCcuoi:
                            phonemes.append(Phoneme(f"{vow} {C}", position=VCP))
                            phonemes.append(Phoneme(f"{C}{V1}"))
                            phonemes.append(Phoneme(f"{V1}{V2}", position=Long))
                            phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                        elif NoNext and prevkocoCcuoi:
                            phonemes.append(Phoneme(f"{vow} {C}", position=VCP))
                            phonemes.append(Phoneme(f"{C}{V1}"))
                            phonemes.append(Phoneme(f"{V1}{V2}", position=Long))
                            phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                            phonemes.append(Phoneme(f"{N}-", position=End))
                        elif NoNext and tontaiCcuoi:
                            phonemes.append(Phoneme(f"{C}{V1}"))
                            phonemes.append(Phoneme(f"{V1}{V2}", position=Long))
                            phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                        elif prevkocoCcuoi and tontaiCcuoi:
                            phonemes.append(Phoneme(f"{vow} {C}", position=VCP))
                            phonemes.append(Phoneme(f"{C}{V1}"))
                            phonemes.append(Phoneme(f"{V1}{V2}", position=Long))
                            phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                        elif prevkocoCcuoi:
                            phonemes.append(Phoneme(f"{vow} {C}", position=VCP))
                            phonemes.append(Phoneme(f"{C}{V1}"))
                            phonemes.append(Phoneme(f"{V1}{V2}", position=Long))
                            phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                        elif NoNext:
                            phonemes.append(Phoneme(f"{C}{V1}"))
                            phonemes.append(Phoneme(f"{V1}{V2}", position=Long))
                            phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                            phonemes.append(Phoneme(f"{N}-", position=End))
                        else:
                            phonemes.append(Phoneme(f"{C}{V1}"))
                            phonemes.append(Phoneme(f"{V1}{V2}", position=Long))
                            phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                    if BR:
                        num = loi[5:]
                        if num == "":
                            num = "1"
                        if vow == "-":
                            phonemes.append(Phoneme(f"breath{num}"))
                        else:
                            phonemes.append(Phoneme(f"{vow}-", position=-60))
                            phonemes.append(Phoneme(f"breath{num}"))
        noteIndex = 0
        for i in range(len(phonemes)):
            attr = note.attr(i)
            alt = alt_str(attr.alternate if attr.alternate is not None else self.get_parent_alternate())
            color = attr.voice_color if attr.voice_color is not None else self.get_parent_voice_color()
            tone_shift = attr.tone_shift if attr.tone_shift is not None else self.get_parent_tone_shift()
            phoneme1 = phonemes[i]
            while noteIndex < len(notes) - 1 and notes[noteIndex].position - note.position < phoneme1.position:
                noteIndex += 1
            tone = (prev_neighbours[-1].tone if i == 0 and prev_neighbours is not None
                and len(prev_neighbours) > 0 else notes[noteIndex].tone)
            oto = self.singer.try_get_mapped_oto(f"{phoneme1.phoneme}{alt}", note.tone + tone_shift, color)
            if oto is not None:
                phoneme1.phoneme = oto.alias
            phonemes[i] = phoneme1
        return phonemes
