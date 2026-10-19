"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Plugin.Builtin/VietnameseVINAPhonemizer.cs

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
    "-=c,C,t,T,-,p,P,R,',1,2,3,4,5",
    ".=.",
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


@phonemizer("Vietnamese VINA Phonemizer", "VIE VINA", language="VI", openutau_class="OpenUtau.Plugin.Builtin.VietnameseVINAPhonemizer", author="Jani Tran - Hoang Phuc")
class VietnameseVINAPhonemizer(Phonemizer):
    # Legacy mapping. Might adjust later to new mapping style.
    legacy_mapping = True

    def process(self, notes, prev, next, prev_neighbour, next_neighbour, prev_neighbours):
        note = copy.copy(notes[0])
        if note.phonetic_hint:
            return self.make_simple_result(note.phonetic_hint)
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
        fry = note.lyric.endswith("'")
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
                .replace("ngh", "N").replace("nh", "J").replace("x", "s").replace("tr", "C").replace("th", "T")
                .replace("q", "k").replace("r", "z"))
        else:
            loi = note.lyric.replace("ì", "i").replace("í", "i").replace("ỉ", "i").replace("ĩ", "i").replace("ị", "i")
            loi = loi.replace("gi", "zi").replace("ng", "N").replace("nh", "J").replace("ch", "C").replace("c", "k")
        tontaiVVC = ("iên" in loi or "iêN" in loi or "iêm" in loi or "iêt" in loi or "iêk" in loi or "iêp" in loi or "iêu" in loi
            or "yên" in loi or "yêN" in loi or "yêm" in loi or "yêt" in loi or "yêk" in loi or "yêp" in loi or "yêu" in loi
            or "uôn" in loi or "uôN" in loi or "uôm" in loi or "uôt" in loi or "uôk" in loi or "uôi" in loi or "ươn" in loi
            or "ươN" in loi or "ươm" in loi or "ươt" in loi or "ươk" in loi or "ươp" in loi or "ươi" in loi or "ươu" in loi)
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
        if tontaiVVC == True:
            koVVCchia = False
        else:
            koVVCchia = True
        tontaiCcuoi = (loi.endswith("k") or loi.endswith("t") or loi.endswith("C") or loi.endswith("p") or loi.endswith("."))
        tontaiC = (loi.startswith("b") or loi.startswith("C") or loi.startswith("d") or loi.startswith("f") or loi.startswith("g")
            or loi.startswith("h") or loi.startswith("k") or loi.startswith("K") or loi.startswith("l")
            or loi.startswith("m") or loi.startswith("n") or loi.startswith("N") or loi.startswith("J")
            or loi.startswith("r") or loi.startswith("s") or loi.startswith("t") or loi.startswith("T")
            or loi.startswith("Z") or loi.startswith("v") or loi.startswith("w") or loi.startswith("z")
            or loi.startswith("p") or loi.startswith("'") or loi.startswith("."))
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
        ViTriDai = (loi.endswith("uy") or loi.endswith("au") or loi.endswith("âu") or loi.endswith("oa") or loi.endswith("oe")
            or loi.endswith("uê") or note.lyric.endswith("qua"))
        ViTriTB = ("ăt" in loi or "ât" in loi or loi.endswith("oay") or loi.endswith("uây") or loi.endswith("ay")
            or loi.endswith("ây") or "ăk" in loi or "âk" in loi or loi.endswith("oay'") or loi.endswith("uây'")
            or loi.endswith("ay'") or loi.endswith("ây'") or "ăp" in loi or "âp" in loi or "ăn" in loi or "ân" in loi
            or "ăN" in loi or "âN" in loi or "ăm" in loi or "âm" in loi or "aJ" in loi or "iJ" in loi or "êJ" in loi
            or "yJ" in loi or "ôN" in loi or "uN" in loi or "oN" in loi or "aC" in loi or "iC" in loi or "êC" in loi
            or "yC" in loi)
        _C = (loi.startswith("f") or loi.startswith("K") or loi.startswith("l") or loi.startswith("m") or loi.startswith("n")
            or loi.startswith("J") or loi.startswith("N") or loi.startswith("s") or loi.startswith("v")
            or loi.startswith("z"))
        _Cw = (loi.startswith("Ku") or loi.startswith("Koa") or loi.startswith("Koe") or loi.startswith("Koă")
            or loi.startswith("su") or loi.startswith("soa") or loi.startswith("soe") or loi.startswith("soă")
            or loi.startswith("zu") or loi.startswith("zoa") or loi.startswith("zoe") or loi.startswith("zoă")
            or loi.startswith("Ky") or loi.startswith("Ki"))
        _CV = (loi.startswith("g") or loi.startswith("h") or loi.startswith("'") or loi.startswith("w") or loi.startswith("y")
            or loi.startswith("'"))
        wV = "oa" in loi or "oe" in loi or "uâ" in loi or "uê" in loi or "uy" in loi or "uơ" in loi or "oă" in loi
        VV_ = ((loi.endswith("ai") or loi.endswith("eo") or loi.endswith("ua") or loi.endswith("ưa") or loi.endswith("ơi") or loi.endswith("oi") or loi.endswith("ôi") or loi.endswith("ui") or loi.endswith("ưi") or loi.endswith("ya") or loi.endswith("êu") or loi.endswith("ưu") or loi.endswith("ao") or loi.endswith("ia") or loi.endswith("ua") or loi.endswith("ưa") or loi.endswith("iu") or loi.endswith("ai'") or loi.endswith("eo'") or loi.endswith("ua'") or loi.endswith("ưa'") or loi.endswith("ơi'") or loi.endswith("oi'") or loi.endswith("ôi'") or loi.endswith("ui'") or loi.endswith("ưi'") or loi.endswith("ya'") or loi.endswith("êu'") or loi.endswith("ưu'") or loi.endswith("ao'") or loi.endswith("ia'") or loi.endswith("ua'") or loi.endswith("ưa'") or loi.endswith("iu'"))
            and (note.lyric != "qua"))
        wAn = loi.startswith("K") or loi.startswith("z")
        H = (loi.startswith("b") or loi.startswith("d") or loi.startswith("k") or loi.startswith("l") or loi.startswith("t")
            or loi.startswith("T") or loi.startswith("C") or loi.startswith("m") or loi.startswith("n")
            or loi.startswith("J") or loi.startswith("N") or loi.startswith("h") or loi.startswith("g")
            or loi.startswith("."))
        if ViTriTB:
            ViTri = Medium
        if ViTriNgan:
            ViTri = Short
        if ViTriDai:
            ViTri = Long
        if loi.endswith("uôN"):
            ViTri = Short
        phoneme = ""
        dem = len(loi)
        phonemes = []
        if note.lyric.startswith("?"):
            phoneme = note.lyric[1:]
        elif prev_neighbour is None:
            if note.lyric == "qua":
                if NoNext:
                    phonemes.append(Phoneme(f"kwa"))
                    phonemes.append(Phoneme(f"a -", position=End))
                else:
                    phoneme = f"kwa"
            else:
                # 1 âm
                if dem == 1:
                    N = loi[0:1]
                    N = (N.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                        .replace("ô", "O").replace("ư", "U").replace("C", "ch").replace("K", "kh").replace("N", "ng")
                        .replace("J", "nh").replace("Z", "tr").replace("T", "th"))
                    if NoNext:
                        phonemes.append(Phoneme(f"- {N}"))
                        phonemes.append(Phoneme(f"{N} -", position=End))
                    else:
                        phonemes.append(Phoneme(f"- {N}"))
                # 2 âm CV, ví dụ: "ba"
                if (dem == 2) and tontaiC:
                    N = loi
                    N1 = loi[0:1]
                    N2 = loi[1:2]
                    N1 = (N1.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                        .replace("ô", "O").replace("ư", "U").replace("C", "ch").replace("K", "kh").replace("N", "ng")
                        .replace("J", "nh").replace("Z", "tr").replace("T", "th"))
                    if _Cw:
                        if N2 == "u":
                            N1 = N1 + "w"
                        if (N2 == "i") or (N2 == "y"):
                            N1 = N1 + "y"
                    N = (N.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                        .replace("ô", "O").replace("ư", "U").replace("C", "ch").replace("K", "kh").replace("N", "ng")
                        .replace("J", "nh").replace("Z", "tr").replace("T", "th"))
                    N2 = (N2.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                        .replace("ô", "O").replace("ư", "U"))
                    if _CV:
                        N = "- " + N
                    if NoNext:
                        # ko co note ke tiep
                        if _C:
                            # co - C
                            phonemes.append(Phoneme(f"- {N1}", position=VCP))
                            phonemes.append(Phoneme(f"{N}"))
                            phonemes.append(Phoneme(f"{N2} -", position=End))
                        else:
                            # ko co gi
                            phonemes.append(Phoneme(f"{N}"))
                            phonemes.append(Phoneme(f"{N2} -", position=End))
                    else:
                        # co note ke tiep
                        if _C:
                            # co - C
                            phonemes.append(Phoneme(f"- {N1}", position=VCP))
                            phonemes.append(Phoneme(f"{N}"))
                        else:
                            # ko co gi
                            phonemes.append(Phoneme(f"{N}"))
            # 3 âm CVV/CVC, ví dụ: "hoa" "hang" "hát"
            if fry:
                pass
            elif dem == 3 and tontaiC:
                C = loi[0:1]
                V1 = loi[1:2]
                V2 = loi[2:]
                V2_2 = V2
                Cw = C
                V1_1 = V1
                if loi.endswith("uy"):
                    V2 = "i"
                    V2_2 = V2
                kAn = loi.endswith("cân") or loi.endswith("kân")
                if V1 == "â":
                    V1 = "@"
                if V1 == "ă":
                    V1_1 = "ae"
                if wV and _Cw:
                    Cw = C + "w"
                    V1 = "w"
                elif wV:
                    V1 = "w"
                elif _Cw:
                    Cw = C + "w"
                if V1 == "i" and _Cw:
                    Cw = C + "y"
                Cw = (Cw.replace("C", "ch").replace("K", "kh").replace("N", "ng").replace("J", "nh").replace("Z", "tr")
                    .replace("T", "th"))
                C = (C.replace("C", "ch").replace("K", "kh").replace("N", "ng").replace("J", "nh").replace("Z", "tr")
                    .replace("T", "th"))
                V1 = (V1.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                    .replace("ô", "O").replace("ư", "U"))
                V2 = (V2.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                    .replace("ô", "O").replace("ư", "U").replace("C", "ch").replace("N", "ng").replace("J", "nh"))
                V2_2 = (V2_2.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("ê", "E").replace("ô", "O")
                    .replace("ư", "U").replace("C", "ch").replace("N", "ng").replace("J", "nh"))
                V1_1 = (V1_1.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("ê", "E").replace("ô", "O")
                    .replace("ư", "U").replace("C", "ch").replace("N", "ng").replace("J", "nh"))
                a = (loi.endswith("ia") or loi.endswith("ua") or loi.endswith("ưa") or loi.endswith("ya"))
                if a and note.lyric != "qua":
                    V2 = "@"
                    V2_2 = "@"
                N = V2
                if V1 + V2 == "Ong" or V1 + V2 == "ung" or V1 + V2 == "ong":
                    N = "ng0"
                if V1 + V2 == "Ai":
                    V2 = "y"
                    N = "i"
                if loi.endswith("ay"):
                    V2 = "y"
                    N = "i"
                if _CV:
                    C = "- " + C
                if tontaiCcuoi:
                    # co C cuoi (at, ac,...)
                    if _C:
                        # co - C
                        phonemes.append(Phoneme(f"- {Cw}", position=VCP))
                        phonemes.append(Phoneme(f"{C}{V1}"))
                        phonemes.append(Phoneme(f"{V1_1}{V2_2}", position=ViTri))
                    else:
                        # bths
                        phonemes.append(Phoneme(f"{C}{V1}"))
                        phonemes.append(Phoneme(f"{V1_1}{V2_2}", position=ViTri))
                elif kAn:
                    if NoNext:
                        phonemes.append(Phoneme(f"kAn"))
                        phonemes.append(Phoneme(f"n -", position=End))
                    else:
                        phonemes.append(Phoneme(f"kAn"))
                elif NoNext:
                    # ko co note ke tiep
                    if _C:
                        # co - C
                        if VV_:
                            phonemes.append(Phoneme(f"- {Cw}", position=VCP))
                            phonemes.append(Phoneme(f"{C}{V1}"))
                            phonemes.append(Phoneme(f"{V1_1}{V2} -", position=End))
                        elif wV:
                            phonemes.append(Phoneme(f"- {Cw}", position=VCP))
                            phonemes.append(Phoneme(f"{C}{V1}{V2_2}"))
                            phonemes.append(Phoneme(f"{V2} -", position=End))
                        else:
                            # bths
                            phonemes.append(Phoneme(f"- {Cw}", position=VCP))
                            phonemes.append(Phoneme(f"{C}{V1}"))
                            phonemes.append(Phoneme(f"{V1_1}{V2_2}", position=ViTri))
                            phonemes.append(Phoneme(f"{N} -", position=End))
                    else:
                        # ko - C, - CV
                        if VV_:
                            phonemes.append(Phoneme(f"{C}{V1}"))
                            phonemes.append(Phoneme(f"{V1_1}{V2} -", position=End))
                        elif wV:
                            phonemes.append(Phoneme(f"{C}{V1}{V2_2}"))
                            phonemes.append(Phoneme(f"{V2} -", position=End))
                        else:
                            # bths
                            phonemes.append(Phoneme(f"{C}{V1}"))
                            phonemes.append(Phoneme(f"{V1_1}{V2_2}", position=ViTri))
                            phonemes.append(Phoneme(f"{N} -", position=End))
                else:
                    # co note ke tiep
                    if _C:
                        # co - C
                        if VV_:
                            phonemes.append(Phoneme(f"- {Cw}", position=VCP))
                            phonemes.append(Phoneme(f"{C}{V1}"))
                            phonemes.append(Phoneme(f"{V1_1}{V2_2}", position=ViTri))
                        elif wV:
                            phonemes.append(Phoneme(f"- {Cw}", position=VCP))
                            phonemes.append(Phoneme(f"{C}{V1}{V2_2}"))
                        else:
                            # bths
                            phonemes.append(Phoneme(f"- {Cw}", position=VCP))
                            phonemes.append(Phoneme(f"{C}{V1}"))
                            phonemes.append(Phoneme(f"{V1_1}{V2_2}", position=ViTri))
                    else:
                        # bth ko - C, ko - CV
                        if VV_:
                            phonemes.append(Phoneme(f"{C}{V1}"))
                            phonemes.append(Phoneme(f"{V1_1}{V2_2}", position=ViTri))
                        elif wV:
                            phonemes.append(Phoneme(f"{C}{V1}{V2_2}"))
                        else:
                            # bths
                            phonemes.append(Phoneme(f"{C}{V1}"))
                            phonemes.append(Phoneme(f"{V1_1}{V2_2}", position=ViTri))
            # 4 âm VVVC có VVC liền, chia 3 nốt, ví dụ "uyết" "uyên"
            if fry:
                pass
            elif dem == 4 and kocoC and tontaiVVC:
                V1 = loi[0:1]
                V2 = loi[1:2]
                VVC = loi[1:]
                C = loi[3:]
                if V1 == "u":
                    V1 = "w"
                V1 = (V1.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                    .replace("ô", "O").replace("ư", "U"))
                V2 = (V2.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                    .replace("ô", "O").replace("ư", "U"))
                VVC = (VVC.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                    .replace("ô", "O").replace("ư", "U").replace("C", "ch").replace("N", "ng").replace("J", "nh"))
                C = C.replace("C", "ch").replace("N", "ng").replace("J", "nh")
                if NoNext and tontaiCcuoi:
                    phonemes.append(Phoneme(f"- {V1}{V2}"))
                    phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                elif NoNext:
                    phonemes.append(Phoneme(f"- {V1}{V2}"))
                    phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                    phonemes.append(Phoneme(f"{C} -", position=End))
                else:
                    phonemes.append(Phoneme(f"- {V1}{V2}"))
                    phonemes.append(Phoneme(f"{VVC}", position=ViTri))
            # 4 âm CVVC/CVVV, chia 3 nốt, ví dụ "thoát" "toan" "toại"
            if tontaiVVC:
                pass
            elif fry:
                pass
            elif dem == 4 and tontaiC:
                C = loi[0:1]
                Cw = C
                V1 = loi[1:2]
                V2 = loi[2:3]
                V2_2 = V2
                VC = loi[2:]
                N = loi[3:]
                N_ = N
                a = (loi.endswith("ia") or loi.endswith("ua") or loi.endswith("ưa") or loi.endswith("ya"))
                if a and note.lyric != "qua":
                    N = "@"
                    N_ = "@"
                if V1 == "u":
                    V1 = "w"
                if wV and _Cw:
                    Cw = C + "w"
                    V1 = "w"
                elif wV:
                    V1 = "w"
                if V1 == "i":
                    Cw = C + "y"
                if V2 == "ă":
                    V2_2 = "ae"
                C = (C.replace("C", "ch").replace("K", "kh").replace("N", "ng").replace("J", "nh").replace("Z", "tr")
                    .replace("T", "th"))
                Cw = (Cw.replace("C", "ch").replace("K", "kh").replace("N", "ng").replace("J", "nh").replace("Z", "tr")
                    .replace("T", "th"))
                V1 = (V1.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                    .replace("ô", "O").replace("ư", "U"))
                V2 = (V2.replace("ă", "a").replace("â", "@").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                    .replace("ô", "O").replace("ư", "U"))
                VC = (VC.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                    .replace("ô", "O").replace("ư", "U").replace("C", "ch").replace("N", "ng").replace("J", "nh"))
                N = (N.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("ê", "E").replace("ô", "O")
                    .replace("ư", "U").replace("C", "ch").replace("N", "ng").replace("J", "nh"))
                N_ = (N_.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                    .replace("ô", "O").replace("ư", "U").replace("C", "ch").replace("N", "ng").replace("J", "nh"))
                if _CV:
                    C = "- " + C
                if tontaiCcuoi:
                    # có C ngắt
                    if _C:
                        phonemes.append(Phoneme(f"- {Cw}", position=VCP))
                        phonemes.append(Phoneme(f"{C}{V1}{V2}"))
                        phonemes.append(Phoneme(f"{VC}", position=ViTri))
                    else:
                        phonemes.append(Phoneme(f"{C}{V1}{V2}"))
                        phonemes.append(Phoneme(f"{VC}", position=ViTri))
                elif note.lyric.endswith("uân") or note.lyric.endswith("uâng"):
                    if wAn == False:
                        if NoNext:
                            if loi.startswith("."):
                                phonemes.append(Phoneme(f"{C}w@"))
                                phonemes.append(Phoneme(f"A{N}", position=ViTri))
                                phonemes.append(Phoneme(f"{N_} -", position=End))
                            elif _C:
                                phonemes.append(Phoneme(f"- {Cw}", position=VCP))
                                phonemes.append(Phoneme(f"{C}wA{N}"))
                                phonemes.append(Phoneme(f"{N_} -", position=End))
                            else:
                                phonemes.append(Phoneme(f"{C}wA{N}"))
                                phonemes.append(Phoneme(f"{N_} -", position=End))
                        else:
                            # 
                            if loi.startswith("."):
                                phonemes.append(Phoneme(f"{C}w@"))
                                phonemes.append(Phoneme(f"A{N}", position=ViTri))
                            elif _C:
                                phonemes.append(Phoneme(f"- {Cw}", position=VCP))
                                phonemes.append(Phoneme(f"{C}wA{N}"))
                            else:
                                phonemes.append(Phoneme(f"{C}wA{N}"))
                    else:
                        # khuân luân
                        if NoNext:
                            if _C:
                                phonemes.append(Phoneme(f"- {Cw}", position=VCP))
                                phonemes.append(Phoneme(f"{C}w"))
                                phonemes.append(Phoneme(f"_w@", position=Long))
                                phonemes.append(Phoneme(f"A{N}", position=Medium))
                                phonemes.append(Phoneme(f"{N_} -", position=End))
                            else:
                                phonemes.append(Phoneme(f"{C}w"))
                            phonemes.append(Phoneme(f"_w@", position=Long))
                            phonemes.append(Phoneme(f"A{N}", position=Medium))
                            phonemes.append(Phoneme(f"{N_} -", position=End))
                        else:
                            # 
                            if _C:
                                phonemes.append(Phoneme(f"- {Cw}", position=VCP))
                                phonemes.append(Phoneme(f"{C}w"))
                                phonemes.append(Phoneme(f"_w@", position=Long))
                                phonemes.append(Phoneme(f"A{N}", position=Medium))
                            else:
                                phonemes.append(Phoneme(f"{C}w"))
                                phonemes.append(Phoneme(f"_w@", position=Long))
                                phonemes.append(Phoneme(f"A{N}", position=Medium))
                elif NoNext:
                    if VV_:
                        if _C:
                            phonemes.append(Phoneme(f"- {Cw}", position=VCP))
                            phonemes.append(Phoneme(f"{C}{V1}{V2}"))
                            phonemes.append(Phoneme(f"{V2}{N_} -", position=End))
                        else:
                            phonemes.append(Phoneme(f"{C}{V1}{V2}"))
                            phonemes.append(Phoneme(f"{V2}{N_} -", position=End))
                    else:
                        # ko có VV -
                        if _C:
                            phonemes.append(Phoneme(f"- {Cw}", position=VCP))
                            phonemes.append(Phoneme(f"{C}{V1}{V2}"))
                            phonemes.append(Phoneme(f"{V2_2}{N}", position=ViTri))
                            phonemes.append(Phoneme(f"{N_} -", position=End))
                        else:
                            phonemes.append(Phoneme(f"{C}{V1}{V2}"))
                            phonemes.append(Phoneme(f"{V2_2}{N}", position=ViTri))
                            phonemes.append(Phoneme(f"{N_} -", position=End))
                else:
                    if VV_:
                        if _C:
                            phonemes.append(Phoneme(f"- {Cw}", position=VCP))
                            phonemes.append(Phoneme(f"{C}{V1}{V2}"))
                            phonemes.append(Phoneme(f"{V2}{N}", position=ViTri))
                        else:
                            phonemes.append(Phoneme(f"{C}{V1}{V2}"))
                            phonemes.append(Phoneme(f"{V2}{N}", position=ViTri))
                    else:
                        # ko có VV -
                        if _C:
                            phonemes.append(Phoneme(f"- {Cw}", position=VCP))
                            phonemes.append(Phoneme(f"{C}{V1}{V2}"))
                            phonemes.append(Phoneme(f"{V2_2}{N}", position=ViTri))
                        else:
                            phonemes.append(Phoneme(f"{C}{V1}{V2}"))
                            phonemes.append(Phoneme(f"{V2_2}{N}", position=ViTri))
            # 4 âm CVVC/CVVV, (tiên, tiết)
            if fry:
                pass
            elif dem == 4 and tontaiVVC and tontaiC:
                C = loi[0:1]
                Cw = C
                V1 = loi[1:2]
                VVC = loi[1:]
                N = loi[3:]
                if V1 == "i" and _Cw:
                    Cw = C + "y"
                C = (C.replace("C", "ch").replace("K", "kh").replace("N", "ng").replace("J", "nh").replace("Z", "tr")
                    .replace("T", "th"))
                Cw = (Cw.replace("C", "ch").replace("K", "kh").replace("N", "ng").replace("J", "nh").replace("Z", "tr")
                    .replace("T", "th"))
                V1 = (V1.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                    .replace("ô", "O").replace("ư", "U"))
                VVC = (VVC.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                    .replace("ô", "O").replace("ư", "U").replace("C", "ch").replace("N", "ng").replace("J", "nh"))
                N = N.replace("N", "ng").replace("J", "nh")
                if _CV:
                    C = "- " + C
                if tontaiCcuoi:
                    # có C ngắt
                    if _C:
                        phonemes.append(Phoneme(f"- {Cw}", position=VCP))
                        phonemes.append(Phoneme(f"{C}{V1}"))
                        phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                    else:
                        phonemes.append(Phoneme(f"{C}{V1}"))
                        phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                elif NoNext:
                    # ko có note kế tiếp
                    if _C:
                        phonemes.append(Phoneme(f"- {Cw}", position=VCP))
                        phonemes.append(Phoneme(f"{C}{V1}"))
                        phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                        phonemes.append(Phoneme(f"{N} -", position=End))
                    else:
                        phonemes.append(Phoneme(f"{C}{V1}"))
                        phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                        phonemes.append(Phoneme(f"{N} -", position=End))
                else:
                    # có note kế tiếp
                    if _C:
                        phonemes.append(Phoneme(f"- {Cw}", position=VCP))
                        phonemes.append(Phoneme(f"{C}{V1}"))
                        phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                    else:
                        phonemes.append(Phoneme(f"{C}{V1}"))
                        phonemes.append(Phoneme(f"{VVC}", position=ViTri))
            # 5 âm CVVVC, có VVC liền, chia 3 nốt, ví dụ "thuyết"
            if fry:
                pass
            elif dem == 5 and tontaiVVC and tontaiC:
                C = loi[0:1]
                Cw = C
                V1 = loi[1:2]
                V2 = loi[2:3]
                VVC = loi[2:]
                N = loi[4:]
                if wV and _Cw:
                    Cw = C + "w"
                    V1 = "w"
                elif wV:
                    V1 = "w"
                if V1 == "i":
                    Cw = C + "y"
                C = (C.replace("C", "ch").replace("K", "kh").replace("N", "ng").replace("J", "nh").replace("Z", "tr")
                    .replace("T", "th"))
                Cw = (Cw.replace("C", "ch").replace("K", "kh").replace("N", "ng").replace("J", "nh").replace("Z", "tr")
                    .replace("T", "th"))
                V1 = (V1.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                    .replace("ô", "O").replace("ư", "U"))
                V2 = (V2.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                    .replace("ô", "O").replace("ư", "U"))
                VVC = (VVC.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                    .replace("ô", "O").replace("ư", "U").replace("C", "ch").replace("N", "ng").replace("J", "nh"))
                N = N.replace("N", "ng").replace("J", "nh")
                if _CV:
                    C = "- " + C
                if tontaiCcuoi:
                    # có C ngắt
                    if _C:
                        phonemes.append(Phoneme(f"- {Cw}", position=VCP))
                        phonemes.append(Phoneme(f"{C}{V1}{V2}"))
                        phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                    else:
                        phonemes.append(Phoneme(f"{C}{V1}{V2}"))
                        phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                elif NoNext:
                    # ko có note kế tiếp
                    if _C:
                        phonemes.append(Phoneme(f"- {Cw}", position=VCP))
                        phonemes.append(Phoneme(f"{C}{V1}{V2}"))
                        phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                        phonemes.append(Phoneme(f"{N} -", position=End))
                    else:
                        phonemes.append(Phoneme(f"{C}{V1}{V2}"))
                    phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                    phonemes.append(Phoneme(f"{N} -", position=End))
                else:
                    # có note kế tiếp
                    if _C:
                        phonemes.append(Phoneme(f"- {Cw}", position=VCP))
                        phonemes.append(Phoneme(f"{C}{V1}{V2}"))
                        phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                    else:
                        phonemes.append(Phoneme(f"{C}{V1}{V2}"))
                        phonemes.append(Phoneme(f"{VVC}", position=ViTri))
            if BR:
                num = loi[5:]
                if num == "":
                    num = "1"
                if prev_neighbour is None:
                    phonemes.append(Phoneme(f"breath{num}"))
            if note.lyric.startswith("y") and koVVCchia:
                if dem == 2:
                    # ya
                    C = note.lyric[0:1]
                    V = note.lyric[1:2]
                    V = (V.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                        .replace("ô", "O").replace("ư", "U").replace("C", "ch").replace("N", "ng").replace("J", "nh"))
                    if NoNext:
                        phonemes.append(Phoneme(f"- {C}{V}"))
                        phonemes.append(Phoneme(f"{V} -", position=ViTri))
                    else:
                        phonemes.append(Phoneme(f"- {C}{V}"))
                elif dem == 3:
                    C = note.lyric[0:1]
                    V1 = note.lyric[1:2]
                    V2 = note.lyric[2:3]
                    V1 = (V1.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                        .replace("ô", "O").replace("ư", "U").replace("C", "ch").replace("N", "ng").replace("J", "nh"))
                    V2 = (V2.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                        .replace("ô", "O").replace("ư", "U").replace("C", "ch").replace("N", "ng").replace("J", "nh"))
                    if wV:
                        V1 = "w"
                    a = (loi.endswith("ia") or loi.endswith("ua") or loi.endswith("ưa") or loi.endswith("ya"))
                    if a and note.lyric != "qua":
                        V2 = "@"
                    N = V2
                    if V1 + V2 == "Ong" or V1 + V2 == "ung" or V1 + V2 == "ong":
                        N = "ng0"
                    if V1 + V2 == "Ai":
                        V2 = "y"
                        N = "i"
                    if loi.endswith("ay"):
                        V2 = "y"
                        N = "i"
                    if tontaiCcuoi:
                        phonemes.append(Phoneme(f"- {C}{V1}"))
                        phonemes.append(Phoneme(f"{V1}{V2}", position=ViTri))
                    elif NoNext:
                        if VV_:
                            phonemes.append(Phoneme(f"- {C}{V1}"))
                            phonemes.append(Phoneme(f"{V1}{V2} -", position=End))
                        elif wV:
                            phonemes.append(Phoneme(f"- {C}{V1}{V2}"))
                            phonemes.append(Phoneme(f"{V2} -", position=End))
                        else:
                            phonemes.append(Phoneme(f"- {C}{V1}"))
                            phonemes.append(Phoneme(f"{V1}{V2}", position=ViTri))
                            phonemes.append(Phoneme(f"{V2} -", position=End))
                    elif wV:
                        phonemes.append(Phoneme(f"- {C}{V1}{V2}"))
                    else:
                        phonemes.append(Phoneme(f"- {C}{V1}"))
                        phonemes.append(Phoneme(f"{V1}{V2}", position=ViTri))
            else:
                # phụ âm y
                # nếu ko phải phụ âm y
                # 2 âm VV, ví dụ: "oa"
                if fry:
                    pass
                elif (dem == 2) and kocoC:
                    V1 = loi[0:1]
                    V1_ = V1
                    V2 = loi[1:2]
                    N = V2
                    if loi.startswith("uy"):
                        V2 = "i"
                    if V1 + V2 == "ôN" or V1 + V2 == "uN" or V1 + V2 == "oN":
                        N = "ng0"
                    if V2 == "y":
                        N = "i"
                    if wV:
                        V1 = "w"
                    if V1 == "â":
                        V1 = "@"
                    if V1 + V2 == "ia" or V1 + V2 == "ua" or V1 + V2 == "ưa":
                        N = "@"
                    if V1 == "ă":
                        V1_ = "ae"
                    V1 = (V1.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                        .replace("ô", "O").replace("ư", "U"))
                    V1_ = (V1_.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                        .replace("ô", "O").replace("ư", "U"))
                    V2 = (V2.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("ê", "E").replace("ô", "O")
                        .replace("ư", "U").replace("C", "ch").replace("N", "ng").replace("J", "nh"))
                    N = (N.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("ê", "E").replace("ô", "O")
                        .replace("ư", "U").replace("C", "ch").replace("N", "ng").replace("J", "nh"))
                    a = (loi.endswith("ia") or loi.endswith("ua") or loi.endswith("ưa"))
                    if a:
                        V2 = "@"
                    if tontaiCcuoi:
                        phonemes.append(Phoneme(f"- {V1}"))
                        phonemes.append(Phoneme(f"{V1}{V2}", position=ViTri))
                    elif NoNext:
                        # ko co note ke tiep
                        if wV:
                            # oa oe uê ,...
                            phonemes.append(Phoneme(f"- {V1}{V2}"))
                            phonemes.append(Phoneme(f"{N} -", position=End))
                        elif VV_:
                            # ai eo êu ao,...
                            phonemes.append(Phoneme(f"- {V1}"))
                            phonemes.append(Phoneme(f"{V1}{N} -", position=End))
                        else:
                            # an anh
                            phonemes.append(Phoneme(f"- {V1}"))
                            phonemes.append(Phoneme(f"{V1_}{V2}", position=ViTri))
                            phonemes.append(Phoneme(f"{N} -", position=End))
                    else:
                        # co note ke tiep
                        if wV:
                            # oa oe uê ,...
                            phonemes.append(Phoneme(f"- {V1}{V2}"))
                        elif VV_:
                            # ai eo êu ao,...
                            phonemes.append(Phoneme(f"- {V1}"))
                            phonemes.append(Phoneme(f"{V1}{N}", position=ViTri))
                        else:
                            # an anh
                            phonemes.append(Phoneme(f"- {V1}"))
                            phonemes.append(Phoneme(f"{V1_}{V2}", position=ViTri))
                # 3 âm VVC/VVV, ví dụ: "oát" "oan" "oai"
                if fry:
                    pass
                elif (dem == 3) and koVVCchia and kocoC:
                    V1 = loi[0:1]
                    V2 = loi[1:2]
                    V2_2 = V2
                    V3 = loi[2:3]
                    a = (loi.endswith("ia") or loi.endswith("ua") or loi.endswith("ưa") or loi.endswith("ya"))
                    if a and note.lyric != "qua":
                        V3 = "@"
                    if wV:
                        V1 = "w"
                    if V2 == "ă":
                        V2_2 = "ae"
                    if V2 == "â":
                        V2 = "@"
                    V1 = (V1.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                        .replace("ô", "O").replace("ư", "U"))
                    V2 = (V2.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                        .replace("ô", "O").replace("ư", "U"))
                    V2_2 = (V2_2.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                        .replace("ô", "O").replace("ư", "U"))
                    V3 = (V3.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("ê", "E").replace("ô", "O")
                        .replace("ư", "U").replace("C", "ch").replace("N", "ng").replace("J", "nh"))
                    N = V3
                    if V2 + V3 == "Ong" or V2 + V3 == "ung" or V2 + V3 == "ong":
                        N = "ng0"
                    if V3 == "y":
                        N = "i"
                    if tontaiCcuoi and wV:
                        phonemes.append(Phoneme(f"- {V1}{V2}"))
                        phonemes.append(Phoneme(f"{V2}{V3}", position=ViTri))
                    elif NoNext:
                        # ko co note ke tiep
                        if wV and VV_:
                            phonemes.append(Phoneme(f"- {V1}{V2}"))
                            phonemes.append(Phoneme(f"{V2_2}{N} -", position=End))
                        elif wV:
                            phonemes.append(Phoneme(f"- {V1}{V2}"))
                            phonemes.append(Phoneme(f"{V2_2}{V3}", position=ViTri))
                            phonemes.append(Phoneme(f"{N} -", position=End))
                    else:
                        # co note ke tiep
                        if wV:
                            phonemes.append(Phoneme(f"- {V1}{V2}"))
                            phonemes.append(Phoneme(f"{V2_2}{V3}", position=ViTri))
                # 3 âm VVV/VVC chia 2 nốt, ví dụ: "yên" "ướt"
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
                        phonemes.append(Phoneme(f"- {V1}"))
                        phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                    elif NoNext:
                        phonemes.append(Phoneme(f"- {V1}"))
                        phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                        phonemes.append(Phoneme(f"{C} -", position=End))
                    else:
                        phonemes.append(Phoneme(f"- {V1}"))
                        phonemes.append(Phoneme(f"{VVC}", position=ViTri))
        elif prev_neighbour is not None:
            lyric = prev_neighbour.phonetic_hint if prev_neighbour.phonetic_hint is not None else prev_neighbour.lyric
            unicode = to_unicode_elements(lyric)
            vow = VOWEL_LOOKUP.get(unicode[-1] if unicode else "")
            if vow is not None:
                PR = prev_neighbour.lyric
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
                if loi == "R":
                    a = (PR.endswith("ua") or PR.endswith("ưa") or PR.endswith("ia") or PR.endswith("uya"))
                    if a:
                        vow = "@"
                else:
                    a = (PR.endswith("ua") or PR.endswith("ưa") or PR.endswith("ia") or PR.endswith("uya"))
                    if a:
                        vow = "@0"
                    a = PR.endswith("breaT")
                    if a:
                        vow = "-"
                    if PR.endswith("ao") or PR.endswith("eo") or PR.endswith("êu") or PR.endswith("iu") or PR.endswith("ưu"):
                        vow = "u0"
                    if (PR.endswith("ai") or PR.endswith("ơi") or PR.endswith("oi") or PR.endswith("ôi")
                        or PR.endswith("ui") or PR.endswith("ưi")):
                        vow = "i0"
                ng0 = (PR.endswith("uN") or PR.endswith("ôN") or PR.endswith("oN"))
                if PR.endswith("uôN"):
                    vow = "ng"
                elif ng0:
                    vow = "ng0"
                prevtontaiCcuoi = PR.endswith("t") or PR.endswith("C") or PR.endswith("p") or PR.endswith("k") or PR.endswith("'")
                if prevtontaiCcuoi and _C:
                    if PR.endswith("t"):
                        vow = "t"
                    if PR.endswith("C"):
                        vow = "ch"
                    if PR.endswith("p"):
                        vow = "p"
                    if PR.endswith("k"):
                        vow = "k"
                    if PR.endswith("'"):
                        vow = "-"
                B1 = PR[len(PR) - 1:]
                B2 = loi[0:1]
                M = (B1 == B2) and vow != "ng0"
                NoVCP = (H and prevtontaiCcuoi) or M
                Cvoiced = PR.endswith("J") or PR.endswith("n") or PR.endswith("m") or PR.endswith("N")
                if prevtontaiCcuoi == True:
                    prevkocoCcuoi = False
                else:
                    prevkocoCcuoi = True
                if note.lyric.startswith("?"):
                    phoneme = note.lyric[1:]
                else:
                    if note.lyric == "qua":
                        if NoVCP:
                            if NoNext:
                                phonemes.append(Phoneme(f"kwa"))
                                phonemes.append(Phoneme(f"a -", position=End))
                            else:
                                phonemes.append(Phoneme(f"kwa"))
                        elif NoNext:
                            phonemes.append(Phoneme(f"{vow} k", position=VCP))
                            phonemes.append(Phoneme(f"kwa"))
                            phonemes.append(Phoneme(f"a -", position=End))
                        else:
                            phonemes.append(Phoneme(f"{vow} k", position=VCP))
                            phonemes.append(Phoneme(f"kwa"))
                    else:
                        # 1 âm
                        if dem == 1 and loi != "R":
                            N = loi
                            N = (N.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                                .replace("ô", "O").replace("ư", "U").replace("C", "ch").replace("K", "kh").replace("N", "ng")
                                .replace("J", "nh").replace("Z", "tr").replace("T", "th"))
                            N2 = N
                            A = (vow == "o" or vow == "O" or vow == "u")
                            if A and loi == "ng":
                                N2 = "ng0"
                            if loi == "N" or loi == "n" or loi == "J" or loi == "m":
                                pass
                            else:
                                vow = vow + " "
                            if (loi == "N" or loi == "n" or loi == "J" or loi == "m") and prevtontaiCcuoi:
                                vow = "- "
                            elif prevtontaiCcuoi:
                                vow = "."
                            if NoNext:
                                phonemes.append(Phoneme(f"{vow}{N}"))
                                phonemes.append(Phoneme(f"{N2} -", position=End))
                            else:
                                phonemes.append(Phoneme(f"{vow}{N}"))
                        if note.lyric == "R":
                            # R
                            phonemes.append(Phoneme(f"{vow} --"))
                        # 2 âm CV, ví dụ: "ba"
                        if (dem == 2) and tontaiC:
                            N = loi
                            N1 = loi[0:1]
                            N2 = loi[1:2]
                            N1 = (N1.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                                .replace("ô", "O").replace("ư", "U").replace("C", "ch").replace("K", "kh").replace("N", "ng")
                                .replace("J", "nh").replace("Z", "tr").replace("T", "th"))
                            if _Cw:
                                if N2 == "u":
                                    N1 = N1 + "w"
                                if (N2 == "i") or (N2 == "y"):
                                    N1 = N1 + "y"
                            N = (N.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                                .replace("ô", "O").replace("ư", "U").replace("C", "ch").replace("K", "kh").replace("N", "ng")
                                .replace("J", "nh").replace("Z", "tr").replace("T", "th"))
                            N2 = (N2.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                                .replace("ô", "O").replace("ư", "U"))
                            if _CV and prevtontaiCcuoi:
                                N = "- " + N
                            vow = vow + " "
                            if NoNext:
                                # ko co note ke tiep
                                if NoVCP:
                                    phonemes.append(Phoneme(f"{N}"))
                                    phonemes.append(Phoneme(f"{N2} -", position=End))
                                else:
                                    phonemes.append(Phoneme(f"{vow}{N1}", position=VCP))
                                    phonemes.append(Phoneme(f"{N}"))
                                    phonemes.append(Phoneme(f"{N2} -", position=End))
                            else:
                                # co note ke tiep
                                if NoVCP:
                                    # co - C
                                    phonemes.append(Phoneme(f"{N}"))
                                else:
                                    # ko co gi
                                    phonemes.append(Phoneme(f"{vow}{N1}", position=VCP))
                                    phonemes.append(Phoneme(f"{N}"))
                        # 3 âm CVV/CVC, ví dụ: "hoa" "hang" "hát"
                        if fry:
                            pass
                        elif dem == 3 and tontaiC:
                            C = loi[0:1]
                            V1 = loi[1:2]
                            V2 = loi[2:]
                            V2_2 = V2
                            Cw = C
                            V1_1 = V1
                            if loi.endswith("uy"):
                                V2 = "i"
                                V2_2 = V2
                            kAn = loi.endswith("cân") or loi.endswith("kân")
                            if V1 == "â":
                                V1 = "@"
                            if V1 == "ă":
                                V1_1 = "ae"
                            if wV and _Cw:
                                Cw = C + "w"
                                V1 = "w"
                            elif wV:
                                V1 = "w"
                            elif _Cw:
                                Cw = C + "w"
                            if V1 == "i" and _Cw:
                                Cw = C + "y"
                            Cw = (Cw.replace("C", "ch").replace("K", "kh").replace("N", "ng").replace("J", "nh")
                                .replace("Z", "tr").replace("T", "th"))
                            C = (C.replace("C", "ch").replace("K", "kh").replace("N", "ng").replace("J", "nh")
                                .replace("Z", "tr").replace("T", "th"))
                            V1 = (V1.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                                .replace("ô", "O").replace("ư", "U"))
                            V2 = (V2.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                                .replace("ô", "O").replace("ư", "U").replace("C", "ch").replace("N", "ng").replace("J", "nh"))
                            V2_2 = (V2_2.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("ê", "E")
                                .replace("ô", "O").replace("ư", "U").replace("C", "ch").replace("N", "ng").replace("J", "nh"))
                            V1_1 = (V1_1.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("ê", "E")
                                .replace("ô", "O").replace("ư", "U").replace("C", "ch").replace("N", "ng").replace("J", "nh"))
                            a = (loi.endswith("ia") or loi.endswith("ua") or loi.endswith("ưa") or loi.endswith("ya"))
                            if a and note.lyric != "qua":
                                V2 = "@"
                                V2_2 = "@"
                            N = V2
                            if V1 + V2 == "Ong" or V1 + V2 == "ung" or V1 + V2 == "ong":
                                N = "ng0"
                            if V1 + V2 == "Ai":
                                V2 = "y"
                                N = "i"
                            if loi.endswith("ay"):
                                V2 = "y"
                                N = "i"
                            if _CV and prevtontaiCcuoi:
                                C = "- " + C
                            vow = vow + " "
                            if NoVCP:
                                if tontaiCcuoi:
                                    # co C cuoi (at, ac,...)
                                    phonemes.append(Phoneme(f"{C}{V1}"))
                                    phonemes.append(Phoneme(f"{V1_1}{V2_2}", position=ViTri))
                                elif kAn:
                                    if NoNext:
                                        phonemes.append(Phoneme(f"kAn"))
                                        phonemes.append(Phoneme(f"n -", position=End))
                                    else:
                                        phonemes.append(Phoneme(f"kAn"))
                                elif NoNext:
                                    # ko co note ke tiep
                                    if VV_:
                                        phonemes.append(Phoneme(f"{C}{V1}"))
                                        phonemes.append(Phoneme(f"{V1_1}{V2} -", position=End))
                                    elif wV:
                                        phonemes.append(Phoneme(f"{C}{V1}{V2_2}"))
                                        phonemes.append(Phoneme(f"{V2} -", position=End))
                                    else:
                                        # bths
                                        phonemes.append(Phoneme(f"{C}{V1}"))
                                        phonemes.append(Phoneme(f"{V1_1}{V2_2}", position=ViTri))
                                        phonemes.append(Phoneme(f"{N} -", position=End))
                                else:
                                    # co note ke tiep
                                    if VV_:
                                        phonemes.append(Phoneme(f"{C}{V1}"))
                                        phonemes.append(Phoneme(f"{V1_1}{V2_2}", position=ViTri))
                                    elif wV:
                                        phonemes.append(Phoneme(f"{C}{V1}{V2_2}"))
                                    else:
                                        phonemes.append(Phoneme(f"{C}{V1}"))
                                        phonemes.append(Phoneme(f"{V1_1}{V2_2}", position=ViTri))
                            elif tontaiCcuoi:
                                # co C cuoi (at, ac,...)
                                if _C:
                                    # co - C
                                    phonemes.append(Phoneme(f"{vow}{Cw}", position=VCP))
                                    phonemes.append(Phoneme(f"{C}{V1}"))
                                    phonemes.append(Phoneme(f"{V1_1}{V2_2}", position=ViTri))
                                else:
                                    # bths
                                    phonemes.append(Phoneme(f"{vow}{Cw}", position=VCP))
                                    phonemes.append(Phoneme(f"{C}{V1}"))
                                    phonemes.append(Phoneme(f"{V1_1}{V2_2}", position=ViTri))
                            elif kAn:
                                if NoNext:
                                    phonemes.append(Phoneme(f"{vow}k", position=VCP))
                                    phonemes.append(Phoneme(f"kAn"))
                                    phonemes.append(Phoneme(f"n -", position=End))
                                else:
                                    phonemes.append(Phoneme(f"{vow}k", position=VCP))
                                    phonemes.append(Phoneme(f"kAn"))
                            elif NoNext:
                                # ko co note ke tiep
                                if _C:
                                    # co - C
                                    if VV_:
                                        phonemes.append(Phoneme(f"{vow}{Cw}", position=VCP))
                                        phonemes.append(Phoneme(f"{C}{V1}"))
                                        phonemes.append(Phoneme(f"{V1_1}{V2} -", position=End))
                                    elif wV:
                                        phonemes.append(Phoneme(f"{vow}{Cw}", position=VCP))
                                        phonemes.append(Phoneme(f"{C}{V1}{V2_2}"))
                                        phonemes.append(Phoneme(f"{V2} -", position=End))
                                    else:
                                        # bths
                                        phonemes.append(Phoneme(f"{vow}{Cw}", position=VCP))
                                        phonemes.append(Phoneme(f"{C}{V1}"))
                                        phonemes.append(Phoneme(f"{V1_1}{V2_2}", position=ViTri))
                                        phonemes.append(Phoneme(f"{N} -", position=End))
                                else:
                                    # ko - C, - CV
                                    if VV_:
                                        phonemes.append(Phoneme(f"{vow}{Cw}", position=VCP))
                                        phonemes.append(Phoneme(f"{C}{V1}"))
                                        phonemes.append(Phoneme(f"{V1_1}{V2} -", position=End))
                                    elif wV:
                                        phonemes.append(Phoneme(f"{vow}{Cw}", position=VCP))
                                        phonemes.append(Phoneme(f"{C}{V1}{V2_2}"))
                                        phonemes.append(Phoneme(f"{V2} -", position=End))
                                    else:
                                        # bths
                                        phonemes.append(Phoneme(f"{vow}{Cw}", position=VCP))
                                        phonemes.append(Phoneme(f"{C}{V1}"))
                                        phonemes.append(Phoneme(f"{V1_1}{V2_2}", position=ViTri))
                                        phonemes.append(Phoneme(f"{N} -", position=End))
                            else:
                                # co note ke tiep
                                if _C:
                                    # co - C
                                    if VV_:
                                        phonemes.append(Phoneme(f"{vow}{Cw}", position=VCP))
                                        phonemes.append(Phoneme(f"{C}{V1}"))
                                        phonemes.append(Phoneme(f"{V1_1}{V2_2}", position=ViTri))
                                    elif wV:
                                        phonemes.append(Phoneme(f"{vow}{Cw}", position=VCP))
                                        phonemes.append(Phoneme(f"{C}{V1}{V2_2}"))
                                    else:
                                        # bths
                                        phonemes.append(Phoneme(f"{vow}{Cw}", position=VCP))
                                        phonemes.append(Phoneme(f"{C}{V1}"))
                                        phonemes.append(Phoneme(f"{V1_1}{V2_2}", position=ViTri))
                                else:
                                    # bth ko - C, ko - CV
                                    if VV_:
                                        phonemes.append(Phoneme(f"{vow}{Cw}", position=VCP))
                                        phonemes.append(Phoneme(f"{C}{V1}"))
                                        phonemes.append(Phoneme(f"{V1_1}{V2_2}", position=ViTri))
                                    elif wV:
                                        phonemes.append(Phoneme(f"{vow}{Cw}", position=VCP))
                                        phonemes.append(Phoneme(f"{C}{V1}{V2_2}"))
                                    else:
                                        # 
                                        phonemes.append(Phoneme(f"{vow}{Cw}", position=VCP))
                                        phonemes.append(Phoneme(f"{C}{V1}"))
                                        phonemes.append(Phoneme(f"{V1_1}{V2_2}", position=ViTri))
                        # 4 âm VVVC có VVC liền, chia 3 nốt, ví dụ "uyết" "uyên"
                        if fry:
                            pass
                        elif dem == 4 and kocoC and tontaiVVC:
                            V1 = loi[0:1]
                            V2 = loi[1:2]
                            VVC = loi[1:]
                            C = loi[3:]
                            if V1 == "u":
                                V1 = "w"
                            V1 = (V1.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                                .replace("ô", "O").replace("ư", "U"))
                            V2 = (V2.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                                .replace("ô", "O").replace("ư", "U"))
                            VVC = (VVC.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                                .replace("ô", "O").replace("ư", "U").replace("C", "ch").replace("N", "ng").replace("J", "nh"))
                            C = C.replace("C", "ch").replace("N", "ng").replace("J", "nh")
                            if prevtontaiCcuoi:
                                vow = "."
                            else:
                                vow = vow + " "
                            if prevtontaiCcuoi:
                                if tontaiCcuoi:
                                    phonemes.append(Phoneme(f"{vow}{V1}{V2}"))
                                    phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                                elif NoNext:
                                    phonemes.append(Phoneme(f"{vow}{V1}{V2}"))
                                    phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                                    phonemes.append(Phoneme(f"{C} -", position=End))
                                else:
                                    phonemes.append(Phoneme(f"{vow}{V1}{V2}"))
                                    phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                            elif NoNext and tontaiCcuoi:
                                phonemes.append(Phoneme(f"{vow}{V1}", position=VCP))
                                phonemes.append(Phoneme(f"{V1}{V2}"))
                                phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                            elif NoNext:
                                phonemes.append(Phoneme(f"{vow}{V1}", position=VCP))
                                phonemes.append(Phoneme(f"{V1}{V2}"))
                                phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                                phonemes.append(Phoneme(f"{C} -", position=End))
                            else:
                                phonemes.append(Phoneme(f"{vow}{V1}", position=VCP))
                                phonemes.append(Phoneme(f"{V1}{V2}"))
                                phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                        # 4 âm CVVC/CVVV, chia 3 nốt, ví dụ "thoát" "toan" "toại"
                        if tontaiVVC:
                            pass
                        elif fry:
                            pass
                        elif dem == 4 and tontaiC:
                            C = loi[0:1]
                            Cw = C
                            V1 = loi[1:2]
                            V2 = loi[2:3]
                            V2_2 = V2
                            VC = loi[2:]
                            N = loi[3:]
                            N_ = N
                            a = (loi.endswith("ia") or loi.endswith("ua") or loi.endswith("ưa") or loi.endswith("ya"))
                            if a and note.lyric != "qua":
                                N = "@"
                                N_ = "@"
                            if V1 == "u":
                                V1 = "w"
                            if wV and _Cw:
                                Cw = C + "w"
                                V1 = "w"
                            elif wV:
                                V1 = "w"
                            if V1 == "i":
                                Cw = C + "y"
                            if V2 == "ă":
                                V2_2 = "ae"
                            if V2 == "â":
                                V2 = "@"
                            C = (C.replace("C", "ch").replace("K", "kh").replace("N", "ng").replace("J", "nh")
                                .replace("Z", "tr").replace("T", "th"))
                            Cw = (Cw.replace("C", "ch").replace("K", "kh").replace("N", "ng").replace("J", "nh")
                                .replace("Z", "tr").replace("T", "th"))
                            V1 = (V1.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                                .replace("ô", "O").replace("ư", "U"))
                            V2_2 = (V2_2.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i")
                                .replace("ê", "E").replace("ô", "O").replace("ư", "U"))
                            V2 = (V2.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                                .replace("ô", "O").replace("ư", "U"))
                            VC = (VC.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("ê", "E").replace("ô", "O")
                                .replace("ư", "U").replace("C", "ch").replace("N", "ng").replace("J", "nh"))
                            N = (N.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("ê", "E").replace("ô", "O")
                                .replace("ư", "U").replace("C", "ch").replace("N", "ng").replace("J", "nh"))
                            N_ = (N_.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                                .replace("ô", "O").replace("ư", "U").replace("C", "ch").replace("N", "ng").replace("J", "nh"))
                            if _CV and prevtontaiCcuoi:
                                N = "- " + N
                            vow = vow + " "
                            if NoVCP:
                                if tontaiCcuoi:
                                    # có C ngắt
                                    phonemes.append(Phoneme(f"{C}{V1}{V2}"))
                                    phonemes.append(Phoneme(f"{VC}", position=ViTri))
                                elif note.lyric.endswith("uân"):
                                    if wAn == False:
                                        if NoNext:
                                            if loi.startswith("."):
                                                phonemes.append(Phoneme(f"{C}w@"))
                                                phonemes.append(Phoneme(f"An", position=ViTri))
                                                phonemes.append(Phoneme(f"n -", position=End))
                                            else:
                                                phonemes.append(Phoneme(f"{C}wAn"))
                                            phonemes.append(Phoneme(f"n -", position=End))
                                        else:
                                            # 
                                            if loi.startswith("."):
                                                phonemes.append(Phoneme(f"{C}w@"))
                                                phonemes.append(Phoneme(f"An", position=ViTri))
                                            else:
                                                phonemes.append(Phoneme(f"{C}wAn"))
                                    else:
                                        # khuân luân
                                        if NoNext:
                                            phonemes.append(Phoneme(f"{C}w"))
                                            phonemes.append(Phoneme(f"w@", position=Long))
                                            phonemes.append(Phoneme(f"An", position=Medium))
                                            phonemes.append(Phoneme(f"n -", position=End))
                                        else:
                                            # 
                                            phonemes.append(Phoneme(f"{C}w"))
                                            phonemes.append(Phoneme(f"w@", position=Long))
                                            phonemes.append(Phoneme(f"An", position=Medium))
                                elif NoNext:
                                    if VV_:
                                        phonemes.append(Phoneme(f"{C}{V1}{V2}"))
                                        phonemes.append(Phoneme(f"{V2}{N} -", position=End))
                                    else:
                                        # ko có VV -
                                        phonemes.append(Phoneme(f"{C}{V1}{V2}"))
                                        phonemes.append(Phoneme(f"{V2_2}{N}", position=ViTri))
                                        phonemes.append(Phoneme(f"{N} -", position=End))
                                else:
                                    if VV_:
                                        phonemes.append(Phoneme(f"{C}{V1}{V2}"))
                                        phonemes.append(Phoneme(f"{V2}{N}", position=ViTri))
                                    else:
                                        # ko có VV -
                                        phonemes.append(Phoneme(f"{C}{V1}{V2}"))
                                        phonemes.append(Phoneme(f"{V2_2}{N}", position=ViTri))
                            elif tontaiCcuoi:
                                # có C ngắt
                                phonemes.append(Phoneme(f"{vow}{Cw}", position=VCP))
                                phonemes.append(Phoneme(f"{C}{V1}{V2}"))
                                phonemes.append(Phoneme(f"{VC}", position=ViTri))
                            elif note.lyric.endswith("uân") or note.lyric.endswith("uâng"):
                                if wAn == False:
                                    if NoNext:
                                        if loi.startswith("."):
                                            phonemes.append(Phoneme(f"{vow}{Cw}", position=VCP))
                                            phonemes.append(Phoneme(f"{C}w@"))
                                            phonemes.append(Phoneme(f"A{N}", position=ViTri))
                                            phonemes.append(Phoneme(f"{N_} -", position=End))
                                        else:
                                            phonemes.append(Phoneme(f"{vow}{Cw}", position=VCP))
                                            phonemes.append(Phoneme(f"{C}wA{N}"))
                                            phonemes.append(Phoneme(f"{N_} -", position=End))
                                    else:
                                        # 
                                        if loi.startswith("."):
                                            phonemes.append(Phoneme(f"{vow}{Cw}", position=VCP))
                                            phonemes.append(Phoneme(f"{C}w@"))
                                            phonemes.append(Phoneme(f"A{N}", position=ViTri))
                                        else:
                                            phonemes.append(Phoneme(f"{vow}{Cw}", position=VCP))
                                            phonemes.append(Phoneme(f"{C}wA{N}"))
                                else:
                                    # khuân luân
                                    if NoNext:
                                        phonemes.append(Phoneme(f"{vow}{Cw}", position=VCP))
                                        phonemes.append(Phoneme(f"{C}w"))
                                        phonemes.append(Phoneme(f"_w@", position=Long))
                                        phonemes.append(Phoneme(f"A{N}", position=Medium))
                                        phonemes.append(Phoneme(f"{N_} -", position=End))
                                    else:
                                        # 
                                        phonemes.append(Phoneme(f"{vow}{Cw}", position=VCP))
                                        phonemes.append(Phoneme(f"{C}w"))
                                        phonemes.append(Phoneme(f"_w@", position=Long))
                                        phonemes.append(Phoneme(f"A{N}", position=Medium))
                            elif NoNext:
                                if VV_:
                                    phonemes.append(Phoneme(f"{vow}{Cw}", position=VCP))
                                    phonemes.append(Phoneme(f"{C}{V1}{V2}"))
                                    phonemes.append(Phoneme(f"{V2}{N_} -", position=End))
                                else:
                                    # ko có VV -
                                    phonemes.append(Phoneme(f"{vow}{Cw}", position=VCP))
                                    phonemes.append(Phoneme(f"{C}{V1}{V2}"))
                                    phonemes.append(Phoneme(f"{V2_2}{N}", position=ViTri))
                                    phonemes.append(Phoneme(f"{N_} -", position=End))
                            else:
                                if VV_:
                                    phonemes.append(Phoneme(f"{vow}{Cw}", position=VCP))
                                    phonemes.append(Phoneme(f"{C}{V1}{V2}"))
                                    phonemes.append(Phoneme(f"{V2}{N}", position=ViTri))
                                else:
                                    # ko có VV -
                                    phonemes.append(Phoneme(f"{vow}{Cw}", position=VCP))
                                    phonemes.append(Phoneme(f"{C}{V1}{V2}"))
                                    phonemes.append(Phoneme(f"{V2_2}{N}", position=ViTri))
                        # 4 âm CVVC/CVVV, (tiên, tiết)
                        if fry:
                            pass
                        elif dem == 4 and tontaiVVC and tontaiC:
                            C = loi[0:1]
                            Cw = C
                            V1 = loi[1:2]
                            VVC = loi[1:]
                            N = loi[3:]
                            if V1 == "i" and _Cw:
                                Cw = C + "y"
                            C = (C.replace("C", "ch").replace("K", "kh").replace("N", "ng").replace("J", "nh")
                                .replace("Z", "tr").replace("T", "th"))
                            Cw = (Cw.replace("C", "ch").replace("K", "kh").replace("N", "ng").replace("J", "nh")
                                .replace("Z", "tr").replace("T", "th"))
                            V1 = (V1.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                                .replace("ô", "O").replace("ư", "U"))
                            VVC = (VVC.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                                .replace("ô", "O").replace("ư", "U").replace("C", "ch").replace("N", "ng").replace("J", "nh"))
                            N = N.replace("N", "ng").replace("J", "nh")
                            if _CV and prevtontaiCcuoi:
                                C = "- " + C
                            vow = vow + " "
                            if NoVCP:
                                if tontaiCcuoi:
                                    # có C ngắt
                                    phonemes.append(Phoneme(f"{C}{V1}"))
                                    phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                                elif NoNext:
                                    # ko có note kế tiếp
                                    phonemes.append(Phoneme(f"{C}{V1}"))
                                    phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                                    phonemes.append(Phoneme(f"{N} -", position=End))
                                else:
                                    # có note kế tiếp
                                    phonemes.append(Phoneme(f"{C}{V1}"))
                                    phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                            elif tontaiCcuoi:
                                # có C ngắt
                                phonemes.append(Phoneme(f"{vow}{Cw}", position=VCP))
                                phonemes.append(Phoneme(f"{C}{V1}"))
                                phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                            elif NoNext:
                                # ko có note kế tiếp
                                phonemes.append(Phoneme(f"{vow}{Cw}", position=VCP))
                                phonemes.append(Phoneme(f"{C}{V1}"))
                                phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                                phonemes.append(Phoneme(f"{N} -", position=End))
                            else:
                                # có note kế tiếp
                                phonemes.append(Phoneme(f"{vow}{Cw}", position=VCP))
                                phonemes.append(Phoneme(f"{C}{V1}"))
                                phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                        # 5 âm CVVVC, có VVC liền, chia 3 nốt, ví dụ "thuyết"
                        if fry:
                            pass
                        elif dem == 5 and tontaiVVC and tontaiC:
                            C = loi[0:1]
                            Cw = C
                            V1 = loi[1:2]
                            V2 = loi[2:3]
                            VVC = loi[2:]
                            N = loi[4:]
                            if wV and _Cw:
                                Cw = C + "w"
                                V1 = "w"
                            elif wV:
                                V1 = "w"
                            if V1 == "i":
                                Cw = C + "y"
                            C = (C.replace("C", "ch").replace("K", "kh").replace("N", "ng").replace("J", "nh")
                                .replace("Z", "tr").replace("T", "th"))
                            Cw = (Cw.replace("C", "ch").replace("K", "kh").replace("N", "ng").replace("J", "nh")
                                .replace("Z", "tr").replace("T", "th"))
                            V1 = (V1.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                                .replace("ô", "O").replace("ư", "U"))
                            V2 = (V2.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                                .replace("ô", "O").replace("ư", "U"))
                            VVC = (VVC.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i").replace("ê", "E")
                                .replace("ô", "O").replace("ư", "U").replace("C", "ch").replace("N", "ng").replace("J", "nh"))
                            N = N.replace("N", "ng").replace("J", "nh")
                            if _CV and prevtontaiCcuoi:
                                N = "- " + N
                            vow = vow + " "
                            if NoVCP:
                                if tontaiCcuoi:
                                    # có C ngắt
                                    phonemes.append(Phoneme(f"{C}{V1}{V2}"))
                                    phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                                elif NoNext:
                                    # ko có note kế tiếp
                                    phonemes.append(Phoneme(f"{C}{V1}{V2}"))
                                    phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                                    phonemes.append(Phoneme(f"{N} -", position=End))
                                else:
                                    # có note kế tiếp
                                    phonemes.append(Phoneme(f"{C}{V1}{V2}"))
                                    phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                            elif tontaiCcuoi:
                                # có C ngắt
                                phonemes.append(Phoneme(f"{vow}{Cw}", position=VCP))
                                phonemes.append(Phoneme(f"{C}{V1}{V2}"))
                                phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                            elif NoNext:
                                # ko có note kế tiếp
                                phonemes.append(Phoneme(f"{vow}{Cw}", position=VCP))
                                phonemes.append(Phoneme(f"{C}{V1}{V2}"))
                                phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                                phonemes.append(Phoneme(f"{N} -", position=End))
                            else:
                                # có note kế tiếp
                                phonemes.append(Phoneme(f"{vow}{Cw}", position=VCP))
                                phonemes.append(Phoneme(f"{C}{V1}{V2}"))
                                phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                        # y
                        if note.lyric.startswith("y") and koVVCchia:
                            if dem == 2:
                                # ya
                                C = note.lyric[0:1]
                                V = note.lyric[1:2]
                                V = (V.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i")
                                    .replace("ê", "E").replace("ô", "O").replace("ư", "U").replace("C", "ch")
                                    .replace("N", "ng").replace("J", "nh"))
                                vow = vow + " "
                                if prevtontaiCcuoi:
                                    if NoNext:
                                        phonemes.append(Phoneme(f"- {C}{V}"))
                                        phonemes.append(Phoneme(f"{V} -", position=End))
                                    else:
                                        phonemes.append(Phoneme(f"- {C}{V}"))
                                elif NoNext:
                                    phonemes.append(Phoneme(f"{vow}{C}", position=VCP))
                                    phonemes.append(Phoneme(f"{C}{V}"))
                                    phonemes.append(Phoneme(f"{V} -", position=End))
                                else:
                                    phonemes.append(Phoneme(f"{vow}{C}", position=VCP))
                                    phonemes.append(Phoneme(f"{C}{V}"))
                            elif dem == 3:
                                C = note.lyric[0:1]
                                V1 = note.lyric[1:2]
                                V2 = note.lyric[2:3]
                                V1 = (V1.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i")
                                    .replace("ê", "E").replace("ô", "O").replace("ư", "U").replace("C", "ch")
                                    .replace("N", "ng").replace("J", "nh"))
                                V2 = (V2.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i")
                                    .replace("ê", "E").replace("ô", "O").replace("ư", "U").replace("C", "ch")
                                    .replace("N", "ng").replace("J", "nh"))
                                if wV:
                                    V1 = "w"
                                a = (loi.endswith("ia") or loi.endswith("ua") or loi.endswith("ưa") or loi.endswith("ya"))
                                if a and note.lyric != "qua":
                                    V2 = "@"
                                N = V2
                                if V1 + V2 == "Ong" or V1 + V2 == "ung" or V1 + V2 == "ong":
                                    N = "ng0"
                                if V1 + V2 == "Ai":
                                    V2 = "y"
                                    N = "i"
                                if loi.endswith("ay"):
                                    V2 = "y"
                                    N = "i"
                                vow = vow + " "
                                if prevtontaiCcuoi:
                                    if tontaiCcuoi:
                                        phonemes.append(Phoneme(f"- {C}{V1}"))
                                        phonemes.append(Phoneme(f"{V1}{V2}", position=ViTri))
                                    elif NoNext:
                                        if VV_:
                                            phonemes.append(Phoneme(f"- {C}{V1}"))
                                            phonemes.append(Phoneme(f"{V1}{V2} -", position=End))
                                        elif wV:
                                            phonemes.append(Phoneme(f"- {C}{V1}{V2}"))
                                            phonemes.append(Phoneme(f"{V2} -", position=End))
                                        else:
                                            phonemes.append(Phoneme(f"- {C}{V1}"))
                                            phonemes.append(Phoneme(f"{V1}{V2}", position=ViTri))
                                            phonemes.append(Phoneme(f"{V2} -", position=End))
                                    elif wV:
                                        phonemes.append(Phoneme(f"- {C}{V1}{V2}"))
                                    else:
                                        phonemes.append(Phoneme(f"- {C}{V1}"))
                                        phonemes.append(Phoneme(f"{V1}{V2}", position=ViTri))
                                elif tontaiCcuoi:
                                    phonemes.append(Phoneme(f"{vow}{C}", position=VCP))
                                    phonemes.append(Phoneme(f"{C}{V1}"))
                                    phonemes.append(Phoneme(f"{V1}{V2}", position=ViTri))
                                elif NoNext:
                                    if VV_:
                                        phonemes.append(Phoneme(f"{vow}{C}", position=VCP))
                                        phonemes.append(Phoneme(f"{C}{V1}"))
                                        phonemes.append(Phoneme(f"{V1}{V2} -", position=End))
                                    elif wV:
                                        phonemes.append(Phoneme(f"{vow}{C}", position=VCP))
                                        phonemes.append(Phoneme(f"{C}{V1}{V2}"))
                                        phonemes.append(Phoneme(f"{V2} -", position=End))
                                    else:
                                        phonemes.append(Phoneme(f"{vow}{C}", position=VCP))
                                        phonemes.append(Phoneme(f"{C}{V1}"))
                                        phonemes.append(Phoneme(f"{V1}{V2}", position=ViTri))
                                        phonemes.append(Phoneme(f"{V2} -", position=End))
                                elif wV:
                                    phonemes.append(Phoneme(f"{vow}{C}", position=VCP))
                                    phonemes.append(Phoneme(f"{C}{V1}{V2}"))
                                else:
                                    phonemes.append(Phoneme(f"{vow}{C}", position=VCP))
                                    phonemes.append(Phoneme(f"{C}{V1}"))
                                    phonemes.append(Phoneme(f"{V1}{V2}", position=ViTri))
                        else:
                            # nếu ko phải phụ âm y
                            # 2 âm VV, ví dụ: "oa"
                            if fry:
                                pass
                            elif (dem == 2) and kocoC:
                                V1 = loi[0:1]
                                V1_ = V1
                                V2 = loi[1:2]
                                N = V2
                                if loi.startswith("uy"):
                                    V2 = "i"
                                if V1 + V2 == "ôN" or V1 + V2 == "uN" or V1 + V2 == "oN":
                                    N = "ng0"
                                if V2 == "y":
                                    N = "i"
                                if wV:
                                    V1 = "w"
                                if V1 == "â":
                                    V1 = "@"
                                if V1 + V2 == "ia" or V1 + V2 == "ua" or V1 + V2 == "ưa":
                                    N = "@"
                                if V1 == "ă":
                                    V1_ = "ae"
                                V1 = (V1.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i")
                                    .replace("ê", "E").replace("ô", "O").replace("ư", "U"))
                                V1_ = (V1_.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i")
                                    .replace("ê", "E").replace("ô", "O").replace("ư", "U"))
                                V2 = (V2.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("ê", "E")
                                    .replace("ô", "O").replace("ư", "U").replace("C", "ch").replace("N", "ng")
                                    .replace("J", "nh"))
                                N = (N.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("ê", "E")
                                    .replace("ô", "O").replace("ư", "U").replace("C", "ch").replace("N", "ng")
                                    .replace("J", "nh"))
                                a = (loi.endswith("ia") or loi.endswith("ua") or loi.endswith("ưa"))
                                if a:
                                    V2 = "@"
                                if prevtontaiCcuoi:
                                    vow = "."
                                else:
                                    vow = vow + " "
                                if prevtontaiCcuoi:
                                    if tontaiCcuoi:
                                        phonemes.append(Phoneme(f"{vow}{V1}"))
                                        phonemes.append(Phoneme(f"{V1}{V2}", position=ViTri))
                                    elif NoNext:
                                        # ko co note ke tiep
                                        if wV:
                                            # oa oe uê ,...
                                            phonemes.append(Phoneme(f"{vow}{V1}{V2}"))
                                            phonemes.append(Phoneme(f"{N} -", position=End))
                                        elif VV_:
                                            # ai eo êu ao,...
                                            phonemes.append(Phoneme(f"{vow}{V1}"))
                                            phonemes.append(Phoneme(f"{V1}{N} -", position=End))
                                        else:
                                            # an anh
                                            phonemes.append(Phoneme(f"{vow}{V1}"))
                                            phonemes.append(Phoneme(f"{V1_}{V2}", position=ViTri))
                                            phonemes.append(Phoneme(f"{N} -", position=End))
                                    else:
                                        # co note ke tiep
                                        if wV:
                                            # oa oe uê ,...
                                            phonemes.append(Phoneme(f"{vow}{V1}{V2}"))
                                        elif VV_:
                                            # ai eo êu ao,...
                                            phonemes.append(Phoneme(f"{vow}{V1}"))
                                            phonemes.append(Phoneme(f"{V1}{N}", position=ViTri))
                                        else:
                                            # an anh
                                            phonemes.append(Phoneme(f"{vow}{V1}"))
                                            phonemes.append(Phoneme(f"{V1_}{V2}", position=ViTri))
                                elif tontaiCcuoi:
                                    phonemes.append(Phoneme(f"{vow}{V1}"))
                                    phonemes.append(Phoneme(f"{V1}{V2}", position=ViTri))
                                elif NoNext:
                                    # ko co note ke tiep
                                    if wV:
                                        # oa oe uê ,...
                                        phonemes.append(Phoneme(f"{vow}{V1}", position=VCP))
                                        phonemes.append(Phoneme(f"{V1}{V2}"))
                                        phonemes.append(Phoneme(f"{N} -", position=End))
                                    elif VV_:
                                        # ai eo êu ao,...
                                        phonemes.append(Phoneme(f"{vow}{V1}"))
                                        phonemes.append(Phoneme(f"{V1}{N} -", position=End))
                                    else:
                                        # an anh
                                        phonemes.append(Phoneme(f"{vow}{V1}"))
                                        phonemes.append(Phoneme(f"{V1_}{V2}", position=ViTri))
                                        phonemes.append(Phoneme(f"{N} -", position=End))
                                else:
                                    # co note ke tiep
                                    if wV:
                                        # oa oe uê ,...
                                        phonemes.append(Phoneme(f"{vow}{V1}", position=VCP))
                                        phonemes.append(Phoneme(f"{V1}{V2}"))
                                    elif VV_:
                                        # ai eo êu ao,...
                                        phonemes.append(Phoneme(f"{vow}{V1}"))
                                        phonemes.append(Phoneme(f"{V1}{N}", position=ViTri))
                                    else:
                                        # an anh
                                        phonemes.append(Phoneme(f"{vow}{V1}"))
                                        phonemes.append(Phoneme(f"{V1_}{V2}", position=ViTri))
                            # 3 âm VVC/VVV, ví dụ: "oát" "oan" "oai" "uân"
                            if fry:
                                pass
                            elif (dem == 3) and koVVCchia and kocoC:
                                V1 = loi[0:1]
                                V2 = loi[1:2]
                                V2_2 = V2
                                V3 = loi[2:3]
                                a = (loi.endswith("ia") or loi.endswith("ua") or loi.endswith("ưa") or loi.endswith("ya"))
                                if a:
                                    V3 = "@"
                                if wV:
                                    V1 = "w"
                                if V2 == "ă":
                                    V2_2 = "ae"
                                if V2 == "â":
                                    V2 = "@"
                                V1 = (V1.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i")
                                    .replace("ê", "E").replace("ô", "O").replace("ư", "U"))
                                V2 = (V2.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i")
                                    .replace("ê", "E").replace("ô", "O").replace("ư", "U"))
                                V2_2 = (V2_2.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i")
                                    .replace("ê", "E").replace("ô", "O").replace("ư", "U"))
                                V3 = (V3.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("ê", "E")
                                    .replace("ô", "O").replace("ư", "U").replace("C", "ch").replace("N", "ng")
                                    .replace("J", "nh"))
                                N = V3
                                if V3 == "y":
                                    N = "i"
                                if V2 + V3 == "Ong" or V2 + V3 == "ung" or V2 + V3 == "ong":
                                    N = "ng0"
                                if prevtontaiCcuoi:
                                    vow = "."
                                else:
                                    vow = vow + " "
                                if prevtontaiCcuoi:
                                    if NoNext:
                                        # ko co note ke tiep
                                        if VV_:
                                            phonemes.append(Phoneme(f"{vow}{V1}{V2}"))
                                            phonemes.append(Phoneme(f"{V2_2}{N} -", position=End))
                                        else:
                                            phonemes.append(Phoneme(f"{vow}{V1}{V2}"))
                                            phonemes.append(Phoneme(f"{V2_2}{V3}", position=ViTri))
                                            phonemes.append(Phoneme(f"{N} -", position=End))
                                    else:
                                        # co note ke tiep
                                        if VV_:
                                            phonemes.append(Phoneme(f"{vow}{V1}{V2}"))
                                            phonemes.append(Phoneme(f"{V2_2}{V3}", position=ViTri))
                                        else:
                                            phonemes.append(Phoneme(f"{vow}{V1}{V2}"))
                                            phonemes.append(Phoneme(f"{V2_2}{V3}", position=ViTri))
                                else:
                                    if NoNext:
                                        # ko co note ke tiep
                                        if wV and VV_:
                                            phonemes.append(Phoneme(f"{vow}{V1}", position=VCP))
                                            phonemes.append(Phoneme(f"{V1}{V2}"))
                                            phonemes.append(Phoneme(f"{V2_2}{N} -", position=End))
                                        elif wV:
                                            phonemes.append(Phoneme(f"{vow}{V1}", position=VCP))
                                            phonemes.append(Phoneme(f"{V1}{V2}"))
                                            phonemes.append(Phoneme(f"{V2_2}{V3}", position=ViTri))
                                            phonemes.append(Phoneme(f"{N} -", position=End))
                                    else:
                                        # co note ke tiep
                                        if wV and VV_:
                                            phonemes.append(Phoneme(f"{vow}{V1}", position=VCP))
                                            phonemes.append(Phoneme(f"{V1}{V2}"))
                                            phonemes.append(Phoneme(f"{V2_2}{V3}", position=ViTri))
                                        elif wV:
                                            phonemes.append(Phoneme(f"{vow}{V1}", position=VCP))
                                            phonemes.append(Phoneme(f"{V1}{V2}"))
                                            phonemes.append(Phoneme(f"{V2_2}{V3}", position=ViTri))
                            # 3 âm VVV/VVC chia 2 nốt, ví dụ: "yên" "ướt"
                            if (dem == 3) and tontaiVVC and kocoC:
                                V1 = loi[0:1]
                                VVC = loi[0:]
                                C = loi[2:]
                                V1 = (V1.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i")
                                    .replace("ê", "E").replace("ô", "O").replace("ư", "U"))
                                VVC = (VVC.replace("ă", "a").replace("â", "A").replace("ơ", "@").replace("y", "i")
                                    .replace("ê", "E").replace("ô", "O").replace("ư", "U").replace("C", "ch")
                                    .replace("N", "ng").replace("J", "nh"))
                                C = C.replace("C", "ch").replace("N", "ng").replace("J", "nh")
                                if prevtontaiCcuoi:
                                    vow = "."
                                else:
                                    vow = vow + " "
                                if NoNext and tontaiCcuoi:
                                    phonemes.append(Phoneme(f"{vow}{V1}"))
                                    phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                                elif NoNext:
                                    phonemes.append(Phoneme(f"{vow}{V1}"))
                                    phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                                    phonemes.append(Phoneme(f"{C} -", position=End))
                                else:
                                    phonemes.append(Phoneme(f"{vow}{V1}"))
                                    phonemes.append(Phoneme(f"{VVC}", position=ViTri))
                        # BR
                        if BR:
                            num = loi[5:]
                            if num == "":
                                num = "1"
                            if vow == "-":
                                phonemes.append(Phoneme(f"breath{num}"))
                            else:
                                phonemes.append(Phoneme(f"{vow} -", position=-60))
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
