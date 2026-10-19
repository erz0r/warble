"""split lyric text into singable units and assign them to notes.

japanese: mora (kanji read via pykakasi when installed, with the reading reported per word so a
misreading can be corrected); small kana join their mora, っ is its own mora, ー extends the
previous vowel as a '+' note. english: one unit per word spanning as many notes as it has
syllables (word on the first note, '+' on the rest, the convention openutau's english phonemizers
use). chinese: one character per note.
nothing is dropped silently: leftover text or notes are reported.
"""

import re
import unicodedata

from .errors import WarbleError
from .lang import ja

PUNCT = set("、。，．,.!?！？「」『』（）()[]【】・…‥:;：；\"'“”‘’〜~")


def _is_kanji(ch):
    return "一" <= ch <= "鿿" or "㐀" <= ch <= "䶿" or ch in "々〆ヶ"


def japanese_reading(text):
    """-> (kana text, [{"text": original, "reading": kana}]) for every chunk that contained kanji."""
    readings = []
    if not any(_is_kanji(c) for c in text):
        return text, readings
    try:
        import pykakasi
    except ImportError:
        raise WarbleError("kanji_reader_missing", "text has kanji but pykakasi is not installed", hint="pip install pykakasi, or give the lyrics in kana")
    items = pykakasi.kakasi().convert(text)
    out = []
    for i, item in enumerate(items):
        orig, hira = item["orig"], item["hira"]
        nxt = items[i + 1]["orig"] if i + 1 < len(items) else ""
        if any(_is_kanji(c) for c in orig):
            # pykakasi sometimes reads the okurigana into the kanji chunk and then repeats it
            # ('茶摘' -> 'ちゃつみ', then 'み'); drop the overlap
            k = len(nxt)
            while k > 0:
                tail = ja.to_hiragana(nxt[:k])
                if ja.is_kana(tail) and hira.endswith(tail) and len(hira) > len(tail):
                    hira = hira[: -len(tail)]
                    break
                k -= 1
            readings.append({"text": orig, "reading": hira})
        out.append(hira)
    return "".join(out), readings


def split_japanese(text, sokuon="separate"):
    kana, readings = japanese_reading(text)
    units = []
    for word in re.split(r"\s+", kana):
        clean = "".join(c for c in word if c not in PUNCT)
        for m in ja.split_mora(clean):
            if m in ja.CHOON:
                units.append({"lyric": "+", "notes": 1, "from": m})
            elif m in ja.SOKUON and sokuon == "attach" and units and units[-1]["lyric"] != "+":
                units[-1]["lyric"] += m
            else:
                units.append({"lyric": m, "notes": 1})
    return units, readings


VOWELS = "aeiouy"


def english_syllables(word):
    """vowel-group count with the usual silent-e and -le fixes; good enough to size a word."""
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w:
        return 0
    groups = re.findall(r"[aeiouy]+", w)
    n = len(groups)
    if w.endswith("e") and not w.endswith(("le", "ee", "ye")) and n > 1:
        n -= 1
    if w.endswith("le") and len(w) > 2 and w[-3] not in VOWELS:
        n = max(n, len(re.findall(r"[aeiouy]+", w[:-2])) + 1)
    return max(1, n)


def english_hyphenation(word):
    try:
        import pyphen

        return pyphen.Pyphen(lang="en_US").inserted(word).split("-")
    except Exception:  # noqa: BLE001 - display only
        return [word]


def split_english(text):
    units = []
    for word in re.findall(r"[A-Za-z']+", text):
        n = english_syllables(word)
        units.append({"lyric": word.lower(), "notes": n, "syllables": english_hyphenation(word)})
    return units, []


def split_chinese(text):
    return [{"lyric": c, "notes": 1} for c in text if not c.isspace() and c not in PUNCT and unicodedata.category(c)[0] == "L"], []


def split(text, lang, sokuon="separate"):
    if lang == "ja":
        return split_japanese(text, sokuon)
    if lang == "en":
        return split_english(text)
    if lang in ("zh", "yue", "cmn"):
        return split_chinese(text)
    # unknown language: whitespace-separated tokens, one per note
    return [{"lyric": t, "notes": 1} for t in text.split()], []


def assign(notes, units, extra="extend-last"):
    """put units onto notes in order. a unit spanning n notes gets its lyric on the first and '+'
    on the rest. returns a report with any leftover units or notes."""
    lyr = []
    for u in units:
        lyr.append(u["lyric"])
        lyr.extend(["+"] * (u["notes"] - 1))
    report = {"units": len(units), "notes": len(notes), "syllable_slots": len(lyr)}
    n = min(len(notes), len(lyr))
    for i in range(n):
        notes[i].lyric = lyr[i]
        notes[i].hint = None
    if len(lyr) > len(notes):
        report["unassigned_text"] = lyr[len(notes):]
        report["mismatch"] = f"{len(lyr) - len(notes)} more syllable(s) than notes; the tail of the text was not placed"
    elif len(notes) > len(lyr):
        left = notes[len(lyr):]
        if extra == "extend-last" and lyr:
            for nt in left:
                nt.lyric = "+"
        report["extra_notes"] = [nt.position for nt in left]
        report["mismatch"] = f"{len(left)} more note(s) than syllables; they were made '+' continuations of the last syllable"
    return report
