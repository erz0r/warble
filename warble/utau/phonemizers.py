"""classic utau phonemizers: notes -> aliases with positions.

the api mirrors openutau's Phonemizer.Process: a phonemizer gets the current note group plus the
previous/next notes and neighbours, and returns phonemes with tick offsets relative to the group's
first note. ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Core/DefaultPhonemizer.cs,
OpenUtau.Plugin.Builtin/JapaneseVCVPhonemizer.cs, JapaneseCVVCPhonemizer.cs.

this module holds the first ports; the full catalog with parity goldens is milestone 8.
"""

import unicodedata

from .. import lang as langs
from ..errors import WarbleError

REGISTRY = {}


def register(name, openutau_class=None, language=None):
    def deco(cls):
        cls.name = name
        cls.openutau_class = openutau_class
        cls.language = language
        REGISTRY[name] = cls
        return cls

    return deco


class Phonemizer:
    name = "base"

    def __init__(self, voice, tm, color_of=None):
        self.voice = voice
        self.tm = tm
        self.color_of = color_of or (lambda n: n.controls.get("color"))

    def ms_to_tick(self, ms, at_tick):
        start = self.tm.tick_to_ms(at_tick)
        return int(round(self.tm.ms_to_tick(start + ms) - at_tick))

    def hit(self, tests, note, color=None, require_color=False):
        """CheckOtoUntilHit: the first test alias that maps to an oto. -> mapped alias or None."""
        for t in tests:
            if not t:
                continue
            r = self.voice.lookup(t, note.tone + note.controls.get("shift", 0), color or self.color_of(note))
            if r:
                return r[2]
        return None

    def process(self, notes, prev, nxt, prev_nb, next_nb):
        raise NotImplementedError


def _norm(s):
    return unicodedata.normalize("NFC", s or "")


def _lyric(note):
    return _norm(note.hint or note.lyric)


@register("default", "OpenUtau.Core.DefaultPhonemizer")
class DefaultPhonemizer(Phonemizer):
    """the lyric is the alias. as a small extension, kana/romaji spellings are tried too so a
    romaji lyric finds a kana bank and vice versa."""

    def process(self, notes, prev, nxt, prev_nb, next_nb):
        note = notes[0]
        lyr = _lyric(note)
        tests = [lyr] + [c for c in langs.candidates("ja", lyr) if c != lyr]
        alias = self.hit(tests, note) or lyr
        return [{"alias": alias, "position": 0}]


VCV_VOWELS = {
    "a": "ぁ,あ,か,が,さ,ざ,た,だ,な,は,ば,ぱ,ま,ゃ,や,ら,わ,ァ,ア,カ,ガ,サ,ザ,タ,ダ,ナ,ハ,バ,パ,マ,ャ,ヤ,ラ,ワ,a",
    "e": "ぇ,え,け,げ,せ,ぜ,て,で,ね,へ,べ,ぺ,め,れ,ゑ,ェ,エ,ケ,ゲ,セ,ゼ,テ,デ,ネ,ヘ,ベ,ペ,メ,レ,ヱ,e",
    "i": "ぃ,い,き,ぎ,し,じ,ち,ぢ,に,ひ,び,ぴ,み,り,ゐ,ィ,イ,キ,ギ,シ,ジ,チ,ヂ,ニ,ヒ,ビ,ピ,ミ,リ,ヰ,i",
    "o": "ぉ,お,こ,ご,そ,ぞ,と,ど,の,ほ,ぼ,ぽ,も,ょ,よ,ろ,を,ォ,オ,コ,ゴ,ソ,ゾ,ト,ド,ノ,ホ,ボ,ポ,モ,ョ,ヨ,ロ,ヲ,o",
    "n": "ん,n",
    "u": "ぅ,う,く,ぐ,す,ず,つ,づ,ぬ,ふ,ぶ,ぷ,む,ゅ,ゆ,る,ゥ,ウ,ク,グ,ス,ズ,ツ,ヅ,ヌ,フ,ブ,プ,ム,ュ,ユ,ル,ヴ,u",
    "N": "ン,ng",
}
VCV_LOOKUP = {k: v for v, ks in VCV_VOWELS.items() for k in ks.split(",")}


@register("ja_vcv", "OpenUtau.Plugin.Builtin.JapaneseVCVPhonemizer", "ja")
class JapaneseVCVPhonemizer(Phonemizer):
    def process(self, notes, prev, nxt, prev_nb, next_nb):
        note = notes[0]
        cur = _norm(note.lyric)
        if note.hint:
            a = self.hit([_norm(note.hint)], note)
            if a:
                return [{"alias": a, "position": 0}]
        tests = [f"- {cur}", cur]
        if prev_nb is not None:
            prev_l = _norm(prev_nb.hint or prev_nb.lyric)
            vow = VCV_LOOKUP.get(prev_l[-1:] if prev_l else "")
            if vow:
                tests = [f"{vow} {cur}", f"* {cur}", cur, f"- {cur}"]
        a = self.hit(tests, note)
        return [{"alias": a or cur, "position": 0}]


CVVC_PLAIN_VOWELS = {"あ", "い", "う", "え", "お", "を", "ん", "ン"}
CVVC_NON_VOWELS = {"息", "吸", "R", "-", "k", "ky", "g", "gy", "s", "sh", "z", "j", "t", "ch", "ty", "ts", "d", "dy", "n", "ny",
                   "h", "hy", "f", "b", "by", "p", "py", "m", "my", "y", "r", "4", "ry", "w", "v", "ng", "l", "・", "B", "H"}
CVVC_VOWELS = {
    "a": "ぁ,あ,か,が,さ,ざ,た,だ,な,は,ば,ぱ,ま,ゃ,や,ら,わ,ァ,ア,カ,ガ,サ,ザ,タ,ダ,ナ,ハ,バ,パ,マ,ャ,ヤ,ラ,ワ",
    "e": "ぇ,え,け,げ,せ,ぜ,て,で,ね,へ,べ,ぺ,め,れ,ゑ,ェ,エ,ケ,ゲ,セ,ゼ,テ,デ,ネ,ヘ,ベ,ペ,メ,レ,ヱ",
    "i": "ぃ,い,き,ぎ,し,じ,ち,ぢ,に,ひ,び,ぴ,み,り,ゐ,ィ,イ,キ,ギ,シ,ジ,チ,ヂ,ニ,ヒ,ビ,ピ,ミ,リ,ヰ",
    "o": "ぉ,お,こ,ご,そ,ぞ,と,ど,の,ほ,ぼ,ぽ,も,ょ,よ,ろ,を,ォ,オ,コ,ゴ,ソ,ゾ,ト,ド,ノ,ホ,ボ,ポ,モ,ョ,ヨ,ロ,ヲ",
    "n": "ん",
    "u": "ぅ,う,く,ぐ,す,ず,つ,づ,ぬ,ふ,ぶ,ぷ,む,ゅ,ゆ,る,ゥ,ウ,ク,グ,ス,ズ,ツ,ヅ,ヌ,フ,ブ,プ,ム,ュ,ユ,ル,ヴ",
    "N": "ン",
    "・": "・",
}
CVVC_CONSONANTS = {
    "ch": "ち,ちぇ,ちゃ,ちゅ,ちょ", "gy": "ぎ,ぎぇ,ぎゃ,ぎゅ,ぎょ", "ts": "つ,つぁ,つぃ,つぇ,つぉ", "ty": "てぃ,てぇ,てゃ,てゅ,てょ",
    "py": "ぴ,ぴぇ,ぴゃ,ぴゅ,ぴょ", "ry": "り,りぇ,りゃ,りゅ,りょ", "ly": "リ,リェ,リャ,リュ,リョ", "ny": "に,にぇ,にゃ,にゅ,にょ",
    "r": "ら,る,るぃ,れ,ろ", "hy": "ひ,ひぇ,ひゃ,ひゅ,ひょ", "dy": "でぃ,でぇ,でゃ,でゅ,でょ", "by": "び,びぇ,びゃ,びゅ,びょ",
    "b": "ば,ぶ,ぶぃ,べ,ぼ", "d": "だ,で,ど,どぃ,どぅ", "g": "が,ぐ,ぐぃ,げ,ご", "f": "ふ,ふぁ,ふぃ,ふぇ,ふぉ",
    "h": "は,はぃ,へ,ほ,ほぅ", "k": "か,く,くぃ,け,こ", "j": "じ,じぇ,じゃ,じゅ,じょ,ぢ,ぢぇ,ぢゃ,ぢゅ,ぢょ",
    "m": "ま,む,むぃ,め,も", "n": "な,ぬ,ぬぃ,ね,の", "p": "ぱ,ぷ,ぷぃ,ぺ,ぽ", "s": "さ,す,すぃ,せ,そ",
    "sh": "し,しぇ,しゃ,しゅ,しょ", "t": "た,て,と,とぃ,とぅ", "v": "ヴ,ヴぁ,ヴぃ,ヴぅ,ヴぇ,ヴぉ", "ky": "き,きぇ,きゃ,きゅ,きょ",
    "w": "うぃ,うぅ,うぇ,うぉ,わ,ゐ,ゑ,を,ヰ,ヱ", "y": "いぃ,いぇ,や,ゆ,よ", "z": "ざ,ず,ずぃ,ぜ,ぞ", "dz": "づ,づぃ",
    "my": "み,みぇ,みゃ,みゅ,みょ", "ng": "ガ,ギ,グ,ゲ,ゴ,ギェ,ギャ,ギュ,ギョ,カ゜,キ゜,ク゜,ケ゜,コ゜,キ゜ェ,キ゜ャ,キ゜ュ,キ゜ョ",
    "l": "ラ,ル,レ,ロ", "・": "・あ,・い,・う,・え,・お,・ん,・を,・ン",
}
CVVC_SUBST = {"ty": "t", "ch": "t", "ts": "t", "j": "d", "dy": "d", "gy": "g", "ky": "k", "py": "p", "ny": "n", "ry": "r",
              "my": "m", "hy": "h", "f": "h", "by": "b", "v": "b", "dz": "z", "l": "r", "ly": "l"}
CVVC_V = {k: v for v, ks in CVVC_VOWELS.items() for k in ks.split(",")}
CVVC_C = {k: c for c, ks in CVVC_CONSONANTS.items() for k in ks.split(",")}


@register("ja_cvvc", "OpenUtau.Plugin.Builtin.JapaneseCVVCPhonemizer", "ja")
class JapaneseCVVCPhonemizer(Phonemizer):
    def hit_vc(self, tests, note):
        """checkOtoUntilHitVc: a vc is only used when it exists in the note's own color."""
        color = self.color_of(note)
        for t in tests:
            if not t:
                continue
            r = self.voice.lookup(t, note.tone + note.controls.get("shift", 0), color)
            if r:
                return r[2]
        return None

    def process(self, notes, prev, nxt, prev_nb, next_nb):
        note = notes[0]
        cur = _norm(note.hint or note.lyric)
        original = cur
        cf = f"* {cur}"
        if note.hint:
            cur = self.hit([cur], note) or cur
        elif prev_nb is None:
            cur = self.hit([f"- {cur}", cur], note) or cur
        elif cur in CVVC_PLAIN_VOWELS or cur in CVVC_NON_VOWELS:
            prev_l = _norm(prev_nb.hint or prev_nb.lyric)
            vow = CVVC_V.get(prev_l[-1:] if prev_l else "")
            if vow:
                cur = self.hit([f"{vow} {cur}", cf, cur], note) or cur
        else:
            cur = self.hit([cf, cur], note) or cur

        if next_nb is not None and not next_nb.hint:
            nl = _norm(next_nb.lyric)
            if len(nl) == 1 and nl in CVVC_PLAIN_VOWELS:
                return [{"alias": cur, "position": 0}]
            vowel = CVVC_V.get(original[-1:] if original else "", "")
            cons = CVVC_C.get(nl[:1]) or (CVVC_C.get(nl[:2]) if len(nl) >= 2 else None) or ""
            if not cons:
                return [{"alias": cur, "position": 0}]
            tests = [f"{vowel} {cons}", f"{vowel} {CVVC_SUBST[cons]}" if cons in CVVC_SUBST else ""]
            vc = self.hit_vc(tests, note)
            if not vc:
                return [{"alias": cur, "position": 0}]
            total = sum(n.duration for n in notes)
            vc_len = 120
            r = self.voice.lookup(nl, next_nb.tone + next_nb.controls.get("shift", 0), self.color_of(next_nb))
            if r:
                oto = r[1]
                ms = oto.preutter - oto.overlap if oto.overlap < 0 else oto.preutter
                vc_len = self.ms_to_tick(ms, next_nb.position - 1)
            stretch = 2 ** (1 - float(next_nb.controls.get("vel", 100)) / 100)
            vc_len = int(round(min(total / 2, vc_len * stretch)))
            return [{"alias": cur, "position": 0}, {"alias": vc, "position": total - vc_len}]
        return [{"alias": cur, "position": 0}]


# openutau default_phonemizer names -> ours
OPENUTAU_NAMES = {cls.openutau_class: name for name, cls in REGISTRY.items() if cls.openutau_class}
NOT_PORTED = {
    "OpenUtau.Plugin.Builtin.JapanesePresampPhonemizer": "the presamp-based japanese phonemizer is not ported yet (milestone 8)",
}


def choose(bank, reclist_style, requested=None):
    """-> (phonemizer name, how it was chosen, warning or None)."""
    if requested:
        if requested in REGISTRY:
            return requested, "requested", None
        if requested in OPENUTAU_NAMES:
            return OPENUTAU_NAMES[requested], "requested (openutau name)", None
        raise WarbleError("phonemizer_unknown", f"phonemizer '{requested}' is not available", hint=f"available: {sorted(REGISTRY)}")
    warn = None
    dp = bank.character.get("default_phonemizer")
    if dp:
        if dp in OPENUTAU_NAMES:
            return OPENUTAU_NAMES[dp], f"character.yaml default_phonemizer {dp}", None
        warn = f"bank asks for {dp}: {NOT_PORTED.get(dp, 'not ported yet')}; picked one from the reclist style instead"
    styles = reclist_style.split("+")
    if styles[0] == "vcv":
        return "ja_vcv", f"reclist style {reclist_style}", warn
    if styles[0] == "cvvc":
        return "ja_cvvc", f"reclist style {reclist_style}", warn
    if styles[0] == "cv":
        return "default", f"reclist style {reclist_style}", warn
    raise WarbleError(
        "no_phonemizer",
        f"no ported phonemizer fits a '{reclist_style}' bank yet",
        hint=f"give aliases directly in [brackets], or pick one of {sorted(REGISTRY)} with 'phonemizer <name>'",
    )
