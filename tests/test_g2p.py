"""warble.g2p, the port of openutau's g2p layer.

dictionary words: expected outputs are the dict.txt lines inside the zips, with each pack's prep rules
applied (arpabet & co lowercase graphemes and phonemes and drop stress digits, italian drops digits only).
out-of-vocabulary words: expected outputs were checked against openutau itself through the phonemizer
goldens (tests/parity/goldens/en_arpasing.json, fr_sphinx.json, de_diphone.json: the oov_solo_* cases sing
exactly these symbols)."""

import pytest

from warble.g2p import (BY_OPENUTAU_CLASS, G2P_CLASSES, G2pDictionary, G2pFallbacks, G2pRemapper, get_g2p, languages)
from warble.g2p._cs import read_lines, split_ws, to_lower_invariant

DICT_WORDS = {
    "arpabet": {"ballot": ["b", "ae", "l", "ah", "t"], "blair": ["b", "l", "eh", "r"], "andrae": ["aa", "n", "d", "r", "ay"],
                "\"quote": ["k", "w", "ow", "t"], "hello": ["hh", "ah", "l", "ow"]},
    "arpabet-plus": {"gestapo": ["g", "ax", "s", "t", "aa", "p", "ow"],  # "Gestapo  g eh .." is overridden by a later "gestapo" line
                      "pole": ["p", "ow", "l"],
                     "accustomably": ["ax", "k", "ah", "s", "t", "ax", "m", "ax", "b", "l", "iy"]},
    "de": {"ab": ["q", "aa", "p"], "grauen": ["g", "rr", "aw", "ax", "n"],
           "betreffenden": ["b", "ax", "t", "rr", "eh", "f", "ax", "n", "d", "ax", "n"]},
    "de-marzipan": {"abgesehen": ["a", "p", "g", "ex", "z", "eh", "ex", "n"]},
    "es": {"chino": ["ch", "i", "n", "o"], "elabore": ["e", "l", "a", "B", "o", "r", "e"], "inhumana": ["i", "n", "u", "m", "a", "n", "a"]},
    "fil": {"busina'": ["b", "u", "s", "i", "n", "a", "q"], "liling": ["l", "i", "l", "i", "ng"], "'ika'": ["q", "i", "k", "a", "q"]},
    "fr": {"mouchant": ["mm", "ou", "ch", "an"], "gauthier": ["gg", "au", "tt", "yy", "ei"],
           "appeler": ["aa", "pp", "ee", "ll", "ei"]},
    "fr-millefeuille": {"abonnement": ["ah", "b", "oo", "n", "ee", "m", "en"], "resto": ["r", "ae", "s", "t", "oh"]},
    "it": {"abandonare": ["a", "b", "a", "n", "d", "o", "n", "a", "r", "e"], "ignorate": ["i", "JJ", "JJ", "o", "r", "a", "t", "e"],
           "sommità": ["s", "o", "m", "m", "i", "t", "a"]},
    "ja-mono": {"こ": ["k", "o"], "が": ["g", "a"], "gi": ["g", "i"], "息": ["AP"], "breath": ["AP"], "R": ["SP"]},
    "pt": {"prometo": ["p", "r", "o", "m", "e", "t", "u"], "abandonem": ["a", "b", "a~", "d", "o~", "n", "e~", "j~"]},
    "ru": {"арина": ["a", "rr", "ii", "n", "ay"], "бузина": ["b", "u", "zz", "i", "n", "aa"]},
}

# checked against openutau through the parity goldens
OOV_WORDS = {
    "en": {"flurbix": ["f", "l", "er", "b", "ih", "k", "s"], "warblesque": ["w", "ao", "r", "b", "l", "eh", "s", "k", "iy"],
           "quizzlepop": ["k", "w", "ih", "z", "ah", "l", "p", "aa", "p"], "aeiou": ["iy", "uw"], "zzz": ["z"],
           "onnxruntime": ["aa", "n", "k", "s", "r", "ah", "n", "t", "iy", "m"]},
    "fr": {"warblette": ["vv", "aa", "rr", "bb", "ll", "ai", "tt"], "flimpouf": ["ff", "ll", "in", "pp", "ou", "ff"],
           "gnagnagna": ["nn", "yy", "aa", "nn", "yy", "aa", "nn", "yy", "aa"]},
    "de": {"warblefunk": ["v", "aa", "ex", "b", "l", "ax", "f", "uh", "ng", "k"],
           "knödelwelt": ["k", "n", "ohh", "d", "ax", "l", "v", "eh", "l", "t"], "überglitz": ["q", "ue", "b", "ex", "g", "l", "ih", "ts"]},
}


@pytest.mark.parametrize("lang", sorted(DICT_WORDS))
def test_dictionary_words(lang):
    g2p = get_g2p(lang)
    for word, want in DICT_WORDS[lang].items():
        assert g2p.dict.query(word) == want, word
        assert g2p.query(word) == want, word


@pytest.mark.parametrize("lang", sorted(OOV_WORDS))
def test_oov_words_match_openutau(lang):
    g2p = get_g2p(lang)
    for word, want in OOV_WORDS[lang].items():
        assert g2p.dict.query(word) is None, f"{word} is in the dictionary"
        assert g2p.query(word) == want, word
        assert g2p.query(word) == want, word  # second time from the prediction cache


@pytest.mark.parametrize("lang", [k for k in languages() if k != "ja-mono"])
def test_prediction_smoke(lang):
    g2p = get_g2p(lang)
    word = {"ko": "뷁", "ru": "щъюх", "ja-mono": "zz"}.get(lang, "zorblat")
    out = g2p.query(word)
    assert out and all(isinstance(p, str) for p in out)


def test_query_edges():
    g2p = get_g2p("en")
    assert g2p.query("") is None
    assert g2p.query("!") is None and g2p.query("、") is None
    assert get_g2p("ja").query("zzz") is None  # no model in the japanese pack: dictionary only
    out = g2p.query("hello")
    out.append("x")
    assert g2p.query("hello") == ["hh", "ah", "l", "ow"]  # queries return copies


def test_symbols():
    en = get_g2p("en")
    assert en.is_valid_symbol("aa") and en.is_vowel("aa") and not en.is_vowel("b")
    assert en.is_glide("w") and en.is_glide("l") and not en.is_glide("aa")
    assert not en.is_valid_symbol("AA")
    assert en.unpack_hint("hh ah xx l ow") == ["hh", "ah", "l", "ow"]
    assert en.unpack_hint("hh,ah", ",") == ["hh", "ah"]
    assert en.symbols()["iy"] is True and len(en.symbols()) == 39
    # openutau quirk kept: the korean phones.txt separates columns with several spaces, so c# Split() yields
    # more than two parts and no symbol is registered (and dict.txt uses tabs, so no entry is either)
    ko = get_g2p("ko")
    assert ko.symbols() == {} and ko.dict.query("ㄷㅏㄹㅡㄱㅔ") is None
    assert get_g2p("it").is_vowel("a") and get_g2p("ja").is_vowel("a")


def test_registry():
    assert set(G2P_CLASSES) == {"arpabet", "arpabet-plus", "de", "de-marzipan", "es", "fil", "fr", "fr-millefeuille", "it",
                                "ja-mono", "ko", "pt", "ru"}
    assert BY_OPENUTAU_CLASS["OpenUtau.Core.G2p.ArpabetG2p"] is G2P_CLASSES["arpabet"]
    assert type(get_g2p("EN")) is G2P_CLASSES["arpabet"]
    with pytest.raises(KeyError):
        get_g2p("xx")


def test_dictionary_builder_fallbacks_remapper():
    d = (G2pDictionary.new_builder()
         .load("symbols:\n  - {symbol: a, type: vowel}\n  - {symbol: y, type: semivowel}\n  - {symbol: n}\n"
               "entries:\n  - {grapheme: 'no', phonemes: [n, a]}\n  - {grapheme: yes, phonemes: [y, e, s]}\n")
         .build())
    assert d.query("no") == ["n", "a"]  # yaml 'no' stays a string, like YamlDotNet
    assert d.query("yes") == ["y"]  # unknown symbols are dropped when the entry is added
    assert d.query("n") is None and d.is_glide("y") and not d.is_vowel("n")
    f = G2pFallbacks([d, get_g2p("en")])
    assert f.query("no") == ["n", "a"] and f.query("hello") == ["hh", "ah", "l", "ow"]
    assert f.is_vowel("a") and f.is_vowel("aa") and f.is_glide("y")
    r = G2pRemapper(d, {"N": False, "A": True}, {"n": "N", "a": "A"})
    assert r.query("no") == ["N", "A"] and r.is_vowel("A") and r.unpack_hint("N x A") == ["N", "A"]


def test_cs_helpers():
    assert split_ws("a  b\tc") == ["a", "", "b", "c"]
    assert to_lower_invariant("İA") == "ia"
    assert read_lines(b"\xef\xbb\xbfa\r\nb\rc\n\nd\n") == ["a", "b", "c", "", "d"]
