"""text file decoding for voicebank files, which come in shift-jis, utf-8, gbk and friends.

every read reports which encoding was used and why, so a mojibake alias can be traced
back to a guess instead of looking like a broken bank.
"""

import codecs
import unicodedata

# python codec names for the encodings utau banks actually use
CANDIDATES = ["utf-8", "cp932", "gbk", "big5", "cp949"]


def normalize_encoding_name(name):
    """map a .net / openutau encoding name to a python codec, or None if unknown."""
    if not name:
        return None
    key = name.strip().lower().replace("_", "-")
    aliases = {
        "shift-jis": "cp932",
        "shiftjis": "cp932",
        "sjis": "cp932",
        "x-sjis": "cp932",
        "windows-31j": "cp932",
        "utf8": "utf-8",
        "gb2312": "gbk",
        "euc-kr": "cp949",
        "ks-c-5601-1987": "cp949",
    }
    key = aliases.get(key, key)
    try:
        return codecs.lookup(key).name
    except LookupError:
        return None


def _has_kana(text):
    return any("぀" <= ch <= "ヿ" for ch in text)


def _has_hangul(text):
    return any("가" <= ch <= "힣" for ch in text)


def _weird_ratio(text):
    """fraction of non-ascii chars that are private-use, unassigned or halfwidth katakana,
    which is what a wrong cjk codec tends to produce."""
    non_ascii = [ch for ch in text if ord(ch) > 127]
    if not non_ascii:
        return 0.0
    bad = 0
    for ch in non_ascii:
        cat = unicodedata.category(ch)
        if cat in ("Co", "Cn", "Cs") or "｡" <= ch <= "ﾟ":
            bad += 1
    return bad / len(non_ascii)


def decode_bytes(data, declared=None, preferred=None):
    """decode bytes, returning (text, encoding, how).

    order: a declared encoding (#Charset or character.yaml) wins, then a utf-8 bom, then
    strict utf-8, then `preferred` (the encoding the rest of the bank already uses), then the
    cjk codecs scored by how plausible their output looks.
    """
    if declared:
        codec = normalize_encoding_name(declared)
        if codec:
            try:
                return data.decode(codec), codec, "declared"
            except UnicodeDecodeError:
                pass
    if data.startswith(codecs.BOM_UTF8):
        return data[len(codecs.BOM_UTF8):].decode("utf-8", errors="replace"), "utf-8-sig", "bom"
    if data.startswith(codecs.BOM_UTF16_LE) or data.startswith(codecs.BOM_UTF16_BE):
        return data.decode("utf-16", errors="replace"), "utf-16", "bom"
    try:
        text = data.decode("ascii")
        return text, "ascii", "ascii-only"
    except UnicodeDecodeError:
        pass
    try:
        return data.decode("utf-8"), "utf-8", "valid-utf-8"
    except UnicodeDecodeError:
        pass
    pref = normalize_encoding_name(preferred) if preferred else None
    if pref and pref not in ("utf-8", "ascii"):
        try:
            return data.decode(pref), pref, "same as rest of bank"
        except UnicodeDecodeError:
            pass
    scored = []
    for codec in CANDIDATES[1:]:
        try:
            text = data.decode(codec)
        except UnicodeDecodeError:
            continue
        score = _weird_ratio(text)
        # japanese banks are the common case; kana in cp932 output is strong evidence
        if codec == "cp932" and _has_kana(text):
            score -= 0.5
        if codec == "cp949" and _has_hangul(text) and not _has_kana(text):
            score -= 0.2
        scored.append((score, CANDIDATES.index(codec), codec, text))
    if scored:
        scored.sort()
        score, _, codec, text = scored[0]
        if len(scored) == 1:
            how = "only-valid-codec"
        elif codec == "cp932" and _has_kana(text) and score < 0:
            how = "detected (kana present)"
        else:
            how = "guessed"
        return text, codec, how
    return data.decode("cp932", errors="replace"), "cp932", "fallback-with-replacement"


def read_text(path, declared=None, preferred=None):
    with open(path, "rb") as f:
        data = f.read()
    return decode_bytes(data, declared, preferred)


def oto_declared_charset(data):
    """openutau lets an oto.ini declare its encoding with '#Charset:<name>' in its first 10 lines."""
    head = data[:4096].decode("ascii", errors="ignore").splitlines()[:10]
    for line in head:
        line = line.strip()
        if line.startswith("#Charset:"):
            return line[len("#Charset:"):].strip()
    return None
