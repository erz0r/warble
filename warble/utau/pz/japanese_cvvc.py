"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Plugin.Builtin/JapaneseCVVCPhonemizer.cs"""

import unicodedata

from .api import Phoneme, Phonemizer, alt_str, phonemizer

PLAIN_VOWELS = ["あ", "い", "う", "え", "お", "を", "ん", "ン"]
NON_VOWELS = ["息", "吸", "R", "-", "k", "ky", "g", "gy", "s", "sh", "z", "j", "t", "ch", "ty", "ts", "d", "dy", "n", "ny", "h", "hy", "f", "b",
              "by", "p", "py", "m", "my", "y", "r", "4", "ry", "w", "v", "ng", "l", "・", "B", "H"]
VOWELS = [
    "a=ぁ,あ,か,が,さ,ざ,た,だ,な,は,ば,ぱ,ま,ゃ,や,ら,わ,ァ,ア,カ,ガ,サ,ザ,タ,ダ,ナ,ハ,バ,パ,マ,ャ,ヤ,ラ,ワ",
    "e=ぇ,え,け,げ,せ,ぜ,て,で,ね,へ,べ,ぺ,め,れ,ゑ,ェ,エ,ケ,ゲ,セ,ゼ,テ,デ,ネ,ヘ,ベ,ペ,メ,レ,ヱ",
    "i=ぃ,い,き,ぎ,し,じ,ち,ぢ,に,ひ,び,ぴ,み,り,ゐ,ィ,イ,キ,ギ,シ,ジ,チ,ヂ,ニ,ヒ,ビ,ピ,ミ,リ,ヰ",
    "o=ぉ,お,こ,ご,そ,ぞ,と,ど,の,ほ,ぼ,ぽ,も,ょ,よ,ろ,を,ォ,オ,コ,ゴ,ソ,ゾ,ト,ド,ノ,ホ,ボ,ポ,モ,ョ,ヨ,ロ,ヲ",
    "n=ん",
    "u=ぅ,う,く,ぐ,す,ず,つ,づ,ぬ,ふ,ぶ,ぷ,む,ゅ,ゆ,る,ゥ,ウ,ク,グ,ス,ズ,ツ,ヅ,ヌ,フ,ブ,プ,ム,ュ,ユ,ル,ヴ",
    "N=ン",
    "・=・",
]
CONSONANTS = [
    "ch=ち,ちぇ,ちゃ,ちゅ,ちょ", "gy=ぎ,ぎぇ,ぎゃ,ぎゅ,ぎょ", "ts=つ,つぁ,つぃ,つぇ,つぉ", "ty=てぃ,てぇ,てゃ,てゅ,てょ", "py=ぴ,ぴぇ,ぴゃ,ぴゅ,ぴょ",
    "ry=り,りぇ,りゃ,りゅ,りょ", "ly=リ,リェ,リャ,リュ,リョ", "ny=に,にぇ,にゃ,にゅ,にょ", "r=ら,る,るぃ,れ,ろ", "hy=ひ,ひぇ,ひゃ,ひゅ,ひょ",
    "dy=でぃ,でぇ,でゃ,でゅ,でょ", "by=び,びぇ,びゃ,びゅ,びょ", "b=ば,ぶ,ぶぃ,べ,ぼ", "d=だ,で,ど,どぃ,どぅ", "g=が,ぐ,ぐぃ,げ,ご",
    "f=ふ,ふぁ,ふぃ,ふぇ,ふぉ", "h=は,はぃ,へ,ほ,ほぅ", "k=か,く,くぃ,け,こ", "j=じ,じぇ,じゃ,じゅ,じょ,ぢ,ぢぇ,ぢゃ,ぢゅ,ぢょ",
    "m=ま,む,むぃ,め,も", "n=な,ぬ,ぬぃ,ね,の", "p=ぱ,ぷ,ぷぃ,ぺ,ぽ", "s=さ,す,すぃ,せ,そ", "sh=し,しぇ,しゃ,しゅ,しょ", "t=た,て,と,とぃ,とぅ",
    "v=ヴ,ヴぁ,ヴぃ,ヴぅ,ヴぇ,ヴぉ", "ky=き,きぇ,きゃ,きゅ,きょ", "w=うぃ,うぅ,うぇ,うぉ,わ,ゐ,ゑ,を,ヰ,ヱ", "y=いぃ,いぇ,や,ゆ,よ",
    "z=ざ,ず,ずぃ,ぜ,ぞ", "dz=づ,づぃ", "my=み,みぇ,みゃ,みゅ,みょ",
    "ng=ガ,ギ,グ,ゲ,ゴ,ギェ,ギャ,ギュ,ギョ,カ゜,キ゜,ク゜,ケ゜,コ゜,キ゜ェ,キ゜ャ,キ゜ュ,キ゜ョ", "l=ラ,ル,レ,ロ", "・=・あ,・い,・う,・え,・お,・ん,・を,・ン",
]
SUBSTITUTION = ["ty,ch,ts=t", "j,dy=d", "gy=g", "ky=k", "py=p", "ny=n", "ry=r", "my=m", "hy,f=h", "by,v=b", "dz=z", "l=r", "ly=l"]


def _table(lines):
    out = {}
    for line in lines:
        k, vs = line.split("=")
        for v in vs.split(","):
            if v in out:
                raise ValueError(f"duplicate key {v}")  # c# ToDictionary throws on duplicates too
            out[v] = k
    return out


VOWEL_LOOKUP = _table(VOWELS)
CONSONANT_LOOKUP = _table(CONSONANTS)
SUBSTITUTE_LOOKUP = {orig: target for line in SUBSTITUTION for origs, target in [line.split("=")] for orig in origs.split(",")}


def nfc(s):
    return unicodedata.normalize("NFC", s)


@phonemizer("Japanese CVVC Phonemizer (legacy)", "JA CVVC", language="JA", openutau_class="OpenUtau.Plugin.Builtin.JapaneseCVVCPhonemizer", author="TUBS")
class JapaneseCVVCPhonemizer(Phonemizer):
    def _hit(self, tests, note, index, require_color):
        attr = note.attr(index)
        color = attr.voice_color if attr.voice_color is not None else self.get_parent_voice_color()
        shift = attr.tone_shift if attr.tone_shift is not None else self.get_parent_tone_shift()
        alt = attr.alternate if attr.alternate is not None else self.get_parent_alternate()
        otos = []
        for test in tests:
            o = self.singer.try_get_mapped_oto(test + alt_str(alt), note.tone + shift, color)
            if o is not None:
                otos.append(o)
                continue
            o = self.singer.try_get_mapped_oto(test, note.tone + shift, color)
            if o is not None:
                otos.append(o)
        if not otos:
            return None
        match = next((o for o in otos if o.is_color_match(color)), None)
        if require_color:
            return match
        return match or otos[0]

    def process(self, notes, prev, next, prev_neighbour, next_neighbour, prev_neighbours):
        note = notes[0]
        current = nfc(note.lyric)
        if note.phonetic_hint:
            current = nfc(note.phonetic_hint)
        original = current
        cf = f"* {current}"
        if note.phonetic_hint:
            oto = self._hit([current], note, 0, False)
            if oto is not None:
                current = oto.alias
        elif prev_neighbour is None:
            oto = self._hit([f"- {current}", current], note, 0, False)
            if oto is not None:
                current = oto.alias
        elif current in PLAIN_VOWELS or current in NON_VOWELS:
            prev_lyric = nfc(prev_neighbour.lyric)
            if prev_neighbour.phonetic_hint:
                prev_lyric = nfc(prev_neighbour.phonetic_hint)
            vow = VOWEL_LOOKUP.get(prev_lyric[-1:] if prev_lyric else "\0")
            if vow is not None:
                oto = self._hit([f"{vow} {current}", cf, current], note, 0, False)
                if oto is not None:
                    current = oto.alias
        else:
            oto = self._hit([cf, current], note, 0, False)
            if oto is not None:
                current = oto.alias

        if next_neighbour is not None and not next_neighbour.phonetic_hint:
            next_lyric = nfc(next_neighbour.lyric)
            if len(next_lyric) == 1 and next_lyric in PLAIN_VOWELS:
                return [Phoneme(current)]
            vowel = VOWEL_LOOKUP.get(original[-1:] if original else "\0", "")
            consonant = CONSONANT_LOOKUP.get(next_lyric[:1] if next_lyric else "\0")
            if consonant is None and len(next_lyric) >= 2:
                consonant = CONSONANT_LOOKUP.get(next_lyric[:2])
            consonant = consonant or ""
            if consonant == "":
                return [Phoneme(current)]
            vc = f"{vowel} {consonant}"
            vcs = [vc, ""]
            sub = SUBSTITUTE_LOOKUP.get(consonant)
            if sub is not None:
                vcs[1] = f"{vowel} {sub}"
            oto1 = self._hit(vcs, note, 1, True)
            if oto1 is None:
                return [Phoneme(current)]
            vc = oto1.alias
            total = sum(n.duration for n in notes)
            vc_len = 120
            nattr = next_neighbour.attr(0)
            shift = nattr.tone_shift if nattr.tone_shift is not None else self.get_parent_tone_shift()
            color = nattr.voice_color if nattr.voice_color is not None else self.get_parent_voice_color()
            oto = self.singer.try_get_mapped_oto(next_lyric, next_neighbour.tone + shift, color)
            if oto is not None:
                vc_len = self.ms_to_tick(oto.preutter - oto.overlap) if oto.overlap < 0 else self.ms_to_tick(oto.preutter)
            ratio = nattr.consonant_stretch_ratio if nattr.consonant_stretch_ratio is not None else self.get_parent_consonant_stretch_ratio()
            # Convert.ToInt32 rounds half to even, like python's round
            vc_len = int(round(min(total // 2, vc_len * ratio)))
            return [Phoneme(current), Phoneme(vc, position=total - vc_len)]
        return [Phoneme(current)]
