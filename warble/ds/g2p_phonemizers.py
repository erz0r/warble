"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Core/DiffSinger/Phonemizers/*.cs
(DiffSingerPhonemizer, DiffSingerG2pPhonemizer, DiffSingerEnglishPhonemizer, DiffSingerARPAPlusEnglishPhonemizer,
DiffSingerGermanPhonemizer, DiffSingerGermanMarzipanPhonemizer, DiffSingerFrenchMillefeuillePhonemizer,
DiffSingerItalianPhonemizer, DiffSingerSpanishPhonemizer, DiffSingerPortuguesePhonemizer, DiffSingerRussianPhonemizer,
DiffSingerFilipinoPhonemizer, DiffSingerRuleBasedFilipinoPhonemizer (with its RuleBasedFilipinoG2p),
DiffSingerKoreanPhonemizer, DiffSingerKoreanG2PPhonemizer, DiffSingerChinesePhonemizer, DiffSingerJyutpingPhonemizer,
DiffSingerJapanesePhonemizer) and the per-language parts of OpenUtau.Core/DiffSinger/DiffSingerBasePhonemizer.cs and
OpenUtau.Core/MachineLearningPhonemizer.cs (LoadG2p, Romanize, Process).

the duration-model pipeline these classes share (GetSymbols, ProcessWord, ProcessPart) lives in
warble/ds/phonemizer.py, which holds one of these objects and asks it for what differs per language:
the dictionary file name, the language code, the g2p, lyric romanization, SetUp extras (korean) and the
Process step that turns the part result of a note into its phonemes (english+ rewrites some).

    from warble.ds import g2p_phonemizers as gp
    cls = gp.for_lang("en")                       # DiffSingerEnglishPhonemizer
    cls = gp.by_class("DiffSingerARPAPlusEnglishPhonemizer")
"""

import os

import yaml

from ..g2p import (
    ArpabetG2p, ArpabetPlusG2p, FilipinoG2p, FrenchMillefeuilleG2p, G2pDictionary, G2pDictionaryData, G2pFallbacks,
    G2pRemapper, GermanG2p, GermanMarzipanG2p, IG2p, ItalianG2p, KoreanG2p, PortugueseG2p, RussianG2p, SpanishG2p,
)
from ..g2p._cs import is_all_punct
from ..utau.pz import base_chinese
from ..utau.pz import korean_phonemizer_util as kpu
from ..utau.pz._pinyin import CanTone, Jyutping
from ..utau.pz.api import Note as ApiNote
from . import _kana

NS = "OpenUtau.Core.DiffSinger."


class PhonemizerError(Exception):
    """an exception openutau's Process throws for one note (the note shows an error, nothing is sung)."""


class PartNote:
    """the phonemizer's view of a note (OpenUtau.Api.Phonemizer.Note): lyric, phonetic hint, tone, position,
    duration. `src` is warble's score note it came from."""

    __slots__ = ("lyric", "phonetic_hint", "tone", "position", "duration", "src")

    def __init__(self, lyric, phonetic_hint, tone, position, duration, src=None):
        self.lyric = lyric
        self.phonetic_hint = phonetic_hint
        self.tone = tone
        self.position = position
        self.duration = duration
        self.src = src

    def copy(self, **kw):
        n = PartNote(self.lyric, self.phonetic_hint, self.tone, self.position, self.duration, self.src)
        for k, v in kw.items():
            setattr(n, k, v)
        return n


def change_lyric(group, lyric):
    """MachineLearningPhonemizer.ChangeLyric: replaces the group's first note with a copy carrying the lyric."""
    group[0] = group[0].copy(lyric=lyric)
    return group


# ---- DiffSingerG2pDictionaryData ---------------------------------------------------------------------------

def load_dictionary_data(text):
    """Yaml.DefaultDeserializer.Deserialize<DiffSingerG2pDictionaryData>: the G2pDictionaryData fields plus
    `replacements: [{from, to}]` (replacementsDict: later entries win)."""
    data = G2pDictionaryData.deserialize(text)
    if text.startswith("﻿"):
        text = text[1:]
    raw = yaml.load(text, Loader=yaml.BaseLoader)
    replacements = {}
    if isinstance(raw, dict) and isinstance(raw.get("replacements"), list):
        for r in raw["replacements"]:
            if isinstance(r, dict):
                replacements[r.get("from")] = r.get("to")
    return data, replacements


# ---- DiffSingerBasePhonemizer / MachineLearningPhonemizer (per-language parts) -----------------------------

class DiffSingerBasePhonemizer:
    """abstract. the state openutau keeps on the phonemizer between SetUp and Process: part_result
    (note position -> [(symbol, tick offset, ms position)]) and unrecognized_lyrics (note position -> text)."""

    openutau_class = None
    name = None
    tag = None
    language = None  # the [Phonemizer] attribute's language
    lang_keys = ()  # warble language codes that select this class

    def __init__(self):
        self.part_result = {}
        self.unrecognized_lyrics = {}
        self.last_process_part_exception = None
        self.set_up_exception = None

    def get_dictionary_name(self):
        return "dsdict.yaml"

    def get_lang_code(self):
        return ""

    def dictionary_names(self):
        return [self.get_dictionary_name(), "dsdict.yaml"]

    def find_dictionary(self, root_path):
        for name in self.dictionary_names():
            p = os.path.join(root_path, name)
            if os.path.isfile(p):
                return p
        return None

    def load_g2p(self, root_path, use_lang_id, phoneme_tokens):
        """DiffSingerBasePhonemizer.LoadG2p: the bank's dictionary (with SP and AP as vowels), no base g2p."""
        g2ps = []
        builder = G2pDictionary.Builder()
        path = self.find_dictionary(root_path)
        if path is None:
            tried = ", ".join(os.path.join(root_path, n) for n in self.dictionary_names())
            raise FileNotFoundError(f"No dictionary file found. Tried: {tried}")
        with open(path, encoding="utf-8-sig") as f:
            builder.load(f.read())
        builder.add_symbol("SP", True)
        builder.add_symbol("AP", True)
        g2ps.append(builder.build())
        self.dictionary_path = path
        return G2pFallbacks(g2ps)

    def romanize(self, lyrics):
        """MachineLearningPhonemizer.Romanize: identity."""
        return list(lyrics)

    def set_up(self, groups, process_part):
        """MachineLearningPhonemizer.SetUp: clear, romanize the first lyric of every group, then run the timing
        model phrase by phrase (process_part(phrase) fills part_result / unrecognized_lyrics). groups are lists of
        PartNote and are changed in place like the c# arrays."""
        self.set_up_exception = None
        self.last_process_part_exception = None
        self.part_result.clear()
        self.unrecognized_lyrics.clear()
        if len(groups) == 0:
            return
        romanized = self.romanize([g[0].lyric for g in groups])
        for g, lyric in zip(groups, romanized):
            change_lyric(g, lyric)
        self._process_parts(groups, process_part, catch=True)

    def _process_parts(self, groups, process_part, catch):
        phrase = [groups[0]]
        for i in range(1, len(groups)):
            if groups[i - 1][-1].position + groups[i - 1][-1].duration == groups[i][0].position:
                phrase.append(groups[i])
            else:
                self._run_part(phrase, process_part, catch)
                phrase = [groups[i]]
        if phrase:
            self._run_part(phrase, process_part, catch)

    def _run_part(self, phrase, process_part, catch):
        if not catch:
            process_part(list(phrase))
            return
        try:
            process_part(list(phrase))
        except Exception as e:  # noqa: BLE001 - openutau logs and keeps going
            self.last_process_part_exception = e

    def process(self, notes, prev, next_, prev_neighbour, next_neighbour, prevs):
        """MachineLearningPhonemizer.Process -> [(phoneme, tick offset, ms)] or raises PhonemizerError."""
        lyric = self.unrecognized_lyrics.get(notes[0].position)
        if lyric is not None:
            if lyric == "":
                raise PhonemizerError("Phoneme not found for this note")
            raise PhonemizerError(f'Unrecognized phoneme "{lyric}"')
        phonemes = self.part_result.get(notes[0].position)
        if phonemes is None:
            cause = self.last_process_part_exception or self.set_up_exception
            if cause is not None:
                raise PhonemizerError("Phonemizer failed to process.") from cause
            raise PhonemizerError("Part result not found")
        return [tuple(p) for p in phonemes]

    def clean_up(self):
        self.part_result.clear()
        self.unrecognized_lyrics.clear()


class DiffSingerPhonemizer(DiffSingerBasePhonemizer):
    """the generic one ("DIFFS"): the bank's dsdict.yaml, no language prefix.

    warble extension: built with a language code (DiffSingerPhonemizer("th")) it reads dsdict-<lang>.yaml first
    and tries the <lang>/ prefix, so languages openutau has no diffsinger phonemizer for still work."""

    openutau_class = NS + "DiffSingerPhonemizer"
    name, tag, language = "DiffSinger Phonemizer", "DIFFS", None

    def __init__(self, lang=None):
        super().__init__()
        self.lang = lang or ""

    def get_dictionary_name(self):
        return f"dsdict-{self.lang}.yaml" if self.lang else "dsdict.yaml"

    def get_lang_code(self):
        return self.lang


# ---- DiffSingerG2pPhonemizer -------------------------------------------------------------------------------

class DiffSingerG2pPhonemizer(DiffSingerBasePhonemizer):
    """abstract: a diffsinger phonemizer based on one of openutau's builtin g2ps."""

    def __init__(self):
        super().__init__()
        self.phoneme_symbols = {}

    def load_base_g2p(self):
        return None

    def get_base_g2p_vowels(self):
        return []

    def get_base_g2p_consonants(self):
        return []

    def has_phoneme(self, phoneme):
        return phoneme in self.phoneme_symbols

    def load_g2p(self, root_path, use_lang_id, phoneme_tokens):
        g2ps = []
        builder = G2pDictionary.Builder()
        replacements = {}
        path = self.find_dictionary(root_path)
        if path is None:
            tried = ", ".join(os.path.join(root_path, n) for n in self.dictionary_names())
            raise FileNotFoundError(f"No dictionary file found. Tried: {tried}")
        try:
            with open(path, encoding="utf-8-sig") as f:
                data, replacements = load_dictionary_data(f.read())
            builder.load(data)
            if data.symbols is not None:
                for symbol in data.symbols:
                    self.phoneme_symbols[symbol.symbol.strip()] = True
        except Exception as e:
            raise RuntimeError(f"Failed to load {path}") from e
        self.dictionary_path = path
        builder.add_symbol("SP", True)
        builder.add_symbol("AP", True)
        g2ps.append(builder.build())

        base_g2p = self.load_base_g2p()
        if base_g2p is None:
            return G2pFallbacks(g2ps)
        for v in self.get_base_g2p_vowels():
            self.phoneme_symbols[v] = True
        for c in self.get_base_g2p_consonants():
            self.phoneme_symbols[c] = False
        lang_code = self.get_lang_code()
        if lang_code:
            # for diffsinger multi dict voicebanks, the replacements of g2p phonemes default to <langcode>/<phoneme>
            for ph in list(self.get_base_g2p_vowels()) + list(self.get_base_g2p_consonants()):
                if ph in replacements:
                    continue
                prefixed = lang_code + "/" + ph
                if prefixed in phoneme_tokens:
                    replacements[ph] = prefixed
                elif ph in phoneme_tokens:
                    replacements[ph] = ph
                else:
                    replacements[ph] = prefixed if use_lang_id else ph
        for frm, to in replacements.items():
            if base_g2p.is_valid_symbol(to):
                self.phoneme_symbols[frm] = bool(base_g2p.is_vowel(to))
        self.replacements = replacements
        g2ps.append(G2pRemapper(base_g2p, self.phoneme_symbols, replacements))
        return G2pFallbacks(g2ps)


class DiffSingerEnglishPhonemizer(DiffSingerG2pPhonemizer):
    openutau_class = NS + "DiffSingerEnglishPhonemizer"
    name, tag, language = "DiffSinger English Phonemizer", "DIFFS EN", "EN"
    lang_keys = ("en",)

    def get_dictionary_name(self):
        return "dsdict-en.yaml"

    def get_lang_code(self):
        return "en"

    def load_base_g2p(self):
        return ArpabetG2p()

    def get_base_g2p_vowels(self):
        return ["aa", "ae", "ah", "ao", "aw", "ay", "eh", "er",
                "ey", "ih", "iy", "ow", "oy", "uh", "uw"]

    def get_base_g2p_consonants(self):
        return ["b", "ch", "d", "dh", "f", "g", "hh", "jh", "k", "l", "m", "n",
                "ng", "p", "r", "s", "sh", "t", "th", "v", "w", "y", "z", "zh"]


class DiffSingerARPAPlusEnglishPhonemizer(DiffSingerG2pPhonemizer):
    """ARPA+ g2p (glottal stop with ', manual relaxed consonants) plus some rewrites in Process."""

    openutau_class = NS + "DiffSingerARPAPlusEnglishPhonemizer"
    name, tag, language = "DiffSinger English+ Phonemizer", "DIFFS EN+", "EN"
    lang_keys = ("en-plus", "en+", "en-arpaplus")

    def get_dictionary_name(self):
        return "dsdict-en.yaml"

    def get_lang_code(self):
        return "en"

    def load_base_g2p(self):
        return ArpabetPlusG2p()

    def get_base_g2p_vowels(self):
        return ["aa", "ae", "ah", "ao", "aw", "ax", "ay", "eh", "er",
                "ey", "ih", "iy", "ow", "oy", "uh", "uw"]

    def get_base_g2p_consonants(self):
        return ["b", "ch", "d", "dh", "dr", "dx", "f", "g", "hh", "jh",
                "k", "l", "m", "n", "ng", "p", "q", "r", "s", "sh", "t",
                "th", "tr", "v", "w", "y", "z", "zh"]

    def process(self, notes, prev, next_, prev_neighbour, next_neighbour, prevs):
        if notes[0].lyric == "-":
            return [("SP", 0, None)]  # MakeSimpleResult
        if notes[0].lyric == "br":
            return [("AP", 0, None)]
        phonemes = self.part_result.get(notes[0].position)
        if phonemes is None:
            raise PhonemizerError("Result not found in the part")
        processed = []
        lang_code = self.get_lang_code() + "/"
        i = 0
        while i < len(phonemes):
            tu = phonemes[i]
            # "n dx" -> "n" (the actual phoneme is "nx", like winner [w ih nx er])
            if (i < len(phonemes) - 1 and tu[0] == lang_code + "n" and self.has_phoneme(lang_code + "n")
                    and phonemes[i + 1][0] == lang_code + "dx" and self.has_phoneme(lang_code + "dx")):
                processed.append((lang_code + "n", tu[1], tu[2]))
                i += 1
            elif (i < len(phonemes) - 1 and tu[0] == "n" and self.has_phoneme("n") and phonemes[i + 1][0] == "dx"
                  and self.has_phoneme("dx") and not self.has_phoneme(lang_code + "n") and not self.has_phoneme(lang_code + "dx")):
                processed.append(("n", tu[1], tu[2]))
                i += 1
            else:
                ok, replacement = self.should_replace_phoneme(tu[0], prev, next_, prev_neighbour, next_neighbour)
                processed.append((replacement if ok else tu[0], tu[1], tu[2]))
            i += 1
        return processed

    def should_replace_phoneme(self, phoneme, prev, next_, prev_neighbour, next_neighbour):
        replacement = phoneme
        lang_code = self.get_lang_code() + "/"
        no_prev = prev_neighbour is None or _is_null_or_white_space(prev_neighbour.lyric)
        if (phoneme == lang_code + "cl" or not self.has_phoneme("q")) and self.has_phoneme("vf"):
            if no_prev:
                return True, "vf"
        if (phoneme == lang_code + "q" or phoneme == "q") and self.has_phoneme("vf"):
            if no_prev:
                return True, "vf"
        if (phoneme == lang_code + "q" or phoneme == "q") and self.has_phoneme("cl"):
            return True, "cl"
        if phoneme == lang_code + "q" and not self.has_phoneme("cl"):
            return True, "q"
        if phoneme == lang_code + "q" and not self.has_phoneme("cl") and self.has_phoneme(lang_code + "q"):
            return True, lang_code + "q"
        if phoneme == "ax" and not self.has_phoneme("ax"):
            return True, replacement
        if phoneme == lang_code + "ax" and not self.has_phoneme(lang_code + "ax"):
            return True, lang_code + "ah"
        return False, replacement


def _is_null_or_white_space(s):
    return s is None or all(c.isspace() for c in s)


class DiffSingerGermanPhonemizer(DiffSingerG2pPhonemizer):
    openutau_class = NS + "DiffSingerGermanPhonemizer"
    name, tag, language = "DiffSinger German Phonemizer", "DIFFS DE", "DE"
    lang_keys = ("de",)

    def get_dictionary_name(self):
        return "dsdict-de.yaml"

    def get_lang_code(self):
        return "de"

    def load_base_g2p(self):
        return GermanG2p()

    def get_base_g2p_vowels(self):
        return ["aa", "ae", "ah", "ao", "aw", "ax", "ay", "ee", "eh", "er", "ex", "ih", "iy", "oe", "ohh", "ooh", "oy",
                "ue", "uh", "uw", "yy"]

    def get_base_g2p_consonants(self):
        return ["b", "cc", "ch", "d", "dh", "f", "g", "hh", "jh", "k", "l", "m",
                "n", "ng", "p", "pf", "q", "r", "rr", "s", "sh", "t", "th", "ts", "v", "w", "x", "y", "z", "zh"]


class DiDiffSingerGermanMarzipanPhonemizerr(DiffSingerG2pPhonemizer):  # sic, the c# class name
    openutau_class = NS + "DiDiffSingerGermanMarzipanPhonemizerr"
    name, tag, language = "DiffSinger German Marzipan Phonemizer", "DIFFS DE MARZ", "DE"
    lang_keys = ("de-marzipan",)

    def get_dictionary_name(self):
        return "dsdict-de-marzipan.yaml"

    def get_lang_code(self):
        return "de"

    def load_base_g2p(self):
        return GermanMarzipanG2p()

    def get_base_g2p_vowels(self):
        return ["a", "er", "eh", "e", "ih", "i", "uh", "u", "oh", "o", "ueh", "ue", "oeh", "oe", "ex", "ei", "au", "eu"]

    def get_base_g2p_consonants(self):
        return ["j", "p", "t", "k", "f", "s", "sh", "ch", "xh", "h", "pf", "ts",
                "tsh", "th", "m", "n", "ng", "b", "d", "g", "v", "z", "l", "r", "dsh", "zh", "rh", "rr",
                "rx", "dh", "q", "vf", "cl"]


class DiffSingerFrenchMillfeuillePhonemizer(DiffSingerG2pPhonemizer):  # sic, the c# class name
    openutau_class = NS + "DiffSingerFrenchMillfeuillePhonemizer"
    name, tag, language = "DiffSinger French Millefeuille Phonemizer", "DIFFS FR MILLE", "FR"
    lang_keys = ("fr", "fr-millefeuille")

    def get_dictionary_name(self):
        return "dsdict-fr-millefeuille.yaml"

    def get_lang_code(self):
        return "fr"

    def load_base_g2p(self):
        return FrenchMillefeuilleG2p()

    def get_base_g2p_vowels(self):
        return ["ah", "eh", "ae", "ee", "oe", "ih", "oh", "oo", "ou", "uh", "en", "in", "on"]

    def get_base_g2p_consonants(self):
        return ["y", "w", "f", "k", "p", "s", "sh", "t", "h", "b", "d", "g", "l",
                "m", "n", "r", "v", "z", "j", "ng", "q", "uy", "vf", "cl"]


class DiffSingerItalianPhonemizer(DiffSingerG2pPhonemizer):
    openutau_class = NS + "DiffSingerItalianPhonemizer"
    name, tag, language = "DiffSinger Italian Phonemizer", "DIFFS IT", "IT"
    lang_keys = ("it",)

    def get_dictionary_name(self):
        return "dsdict-it.yaml"

    def get_lang_code(self):
        return "it"

    def load_base_g2p(self):
        return ItalianG2p()

    def get_base_g2p_vowels(self):
        return ["a", "e", "EE", "i", "o", "OO", "u"]

    def get_base_g2p_consonants(self):
        return ["b", "d", "dz", "dZZ", "f", "g", "j", "JJ", "k", "l", "LL", "m", "n",
                "nf", "ng", "p", "r", "s", "SS", "t", "ts", "tSS", "v", "w", "z"]


class DiffSingerSpanishPhonemizer(DiffSingerG2pPhonemizer):
    openutau_class = NS + "DiffSingerSpanishPhonemizer"
    name, tag, language = "DiffSinger Spanish Phonemizer", "DIFFS ES", "ES"
    lang_keys = ("es",)

    def get_dictionary_name(self):
        return "dsdict-es.yaml"

    def get_lang_code(self):
        return "es"

    def load_base_g2p(self):
        return SpanishG2p()

    def get_base_g2p_vowels(self):
        return ["a", "e", "i", "o", "u"]

    def get_base_g2p_consonants(self):
        return ["b", "B", "ch", "d", "D", "f", "g", "G", "gn", "I", "k", "l",
                "ll", "m", "n", "p", "r", "rr", "s", "t", "U", "w", "x", "y", "Y", "z"]


class DiffSingerPortuguesePhonemizer(DiffSingerG2pPhonemizer):
    openutau_class = NS + "DiffSingerPortuguesePhonemizer"
    name, tag, language = "DiffSinger Portuguese Phonemizer", "DIFFS PT", "PT"
    lang_keys = ("pt",)

    def get_dictionary_name(self):
        return "dsdict-pt.yaml"

    def get_lang_code(self):
        return "pt"

    def load_base_g2p(self):
        return PortugueseG2p()

    def get_base_g2p_vowels(self):
        return ["E", "O", "a", "a~", "e", "e~", "i", "i~", "o", "o~", "u", "u~"]

    def get_base_g2p_consonants(self):
        return ["J", "L", "R", "S", "X", "Z", "b", "d", "dZ", "f", "g", "j", "j~",
                "k", "l", "m", "n", "p", "r", "s", "t", "tS", "v", "w", "w~", "z"]


class DiffSingerRussianPhonemizer(DiffSingerG2pPhonemizer):
    openutau_class = NS + "DiffSingerRussianPhonemizer"
    name, tag, language = "DiffSinger Russian Phonemizer", "DIFFS RU", "RU"
    lang_keys = ("ru",)

    def get_dictionary_name(self):
        return "dsdict-ru.yaml"

    def get_lang_code(self):
        return "ru"

    def load_base_g2p(self):
        return RussianG2p()

    def get_base_g2p_vowels(self):
        return ["a", "aa", "ay", "ee", "i", "ii", "ja", "je", "jo", "ju", "oo",
                "u", "uj", "uu", "y", "yy"]

    def get_base_g2p_consonants(self):
        return ["b", "bb", "c", "ch", "d", "dd", "f", "ff", "g", "gg", "h", "hh",
                "j", "k", "kk", "l", "ll", "m", "mm", "n", "nn", "p", "pp", "r",
                "rr", "s", "sch", "sh", "ss", "t", "tt", "v", "vv", "z", "zh", "zz"]


class DiffSingerFilipinoPhonemizer(DiffSingerG2pPhonemizer):
    openutau_class = NS + "DiffSingerFilipinoPhonemizer"
    name, tag, language = "DiffSinger Filipino Phonemizer", "DIFFS FIL", "FIL"
    lang_keys = ("fil", "tl")

    def get_dictionary_name(self):
        return "dsdict-fil.yaml"

    def get_lang_code(self):
        return "fil"

    def load_base_g2p(self):
        return FilipinoG2p()

    def get_base_g2p_vowels(self):
        return ["a", "e", "i", "o", "u"]

    def get_base_g2p_consonants(self):
        return ["q", "b", "d", "dy", "f", "g", "H", "hh", "j", "k", "l",
                "m", "n", "ng", "ny", "p", "dx", "s", "sy", "t", "th",
                "ch", "v", "w", "z"]


# ---- RuleBasedFilipinoG2p (OpenUtau.Core.G2p, defined in DiffSingerRuleBasedFilipinoPhonemizer.cs) ----------

class RuleBasedFilipinoG2p(IG2p):
    valid_phonemes = ["m", "n", "ng", "p", "t", "ty", "k", "q", "b", "d", "dy", "g", "s", "sy", "h", "l", "y", "Y",
                      "w", "W", "r", "vf", "a", "e", "i", "o", "u"]
    glides = ["w", "y"]
    vowels = ["a", "e", "i", "o", "u"]

    def is_glide(self, symbol):
        return symbol in self.glides

    def is_valid_symbol(self, symbol):
        return symbol in self.valid_phonemes

    def is_vowel(self, symbol):
        return symbol in self.vowels

    def _is_consonant(self, symbol):
        return symbol != "|" and not self.is_vowel(symbol)

    def unpack_hint(self, hint, separator=" "):
        return [x for x in hint.split(separator) if x in self.valid_phonemes]

    def query(self, grapheme):
        if grapheme is None or grapheme == "" or is_all_punct(grapheme):
            return None
        return self.predict(grapheme)

    def predict(self, grapheme):
        grapheme = grapheme.lower()  # ToLower(new CultureInfo("fil-PH")): no special casing rules for filipino
        if grapheme == "mga":
            grapheme = "manga"
        if grapheme == "ng":
            grapheme = "nang"
        phonemes = []
        for c in grapheme:
            prev = phonemes[-1] if phonemes else ""
            if c in ("a", "o", "u"):
                if prev == "c":
                    phonemes[-1] = "k"
                elif self.is_vowel(prev):
                    phonemes.append("q")
                phonemes.append(c)
            elif c == "e":
                if prev == "c":
                    phonemes[-1] = "s"
                elif self.is_vowel(prev):
                    phonemes.append("q")
                phonemes.append("e")
            elif c == "i":
                if prev == "c":
                    phonemes[-1] = "sy"
                elif self.is_vowel(prev):
                    phonemes.append("q")
                    phonemes.append("i")
                else:
                    phonemes.append("i")
            elif c == "f":
                phonemes.append("p")
            elif c == "g":
                if prev == "n":
                    phonemes[-1] = "ng"
                else:
                    phonemes.append("g")
            elif c == "h":
                if prev == "c":
                    phonemes[-1] = "ty"
                elif prev == "s":
                    phonemes[-1] = "sy"
                else:
                    phonemes.append("h")
            elif c == "j":
                phonemes.append("dy")
            elif c == "ñ":
                phonemes.append("n")
                phonemes.append("y")
            elif c == "s":
                if prev == "t":
                    phonemes[-1] = "ty"
                else:
                    phonemes.append("s")
            elif c == "y":
                if prev in ("t", "d", "s"):
                    phonemes[-1] = prev + "y"
                else:
                    phonemes.append("y")
            elif c == "z":
                phonemes.append("s")
            elif c == "-":
                phonemes.append("q")
            elif c == "'":
                phonemes.append("vf")
            else:
                phonemes.append(c)
        # glide+coda pass
        for i in range(1, len(phonemes) - 1):
            prev, curr, nxt = phonemes[i - 1], phonemes[i], phonemes[i + 1]
            if curr == "u" and self._is_consonant(prev) and self.is_vowel(nxt):
                phonemes[i] = "w"
            elif curr == "i" and self._is_consonant(prev) and self.is_vowel(nxt):
                phonemes[i] = "y"
            elif curr == "w" and self.is_vowel(prev) and self._is_consonant(nxt):
                phonemes[i] = "W"
            elif curr == "y" and self.is_vowel(prev) and self._is_consonant(nxt):
                phonemes[i] = "Y"
        # end coda
        if len(phonemes) >= 2 and self.is_vowel(phonemes[-2]) and self.is_glide(phonemes[-1]):
            phonemes[-1] = phonemes[-1].upper()
        filtered = [x for x in phonemes if x in self.valid_phonemes]
        return None if len(filtered) == 0 else filtered


class DiffSingerRuleBasedFilipinoPhonemizer(DiffSingerG2pPhonemizer):
    openutau_class = NS + "DiffSingerRuleBasedFilipinoPhonemizer"
    name, tag, language = "DiffSinger Rule-based Filipino Phonemizer", "DIFFS FIL", "FIL"
    lang_keys = ("fil-rule",)

    def get_dictionary_name(self):
        return "dsdict-fil.yaml"

    def get_lang_code(self):
        return "fil"

    def load_base_g2p(self):
        return RuleBasedFilipinoG2p()

    def get_base_g2p_vowels(self):
        return ["a", "e", "i", "o", "u"]

    def get_base_g2p_consonants(self):
        return ["m", "n", "ng", "p", "t", "ty", "k", "q", "b", "d", "dy", "g", "s", "sy", "h", "l", "y", "Y", "w",
                "W", "r", "vf"]


# ---- korean ------------------------------------------------------------------------------------------------

class DiffSingerKoreanG2PPhonemizer(DiffSingerG2pPhonemizer):
    openutau_class = NS + "DiffSingerKoreanG2PPhonemizer"
    name, tag, language = "DiffSinger Korean G2P Phonemizer", "DIFFS KO", "KO"
    lang_keys = ("ko",)

    def get_dictionary_name(self):
        return "dsdict-ko.yaml"

    def get_lang_code(self):
        return "ko"

    def load_base_g2p(self):
        return KoreanG2p()

    def get_base_g2p_vowels(self):
        return ["a", "e", "eo", "eu", "i", "o", "u", "w", "y"]

    def get_base_g2p_consonants(self):
        return ["K", "L", "M", "N", "NG", "P", "T", "b", "ch", "d",
                "g", "h", "j", "jj", "k", "kk", "m", "n", "p", "pp",
                "r", "s", "ss", "t", "tt"]


class DiffSingerKoreanPhonemizer(DiffSingerBasePhonemizer):
    """dictionary only; SetUp runs the base SetUp, then variates the hangul lyrics (batchim rules) and runs every
    phrase again. results of the second pass replace the first; unrecognized lyrics of both passes stay."""

    openutau_class = NS + "DiffSingerKoreanPhonemizer"
    name, tag, language = "DiffSinger Korean Phonemizer", "DIFFS KO", "KO"
    lang_keys = ("ko-dict",)

    def get_dictionary_name(self):
        return "dsdict-ko.yaml"

    def get_lang_code(self):
        return "ko"

    def set_up(self, groups, process_part):
        super().set_up(groups, process_part)
        if len(groups) == 0:
            return
        romanize_korean_notes(groups)
        # the c# calls ProcessPart without the try/catch of the base SetUp
        self._process_parts(groups, process_part, catch=False)


def romanize_korean_notes(groups):
    """KoreanPhonemizerUtil.RomanizeNotes(groups, false) on PartNote groups."""
    ko_groups = [[ApiNote(lyric=n.lyric, tone=n.tone, position=n.position, duration=n.duration, phonetic_hint=n.phonetic_hint)
                  for n in g] for g in groups]
    kpu.romanize_notes(ko_groups, False)
    for g, kg in zip(groups, ko_groups):
        if g[0].lyric != kg[0].lyric:
            change_lyric(g, kg[0].lyric)


# ---- chinese / cantonese / japanese ------------------------------------------------------------------------

class DiffSingerChinesePhonemizer(DiffSingerBasePhonemizer):
    openutau_class = NS + "DiffSingerChinesePhonemizer"
    name, tag, language = "DiffSinger Chinese Phonemizer", "DIFFS ZH", "ZH"
    lang_keys = ("zh", "zh-cn", "cmn")

    def get_dictionary_name(self):
        return "dsdict-zh.yaml"

    def get_lang_code(self):
        return "zh"

    def romanize(self, lyrics):
        return base_chinese.romanize(lyrics)


class DiffSingerJyutpingPhonemizer(DiffSingerBasePhonemizer):
    openutau_class = NS + "DiffSingerJyutpingPhonemizer"
    name, tag, language = "DiffSinger Jyutping Phonemizer", "DIFFS ZH-YUE", "ZH-YUE"
    lang_keys = ("yue", "zh-yue", "zh-hk")

    def get_dictionary_name(self):
        return "dsdict-zh-yue.yaml"

    def get_lang_code(self):
        return "yue"

    def romanize(self, lyrics):
        return [res.pinyin for res in Jyutping.instance().hanzi_to_pinyin(list(lyrics), CanTone.NORMAL, 0)]


class DiffSingerJapanesePhonemizer(DiffSingerBasePhonemizer):
    openutau_class = NS + "DiffSingerJapanesePhonemizer"
    name, tag, language = "DiffSinger Japanese Phonemizer", "DIFFS JA", "JA"
    lang_keys = ("ja",)

    def get_dictionary_name(self):
        return "dsdict-ja.yaml"

    def get_lang_code(self):
        return "ja"

    def romanize(self, lyrics):
        lyrics_array = list(lyrics)
        kana_lyrics = [l for l in lyrics_array if _kana.is_kana(l)]
        kana_result = _kana.to_str_list(_kana.kana_to_romaji(kana_lyrics, _kana.ERROR_DEFAULT, False))
        kana_index = 0
        for i in range(len(lyrics_array)):
            if _kana.is_kana(lyrics_array[i]):
                if lyrics_array[i] == "ん":
                    lyrics_array[i] = "N"
                else:
                    lyrics_array[i] = kana_result[kana_index]
                kana_index += 1
        return lyrics_array


# ---- registry ----------------------------------------------------------------------------------------------

CLASSES = [
    DiffSingerPhonemizer, DiffSingerEnglishPhonemizer, DiffSingerARPAPlusEnglishPhonemizer, DiffSingerGermanPhonemizer,
    DiDiffSingerGermanMarzipanPhonemizerr, DiffSingerFrenchMillfeuillePhonemizer, DiffSingerItalianPhonemizer,
    DiffSingerSpanishPhonemizer, DiffSingerPortuguesePhonemizer, DiffSingerRussianPhonemizer, DiffSingerFilipinoPhonemizer,
    DiffSingerRuleBasedFilipinoPhonemizer, DiffSingerKoreanG2PPhonemizer, DiffSingerKoreanPhonemizer,
    DiffSingerChinesePhonemizer, DiffSingerJyutpingPhonemizer, DiffSingerJapanesePhonemizer,
]

# openutau class names ported here (tools/phonemizer_inventory.py reads this)
PORTED = [c.openutau_class for c in CLASSES]

BY_OPENUTAU_CLASS = {c.openutau_class: c for c in CLASSES}

# warble language code -> classes that serve it, the default first. when a language has several, the first whose
# own dictionary file is in the bank wins (see for_lang).
BY_LANG = {}
for _c in CLASSES:
    for _k in _c.lang_keys:
        BY_LANG.setdefault(_k, []).append(_c)
BY_LANG["de"].append(DiDiffSingerGermanMarzipanPhonemizerr)
BY_LANG["fil"].append(DiffSingerRuleBasedFilipinoPhonemizer)
BY_LANG["ko"].append(DiffSingerKoreanPhonemizer)
BY_LANG["en"].append(DiffSingerARPAPlusEnglishPhonemizer)


def by_class(name):
    """a class by openutau type name: full ('OpenUtau.Core.DiffSinger.DiffSingerEnglishPhonemizer') or short,
    case-insensitive. None when unknown."""
    if not name:
        return None
    if name in BY_OPENUTAU_CLASS:
        return BY_OPENUTAU_CLASS[name]
    short = name.rsplit(".", 1)[-1].lower()
    for c in CLASSES:
        if c.openutau_class.rsplit(".", 1)[-1].lower() == short or (c.tag or "").lower() == name.lower():
            return c
    return None


def norm_lang(lang):
    return (lang or "").strip().lower().replace("_", "-")


def for_lang(lang, dict_dir=None):
    """the class for a warble language code, or None. with several candidates (de: german / marzipan,
    en: english / english+, fil: g2p / rule-based, ko: g2p / dictionary), the first whose own dsdict file exists in
    dict_dir wins, else the first listed."""
    cands = BY_LANG.get(norm_lang(lang))
    if not cands:
        return None
    if dict_dir:
        for c in cands:
            if os.path.isfile(os.path.join(dict_dir, c().get_dictionary_name())):
                return c
    return cands[0]


def languages():
    return sorted(BY_LANG)


def describe():
    return [{"class": c.openutau_class, "name": c.name, "tag": c.tag, "language": c.language, "lang": list(c.lang_keys)}
            for c in CLASSES]


__all__ = ["PORTED", "CLASSES", "BY_OPENUTAU_CLASS", "BY_LANG", "by_class", "for_lang", "languages", "PartNote",
           "PhonemizerError", "RuleBasedFilipinoG2p"] + [c.__name__ for c in CLASSES]
