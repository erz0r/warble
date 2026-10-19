"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Core/KoreanPhonemizerUtil.cs

static helpers for the korean phonemizers: hangeul jamo separation / merging, korean romaji
parsing and phoneme variation (음운 변동).

c# Hashtables {0: "ㄴ", 1: "ㅑ", 2: "ㅇ"} are python dicts with int keys. the c# Variate overloads
get distinct names:
  Variate(Hashtable, Hashtable, int=-1)  -> variate_separated(first, next, return_char_index=-1)
  Variate(string)                        -> variate_char(character)
  Variate(Hashtable)                     -> variate_one(separated)       (mutates, like c#)
  Variate(string, string, int=0)         -> variate_chars(first, next, return_char_index=0)
  Variate(Note?, Note, Note?)            -> variate(prev_neighbour, note, next_neighbour)
  Variate(string?, string, string?)      -> variate_lyrics(prev, note, next)

not ported: BaseIniManager (ini settings files written into the singer folder) and JamoDictionary
(a yaml data class); no builtin classic korean phonemizer uses either of them any more.
"""

import dataclasses

FIRST_CONSONANTS = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
MIDDLE_VOWELS = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
LAST_CONSONANTS = " ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"  # the first blank: no last consonant

HANGEUL_UNICODE_START = 0xAC00
HANGEUL_UNICODE_END = 0xD79F

basic_sounds = {"ㄱ": 0, "ㄷ": 1, "ㅂ": 2, "ㅈ": 3, "ㅅ": 4}
aspirate_sounds = {0: "ㅋ", 1: "ㅌ", 2: "ㅍ", 3: "ㅊ", 4: "ㅌ"}
fortis_sounds = {0: "ㄲ", 1: "ㄸ", 2: "ㅃ", 3: "ㅉ", 4: "ㅆ"}
nasal_sounds = {"ㄴ": 0, "ㅇ": 1, "ㅁ": 2}

ROMAJI_KOREAN_FIRST_CONSONANTS_DICT = {
    "g": "ㄱ", "n": "ㄴ", "d": "ㄷ", "r": "ㄹ", "l": "ㄹ", "m": "ㅁ", "b": "ㅂ", "s": "ㅅ", "j": "ㅈ", "ch": "ㅊ", "k": "ㅋ", "t": "ㅌ",
    "p": "ㅍ", "h": "ㅎ", "gg": "ㄲ", "kk": "ㄲ", "dd": "ㄸ", "tt": "ㄸ", "bb": "ㅃ", "pp": "ㅃ", "ss": "ㅆ", "jj": "ㅉ", "": "ㅇ",
}
ROMAJI_KOREAN_MIDDLE_VOWELS_DICT = {
    "yae": "ㅒ", "yeo": "ㅕ", "wae": "ㅙ", "weo": "ㅝ", "eui": "ㅢ", "ui": "ㅢ", "wa": "ㅘ", "oe": "ㅚ", "wo": "ㅝ", "wi": "ㅟ", "we": "ㅞ",
    "ya": "ㅑ", "yu": "ㅠ", "ye": "ㅖ", "yo": "ㅛ", "ae": "ㅐ", "eu": "ㅡ", "eo": "ㅓ", "a": "ㅏ", "i": "ㅣ", "u": "ㅜ", "e": "ㅔ", "o": "ㅗ",
}
ROMAJI_KOREAN_LAST_CONSONANTS_DICT = {"k": "ㄱ", "n": "ㄴ", "t": "ㄷ", "l": "ㄹ", "m": "ㅁ", "p": "ㅂ", "ng": "ㅇ", "": " "}


def _idx(s, i):
    """c# string indexer: throws on a negative or too large index (python would wrap)."""
    if i < 0 or i >= len(s):
        raise IndexError("Index was outside the bounds of the array.")
    return s[i]


def _rem(a, b):
    """c# % (sign follows the dividend)."""
    r = abs(a) % abs(b)
    return -r if a < 0 else r


def _div(a, b):
    """c# integer / (truncates toward zero)."""
    q = abs(a) // abs(b)
    return -q if (a < 0) != (b < 0) else q


def is_hangeul(character):
    if character is not None and character.startswith("!"):
        unicode_index = ord(_idx(character.lstrip("!"), 0))  # not caught in c#
        return not (unicode_index < HANGEUL_UNICODE_START or unicode_index > HANGEUL_UNICODE_END)
    elif character is not None:
        try:
            unicode_index = ord(_idx(character, 0))
            return not (unicode_index < HANGEUL_UNICODE_START or unicode_index > HANGEUL_UNICODE_END)
        except Exception:  # noqa: BLE001
            return False
    return False


def is_korean_romaji(lyric):
    return (not is_hangeul(lyric)) and try_parse_korean_romaji(lyric) is not None


_ROMAJI_TABLE = None


def _romaji_table():
    global _ROMAJI_TABLE
    if _ROMAJI_TABLE is None:
        table = {}
        for first, f in ROMAJI_KOREAN_FIRST_CONSONANTS_DICT.items():
            for middle, m in ROMAJI_KOREAN_MIDDLE_VOWELS_DICT.items():
                for last, l in ROMAJI_KOREAN_LAST_CONSONANTS_DICT.items():
                    table.setdefault(first + middle + last, (f, m, l))  # IndexOf: the first match wins
        _ROMAJI_TABLE = table
    return _ROMAJI_TABLE


def try_parse_korean_romaji(romaji):
    if not romaji:
        return None
    hit = _romaji_table().get(romaji)
    if hit is None:
        return None
    return merge({0: hit[0], 1: hit[1], 2: hit[2]})


def separate(character):
    hangeul_index = ord(_idx(character, 0)) - HANGEUL_UNICODE_START
    last_consonant_index = _rem(hangeul_index, 28)
    hangeul_index = _div(hangeul_index - last_consonant_index, 28)
    middle_vowel_index = _rem(hangeul_index, 21)
    hangeul_index = _div(hangeul_index - middle_vowel_index, 21)
    first_consonant_index = hangeul_index
    return {
        0: _idx(FIRST_CONSONANTS, first_consonant_index),
        1: _idx(MIDDLE_VOWELS, middle_vowel_index),
        2: _idx(LAST_CONSONANTS, last_consonant_index),
    }


def separate_romaji(character):
    # the c# loop breaks or returns on its first iteration, so only the first vowel key is tested
    try:
        separated = []
        for vowel in ROMAJI_KOREAN_MIDDLE_VOWELS_DICT:
            if vowel in character:
                part = character.split(vowel)
                if part[1] != "":
                    separated = [part[0], vowel, part[1]]
                elif len(part) == 2:  # (part == new string[]{"", ""} is a reference compare: never true)
                    separated = [part[0], vowel, ""]
                break
            if len(separated) == 0:
                separated = ["", "", ""]
            return separated
    except Exception:  # noqa: BLE001
        return ["", "", ""]
    return ["", "", ""]


def merge(separated_hangeul, offset=0):
    first_consonant = _idx(separated_hangeul[offset + 0], 0)
    middle_vowel = _idx(separated_hangeul[offset + 1], 0)
    last_consonant = _idx(separated_hangeul[offset + 2], 0)
    if first_consonant == " ":
        first_consonant = "ㅇ"
    first_consonant_index = FIRST_CONSONANTS.find(first_consonant)
    middle_vowel_index = MIDDLE_VOWELS.find(middle_vowel)
    last_consonant_index = LAST_CONSONANTS.find(last_consonant)
    merged_code = HANGEUL_UNICODE_START + (first_consonant_index * 21 + middle_vowel_index) * 28 + last_consonant_index
    if merged_code < 0 or merged_code > 0xFFFF:
        raise OverflowError("Value was either too large or too small for a character.")
    return chr(merged_code)


def variate_separated(first_char_separated, next_char_separated, return_char_index=-1):
    first_last_consonant = first_char_separated[2]
    next_first_consonant = next_char_separated[0]

    # 1. 연음 적용 + ㅎ탈락
    if first_last_consonant != " " and next_first_consonant == "ㅎ":
        if first_last_consonant in basic_sounds:
            next_first_consonant = aspirate_sounds[basic_sounds[first_last_consonant]]
            first_last_consonant = " "
        else:
            next_first_consonant = "ㅇ"

    if next_first_consonant == "ㅇ" and first_last_consonant != " ":
        pairs = {"ㄳ": ("ㄱ", "ㅅ"), "ㄵ": ("ㄴ", "ㅈ"), "ㄶ": ("ㄴ", "ㅎ"), "ㄺ": ("ㄹ", "ㄱ"), "ㄼ": ("ㄹ", "ㅂ"), "ㄽ": ("ㄹ", "ㅅ"),
                 "ㄾ": ("ㄹ", "ㅌ"), "ㄿ": ("ㄹ", "ㅍ"), "ㅀ": ("ㄹ", "ㅎ"), "ㅄ": ("ㅂ", "ㅅ"), "ㄻ": ("ㄹ", "ㅁ")}
        if first_last_consonant in pairs:
            first_last_consonant, next_first_consonant = pairs[first_last_consonant]
        elif first_last_consonant == "ㅇ" and next_first_consonant == "ㅇ":
            pass
        else:
            next_first_consonant = first_last_consonant
            first_last_consonant = " "

    # 1. 유기음화 및 ㅎ탈락 1
    if first_last_consonant == "ㅎ" and next_first_consonant != "ㅅ" and next_first_consonant in basic_sounds:
        first_last_consonant = " "
        next_first_consonant = aspirate_sounds[basic_sounds[next_first_consonant]]
    elif first_last_consonant == "ㅎ" and next_first_consonant != "ㅅ" and next_first_consonant == "ㅇ":
        first_last_consonant = " "
    elif first_last_consonant == "ㄶ" and next_first_consonant != "ㅅ" and next_first_consonant in basic_sounds:
        first_last_consonant = "ㄴ"
        next_first_consonant = aspirate_sounds[basic_sounds[next_first_consonant]]
    elif first_last_consonant == "ㅀ" and next_first_consonant != "ㅅ" and next_first_consonant in basic_sounds:
        first_last_consonant = "ㄹ"
        next_first_consonant = aspirate_sounds[basic_sounds[next_first_consonant]]

    # 2-1. 된소리되기 1
    if first_last_consonant in ("ㄳ", "ㄵ", "ㄽ", "ㄾ", "ㅄ", "ㄼ", "ㄺ", "ㄿ") and next_first_consonant in basic_sounds:
        next_first_consonant = fortis_sounds[basic_sounds[next_first_consonant]]

    # 3. 첫 번째 글자의 자음군단순화 및 평파열음화(음절의 끝소리 규칙)
    if first_last_consonant in ("ㄽ", "ㄾ", "ㄼ"):
        first_last_consonant = "ㄹ"
    elif first_last_consonant in ("ㄵ", "ㅅ", "ㅆ", "ㅈ", "ㅉ", "ㅊ", "ㅌ"):
        first_last_consonant = "ㄷ"
    elif first_last_consonant in ("ㅃ", "ㅍ", "ㄿ", "ㅄ"):
        first_last_consonant = "ㅂ"
    elif first_last_consonant in ("ㄲ", "ㅋ", "ㄺ", "ㄳ"):
        first_last_consonant = "ㄱ"
    elif first_last_consonant == "ㄻ":
        first_last_consonant = "ㅁ"

    # 2-1. 된소리되기 2
    if first_last_consonant in basic_sounds and next_first_consonant in basic_sounds:
        next_first_consonant = fortis_sounds[basic_sounds[next_first_consonant]]

    # 1. 유기음화 2
    if first_last_consonant in basic_sounds and next_first_consonant == "ㅎ":
        next_first_consonant = aspirate_sounds[basic_sounds[first_last_consonant]]
        first_last_consonant = " "
    elif next_first_consonant == "ㅎ":
        next_first_consonant = "ㅇ"

    if first_last_consonant != " " and next_first_consonant == "ㅇ" and first_last_consonant != "ㅇ":
        # 연음 2
        next_first_consonant = first_last_consonant
        first_last_consonant = " "

    # 4. 비음화
    nasal_or_r = next_first_consonant != "ㅇ" and (next_first_consonant in nasal_sounds or next_first_consonant == "ㄹ")
    if first_last_consonant == "ㄱ" and nasal_or_r:
        first_last_consonant = "ㅇ"
    elif first_last_consonant == "ㄷ" and nasal_or_r:
        first_last_consonant = "ㄴ"
    elif first_last_consonant == "ㅂ" and nasal_or_r:
        first_last_consonant = "ㅁ"

    # 4'. 유음화
    if first_last_consonant == "ㄴ" and next_first_consonant == "ㄹ":
        first_last_consonant = "ㄹ"
    elif first_last_consonant == "ㄹ" and next_first_consonant == "ㄴ":
        next_first_consonant = "ㄹ"

    # 4''. ㄹ비음화 (never true: ㄹ is not a nasal sound)
    if next_first_consonant == "ㄹ" and next_first_consonant in nasal_sounds:
        first_last_consonant = "ㄴ"

    # 4'''. 자음동화
    if first_last_consonant == "ㄴ" and next_first_consonant == "ㄱ":
        first_last_consonant = "ㅇ"

    if return_char_index == 0:
        return {0: first_char_separated[0], 1: first_char_separated[1], 2: first_last_consonant}
    elif return_char_index == 1:
        return {0: next_first_consonant, 1: next_char_separated[1], 2: next_char_separated[2]}
    return {0: first_char_separated[0], 1: first_char_separated[1], 2: first_last_consonant,
            3: next_first_consonant, 4: next_char_separated[1], 5: next_char_separated[2]}


def variate_one(separated):
    """Variate(Hashtable): end-of-word simplification, in place."""
    s = separated[2]
    if s in ("ㄽ", "ㄾ", "ㄼ", "ㅀ"):
        separated[2] = "ㄹ"
    elif s in ("ㄵ", "ㅅ", "ㅆ", "ㅈ", "ㅉ", "ㅊ"):
        separated[2] = "ㄷ"
    elif s in ("ㅃ", "ㅍ", "ㄿ", "ㅄ"):
        separated[2] = "ㅂ"
    elif s in ("ㄲ", "ㅋ", "ㄺ", "ㄳ"):
        separated[2] = "ㄱ"
    elif s == "ㄻ":
        separated[2] = "ㅁ"
    elif s == "ㄶ":
        separated[2] = "ㄴ"
    return separated


def variate_char(character):
    """Variate(string)"""
    return variate_one(separate(character))


def variate_chars(first_char, next_char, return_char_index=0):
    """Variate(string, string, int)"""
    return variate_separated(separate(first_char), separate(next_char), return_char_index)


def _variate_core(lyrics):
    """the shared body of Variate(Note?, Note, Note?) and Variate(string?, string, string?) on the
    three lyrics; returns the 9-entry table."""
    where_yeon_eum = -1
    lyrics = list(lyrics)

    if not is_hangeul(lyrics[0]):
        if lyrics[0] is not None:
            lyrics[0] = None
    elif not is_hangeul(lyrics[2]):
        if lyrics[2] is not None:
            lyrics[2] = None
    if lyrics[0] is not None and lyrics[0].startswith("!"):
        lyrics[0] = None
    if lyrics[1] is not None and lyrics[1].startswith("!"):
        lyrics[1] = lyrics[1].lstrip("!")
        lyrics[0] = None
        lyrics[2] = None
    if lyrics[2] is not None and lyrics[2].startswith("!"):
        lyrics[2] = None

    if lyrics[0] is not None and lyrics[0].endswith("."):
        lyrics[0] = lyrics[0].rstrip(".")
        where_yeon_eum = 0
    if lyrics[1] is not None and lyrics[1].endswith("."):
        lyrics[1] = lyrics[1].rstrip(".")
        where_yeon_eum = 1
    if lyrics[2] is not None and lyrics[2].endswith("."):
        lyrics[2] = lyrics[2].rstrip(".")

    nulls = {0: "null", 1: "null", 2: "null"}

    def add(result, this_sep, with_next):
        result[3], result[4], result[5] = this_sep[0], this_sep[1], this_sep[2]
        if with_next:
            result[6], result[7], result[8] = this_sep[3], this_sep[4], this_sep[5]
        else:
            result[6], result[7], result[8] = "null", "null", "null"
        return result

    if lyrics[0] is None and lyrics[2] is not None:
        if where_yeon_eum == 1:
            this = variate_separated(variate_char(lyrics[1]), separate(lyrics[2]), -1)
            return add(dict(nulls), this, True)
        if is_hangeul(lyrics[2]):
            return add(dict(nulls), variate_chars(lyrics[1], lyrics[2], -1), True)
        return add(dict(nulls), variate_char(lyrics[1]), False)
    elif lyrics[0] is not None and lyrics[2] is None:
        if where_yeon_eum == 1:
            result = variate_separated(separate(lyrics[0]), variate_char(lyrics[1]), 0)
            this = variate_one(variate_separated(separate(lyrics[0]), variate_char(lyrics[1]), 1))
            return add(result, this, False)
        elif where_yeon_eum == 0:
            result = variate_separated(variate_char(lyrics[0]), separate(lyrics[1]), 0)
            this = variate_one(variate_separated(variate_char(lyrics[0]), separate(lyrics[1]), 1))
            return add(result, this, False)
        result = variate_chars(lyrics[0], lyrics[1], 0)
        this = variate_one(variate_chars(lyrics[0], lyrics[1], 1))
        return add(result, this, False)
    elif lyrics[0] is not None and lyrics[2] is not None:
        if where_yeon_eum == 1:
            result = variate_separated(separate(lyrics[0]), variate_char(lyrics[1]), 1)  # (sic) 1: the current char
            this = variate_separated(variate_separated(separate(lyrics[0]), variate_char(lyrics[1]), 1), separate(lyrics[2]), -1)
            return add(result, this, True)
        elif where_yeon_eum == 0:
            result = variate_separated(variate_char(lyrics[0]), separate(lyrics[1]), 0)
            this = variate_separated(variate_separated(variate_char(lyrics[0]), separate(lyrics[1]), 1), separate(lyrics[2]), -1)
            return add(result, this, True)
        result = variate_chars(lyrics[0], lyrics[1], 0)
        this = variate_separated(variate_chars(lyrics[0], lyrics[1], 1), separate(lyrics[2]), -1)
        return add(result, this, True)
    return add(dict(nulls), variate_char(lyrics[1]), False)


def variate(prev_neighbour, note, next_neighbour):
    """Variate(Note? prevNeighbour, Note note, Note? nextNeighbour) -> {0..8}: prev, this, next jamo
    ("null" where absent)."""
    return _variate_core([prev_neighbour.lyric if prev_neighbour is not None else None, note.lyric,
                          next_neighbour.lyric if next_neighbour is not None else None])


def variate_lyrics(prev_neighbour, note, next_neighbour):
    """Variate(string?, string, string?) -> the merged current character (for diffsinger)."""
    return merge(_variate_core([prev_neighbour, note, next_neighbour]), 3)


def change_lyric(group, lyric):
    old = group[0]
    group[0] = dataclasses.replace(old, lyric=lyric)
    return group


def modify_lyrics(lyric_separated, lyric, first_consonants, vowels, last_consonants, semivowel_separator):
    # the c# version appends to its by-value string parameter, so it has no effect on the caller
    lyric += first_consonants[lyric_separated[3]][0]
    if vowels[lyric_separated[4]][1] != "":
        lyric += semivowel_separator + vowels[lyric_separated[4]][1] + vowels[lyric_separated[4]][2]
    else:
        lyric += " " + vowels[lyric_separated[4]][2]
    lyric += last_consonants[lyric_separated[5]][0]


def romanize_notes(groups, _modify_lyrics=False, first_consonants=None, vowels=None, last_consonants=None, semivowel_separator=" "):
    """RomanizeNotes: replaces each group's first note lyric with its phoneme-variated hangeul."""
    modify = not (not _modify_lyrics or first_consonants is None or vowels is None or last_consonants is None)
    prev_note = None
    result_lyrics = []
    for note_idx in range(len(groups)):
        current_note = groups[note_idx]
        original_lyric = current_note[0].lyric

        if len(groups) > note_idx + 1 and is_hangeul(groups[note_idx + 1][0].lyric):
            next_note = groups[note_idx + 1]
        else:
            next_note = None

        if prev_note is not None:
            prev_note_ = prev_note[0]
            if prev_note[0].position + sum(n.duration for n in prev_note) != current_note[0].position:
                prev_note_ = None
        else:
            prev_note_ = None

        if next_note is not None:
            next_note_ = next_note[0]
            if next_note[0].position != current_note[0].position + sum(n.duration for n in current_note):
                next_note_ = None
        else:
            next_note_ = None

        lyric = original_lyric
        if not is_hangeul(current_note[0].lyric):
            result_lyrics.append(current_note[0].lyric)
            prev_note = current_note
            continue

        lyric_separated = variate(prev_note_, current_note[0], next_note_)
        if modify:
            modify_lyrics(lyric_separated, lyric, first_consonants, vowels, last_consonants, semivowel_separator)
        else:
            lyric = merge(lyric_separated, 3)
        result_lyrics.append(lyric.strip())
        prev_note = current_note

    if not groups:
        raise ValueError("Sequence contains no elements")  # Enumerable.Last() on an empty zip
    for group, lyric in zip(groups, result_lyrics):
        change_lyric(group, lyric)
