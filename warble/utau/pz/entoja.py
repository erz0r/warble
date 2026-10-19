"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Plugin.Builtin/ENtoJAPhonemizer.cs

english to japanese (tubs, cadlaxa; "EN2JA+ merged"): arpabet+ g2p, the en2ja.yaml replacements turn arpabet into
romaji-ish symbols, and every syllable is spelled with the bank's own kana: the yaml's `wanakana` table (romaji ->
kana candidates, the first one the bank has wins) drives ToHiragana, with vcv ("a か"), cvvc ("a k") and plain cv
lookups, consonant clusters split into kana morae, and alt/extra cv tables for sounds japanese doesn't have.

also here: to_romaji, a port of WanaKanaNet's WanaKana.ToRomaji (default options, hepburn), which the c# uses to
find the last sound of an alias; estoja.py reuses it."""

import os
import unicodedata

from ...g2p import ArpabetPlusG2p
from .api import phonemizer
from .syllable_based import (SyllableBasedPhonemizer, _null, _obj_to_string, _yaml_bool, _yaml_str, last, skip, take,
                             yaml_data_from_raw)

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "to_ja")


# ---------------------------------------------------------------------------------------------------------
# WanaKanaNet: WanaKana.ToRomaji(input) with default options (hepburn, no uppercase katakana, ImeMode.None)
# ---------------------------------------------------------------------------------------------------------

class _TrieNode:
    __slots__ = ("value", "children")

    def __init__(self, value=None):
        self.value = value
        self.children = {}


class _Trie:
    def __init__(self, root=None):
        self.root = root if root is not None else _TrieNode()

    def _node(self, key, create):
        node = self.root
        for ch in key:
            nxt = node.children.get(ch)
            if nxt is None:
                if not create:
                    return None
                nxt = node.children[ch] = _TrieNode()
            node = nxt
        return node

    def __getitem__(self, key):
        node = self._node(key, False)
        return node.value if node is not None else None

    def __setitem__(self, key, value):
        self._node(key, True).value = value

    def entries(self):
        def in_depth(prefix, node):
            if node.value is not None:
                yield prefix, node.value
            for ch, child in node.children.items():
                yield from in_depth(prefix + ch, child)
        return list(in_depth("", self.root))

    def insert_subtrie(self, prefix, trie):
        node = self._node(prefix, True)
        for ch, child in trie.root.children.items():
            node.children[ch] = child


_BASIC_ROMAJI = {
    "あ": "a", "い": "i", "う": "u", "え": "e", "お": "o", "か": "ka", "き": "ki", "く": "ku", "け": "ke", "こ": "ko",
    "さ": "sa", "し": "shi", "す": "su", "せ": "se", "そ": "so", "た": "ta", "ち": "chi", "つ": "tsu", "て": "te", "と": "to",
    "な": "na", "に": "ni", "ぬ": "nu", "ね": "ne", "の": "no", "は": "ha", "ひ": "hi", "ふ": "fu", "へ": "he", "ほ": "ho",
    "ま": "ma", "み": "mi", "む": "mu", "め": "me", "も": "mo", "ら": "ra", "り": "ri", "る": "ru", "れ": "re", "ろ": "ro",
    "や": "ya", "ゆ": "yu", "よ": "yo", "わ": "wa", "ゐ": "wi", "ゑ": "we", "を": "wo", "ん": "n", "が": "ga", "ぎ": "gi",
    "ぐ": "gu", "げ": "ge", "ご": "go", "ざ": "za", "じ": "ji", "ず": "zu", "ぜ": "ze", "ぞ": "zo", "だ": "da", "ぢ": "ji",
    "づ": "zu", "で": "de", "ど": "do", "ば": "ba", "び": "bi", "ぶ": "bu", "べ": "be", "ぼ": "bo", "ぱ": "pa", "ぴ": "pi",
    "ぷ": "pu", "ぺ": "pe", "ぽ": "po", "ゔぁ": "va", "ゔぃ": "vi", "ゔ": "vu", "ゔぇ": "ve", "ゔぉ": "vo",
}
_SPECIAL_SYMBOLS = {"。": ".", "、": ",", "：": ":", "・": "/", "！": "!", "？": "?", "〜": "~", "ー": "-", "「": "‘", "」": "’",
                    "『": "“", "』": "”", "［": "[", "］": "]", "（": "(", "）": ")", "｛": "{", "｝": "}", "　": " "}
_AMBIGUOUS_VOWELS = "あいうえおやゆよ"
_SMALL_Y = {"ゃ": "ya", "ゅ": "yu", "ょ": "yo"}
_SMALL_AIUEO = {"ぁ": "a", "ぃ": "i", "ぅ": "u", "ぇ": "e", "ぉ": "o"}
_YOON_KANA = "きにひみりぎびぴゔくふ"
_YOON_EXCEPTIONS = {"し": "sh", "ち": "ch", "じ": "j", "ぢ": "j"}
_SOKUON_WHITELIST = {"b": "b", "c": "t", "d": "d", "f": "f", "g": "g", "h": "h", "j": "j", "k": "k", "m": "m", "p": "p",
                     "q": "q", "r": "r", "s": "s", "t": "t", "v": "v", "w": "w", "x": "x", "z": "z"}
_LONG_VOWELS = {"a": "あ", "i": "い", "u": "う", "e": "え", "o": "う"}

_HEPBURN = None


def _kana_to_hepburn_tree():
    global _HEPBURN
    if _HEPBURN is not None:
        return _HEPBURN
    trie = _Trie()
    for k, v in _BASIC_ROMAJI.items():
        trie[k] = v
    for k, v in _SPECIAL_SYMBOLS.items():
        trie[k] = v
    for k, v in _SMALL_Y.items():
        trie[k] = v
    for k, v in _SMALL_AIUEO.items():
        trie[k] = v
    for c in _YOON_KANA:
        c2 = trie[c][0]
        for k, v in _SMALL_Y.items():
            trie[c + k] = c2 + v
    for key, value in _YOON_EXCEPTIONS.items():
        for k2, v2 in _SMALL_Y.items():
            trie[key + k2] = value + v2[1]
        trie[key + "ぃ"] = value + "yi"
        trie[key + "ぇ"] = value + "e"
    # ResolveTsu
    tsu = _Trie()
    for k, v in trie.entries():
        first = v[0]
        tsu[k] = _SOKUON_WHITELIST[first] + v if first in _SOKUON_WHITELIST else v
    trie.insert_subtrie("っ", tsu)
    for c in _AMBIGUOUS_VOWELS:
        trie[f"ん{c}"] = "n'" + trie[c]
    _HEPBURN = trie
    return trie


def _apply_trie(text, trie, convert_ending=True):
    """TrieHelpers.ApplyTrie -> [(start, end, value or None)]."""
    root = trie.root
    out = []
    pos = 0
    n = len(text)
    while pos < n:
        node = root.children.get(text[pos])
        if node is None:
            node = _TrieNode(text[pos])
        last_cursor = pos
        cur = pos + 1
        while True:
            if cur >= n:
                out.append((last_cursor, cur, node.value if (convert_ending or not node.children) else None))
                pos = cur
                break
            if not node.children:
                out.append((last_cursor, cur, node.value))
                pos = cur
                break
            nxt = node.children.get(text[cur])
            if nxt is None:
                out.append((last_cursor, cur, node.value if node.value is not None else text[last_cursor:cur]))
                pos = cur
                break
            node = nxt
            cur += 1
    return out


def _is_katakana(c):
    return c == "ー" or "゠" <= c <= "ヿ"


def _katakana_to_hiragana(text, is_destination_romaji=False):
    """KanaConverters.KatakanaToHiragana."""
    prev = None
    out = []
    for i, c in enumerate(text):
        if c == "・" or (c == "ー" and i == 0) or c in "ヶヵ":
            out.append(c)
        elif prev is not None and c == "ー" and i > 0:
            c3 = to_romaji(prev)[-1]
            if _is_katakana(text[i - 1]) and c3 == "o" and is_destination_romaji:
                out.append("お")
            else:
                out.append(_LONG_VOWELS[c3])
        elif c != "ー" and _is_katakana(c):
            h = chr(ord(c) - 12449 + 12353)
            prev = h
            out.append(h)
        else:
            prev = None
            out.append(c)
    return "".join(out)


def to_romaji(text):
    """WanaKana.ToRomaji(input) with default options."""
    if text is None:
        raise TypeError("Value cannot be null. (Parameter 'input')")
    if text == "":
        return ""
    tokens = _apply_trie(_katakana_to_hiragana(text, True), _kana_to_hepburn_tree(), True)
    return "".join(v for _, _, v in tokens if v is not None)


def _last_char(s):
    """s.Last<char>().ToString(): throws on an empty string."""
    return last(s)


def _is_cs_digit(c):
    return unicodedata.category(c) == "Nd"


# ---------------------------------------------------------------------------------------------------------
# the phonemizer
# ---------------------------------------------------------------------------------------------------------

def _wk_list(v):
    """WanaKanaData.FromList / ToList on the deserialized `object`."""
    if v is None:
        return []
    if isinstance(v, str):
        return [v]
    if isinstance(v, list):
        out = []
        for x in v:
            s = "" if x is None else _obj_to_string(x)
            if s:
                out.append(s)
        return out
    return [_obj_to_string(v)]


def _wk_obj(v):
    if isinstance(v, list):
        return [None if (not isinstance(x, (list, dict)) and _null(x)) else x for x in v]
    if isinstance(v, dict):
        return v
    return None if _null(v) else v


@phonemizer("English to Japanese Phonemizer", "EN to JA", language="EN", openutau_class="OpenUtau.Plugin.Builtin.ENtoJAPhonemizer", author="TUBS, Cadlaxa")
class ENtoJAPhonemizer(SyllableBasedPhonemizer):
    yaml_file_name = "en2ja.yaml"
    yaml_template = os.path.join(DATA_DIR, "en2ja.template.yaml")
    yaml_version = "1.2.1"
    enable_phoneme_tokenization = True

    special_clusters = "ky gy ts ny hy by py my ry ly".split()

    alt_cv = {
        "si": "suli", "zi": "zuli",
        "ti": "teli", "tu": "tolu",
        "di": "deli", "du": "dolu",
        "hu": "holu",
        "yi": "i", "wu": "u", "rra": "wa",
        "rri": "wi", "rru": "ru", "rre": "we", "rro": "ulo",
    }

    extra_cv = {
        "kye": ["ki", "e"], "gye": ["gi", "e"], "suli": ["se", "i"],
        "she": ["si", "e"], "zuli": ["ze", "i"], "je": ["ji", "e"],
        "teli": ["te", "i"], "tolu": ["to", "u"], "che": ["chi", "e"],
        "tsa": ["tsu", "a"], "tsi": ["tsu", "i"], "tse": ["tsu", "e"],
        "tso": ["tsu", "o"], "deli": ["de", "i"], "dolu": ["do", "u"],
        "nye": ["ni", "e"], "hye": ["hi", "e"], "holu": ["ho", "u"],
        "fa": ["fu", "a"], "fi": ["fu", "i"], "fe": ["fu", "e"],
        "fo": ["fu", "o"], "bye": ["bi", "e"], "pye": ["pi", "e"],
        "mye": ["mi", "e"], "ye": ["i", "e"], "rye": ["ri", "e"],
        "wi": ["u", "i"], "we": ["u", "e"], "ulo": ["u", "o"],
    }

    def __init__(self):
        super().__init__()
        self.vowels = [
            "aa", "ax", "ae", "ah", "ao", "aw", "ay", "eh", "er", "ey", "ih", "iy", "ow", "oy", "uh", "uw",
            "a", "e", "i", "o", "u",
        ]
        self.consonants = "b,ch,d,dh,dr,dx,f,g,hh,jh,k,l,m,n,ng,p,q,r,s,sh,t,th,tr,v,w,y,z".split(",")
        self.transitional_cluster_settings = {}
        self.wanakana_dictionary = {}

    def get_vowels(self):
        return self.vowels

    def get_consonants(self):
        return self.consonants

    def get_dictionary_name(self):
        return ""

    def get_base_g2ps(self):
        return [ArpabetPlusG2p()]

    def set_singer(self, singer):
        super().set_singer(singer)
        if self.singer is None:
            return
        global_file = self.plugin_yaml_path()
        singer_file = self._singer_yaml_path()
        files_to_parse = []
        if global_file is not None and os.path.isfile(global_file):
            files_to_parse.append(global_file)
        if singer_file and os.path.isfile(singer_file) and global_file != singer_file:
            files_to_parse.append(singer_file)

        self.wanakana_dictionary.clear()
        for file in files_to_parse:
            try:
                raw = self.load_yaml_raw(file)
                yaml_data_from_raw(raw)  # the YAMLData part must deserialize too
                wanakana, clusters = self._child_yaml_data(raw)
                if wanakana is not None:
                    # reverse the array so when we Insert(0), the top of the YAML stays at the top of the final list
                    for roma, kana in reversed(wanakana):
                        key = "".join(_wk_list(roma))
                        value = " ".join(_wk_list(kana))
                        if not key or not value:
                            continue
                        if key not in self.wanakana_dictionary:
                            self.wanakana_dictionary[key] = []
                        # prepends the kana value to the very top of the priority list
                        if value not in self.wanakana_dictionary[key]:
                            self.wanakana_dictionary[key].insert(0, value)
                        # keeps the romaji (key) as a fallback at the very end of the candidates
                        if key not in self.wanakana_dictionary[key]:
                            self.wanakana_dictionary[key].append(key)
                self.transitional_cluster_settings.clear()
                if clusters is not None:
                    for symbol, value in clusters:
                        if symbol:
                            self.transitional_cluster_settings[symbol] = value
            except Exception:  # noqa: BLE001 - Log.Error($"Failed to parse yaml data from {file}: ...")
                pass

    @staticmethod
    def _child_yaml_data(raw):
        """ChildYAMLData's own properties: wanakana [(roma, kana)] and transitionalclusters [(symbol, value)]."""
        if raw is None or (isinstance(raw, str) and _null(raw)):
            return None, None
        if not isinstance(raw, dict):
            raise ValueError("expected a mapping")
        wanakana = []
        clusters = []

        def seq(v):
            if isinstance(v, list):
                return v
            if not isinstance(v, dict) and _null(v):
                return None
            raise ValueError("expected a sequence")

        if "wanakana" in raw:
            items = seq(raw["wanakana"])
            if items is None:
                wanakana = None
            else:
                for item in items:
                    if item is None or (not isinstance(item, (dict, list)) and _null(item)):
                        raise TypeError("Object reference not set to an instance of an object.")
                    if not isinstance(item, dict):
                        raise ValueError("expected a mapping")
                    wanakana.append((_wk_obj(item.get("roma")), _wk_obj(item.get("kana"))))
        if "transitionalclusters" in raw:
            items = seq(raw["transitionalclusters"])
            if items is None:
                clusters = None
            else:
                for item in items:
                    if item is None or (not isinstance(item, (dict, list)) and _null(item)):
                        clusters.append(None)
                        continue
                    if not isinstance(item, dict):
                        raise ValueError("expected a mapping")
                    symbol = _yaml_str(item.get("symbol"))
                    value = True
                    if "value" in item:
                        b = _yaml_bool(item["value"])
                        if b is None:
                            raise ValueError("null into bool")
                        value = b
                    clusters.append((symbol, value))
                if any(c is None for c in clusters):
                    raise TypeError("Object reference not set to an instance of an object.")
        return wanakana, clusters

    def get_symbols(self, note):
        original = super().get_symbols(note)
        if original is None:
            return None
        final_processed_phonemes = []
        # apply dr/tr splits dynamically
        for s in original:
            if s == "dr":
                final_processed_phonemes.extend(["jh", s[1]])
            elif s == "tr":
                final_processed_phonemes.extend(["ch", s[1]])
            else:
                final_processed_phonemes.append(s)
        return final_processed_phonemes

    def _is_transitional_c_enabled(self, symbol):
        return self.transitional_cluster_settings.get(symbol, True)

    def _adjust_cc(self, cc):
        adjusted = []
        i = 0
        while i < len(cc):
            if i == len(cc) - 1:
                adjusted.append(cc[i])
            else:
                if cc[i] == cc[i + 1]:
                    adjusted.append(cc[i])
                    i += 2
                    continue
                diphone = f"{cc[i]}{cc[i + 1]}"
                if diphone in self.special_clusters:
                    adjusted.append(diphone)
                    i += 1
                else:
                    adjusted.append(cc[i])
            i += 1
        return adjusted

    def process_syllable(self, syllable):
        has = self.has_oto
        va = self.validate_alias
        tone = syllable.tone
        vtone = syllable.vowel_tone
        prev_v = "" if not syllable.prev_v else self.replace_phoneme(syllable.prev_v, tone)
        v = self.replace_phoneme(syllable.v, vtone)
        cc = [self.replace_phoneme(c, tone) for c in syllable.cc]

        phonemes = []

        if self.can_make_alias_extension(syllable):
            return [None]

        using_vc = False

        if len(prev_v) == 0:
            prev_v = "-"

        cc = self._adjust_cc(cc)

        final_cons = ""
        if len(cc) > 0:
            final_cons = cc[-1]

            start = 0
            has_vc, vc_phonemes, vc_consumed, _ = self._has_vc(prev_v, cc, v, "", tone)
            using_vc = has_vc

            has_start_alias = False
            step = 0

            if prev_v == "-":
                # starting multi-consonants (- CC)
                for i in range(len(cc), 1, -1):
                    spaced = " ".join(take(cc, i))
                    merged = "".join(take(cc, i))
                    if self.try_add_phoneme(phonemes, tone,
                                            f"- {spaced}", va(f"- {spaced}", tone),
                                            f"-{spaced}", va(f"-{spaced}", tone),
                                            f"- {merged}", va(f"- {merged}", tone),
                                            f"-{merged}", va(f"-{merged}", tone)):
                        has_start_alias = True
                        step = i  # consumed i consonants from cluster
                        break

                # starting single consonants (- C)
                if not has_start_alias:
                    if self.try_add_phoneme(phonemes, tone,
                                            f"- {cc[0]}", va(f"- {cc[0]}", tone),
                                            f"-{cc[0]}", va(f"-{cc[0]}", tone)):
                        has_start_alias = True
                        step = 1
                    # if no starting - c exists, use singular c before the hiragana one in clusters
                    elif len(cc) > 1 and self.try_add_phoneme(phonemes, tone, cc[0], va(cc[0], tone)):
                        has_start_alias = True
                        step = 1

            if not has_start_alias:
                phonemes.extend(vc_phonemes)
                start = vc_consumed
            else:
                using_vc = True
                start = step

            if len(phonemes) > 0:
                prev_v = _last_char(to_romaji(phonemes[-1]))

            i = start
            while i < len(cc) - 1:
                selected = None
                loop_step = 0

                extended_space1 = f"{cc[i]} {''.join(skip(cc, i + 1))}"
                extended_space2 = f"{cc[i]} {' '.join(skip(cc, i + 1))}"
                extended_no_space = f"{cc[i]}{''.join(skip(cc, i + 1))}"

                # check multi-consonant transitions first ([C1 C2] or [C1 C2C3])
                if has(extended_space1, tone):
                    selected = extended_space1
                    loop_step = len(cc) - 2 - i
                elif has(extended_space2, tone):
                    selected = extended_space2
                    loop_step = len(cc) - 2 - i
                elif has(extended_no_space, tone):
                    selected = extended_no_space
                    loop_step = len(cc) - 2 - i
                elif has(f"{cc[i]} {cc[i + 1]}", tone):
                    selected = f"{cc[i]} {cc[i + 1]}"
                elif has(va(f"{cc[i]} {cc[i + 1]}", tone), tone):
                    selected = va(f"{cc[i]} {cc[i + 1]}", tone)
                elif has(f"{cc[i]}{cc[i + 1]}", tone):
                    selected = f"{cc[i]}{cc[i + 1]}"
                elif has(va(f"{cc[i]}{cc[i + 1]}", tone), tone):
                    selected = va(f"{cc[i]}{cc[i + 1]}", tone)

                if selected is not None:
                    self.try_add_phoneme(phonemes, tone, selected)
                    prev_v = _last_char(to_romaji(selected))
                    i += loop_step
                    i += 1
                    continue

                # singular C handling
                is_stop = self.stop is not None and cc[i] in self.stop
                has_roman_c = has(cc[i], tone) or has(va(cc[i], tone), tone)
                is_transition_enabled = True
                if len(cc) == 2:
                    is_transition_enabled = self._is_transitional_c_enabled(cc[i])
                # skip the stop ONLY if a VC already absorbed it (usingVC && i == start) in a <= 2 CC cluster
                if is_stop and using_vc and i == start and len(cc) <= 2 and not has_roman_c:
                    i += 1
                    continue

                # if not absorbed by VC, or in clusters > 2, preserve the stop or fall back to mora/VCV
                if is_stop:
                    if has_roman_c:
                        selected = cc[i] if has(cc[i], tone) else va(cc[i], tone)
                    else:
                        hiragana_stop = self._to_hiragana(cc[i], tone)
                        hiragana_stop_vcv = self._try_vcv(prev_v, hiragana_stop, tone)
                        if has(hiragana_stop_vcv, tone):
                            selected = hiragana_stop_vcv
                            using_vc = True
                        elif has(hiragana_stop, tone):
                            selected = hiragana_stop
                        elif has(va(hiragana_stop, tone), tone):
                            selected = va(hiragana_stop, tone)

                    if selected is not None and is_transition_enabled:
                        self.try_add_phoneme(phonemes, tone, selected)
                        prev_v = _last_char(to_romaji(selected))
                    i += 1
                    continue

                # direct roman single consonant check [r], [s], [m], [n], [l], [f], [v]
                if using_vc and i == start:
                    is_affricate = self.affricate is not None and cc[i] in self.affricate
                    if has(cc[i], tone):
                        selected = cc[i]
                    elif has(va(cc[i], tone), tone):
                        selected = va(cc[i], tone)
                    # if it's an affricate, also check and allow japanese kana entries (e.g. [ち], [つ])
                    elif is_affricate:
                        hiragana_aff = self._to_hiragana(cc[i], tone)
                        hiragana_vcv = self._try_vcv(prev_v, hiragana_aff, tone)
                        if has(hiragana_vcv, tone):
                            selected = hiragana_vcv
                        elif has(hiragana_aff, tone):
                            selected = hiragana_aff
                        elif has(va(hiragana_aff, tone), tone):
                            selected = va(hiragana_aff, tone)

                    if selected is not None and is_transition_enabled:
                        self.try_add_phoneme(phonemes, tone, selected)
                        prev_v = _last_char(to_romaji(selected))
                    # for non-affricates without an explicit roman entry, let the VC connect directly to the next CV
                    i += 1
                    continue
                # only fall back to kana / CV representations if roman standalone C doesn't exist in oto
                elif is_transition_enabled:
                    hiragana_cc = self._to_hiragana(cc[i], tone)
                    hiragana_vcv = self._try_vcv(prev_v, hiragana_cc, tone)
                    if has(hiragana_vcv, tone):
                        self.try_add_phoneme(phonemes, tone, hiragana_vcv)
                        prev_v = _last_char(to_romaji(hiragana_vcv))
                        using_vc = True
                    elif has(hiragana_cc, tone):
                        self.try_add_phoneme(phonemes, tone, hiragana_cc)
                        prev_v = _last_char(to_romaji(hiragana_cc))
                i += 1

        cv = f"{final_cons}{v}"
        crv = f"{final_cons} {v}"
        hiragana_cv = self._to_hiragana(cv, vtone)

        # switch (usingVC): both arms are the same lookups
        try_vcv = self._try_vcv(prev_v, hiragana_cv, vtone)
        if has(try_vcv, vtone) or has(va(try_vcv, vtone), vtone):
            hiragana_cv = try_vcv
        elif has(self._fix_cv(hiragana_cv, vtone), vtone) or has(va(self._fix_cv(hiragana_cv, vtone), vtone), vtone):
            hiragana_cv = self._fix_cv(hiragana_cv, vtone)
        elif (has(crv, vtone) or has(va(crv, vtone), vtone)) or (has(cv, vtone) or has(va(cv, vtone), vtone)):
            hiragana_cv = self._fix_cv(self._alias_format(f"{final_cons} {v}", "dynMid", vtone, ""), vtone)
        else:
            hiragana_cv = self._fix_cv(hiragana_cv, vtone)
        if using_vc:
            using_vc = True

        split = False
        is_start = not syllable.prev_v or prev_v == "-"
        final_alias = None

        def first_of(*candidates):
            for c in candidates:
                if has(c, vtone):
                    return c
                vc = va(c, vtone)
                if has(vc, vtone):
                    return vc
            return None

        if is_start and len(cc) <= 1:
            dash_cv = f"- {hiragana_cv}"
            dash_cv_no_space = f"-{hiragana_cv}"
            dash_romaji = f"- {cv}"
            dash_romaji_no_space = f"-{cv}"
            # priority 1: kana with dash; 2: base kana; 3: romaji with dash; 4: base romaji; 5: complex romaji (crv)
            final_alias = first_of(dash_cv, dash_cv_no_space, hiragana_cv, dash_romaji, dash_romaji_no_space, cv, crv)
        else:
            # non-start behavior (mid-phrase syllables)
            final_alias = first_of(hiragana_cv, f"- {hiragana_cv}", f"-{hiragana_cv}", cv)

        if final_alias is not None:
            # double onset cleanup: if finalAlias already contains the onset dash ("- わ"), remove redundant "- w"
            if is_start and len(cc) == 1 and (final_alias.startswith("- ") or final_alias.startswith("-")):
                c = cc[0]
                kana_c = self._to_hiragana(c, tone)
                drop = {f"- {c}", f"-{c}", f"- {kana_c}", f"-{kana_c}",
                        va(f"- {c}", tone), va(f"-{c}", tone), va(f"- {kana_c}", tone), va(f"-{kana_c}", tone)}
                phonemes[:] = [p for p in phonemes if p not in drop]
            phonemes.append(final_alias)
        else:
            split = True

        if split:
            handled_by_alt = False
            substitute_cv = self.alt_cv.get(cv)
            # try AltCv substitution first
            if substitute_cv is not None:
                alt_kana = self._to_hiragana(substitute_cv, vtone)
                alt_vcv = self._try_vcv(prev_v, alt_kana, vtone)
                if has(alt_vcv, vtone) or has(va(alt_vcv, vtone), vtone):
                    phonemes.append(alt_vcv if has(alt_vcv, vtone) else va(alt_vcv, vtone))
                    handled_by_alt = True
                elif has(alt_kana, vtone) or has(va(alt_kana, vtone), vtone):
                    phonemes.append(self._fix_cv(alt_kana, vtone))
                    handled_by_alt = True
                elif has(substitute_cv, vtone) or has(va(substitute_cv, vtone), vtone):
                    phonemes.append(self._fix_cv(substitute_cv, vtone))
                    handled_by_alt = True

            # fall back to multi-step ExtraCv decomposition if AltCv wasn't matched
            split_cv = None
            if not handled_by_alt:
                if cv in self.extra_cv:
                    split_cv = self.extra_cv[cv]
                elif substitute_cv is not None and substitute_cv in self.extra_cv:
                    split_cv = self.extra_cv[substitute_cv]

            if split_cv is not None:
                for part in split_cv:
                    if part != prev_v:
                        converted = self._to_hiragana(part, vtone)
                        if prev_v == "-" or not prev_v:
                            candidate = self._fix_cv(converted, vtone)
                        else:
                            candidate = self._try_vcv(prev_v, converted, vtone)
                        if has(candidate, vtone) or has(va(candidate, vtone), vtone):
                            phonemes.append(candidate if has(candidate, vtone) else va(candidate, vtone))
                        else:
                            phonemes.append(converted)
                        prev_v = _last_char(part)
        return phonemes

    def process_ending(self, ending):
        has = self.has_oto
        va = self.validate_alias
        tone = ending.tone
        prev_v = self.replace_phoneme(ending.prev_v, tone)
        cc = [self.replace_phoneme(c, tone) for c in ending.cc]
        phonemes = []
        v = self.replace_phoneme(ending.prev_v, tone)
        t = self.replace_phoneme(ending.tail, tone) if ending.has_tail else "-"

        cc = self._adjust_cc(cc)

        using_vc = False
        added_ending = False

        if len(cc) > 0:
            has_vc, vc_phonemes, vc_consumed, is_tail = self._has_vc(prev_v, cc, "", t, tone)
            using_vc = has_vc
            phonemes.extend(vc_phonemes)
            if is_tail:
                added_ending = True

            # (the c# also computes hasVCV / skipFirstFallback here, which nothing reads)
            start = vc_consumed

            if len(phonemes) > 0:
                prev_v = _last_char(to_romaji(phonemes[-1]))

            i = start
            while i < len(cc):
                selected = None
                loop_step = 0

                is_cc_ending_index = i == len(cc) - 2
                is_cc_ending_skipped = i == len(cc) - 1 and start > len(cc) - 2 and len(cc) > 1

                if (is_cc_ending_index or is_cc_ending_skipped) and ending.is_ending_vc_with_more_than_one_consonant:
                    c1 = cc[len(cc) - 2]
                    c2 = cc[len(cc) - 1]
                    for end_alias in (f"{c1} {c2} {t}", f"{c1}{c2} {t}", f"{c1} {c2}{t}", f"{c1}{c2}{t}"):
                        if has(end_alias, tone):
                            selected = end_alias
                            loop_step = 1 if is_cc_ending_index else 0
                            added_ending = True
                            break
                        elif has(va(end_alias), tone):
                            selected = va(end_alias)
                            loop_step = 1 if is_cc_ending_index else 0
                            added_ending = True
                            break

                if selected is None and cc[i] in ("n", "w", "y"):
                    hiragana_n = self._to_hiragana(cc[i], tone)
                    hiragana_n_vcv = self._try_vcv(prev_v, hiragana_n, tone)
                    has_vcv = hiragana_n_vcv != hiragana_n and (has(hiragana_n_vcv, tone) or has(va(hiragana_n_vcv, tone), tone))
                    has_kana = has(hiragana_n, tone) or has(va(hiragana_n, tone), tone)

                    if i == len(cc) - 1 or has_vcv:
                        if has_vcv or has_kana:
                            if has_vcv:
                                selected = hiragana_n_vcv if has(hiragana_n_vcv, tone) else va(hiragana_n_vcv, tone)
                            else:
                                selected = hiragana_n if has(hiragana_n, tone) else va(hiragana_n, tone)
                            using_vc = True
                            loop_step = 0

                            # at final position, check if a coda tail (e.g. [n R], [n -]) can follow this mora
                            if i == len(cc) - 1:
                                self.try_add_phoneme(phonemes, tone, selected)
                                prev_v = _last_char(to_romaji(selected))
                                selected = None
                                for tail_alias in (f"{cc[i]} {t}", f"{cc[i]} R", f"{cc[i]}{t}", f"{cc[i]} -", f"{cc[i]}-"):
                                    if has(tail_alias, tone):
                                        selected = tail_alias
                                        added_ending = True
                                        break
                                if selected is not None:
                                    self.try_add_phoneme(phonemes, tone, selected)
                                i += 1
                                continue

                if selected is None and i == len(cc) - 1 and (ending.is_ending_vc_with_one_consonant or ending.is_ending_vc_with_more_than_one_consonant):
                    vc_ = va(cc[i])
                    for end_alias in (f"{cc[i]} {t}", f"{cc[i]} R", f"{cc[i]}{t}", f"{cc[i]} -", f"{cc[i]}-", cc[i],
                                      f"{vc_} {t}", f"{vc_} R", f"{vc_}{t}", f"{vc_} -", f"{vc_}-", vc_):
                        if has(end_alias, tone):
                            selected = end_alias
                            loop_step = 0
                            added_ending = True
                            break

                if selected is None and i < len(cc) - 1:
                    extended_space1 = f"{cc[i]} {''.join(skip(cc, i + 1))}"
                    extended_space2 = f"{cc[i]} {' '.join(skip(cc, i + 1))}"
                    extended_no_space = f"{cc[i]}{''.join(skip(cc, i + 1))}"
                    if has(extended_space1, tone):
                        selected = extended_space1
                        loop_step = len(cc) - 1 - i
                    elif has(extended_space2, tone):
                        selected = extended_space2
                        loop_step = len(cc) - 1 - i
                    elif has(extended_no_space, tone):
                        selected = extended_no_space
                        loop_step = len(cc) - 1 - i
                    elif has(f"{cc[i]} {cc[i + 1]}", tone):
                        selected = f"{cc[i]} {cc[i + 1]}"
                        loop_step = 0
                    elif has(va(f"{cc[i]} {cc[i + 1]}"), tone):
                        selected = va(f"{cc[i]} {cc[i + 1]}")
                        loop_step = 0
                    elif has(f"{cc[i]}{cc[i + 1]}", tone):
                        selected = f"{cc[i]}{cc[i + 1]}"
                        loop_step = 0
                    elif has(va(f"{cc[i]}{cc[i + 1]}"), tone):
                        selected = va(f"{cc[i]}{cc[i + 1]}")
                        loop_step = 0

                skip_singular = using_vc and i == start

                if selected is None and not skip_singular:
                    if has(cc[i], tone):
                        selected = cc[i]
                        loop_step = 0
                    elif has(va(cc[i]), tone):
                        selected = va(cc[i])
                        loop_step = 0

                if selected is not None:
                    self.try_add_phoneme(phonemes, tone, selected)
                    prev_v = _last_char(to_romaji(selected))
                    i += loop_step
                else:
                    if skip_singular:
                        i += 1
                        continue
                    hiragana = self._to_hiragana(cc[i], tone)
                    hiragana_vcv = self._try_vcv(prev_v, hiragana, tone)
                    block_vcv = using_vc and i == start
                    if not block_vcv and has(hiragana_vcv, tone):
                        self.try_add_phoneme(phonemes, tone, hiragana_vcv)
                        prev_v = _last_char(to_romaji(hiragana_vcv))
                        using_vc = True
                    elif has(hiragana, tone):
                        self.try_add_phoneme(phonemes, tone, hiragana)
                        prev_v = _last_char(to_romaji(hiragana))
                    else:
                        self.try_add_phoneme(phonemes, tone, va(hiragana), cc[i], va(cc[i]))
                        prev_v = _last_char(to_romaji(hiragana))
                i += 1

        if ending.is_ending_v:
            # if there is no previous vowel (e.g. "-" on a pure tail note), do not generate a vowel tail
            if not prev_v or prev_v == "-":
                return phonemes
            self.try_add_phoneme(phonemes, tone, f"{prev_v} {t}", f"{prev_v} R", f"{prev_v}{t}",
                                 f"{va(prev_v)} {t}", f"{va(prev_v)} R", f"{va(prev_v)}{t}")
        elif not added_ending and (ending.is_ending_vc_with_one_consonant or ending.is_ending_vc_with_more_than_one_consonant):
            if len(cc) > 0:
                last_cc = cc[-1]
                self.try_add_phoneme(phonemes, tone, f"{last_cc} {t}", f"{last_cc} R", f"{last_cc}{t}",
                                     f"{va(last_cc)} {t}", f"{va(last_cc)} R", f"{va(last_cc)}{t}")
        return phonemes

    _ALIAS_FORMATS = {
        "dynStart": [""], "dynMid": [""],
        "dynMid_vv": [""], "dynEnd": [""],
        "startingV": ["-", "- ", "_", ""], "vcEx": None,
        "vvExtend": ["", "_", "-", "- "], "cv": ["-", "", "- ", "_"],
        "cvStart": ["-", "- ", "_"], "consEn": ["_", "- ", "_"],
        "ending": [" R", "-", " -"], "ending_mix": ["-", " -", "R", " R", "_", "--"],
        "cc": ["", "-", "- ", "_"], "cc_start": ["- ", "-"],
        "cc_end": [" -", "-", ""], "cc_mix": [" -", " R", "-", "", "_", "- ", "-"],
        "cc1_mix": ["", " -", "-", " R", "_", "- ", "-"], "cc_teto": ["_", ""],
        "cc_teto_end": ["_", ""],
    }

    def _alias_format(self, alias, type_, tone, prev_v):
        has = self.has_oto
        va = self.validate_alias
        alias_formats = dict(self._ALIAS_FORMATS)
        alias_formats["vcEx"] = [f"{prev_v} ", f"{prev_v}"]

        if type_ not in alias_formats and "dynamic" not in type_:
            return alias

        def split_cv(a, swap=False):
            if " " in a:
                parts = a.split(" ")
                return (parts[1], parts[0]) if swap else (parts[0], parts[1])
            return a, ""

        if "dynStart" in type_:
            consonant, vowel = split_cv(alias)
            for variation in (f"- {consonant}{vowel}", f"- {consonant} {vowel}", f"-{consonant} {vowel}",
                              f"-{consonant}{vowel}", f"-{consonant}_{vowel}", f"- {consonant}_{vowel}"):
                if has(variation, tone) or has(va(variation), tone):
                    return variation

        if "dynMid" in type_:
            consonant, vowel = split_cv(alias)
            for variation in (f"{consonant}{vowel}", f"{consonant} {vowel}", f"{consonant}_{vowel}"):
                if has(variation, tone) or has(va(variation), tone):
                    return variation

        if "dynMid_vv" in type_:
            consonant, vowel = split_cv(alias)
            for variation in (f"{consonant} {vowel}", f"{consonant}{vowel}", f"{consonant}_{vowel}"):
                if has(variation, tone) or has(va(variation), tone):
                    return variation

        if "dynEnd" in type_:
            consonant, vowel = split_cv(alias, swap=True)
            for variation in (f"{vowel}{consonant} -", f"{vowel} {consonant}-", f"{vowel}{consonant}-", f"{vowel} {consonant} -"):
                if has(variation, tone) or has(va(variation), tone):
                    return variation

        formats_to_try = alias_formats[type_]  # KeyNotFound for an unlisted "dynamic..." type, like c#
        counter = 0
        for fmt in formats_to_try:
            if "mix" in type_ and counter < 4:
                alias_format = f"{alias}{fmt}" if counter % 2 == 0 else f"{fmt}{alias}"
                counter += 1
            elif "end" in type_ and "dynEnd" not in type_:
                alias_format = f"{alias}{fmt}"
            else:
                alias_format = f"{fmt}{alias}"
            if has(alias_format, tone) or has(va(alias_format), tone):
                return alias_format
        return alias

    def validate_alias(self, alias, tone=0):
        if self.has_oto(alias, tone):
            return alias

        base_resolved = super().validate_alias(alias, tone)
        if base_resolved and base_resolved != alias:
            if self.has_oto(base_resolved, tone):
                return base_resolved
            alias = base_resolved

        if alias in ("a dx", "e dx", "i dx", "o dx", "u dx"):
            return alias.replace("dx", "r")

        consonants = self.get_consonants()
        for c2 in consonants:
            alias = alias.replace("ng" + " " + c2, "n" + " " + c2)
        for c2 in consonants:
            if not (f"aw {c2}" in alias or f"ew {c2}" in alias or f"ow {c2}" in alias or f"uw {c2}" in alias):
                alias = alias.replace(f"r {c2}", f"er {c2}")
        for c2 in consonants:
            if not (f"aw {c2}" in alias or f"ew {c2}" in alias or f"ow {c2}" in alias or f"uw {c2}" in alias):
                alias = alias.replace(f"{c2} r", f"{c2} er")
        for c2 in consonants:
            if not (f"aw {c2}" in alias or f"ew {c2}" in alias or f"iw {c2}" in alias or f"ow {c2}" in alias or f"uw {c2}" in alias):
                alias = alias.replace(f"w {c2}", f"uw {c2}")
        for c2 in consonants:
            if not (f"aw {c2}" in alias or f"ew {c2}" in alias or f"iw {c2}" in alias or f"ow {c2}" in alias or f"uw {c2}" in alias):
                alias = alias.replace(f"{c2} w", f"{c2} uw")
        if alias == "w -":
            return alias.replace("w", "uw")

        for c2 in consonants:
            if not (f"ay {c2}" in alias or f"ey {c2}" in alias or f"iy {c2}" in alias or f"oy {c2}" in alias):
                alias = alias.replace(f"y {c2}", f"i {c2}")
        # (the c# then replaces "{c2} y" with itself for every consonant, a no-op)
        if alias == "y -":
            return alias.replace("y", "iy")

        for c2 in consonants:
            if not (f"ay {c2}" in alias or f"ey {c2}" in alias or f"iy {c2}" in alias or f"oy {c2}" in alias):
                alias = alias.replace(f"{c2} R", f"{c2} -")
        for c2 in self.get_vowels():
            alias = alias.replace(f"{c2} -", f"{c2} R")
        return alias

    def _single_rules(self):
        return [r for r in self.yaml_fallbacks if len(r.from_list) == 1]

    @staticmethod
    def _jp_vowel(safe_vowel):
        romaji = to_romaji(safe_vowel)
        last_vowel = None
        for c in romaji:
            if c in "aeiouAEIOU":
                last_vowel = c
        return last_vowel.lower() if last_vowel is not None else safe_vowel

    def _has_vc(self, vowel, cc, next_v, t, tone):
        has = self.has_oto
        va = self.validate_alias
        if not vowel or vowel == "-":
            return False, [], 0, False

        safe_vowel = vowel.replace("_", "").replace("-", "").strip()
        jp_vowel = self._jp_vowel(safe_vowel)

        single_rules = self._single_rules()
        for rule in single_rules:
            if rule.from_list[0] == jp_vowel and len(rule.to_list) > 0:
                jp_vowel = rule.to_list[0]
                break
            if rule.from_list[0] == safe_vowel and len(rule.to_list) > 0:
                jp_vowel = rule.to_list[0]
                break

        def hash_list(*items):
            out = []
            for x in items:
                if x not in out:
                    out.append(x)
            return [x for x in out if x]

        vowels_to_try = hash_list(vowel, jp_vowel, va(vowel), va(jp_vowel))

        c1 = cc[0] if len(cc) > 0 else ""
        c1_val = va(c1)
        c1_mapped = c1
        for rule in single_rules:
            if rule.from_list[0] == c1 and len(rule.to_list) > 0:
                c1_mapped = rule.to_list[0]
                break
        c1_candidates = hash_list(c1, c1_mapped, c1_val, va(c1_mapped))

        def found(fmt):
            if has(fmt, tone):
                return fmt
            v_ = va(fmt, tone)
            if has(v_, tone):
                return v_
            return None

        # VCC formats (v cc, vc c, vcc)
        if len(cc) > 1:
            c2 = cc[1]
            c2_val = va(c2)
            c2_mapped = c2
            for rule in single_rules:
                if rule.from_list[0] == c2 and len(rule.to_list) > 0:
                    c2_mapped = rule.to_list[0]
                    break
            c2_candidates = hash_list(c2, c2_mapped, c2_val, va(c2_mapped))

            # tail endings FIRST (returns 2 consumed, isTail = true)
            if t:
                for v in vowels_to_try:
                    for ca in c1_candidates:
                        for cb in c2_candidates:
                            for fmt in (f"{v} {ca}{cb} {t}", f"{v} {ca} {cb} {t}", f"{v}{ca} {cb} {t}", f"{v}{ca}{cb} {t}",
                                        f"{v} {ca}{cb}{t}", f"{v} {ca} {cb}{t}", f"{v}{ca} {cb}{t}", f"{v}{ca}{cb}{t}"):
                                r = found(fmt)
                                if r is not None:
                                    return True, [r], 2, True

            # standard VCC formats (returns 1 consumed, isTail = false)
            for v in vowels_to_try:
                for ca in c1_candidates:
                    for cb in c2_candidates:
                        for fmt in (f"{v} {ca}{cb}", f"{v} {ca} {cb}", f"{v}{ca} {cb}", f"{v}{ca}{cb}"):
                            r = found(fmt)
                            if r is not None:
                                return True, [r], 1, False

        # standard VC formats (v c, vc)
        if len(cc) > 0:
            if c1 == "n":
                c1_candidates.append("ん")
                c1_candidates.append("N")
                c1_candidates.append("n")

            for v in vowels_to_try:
                for ca in c1_candidates:
                    for fmt in (f"{v} {ca}", f"{v}{ca}"):
                        r = found(fmt)
                        if r is not None:
                            consumed_mora = ca == "ん" or ca == "N"
                            return True, [r], 1 if consumed_mora else 0, False

            # tail endings (returns 1 consumed, isTail = true)
            if t:
                for v in vowels_to_try:
                    for ca in c1_candidates:
                        for fmt in (f"{v} {ca} {t}", f"{v}{ca} {t}", f"{v} {ca}{t}", f"{v}{ca}{t}"):
                            r = found(fmt)
                            if r is not None:
                                return True, [r], 1, True
        return False, [], 0, False

    def _try_vcv(self, vowel, cv, tone):
        safe_vowel = vowel.replace("_", "").replace("-", "").strip()
        jp_vowel = self._jp_vowel(safe_vowel)
        if vowel == "-":
            jp_vowel = "-"

        single_rules = self._single_rules()
        for rule in single_rules:
            if rule.from_list[0] == jp_vowel and len(rule.to_list) > 0:
                jp_vowel = rule.to_list[0]
                break
        for rule in single_rules:
            if rule.from_list[0] == safe_vowel and len(rule.to_list) > 0:
                jp_vowel = rule.to_list[0]
                break

        vcv = f"{jp_vowel} {cv}"
        vcv_no_space = f"{jp_vowel}{cv}"
        if self.has_oto(vcv, tone):
            return vcv
        if self.has_oto(vcv_no_space, tone):
            return vcv_no_space
        validated_vcv = self.validate_alias(vcv)
        if self.has_oto(validated_vcv, tone):
            return validated_vcv
        return cv

    def _fix_cv(self, cv, tone):
        has = self.has_oto
        va = self.validate_alias
        alt = f"- {cv}"
        alt_no_space = f"-{cv}"
        if has(cv, tone):
            return cv
        elif has(va(cv), tone):
            return va(cv)
        elif has(alt, tone):
            return alt
        elif has(va(alt), tone):
            return va(alt)
        elif has(alt_no_space, tone):
            return alt_no_space
        elif has(va(alt_no_space), tone):
            return va(alt_no_space)
        return cv

    def _to_hiragana(self, alias, tone):
        has = self.has_oto
        va = self.validate_alias
        wk = self.wanakana_dictionary
        fallback_alias = alias
        single_rules = self._single_rules()

        # romaji fallbacks (do not strip if WanaKanaDictionary already defines an exact match for alias)
        if fallback_alias not in wk:
            for rule in single_rules:
                from_key = rule.from_list[0]
                to_value = rule.to_list[0] if len(rule.to_list) > 0 else from_key
                if fallback_alias == from_key:
                    fallback_alias = to_value
                    break
                elif fallback_alias.endswith(from_key) and from_key != to_value and from_key not in wk:
                    fallback_alias = fallback_alias[:len(fallback_alias) - len(from_key)] + to_value
                    break

        converted = ""
        i = 0
        n = len(fallback_alias)
        while i < n:
            found_match = False
            # priority 1: exact case match so capital letters (N, J, C, S, T, Z) are distinct from lowercase
            keys = [k for k in wk if n >= i + len(k) and fallback_alias[i:i + len(k)] == k]
            # priority 2: case-insensitive fallback only if no exact case key exists
            if len(keys) == 0:
                keys = [k for k in wk if n >= i + len(k) and fallback_alias[i:i + len(k)].upper() == k.upper()]
            keys.sort(key=len, reverse=True)

            for romaji_key in keys:
                for kana in wk[romaji_key]:
                    is_match = has(kana, tone) or has(va(kana, tone), tone)
                    # pure VCV probe
                    if not is_match:
                        for probe in (f"- {kana}", f"-{kana}", f"a {kana}", f"a{kana}", f"e {kana}", f"e{kana}"):
                            if has(probe, tone) or has(va(probe, tone), tone):
                                is_match = True
                                break
                    if is_match:
                        converted += kana
                        i += len(romaji_key)
                        found_match = True
                        break
                if found_match:
                    break

            if not found_match and len(keys) > 0:
                # fall back to the very first item (top of YAML list)
                values = wk[keys[0]]
                converted += values[0] if values else fallback_alias[i]
                i += len(keys[0])
                found_match = True

            if not found_match:
                converted += fallback_alias[i]
                i += 1

        for rule in single_rules:
            from_key = rule.from_list[0]
            to_value = rule.to_list[0] if len(rule.to_list) > 0 else from_key
            if any(ord(c) > 0xFF for c in from_key):
                converted = converted.replace(from_key, to_value)
        return converted

    def get_transition_basic_length_ms_with_attr(self, alias, tone, attr):
        oto_length = self.get_transition_basic_length_ms_by_oto(alias, tone, attr)
        parts = [p for p in alias.split(" ") if p]
        is_vcv = False
        if len(parts) == 2:
            starting_vowels = list(self.get_vowels()) + ["n", "N"]
            if parts[0] in starting_vowels:
                cv = parts[1]
                is_japanese_vcv = any(ord(c) > 0xFF for c in cv)
                clean_cv = ""
                for c in cv:
                    if _is_cs_digit(c) or c == "_" or c == "#":
                        break
                    clean_cv += c
                is_romaji_vcv = any(clean_cv.endswith(v) for v in self.get_vowels())
                if is_romaji_vcv or is_japanese_vcv:
                    is_vcv = True
        if is_vcv:
            return self.get_transition_basic_length_ms_by_constant() * 1.3
        return oto_length
