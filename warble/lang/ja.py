"""japanese front-end: kana normalization, mora splitting and kana -> romaji.

used only when a bank's own dictionary doesn't already cover the lyric. romaji follows the
hepburn-ish spelling openutau's kana converter (WanaKana-style) produces: し=shi, ち=chi, つ=tsu,
ふ=fu, じ=ji, ん=N (the diffsinger japanese phonemizer maps ん to N).
"""

SMALL = set("ぁぃぅぇぉゃゅょゎァィゥェォャュョヮ")
SOKUON = {"っ", "ッ"}
CHOON = {"ー", "～", "〜"}

BASE = {
    "あ": "a", "い": "i", "う": "u", "え": "e", "お": "o",
    "か": "ka", "き": "ki", "く": "ku", "け": "ke", "こ": "ko",
    "が": "ga", "ぎ": "gi", "ぐ": "gu", "げ": "ge", "ご": "go",
    "さ": "sa", "し": "shi", "す": "su", "せ": "se", "そ": "so",
    "ざ": "za", "じ": "ji", "ず": "zu", "ぜ": "ze", "ぞ": "zo",
    "た": "ta", "ち": "chi", "つ": "tsu", "て": "te", "と": "to",
    "だ": "da", "ぢ": "ji", "づ": "zu", "で": "de", "ど": "do",
    "な": "na", "に": "ni", "ぬ": "nu", "ね": "ne", "の": "no",
    "は": "ha", "ひ": "hi", "ふ": "fu", "へ": "he", "ほ": "ho",
    "ば": "ba", "び": "bi", "ぶ": "bu", "べ": "be", "ぼ": "bo",
    "ぱ": "pa", "ぴ": "pi", "ぷ": "pu", "ぺ": "pe", "ぽ": "po",
    "ま": "ma", "み": "mi", "む": "mu", "め": "me", "も": "mo",
    "や": "ya", "ゆ": "yu", "よ": "yo",
    "ら": "ra", "り": "ri", "る": "ru", "れ": "re", "ろ": "ro",
    "わ": "wa", "ゐ": "wi", "ゑ": "we", "を": "wo", "ん": "N",
    "ゔ": "vu",
    "ぁ": "a", "ぃ": "i", "ぅ": "u", "ぇ": "e", "ぉ": "o", "ゃ": "ya", "ゅ": "yu", "ょ": "yo", "ゎ": "wa",
}
# two-kana combinations
COMBO = {
    "きゃ": "kya", "きゅ": "kyu", "きょ": "kyo", "きぇ": "kye", "ぎゃ": "gya", "ぎゅ": "gyu", "ぎょ": "gyo", "ぎぇ": "gye",
    "しゃ": "sha", "しゅ": "shu", "しょ": "sho", "しぇ": "she", "じゃ": "ja", "じゅ": "ju", "じょ": "jo", "じぇ": "je",
    "ちゃ": "cha", "ちゅ": "chu", "ちょ": "cho", "ちぇ": "che", "ぢゃ": "ja", "ぢゅ": "ju", "ぢょ": "jo",
    "にゃ": "nya", "にゅ": "nyu", "にょ": "nyo", "にぇ": "nye", "ひゃ": "hya", "ひゅ": "hyu", "ひょ": "hyo", "ひぇ": "hye",
    "びゃ": "bya", "びゅ": "byu", "びょ": "byo", "びぇ": "bye", "ぴゃ": "pya", "ぴゅ": "pyu", "ぴょ": "pyo", "ぴぇ": "pye",
    "みゃ": "mya", "みゅ": "myu", "みょ": "myo", "みぇ": "mye", "りゃ": "rya", "りゅ": "ryu", "りょ": "ryo", "りぇ": "rye",
    "ふぁ": "fa", "ふぃ": "fi", "ふぇ": "fe", "ふぉ": "fo", "ふゅ": "fyu",
    "てぃ": "ti", "でぃ": "di", "とぅ": "tu", "どぅ": "du", "てゅ": "tyu", "でゅ": "dyu",
    "うぃ": "wi", "うぇ": "we", "うぉ": "wo", "いぇ": "ye", "すぃ": "si", "ずぃ": "zi",
    "つぁ": "tsa", "つぃ": "tsi", "つぇ": "tse", "つぉ": "tso",
    "ゔぁ": "va", "ゔぃ": "vi", "ゔぇ": "ve", "ゔぉ": "vo", "くぁ": "kwa", "ぐぁ": "gwa",
}


def to_hiragana(text):
    """katakana -> hiragana; ヴ -> ゔ; う゛ (standalone dakuten) -> ゔ."""
    out = []
    for ch in text:
        o = ord(ch)
        if 0x30A1 <= o <= 0x30F6:
            out.append(chr(o - 0x60))
        else:
            out.append(ch)
    s = "".join(out)
    return s.replace("う゛", "ゔ").replace("ゔ", "ゔ")


def is_kana(text):
    return bool(text) and all(("぀" <= c <= "ヿ") or c in CHOON for c in text)


def split_mora(text):
    """'きゃっとー' -> ['きゃ', 'っ', 'と', 'ー']. small kana join the previous mora; っ and ー are
    their own mora (they take a note in japanese singing)."""
    out = []
    for ch in text:
        if ch in SMALL and out and out[-1] not in SOKUON and out[-1] not in CHOON:
            out[-1] += ch
        else:
            out.append(ch)
    return out


def mora_vowel(mora):
    r = kana_to_romaji(mora)
    for c in reversed(r):
        if c in "aiueo":
            return c
    return "N" if r == "N" else None


def kana_to_romaji(text):
    """romanize one lyric. っ doubles the next consonant ('cl' when nothing follows), ー repeats the vowel."""
    h = to_hiragana(text)
    out = []
    i = 0
    gem = False
    while i < len(h):
        two = h[i:i + 2]
        if two in COMBO:
            r = COMBO[two]
            i += 2
        elif h[i] in ("っ",):
            gem = True
            i += 1
            continue
        elif h[i] in CHOON:
            prev = "".join(out)
            v = next((c for c in reversed(prev) if c in "aiueo"), "")
            r = v
            i += 1
        elif h[i] in BASE:
            r = BASE[h[i]]
            i += 1
        else:
            r = h[i]
            i += 1
        if gem:
            r = (r[0] + r) if r and r[0] not in "aiueoN" else r
            gem = False
        out.append(r)
    if gem:
        out.append("cl")
    return "".join(out)


def normalize_lyric(lyric):
    """variants worth trying against a dictionary, most faithful first."""
    cands = [lyric]
    h = to_hiragana(lyric)
    if h != lyric:
        cands.append(h)
    if is_kana(h):
        r = kana_to_romaji(h)
        if r not in cands:
            cands.append(r)
    return cands


def phoneme_guesses(lyric):
    """when a dictionary lacks a kana, romanize it and split each mora into consonant + vowel
    ('ゔぃ' -> ['v', 'i'], 'きゃっ' -> ['ky', 'a', 'cl']). the caller keeps a guess only if the bank
    has every symbol."""
    h = to_hiragana(lyric)
    if not is_kana(h):
        return []
    out = []
    for mora in split_mora(h):
        if mora in SOKUON:
            out.append("cl")
            continue
        if mora in CHOON:
            if out and out[-1] in "aiueo":
                out.append(out[-1])
            continue
        r = kana_to_romaji(mora)
        if r == "N":
            out.append("N")
            continue
        k = len(r)
        while k > 0 and r[k - 1] in "aiueo":
            k -= 1
        cons, vow = r[:k], r[k:]
        if cons:
            out.append(cons)
        if vow:
            out.append(vow)
    return [out] if out else []
