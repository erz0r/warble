"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Plugin.Builtin/JapaneseVCVPhonemizer.cs"""

import unicodedata

from .api import Phoneme, Phonemizer, alt_str, phonemizer

VOWELS = [
    "a=ぁ,あ,か,が,さ,ざ,た,だ,な,は,ば,ぱ,ま,ゃ,や,ら,わ,ァ,ア,カ,ガ,サ,ザ,タ,ダ,ナ,ハ,バ,パ,マ,ャ,ヤ,ラ,ワ,a",
    "e=ぇ,え,け,げ,せ,ぜ,て,で,ね,へ,べ,ぺ,め,れ,ゑ,ェ,エ,ケ,ゲ,セ,ゼ,テ,デ,ネ,ヘ,ベ,ペ,メ,レ,ヱ,e",
    "i=ぃ,い,き,ぎ,し,じ,ち,ぢ,に,ひ,び,ぴ,み,り,ゐ,ィ,イ,キ,ギ,シ,ジ,チ,ヂ,ニ,ヒ,ビ,ピ,ミ,リ,ヰ,i",
    "o=ぉ,お,こ,ご,そ,ぞ,と,ど,の,ほ,ぼ,ぽ,も,ょ,よ,ろ,を,ォ,オ,コ,ゴ,ソ,ゾ,ト,ド,ノ,ホ,ボ,ポ,モ,ョ,ヨ,ロ,ヲ,o",
    "n=ん,n",
    "u=ぅ,う,く,ぐ,す,ず,つ,づ,ぬ,ふ,ぶ,ぷ,む,ゅ,ゆ,る,ゥ,ウ,ク,グ,ス,ズ,ツ,ヅ,ヌ,フ,ブ,プ,ム,ュ,ユ,ル,ヴ,u",
    "N=ン,ng",
]
VOWEL_LOOKUP = {cv: v for line in VOWELS for v, cvs in [line.split("=")] for cv in cvs.split(",")}


def nfc(s):
    return unicodedata.normalize("NFC", s)


@phonemizer("Japanese VCV Phonemizer (legacy)", "JA VCV", language="JA", openutau_class="OpenUtau.Plugin.Builtin.JapaneseVCVPhonemizer")
class JapaneseVCVPhonemizer(Phonemizer):
    def process(self, notes, prev, next, prev_neighbour, next_neighbour, prev_neighbours):
        note = notes[0]
        current = nfc(note.lyric)
        if note.phonetic_hint:
            oto = self.check_oto_until_hit([nfc(note.phonetic_hint)], note)
            if oto is not None:
                return [Phoneme(oto.alias)]
        tests = [f"- {current}", current]
        if prev_neighbour is not None:
            prev_lyric = nfc(prev_neighbour.lyric)
            if prev_neighbour.phonetic_hint:
                prev_lyric = nfc(prev_neighbour.phonetic_hint)
            unicode = self.to_unicode_elements(prev_lyric)
            vow = VOWEL_LOOKUP.get(unicode[-1] if unicode else "")
            if vow is not None:
                tests = [f"{vow} {current}", f"* {current}", current, f"- {current}"]
        oto = self.check_oto_until_hit(tests, note)
        if oto is not None:
            return [Phoneme(oto.alias)]
        return [Phoneme(current)]

    def check_oto_until_hit(self, tests, note):
        attr = note.attr(0)
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
        if otos:
            return next((o for o in otos if o.is_color_match(color)), otos[0])
        return None
