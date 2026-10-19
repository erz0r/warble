"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Plugin.Builtin/SyllableBasedPhonemizer.cs

the base of the syllable based phonemizers (arpasing+, english vccv / c+v / x-sampa, filipino, and the french,
german, italian, polish, portuguese, russian, spanish and en/es-to-ja ones). a note group becomes symbols (a
dictionary g2p, or the lyric split on spaces), the symbols become syllables "[prevV] [cc...] [v]" (one per
vowel, each owning the consonants in front of it) plus an ending "[prevV] [cc...]" after the last vowel, and
the subclass turns every syllable and the ending into aliases. this class then times the aliases (every alias
but the last of a syllable sits before the vowel, each one a transition long), validates them against the
oto with yaml/hardcoded fallbacks, and maps them through the pitch/color/alt subbanks.

naming follows the c# with snake_case (ProcessSyllable -> process_syllable). Syllable and Ending are c#
structs, so the base always hands subclasses a copy they may change freely.

subclassing (arpasing_plus.py, english_vccv.py, english_cpv.py, en_xsampa.py and filipino.py are worked examples):

    @phonemizer("...", "TAG", language="EN", openutau_class="OpenUtau.Plugin.Builtin.MyPhonemizer")
    class MyPhonemizer(SyllableBasedPhonemizer):
        yaml_file_name = "my.yaml"                 # YamlFileName: <bank>/my.yaml and the plugin-folder my.yaml
        yaml_template = "my.template.yaml"         # YamlTemplate: file under data/syllable_based/, or an absolute
                                                   # path (e.g. into your own data/<family>/), or None
        yaml_version = "1.2"                       # YamlVersion (or None)
        enable_phoneme_tokenization = False        # EnablePhonemeTokenization
        no_gap = True                              # NoGap

        def __init__(self):
            super().__init__()                     # base field initialisers first, like c#
            self.vowels = [...]; self.consonants = [...]; self.dictionary_replacements = {...}

        def get_vowels(self): return self.vowels                  # abstract
        def get_consonants(self): return self.consonants          # needed with a dictionary
        def get_dictionary_name(self): return ""                  # "" -> load a dictionary (yaml + get_base_g2ps)
        def get_base_g2ps(self): return [ArpabetG2p()]            # appended after the yaml dictionaries
        def process_syllable(self, syllable): -> list of aliases  # abstract; last one is the "vowel"
        def process_ending(self, ending): -> list of aliases      # abstract

    overridable hooks (all optional): set_singer, set_up, process, init, get_symbols, tokenize_phonemes,
    is_glide, get_dictionary_phonemes_replacement, make_syllables, handle_not_enough_notes, handle_word_not_found,
    get_dictionary_word_phonemes, replace_phoneme, get_hardcoded_fallback, validate_alias, get_aliases_fallback,
    get_transition_basic_length_ms (the 1-arg c# overload), get_transition_basic_length_ms_with_attr (the
    (alias, tone, attr) c# overload, which is what MakePhonemes calls), get_transition_multiplier,
    load_base_dictionary, parse_dictionary, sync_attributes, get_dynamic_phoneme_attributes, assign_all_affixes,
    is_group_keyword, is_group_match, apply_replacements.

    helpers for subclasses: has_oto, try_add_phoneme(list, tone, *aliases) (a leading bool marks the added
    alias as a glide, like the c# overload), glides(alias), can_make_alias_extension, is_short,
    are_tones_from_the_same_subbank, validate_alias, get_transition_basic_length_ms_by_constant / _by_oto,
    get_tempo_note_length_factor, and the yaml-driven fields vowels, consonants, tails, fricative, aspirate,
    semivowel, liquid, nasal, stop, tap, affricate, dictionary_replacements, phoneme_overrides, yaml_fallbacks,
    cons_exceptions, diphthong_tails, diphthong_splits, vowel_sustains.

notes for porters:
- a subclass with its own yaml keys (vcvowels, useconvel, ...) reads them after super().set_singer() with
  self.load_yaml_raw(path): the document as plain dicts/lists of strings (YamlDotNet-like, nothing typed),
  already migrated if the singer's file is outdated. english_vccv.py does this.
- the legacy text dictionary (get_dictionary_name() -> "cmudict_xx.txt" with no yaml_file_name) is looked up
  in self.dictionaries_path() (api.py: pz/data); openutau's Dictionaries folder holds no such files on a fresh
  install, so skipping a missing file matches openutau there.
- c# overloads become one method each: get_transition_basic_length_ms(alias="") vs
  get_transition_basic_length_ms_with_attr(alias, tone, attr); try_add_phoneme with or without the glide bool.
- c# `bpm` is 0 until SetTiming while api.Phonemizer starts at 120; only matters to an init() that reads bpm.
- c# interpolates arrays as "System.String[]" (cs_str) and cc.Skip(i) as SKIP_ITERATOR_STR; keep those quirks.

what warble does differently (no behaviour a phonemizer can see in a fresh install):
- the plugin-folder yaml is read from the template shipped under data/syllable_based/ (openutau writes the
  template there on first use and never changes it unless its version is older than the template's).
- openutau rewrites an outdated singer yaml in place (merging it into the newer template, keeping a backup);
  warble never writes into banks, it builds the same merged document in memory (_migrated_raw).
- the yaml file watchers (YamlWatcher, global generation counters) are not ported: nothing reloads mid-run.
"""

import copy
import dataclasses
import math
import os
import re
from dataclasses import dataclass, field

import yaml

from ...g2p import G2pDictionary, G2pFallbacks, G2pRemapper, IG2pSymbols
from ...g2p._cs import to_lower_invariant, trim
from ...g2p.g2p_dictionary_data import Entry, G2pDictionaryData, SymbolData
from .api import Phoneme, PhonemeAttributes, Phonemizer
from .phoneme_based import cs_div

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "syllable_based")

_YAML_LOADER = getattr(yaml, "CBaseLoader", yaml.BaseLoader)


# ---------------------------------------------------------------------------------------------------------
# small c# helpers
# ---------------------------------------------------------------------------------------------------------

@dataclass
class PhonemeExpression:
    abbr: str = None
    value: float = 0.0


def take(seq, n):
    """Enumerable.Take: n <= 0 gives nothing (python slicing would count from the end)."""
    return list(seq[:n]) if n > 0 else []


def skip(seq, n):
    """Enumerable.Skip: n <= 0 skips nothing."""
    return list(seq[n:]) if n > 0 else list(seq)


def last(seq):
    """Enumerable.Last(): throws on an empty sequence."""
    if not seq:
        raise ValueError("Sequence contains no elements")
    return seq[-1]


def at(seq, i):
    """c# indexing: no wrap-around for negative indexes."""
    if i < 0:
        raise IndexError("Index was outside the bounds of the array.")
    return seq[i]


def distinct(seq):
    out = []
    seen = set()
    for s in seq:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def cs_replace(s, old, new):
    """string.Replace(old, new): old must not be empty, a null new means ''."""
    if old is None:
        raise TypeError("Value cannot be null. (Parameter 'oldValue')")
    if old == "":
        raise ValueError("The value cannot be an empty string. (Parameter 'oldValue')")
    return s.replace(old, "" if new is None else new)


def cs_str(v):
    """c# string interpolation of a value: null prints as '', arrays print their type name."""
    if v is None:
        return ""
    if isinstance(v, (list, tuple)):
        return "System.String[]"
    if isinstance(v, bool):
        return "True" if v else "False"
    return str(v)


# what $"{cc.Skip(i)}" prints on .net 10 (an IEnumerable<string> partition, not its items)
SKIP_ITERATOR_STR = "System.Linq.Enumerable+IListSkipTakeIterator`1[System.String]"


def find_attr(attrs, index):
    """attributes?.FirstOrDefault(a => a.index == index) ?? default (a fresh default struct)."""
    for a in attrs or []:
        if a.index == index:
            return a
    return PhonemeAttributes()


def copy_attr(a):
    return dataclasses.replace(a)


# ---------------------------------------------------------------------------------------------------------
# the syllable model
# ---------------------------------------------------------------------------------------------------------

@dataclass
class Syllable:
    """Syllable is [V] [C..] [V]"""
    prev_v: str = None  # vowel from previous syllable for VC
    cc: list = None  # CCs, may be empty
    v: str = None  # "base" note. May not actually be vowel, if only consonants way provided
    position: int = 0  # start position for vowel. All VC CC goes before this position
    duration: int = 0  # previous note duration, i.e. this is container for VC and CC notes
    tone: int = 0  # tone for VC and CC
    attr: list = None  # other phoneme attributes for VC and CC
    vowel_tone: int = 0  # tone for base "vowel" phoneme
    vowel_attr: list = None  # other phoneme attributes for base "vowel" phoneme
    prev_word_consonants_count: int = 0  # 0: no consonants taken from the previous word; 1: the first one is, ...
    can_alias_be_extended: bool = False  # see can_make_alias_extension
    # lookahead & context
    next_v: str = None
    next_cc_: list = None
    prev_base_phoneme_: str = None
    next_base_phoneme_: str = None

    def copy(self):
        return copy.copy(self)

    @property
    def next_vowel(self):
        return self.next_v if self.next_v is not None else ""

    @property
    def next_cc(self):
        return self.next_cc_ if self.next_cc_ is not None else []

    @property
    def prev_base_phoneme(self):
        return self.prev_base_phoneme_ if self.prev_base_phoneme_ is not None else ""

    @property
    def next_base_phoneme(self):
        return self.next_base_phoneme_ if self.next_base_phoneme_ is not None else ""

    @property
    def is_starting_v(self):
        return self.prev_v == "" and len(self.cc) == 0

    @property
    def is_vv(self):
        return self.prev_v != "" and len(self.cc) == 0

    @property
    def is_starting_cv(self):
        return self.prev_v == "" and len(self.cc) > 0

    @property
    def is_vcv(self):
        return self.prev_v != "" and len(self.cc) > 0

    @property
    def is_starting_cv_with_one_consonant(self):
        return self.prev_v == "" and len(self.cc) == 1

    @property
    def is_vcv_with_one_consonant(self):
        return self.prev_v != "" and len(self.cc) == 1

    @property
    def is_starting_cv_with_more_than_one_consonant(self):
        return self.prev_v == "" and len(self.cc) > 1

    @property
    def is_vcv_with_more_than_one_consonant(self):
        return self.prev_v != "" and len(self.cc) > 1

    @property
    def previous_word_cc(self):
        return take(self.cc, self.prev_word_consonants_count)

    @property
    def current_word_cc(self):
        return skip(self.cc, self.prev_word_consonants_count)

    def __str__(self):
        return f"({cs_str(self.prev_v)}) {' '.join(self.cc) if self.cc is not None else ''} {cs_str(self.v)}"


@dataclass
class Ending:
    prev_v: str = None  # vowel from the last syllable to make VC
    cc: list = None  # actual CC at the ending
    tail: str = None  # the exact lyric/symbol of the tail (e.g. "R", "br", "-")
    position: int = 0  # last note position + duration, all phonemes must be less than this
    duration: int = 0  # last syllable length, max container for all VC CC C-
    tone: int = 0  # the tone from last syllable, for all ending phonemes
    attr: list = None  # other phoneme attributes from last syllable

    def copy(self):
        return copy.copy(self)

    @property
    def has_tail(self):
        return bool(self.tail)

    @property
    def is_ending_v(self):
        return len(self.cc) == 0

    @property
    def is_ending_vc(self):
        return len(self.cc) > 0

    @property
    def is_ending_vc_with_one_consonant(self):
        return len(self.cc) == 1

    @property
    def is_ending_vc_with_more_than_one_consonant(self):
        return len(self.cc) > 1

    def __str__(self):
        return f"({cs_str(self.prev_v)}) {' '.join(self.cc) if self.cc is not None else ''}"


# ---------------------------------------------------------------------------------------------------------
# the yaml model (YAMLData / Replacement), read like YamlDotNet's TolerantDeserializer reads it
# ---------------------------------------------------------------------------------------------------------

class YamlFormatError(Exception):
    pass


def _null(v):
    return v is None or v in ("~", "null", "Null", "NULL", "")


def _yaml_str(v):
    """a scalar into a string property: plain null scalars are null, mappings/sequences don't fit."""
    if isinstance(v, (dict, list)):
        raise YamlFormatError("expected a scalar")
    return None if _null(v) else v


def _yaml_obj(v):
    """a value into an `object` property: a scalar string, or a List<object> for a sequence."""
    if isinstance(v, list):
        return [_yaml_obj(x) for x in v]
    if isinstance(v, dict):
        return dict(v)
    return None if _null(v) else v


def _yaml_double(v):
    if _null(v):
        raise YamlFormatError("null into double")
    try:
        return float(_yaml_str(v))
    except ValueError:
        raise YamlFormatError(f"not a double: {v}") from None


def _yaml_bool(v):
    if _null(v):
        return None
    v = _yaml_str(v)
    if v.lower() == "true":
        return True
    if v.lower() == "false":
        return False
    raise YamlFormatError(f"not a bool: {v}")


def _seq(v, conv):
    """a sequence property: null stays null, a mapping or a non-null scalar fails."""
    if isinstance(v, list):
        return [conv(x) for x in v]
    if not isinstance(v, dict) and _null(v):
        return None
    raise YamlFormatError("expected a sequence")


def _obj(v, fields):
    """a class-typed item: null stays null, anything but a mapping fails."""
    if isinstance(v, dict):
        return fields(v)
    if not isinstance(v, list) and _null(v):
        return None
    raise YamlFormatError("expected a mapping")


class Replacement:
    def __init__(self, from_=None, to=None, where="inside"):
        self.from_ = from_
        self.to = to
        self.where = where

    @staticmethod
    def _as_list(v):
        if isinstance(v, str):
            return [v]
        if isinstance(v, list):
            return ["null" if x is None else _obj_to_string(x) for x in v]
        return []

    @property
    def from_list(self):
        return self._as_list(self.from_)

    @property
    def to_list(self):
        return self._as_list(self.to)


def _obj_to_string(x):
    """object.ToString() of a deserialized yaml value."""
    if isinstance(x, list):
        return "System.Collections.Generic.List`1[System.Object]"
    if isinstance(x, dict):
        return "System.Collections.Generic.Dictionary`2[System.Object,System.Object]"
    return str(x)


@dataclass
class YAMLData:
    version: str = None
    isglides: bool = None
    symbols: list = field(default_factory=list)  # [(symbol, type)]
    replacements: list = field(default_factory=list)  # [Replacement]
    fallbacks: list = field(default_factory=list)  # [Replacement]
    timings: list = field(default_factory=list)  # [(symbol, value)]
    diphthongs: list = field(default_factory=list)  # [(from, to)]
    vowelsustains: list = field(default_factory=list)  # [(symbol, sustain, offset)]
    entries: list = field(default_factory=list)  # [(grapheme, phonemes)]
    extension_data: dict = field(default_factory=dict)


_KNOWN_KEYS = {"version", "isglides", "symbols", "replacements", "fallbacks", "timings", "diphthongs", "vowelsustains"}


def _replacement(d):
    r = Replacement()
    if "from" in d:
        r.from_ = _yaml_obj(d["from"])
    if "to" in d:
        r.to = _yaml_obj(d["to"])
    if "where" in d:
        r.where = _yaml_str(d["where"])
    return r


def yaml_data_from_raw(raw):
    """TolerantDeserializer.Deserialize<YAMLData>: unknown keys ignored, a type mismatch fails the whole file."""
    if raw is None or (isinstance(raw, str) and _null(raw)):
        return None
    if not isinstance(raw, dict):
        raise YamlFormatError("expected a mapping")
    data = YAMLData()
    for k, v in raw.items():
        if k == "version":
            data.version = _yaml_str(v)
        elif k == "isglides":
            data.isglides = _yaml_bool(v)
        elif k == "symbols":
            data.symbols = _seq(v, lambda x: _obj(x, lambda d: (_yaml_str(d.get("symbol")), _yaml_str(d.get("type")))))
        elif k == "replacements":
            data.replacements = _seq(v, lambda x: _obj(x, _replacement))
        elif k == "fallbacks":
            data.fallbacks = _seq(v, lambda x: _obj(x, _replacement))
        elif k == "timings":
            data.timings = _seq(v, lambda x: _obj(x, lambda d: (_yaml_str(d.get("symbol")), _yaml_double(d["value"]) if "value" in d else 0.0)))
        elif k == "diphthongs":
            data.diphthongs = _seq(v, lambda x: _obj(x, lambda d: (_yaml_str(d.get("from")), _yaml_str(d.get("to")))))
        elif k == "vowelsustains":
            data.vowelsustains = _seq(v, lambda x: _obj(x, lambda d: (_yaml_str(d.get("symbol")), _yaml_str(d.get("sustain")),
                                                                     _yaml_double(d["offset"]) if "offset" in d else 0.0)))
        elif k == "entries":
            data.entries = _seq(v, lambda x: _obj(x, lambda d: (_yaml_str(d.get("grapheme")), _seq(d.get("phonemes"), _yaml_str)
                                                                if "phonemes" in d else None)))
    # LoadYamlCached: the raw map's unknown keys (case-insensitively) become ExtensionData
    for k, v in raw.items():
        if str(k).lower() not in _KNOWN_KEYS:
            data.extension_data[k] = v
    return data


def g2p_data_from_raw(raw):
    """G2pDictionaryData.deserialize on an already parsed document (see g2p_dictionary_data.py)."""
    data = G2pDictionaryData()
    if not isinstance(raw, dict):
        return data
    if raw.get("symbols") not in (None, "", "~", "null"):
        data.symbols = [SymbolData(symbol=_gs(s.get("symbol")), type=_gs(s.get("type"))) for s in raw["symbols"]]
    if raw.get("entries") not in (None, "", "~", "null"):
        data.entries = []
        for e in raw["entries"]:
            ph = e.get("phonemes")
            if isinstance(ph, str):
                if ph in ("", "~", "null"):
                    ph = None
                else:
                    raise ValueError(f"phonemes of {e.get('grapheme')} is not a sequence")
            data.entries.append(Entry(grapheme=_gs(e.get("grapheme")), phonemes=None if ph is None else [_gs(p) for p in ph]))
    return data


def _gs(v):
    if v is None or v in ("~", "null", "Null", "NULL"):
        return None
    return v


_RAW_CACHE = {}
_DATA_CACHE = {}
_G2P_CACHE = {}


def load_raw_yaml(path):
    """the parsed document of a yaml file (all scalars strings), cached by path and mtime like YamlCache."""
    full = os.path.abspath(path)
    mtime = os.path.getmtime(full)
    hit = _RAW_CACHE.get(full)
    if hit is not None and hit[0] == mtime:
        return hit[1]
    with open(full, "rb") as f:
        text = f.read().decode("utf-8-sig", errors="replace")
    raw = yaml.load(text, Loader=_YAML_LOADER)
    _RAW_CACHE[full] = (mtime, raw)
    return raw


def read_version_fast_text(text):
    """ReadVersionFast: the first line starting with 'version:' (ignoring case), its value unquoted."""
    for line in re.split(r"\r\n|\r|\n", text):
        t = trim(line)
        if t.lower().startswith("version:"):
            parts = t.split(":", 1)
            if len(parts) > 1:
                return trim(parts[1]).strip("\"'")
    return ""


def read_version_fast(path):
    if not path or not os.path.isfile(path):
        return ""
    try:
        with open(path, "rb") as f:
            return read_version_fast_text(f.read().decode("utf-8-sig", errors="replace"))
    except OSError:
        return ""


def parse_version(s):
    """System.Version.TryParse: 2 to 4 non-negative integer components. -> comparable tuple or None."""
    if s is None:
        return None
    parts = s.strip().split(".")
    if not 2 <= len(parts) <= 4:
        return None
    out = []
    for p in parts:
        p = p.strip()
        if not re.fullmatch(r"\+?[0-9]+", p):
            return None
        v = int(p)
        if v > 2 ** 31 - 1:
            return None
        out.append(v)
    return tuple(out + [-1] * (4 - len(out)))


# ---------------------------------------------------------------------------------------------------------
# the phonemizer
# ---------------------------------------------------------------------------------------------------------

FORCED_ALIAS_SYMBOL = "?"
_GROUP_KEYWORDS = ["vowel", "vowels", "consonant", "consonants", "affricate", "fricative", "aspirate", "semivowel",
                   "liquid", "nasal", "stop", "tap"]


class SyllableBasedPhonemizer(Phonemizer, IG2pSymbols):
    """see the module docstring for the subclassing guide."""

    transition_basic_length_ms = 100  # TransitionBasicLengthMs
    no_gap = True  # NoGap
    enable_phoneme_tokenization = False  # EnablePhonemeTokenization
    yaml_file_name = None  # YamlFileName
    yaml_template = None  # YamlTemplate: a file name under data/syllable_based/, or an absolute path
    yaml_version = None  # YamlVersion

    def __init__(self):
        super().__init__()
        self._dictionaries = {}
        self.error = ""
        self._singer_loaded = False
        self.runtime_glides = set()
        self.enable_glides = True
        self.vowels = []
        self.consonants = []
        self.tails = "-,R".split(",")
        self.affricate = []
        self.fricative = []
        self.aspirate = []
        self.semivowel = []
        self.liquid = []
        self.nasal = []
        self.stop = []
        self.tap = []
        self.dictionary_replacements = {}
        self.phoneme_overrides = {}
        self.yaml_fallbacks = []
        self.cons_exceptions = []
        self.diphthong_tails = {}
        self.diphthong_splits = {}
        self.vowel_sustains = {}  # symbol -> (sustain, offset)
        self.merging_replacements = []
        self.splitting_replacements = []
        self._backup_vowels = None
        self._backup_consonants = None
        self._backup_diphthong_tails = None
        self._backup_diphthong_splits = None
        self._backup_dictionary_replacements = None
        self._backup_vowel_sustains = None

    # ---- abstract / virtual hooks --------------------------------------------------------------------
    def get_vowels(self):
        raise NotImplementedError

    def get_consonants(self):
        raise NotImplementedError("The method or operation is not implemented.")

    def process_syllable(self, syllable):
        raise NotImplementedError

    def process_ending(self, ending):
        raise NotImplementedError

    def get_aliases_fallback(self):
        """simple alias to alias fallback"""
        return None

    def init(self):
        """some custom init, if needed"""

    def get_dictionary_name(self):
        """dictionary name (in the Dictionaries folder). "" with a yaml file name loads the yaml + base g2ps."""
        return None

    def get_base_g2ps(self):
        return []

    @property
    def has_dictionary(self):
        return type(self) in self._dictionaries

    @property
    def dictionary(self):
        return self._dictionaries[type(self)]

    @property
    def is_dictionary_loading(self):
        return self._dictionaries[type(self)] is None

    def glides(self, alias):
        """flag a generated alias as a glide (anchored on the note instead of before it)."""
        self.runtime_glides.add(alias)

    def is_glide(self, alias):
        return alias in self.runtime_glides and self.enable_glides

    def get_dictionary_phonemes_replacement(self):
        return self.dictionary_replacements if self.dictionary_replacements is not None else {}

    # ---- yaml loading ----------------------------------------------------------------------------------
    def plugin_yaml_path(self):
        """Path.Combine(PluginDir, YamlFileName): the shipped template (what openutau writes there)."""
        if not self.yaml_template:
            return None
        path = os.path.join(DATA_DIR, self.yaml_template)  # an absolute yaml_template wins
        return path if os.path.isfile(path) else None

    def _template_text(self):
        path = self.plugin_yaml_path()
        if path is None:
            return None
        with open(path, "rb") as f:
            return f.read().decode("utf-8-sig", errors="replace")

    def _singer_yaml_path(self):
        singer = self.singer
        if singer is None or not getattr(singer, "location", None):
            return None
        return os.path.join(singer.location, self.yaml_file_name)

    def _target_version(self):
        template = self._template_text()
        if template is None:
            return None
        target = read_version_fast_text(template)
        if not target:
            target = self.yaml_version if self.yaml_version is not None else "1.0"
        return target

    def _is_outdated(self, path, target):
        """UpdateYamlIfNeeded's version check for an existing file."""
        current = read_version_fast(path)
        if not current:
            baseline = self.yaml_version if self.yaml_version is not None else "1.0"
            tv, iv = parse_version(target), parse_version(baseline)
            if tv is not None and iv is not None:
                return tv > iv, current
            return bool(target) and target.lower() != baseline.lower(), current
        cv, tv = parse_version(current), parse_version(target)
        if cv is not None and tv is not None:
            return cv < tv, current
        return current.lower() != target.lower(), current

    def load_yaml_raw(self, path):
        """the document openutau reads at `path` after CheckAndUpdateYamls: an outdated singer yaml is migrated
        (MigrateAndWriteYaml) or, if that fails, replaced by the template; warble does both in memory."""
        raw = load_raw_yaml(path)
        if self.yaml_template is None or path == self.plugin_yaml_path():
            return raw
        target = self._target_version()
        outdated, current = self._is_outdated(path, target)
        if not outdated:
            return raw
        migrated = self._migrated_raw(raw, target)
        if migrated is not None:
            return migrated
        return load_raw_yaml(self.plugin_yaml_path())

    def _migrated_raw(self, user_raw, target_version):
        """MigrateAndWriteYaml, as the document it would write."""
        try:
            user = yaml_data_from_raw(user_raw)
            template_raw = load_raw_yaml(self.plugin_yaml_path())
            tmpl = yaml_data_from_raw(template_raw)
        except Exception:  # noqa: BLE001
            return None
        if user is None or tmpl is None:
            return None

        def merge(base, extra, key):
            out = list(base or [])
            for u in extra or []:
                out = [b for b in out if key(b) != key(u)]
                out.append(u)
            return out

        timings = merge(tmpl.timings, user.timings, lambda t: t[0])
        replacements = merge(tmpl.replacements, user.replacements, self._replacement_key)
        fallbacks = merge(tmpl.fallbacks, user.fallbacks, self._replacement_key)
        sustains = merge(tmpl.vowelsustains, user.vowelsustains, lambda s: s[0])
        symbols = merge(tmpl.symbols, user.symbols, lambda s: s[0])

        def rep(r):
            d = {}
            if r.from_ is not None:
                d["from"] = r.from_
            if r.to is not None:
                d["to"] = r.to
            if r.where is not None and r.where != "inside":
                d["where"] = r.where
            return d

        out = {"version": target_version}
        if tmpl.isglides is not None:
            out["isglides"] = "true" if tmpl.isglides else "false"
        if symbols:
            out["symbols"] = [{k: v for k, v in (("symbol", s[0]), ("type", s[1])) if v is not None} for s in symbols]
        if replacements:
            out["replacements"] = [rep(r) for r in replacements]
        if fallbacks:
            out["fallbacks"] = [rep(r) for r in fallbacks]
        if timings:
            out["timings"] = [{"symbol": t[0], "value": repr(t[1])} for t in timings if t[0] is not None] + \
                             [{"value": repr(t[1])} for t in timings if t[0] is None]
        if tmpl.diphthongs:
            out["diphthongs"] = [{k: v for k, v in (("from", d[0]), ("to", d[1])) if v is not None} for d in tmpl.diphthongs]
        if sustains:
            out["vowelsustains"] = [{"symbol": s[0], "sustain": s[1], "offset": repr(s[2])} for s in sustains]
        if tmpl.entries:
            out["entries"] = [{"grapheme": e[0], "phonemes": e[1]} for e in tmpl.entries]
        for k, v in user.extension_data.items():
            out[k] = v
        return out

    @staticmethod
    def _replacement_key(r):
        if r is None:
            return ""
        return ",".join(r.from_list) + ":" + cs_str(r.where)

    def _cache_key(self, path):
        full = os.path.abspath(path)
        return full, os.path.getmtime(full), self.yaml_template, self.yaml_version

    def _load_yaml_data(self, path):
        """LoadYamlCached: the file as YAMLData, or None if it doesn't deserialize."""
        key = self._cache_key(path)
        if key in _DATA_CACHE:
            return _DATA_CACHE[key]
        try:
            data = yaml_data_from_raw(self.load_yaml_raw(path))
        except Exception:  # noqa: BLE001 - Log.Error("Failed to deserialize YAML")
            data = None
        _DATA_CACHE[key] = data
        return data

    def _g2p_dictionary_from(self, path):
        """G2pDictionary.NewBuilder().Load(File.ReadAllText(path)).Build() (built once per file version; queries
        return copies, so instances can share it)."""
        key = self._cache_key(path)
        hit = _G2P_CACHE.get(key)
        if hit is None:
            hit = G2pDictionary.new_builder().load(g2p_data_from_raw(self.load_yaml_raw(path))).build()
            _G2P_CACHE[key] = hit
        return hit

    # ---- lifecycle ---------------------------------------------------------------------------------------
    def set_singer(self, singer):
        if self._singer_loaded and self.singer is singer:
            return
        self.singer = singer
        self._dictionaries.clear()

        if self.singer is None:
            self._singer_loaded = False
            return

        if not self.yaml_file_name:
            self.vowels = self._backup_vowels if self._backup_vowels is not None else self.get_vowels()
            self.consonants = self._backup_consonants if self._backup_consonants is not None else self.get_consonants()
            if self._backup_dictionary_replacements is not None:
                self.dictionary_replacements.clear()
                for k, v in self._backup_dictionary_replacements.items():
                    self.dictionary_replacements[k] = v
            if not self.has_dictionary:
                self.read_dictionary_and_init()
            else:
                self.init()
            self._singer_loaded = True
            return

        # file paths
        global_file = self.plugin_yaml_path()
        singer_file = self._singer_yaml_path()

        # add to parsing list (Global first, Singer second)
        files_to_parse = []
        if global_file is not None and os.path.isfile(global_file):
            files_to_parse.append(global_file)
        if singer_file and os.path.isfile(singer_file):
            files_to_parse.append(singer_file)

        # backups of hardcoded defaults
        if self._backup_vowels is None:
            v = self.get_vowels()
            self._backup_vowels = v if v is not None else []
        if self._backup_consonants is None:
            c = self.get_consonants()
            self._backup_consonants = c if c is not None else []
        if self._backup_dictionary_replacements is None:
            self._backup_dictionary_replacements = dict(self.dictionary_replacements)
        if self._backup_diphthong_tails is None:
            self._backup_diphthong_tails = dict(self.diphthong_tails)
        if self._backup_diphthong_splits is None:
            self._backup_diphthong_splits = dict(self.diphthong_splits)

        # reset live arrays/lists back to defaults before stacking
        self.vowels = self._backup_vowels
        self.consonants = self._backup_consonants
        self.tails = "-".split(",")
        self.fricative = []
        self.aspirate = []
        self.semivowel = []
        self.liquid = []
        self.nasal = []
        self.stop = []
        self.tap = []
        self.affricate = []

        self.dictionary_replacements.clear()
        for k, v in self._backup_dictionary_replacements.items():
            self.dictionary_replacements[k] = v
        self.diphthong_tails.clear()
        for k, v in self._backup_diphthong_tails.items():
            self.diphthong_tails[k] = v
        self.diphthong_splits.clear()
        for k, v in self._backup_diphthong_splits.items():
            self.diphthong_splits[k] = v

        self.merging_replacements.clear()
        self.splitting_replacements.clear()
        self.yaml_fallbacks.clear()
        self.phoneme_overrides.clear()
        if self._backup_vowel_sustains is None:
            self._backup_vowel_sustains = dict(self.vowel_sustains)
        self.vowel_sustains.clear()
        for k, v in self._backup_vowel_sustains.items():
            self.vowel_sustains[k] = v

        # parse the files sequentially (singer configs overwrite global configs)
        for file in files_to_parse:
            try:
                data = self._load_yaml_data(file)
                if data is None:
                    continue
                self._apply_yaml(data)
            except Exception:  # noqa: BLE001 - Log.Error($"Failed to parse {file}")
                pass

        if not self.has_dictionary:
            self.read_dictionary_and_init()
        else:
            self.init()
        self._singer_loaded = True

    def _apply_yaml(self, data):
        if data.symbols is not None and len(data.symbols) > 0:
            lookup = {}
            for sym, typ in data.symbols:
                if sym and typ:
                    lookup.setdefault(typ.lower(), []).append(sym)

            def grp(name):
                return list(lookup.get(name, []))

            yaml_vowels = grp("vowel") + grp("diphthong")
            self.vowels = distinct(yaml_vowels + list(self.vowels))
            self.tails = distinct(grp("tail") + list(self.tails))
            y_fricative = grp("fricative")
            self.fricative = distinct(y_fricative + self.fricative)
            y_aspirate = grp("aspirate")
            self.aspirate = distinct(y_aspirate + self.aspirate)
            y_semivowel = grp("semivowel")
            self.semivowel = distinct(y_semivowel + self.semivowel)
            y_liquid = grp("liquid")
            self.liquid = distinct(y_liquid + self.liquid)
            y_nasal = grp("nasal")
            self.nasal = distinct(y_nasal + self.nasal)
            y_stop = grp("stop")
            self.stop = distinct(y_stop + self.stop)
            y_tap = grp("tap")
            self.tap = distinct(y_tap + self.tap)
            y_affricate = grp("affricate")
            self.affricate = distinct(y_affricate + self.affricate)
            yaml_consonants = y_fricative + y_aspirate + y_semivowel + y_liquid + y_nasal + y_stop + y_tap + y_affricate
            self.consonants = distinct(yaml_consonants + list(self.consonants))

            # DIPHTHONG AUTO-TAIL DETECTION
            for d in distinct(grp("diphthong")):
                custom = None
                if data.diphthongs is not None:
                    custom = next((dt for dt in data.diphthongs if dt[0] == d), None)
                if custom is not None and custom[1]:
                    self.diphthong_tails[d] = custom[1]
                else:
                    self.diphthong_tails[d] = d + "-"

        if data.isglides is not None:
            self.enable_glides = data.isglides

        # OVERRIDES & DICTIONARIES (singer keys overwrite global keys)
        if data.timings is not None:
            for sym, value in data.timings:
                if sym is None:
                    raise TypeError("Value cannot be null. (Parameter 'key')")
                self.phoneme_overrides[sym] = value

        if data.replacements is not None:
            local_merge = []
            local_split = []

            def from_key(f):
                if isinstance(f, str):
                    return f
                if isinstance(f, (list, dict)):
                    return ",".join("" if x is None else _obj_to_string(x) for x in f)
                return ""

            for raw_rep in data.replacements:
                if raw_rep is None:
                    raise TypeError("Object reference not set to an instance of an object.")
                fk = from_key(raw_rep.from_)
                self.merging_replacements[:] = [r for r in self.merging_replacements if from_key(r.from_) != fk]
                self.splitting_replacements[:] = [r for r in self.splitting_replacements if from_key(r.from_) != fk]
                if isinstance(raw_rep.from_, str):
                    self.dictionary_replacements.pop(raw_rep.from_, None)
                fl = raw_rep.from_list
                tl = raw_rep.to_list
                parsed_from = fl[0] if len(fl) == 1 else list(fl)
                parsed_to = tl[0] if len(tl) == 1 else list(tl)
                clean = Replacement(parsed_from, parsed_to, raw_rep.where)
                if isinstance(parsed_from, str):
                    local_split.append(clean)
                else:
                    local_merge.append(clean)
            self.merging_replacements[0:0] = local_merge
            self.splitting_replacements[0:0] = local_split

        if data.fallbacks is not None:
            local_fallbacks = []
            for df in data.fallbacks:
                if df is None:
                    raise TypeError("Object reference not set to an instance of an object.")
                if len(df.from_list) > 0 and len(df.to_list) > 0:
                    local_fallbacks.append(df)
            self.yaml_fallbacks[0:0] = local_fallbacks

        if data.diphthongs is not None:
            for d in data.diphthongs:
                if d[0] and d[1]:
                    self.diphthong_tails[d[0]] = d[1]

        if data.vowelsustains is not None:
            for sym, sustain, offset in data.vowelsustains:
                if sym and sustain:
                    self.vowel_sustains[sym] = (sustain, offset)

    def read_dictionary_and_init(self):
        dictionary_name = self.get_dictionary_name()
        if dictionary_name is None and not self.yaml_file_name:
            return
        try:
            self._read_dictionary(dictionary_name)
            self.init()
        except Exception:  # noqa: BLE001 - Log.Error($"Failed to read dictionary {dictionaryName}")
            pass

    def _read_dictionary(self, dictionary_name):
        try:
            phoneme_symbols = {}
            for vowel in self.get_vowels():
                phoneme_symbols[vowel] = True
            for consonant in (self.consonants if len(self.consonants) > 0 else self.get_consonants()):
                phoneme_symbols[consonant] = False
            child = self.get_dictionary_phonemes_replacement()
            safe = dict(child) if child is not None else {}
            self._dictionaries[type(self)] = G2pRemapper(self.load_base_dictionary(), phoneme_symbols, safe)
        except Exception:  # noqa: BLE001
            pass

    def load_base_dictionary(self):
        g2ps = []
        if self.yaml_file_name:
            path = self.plugin_yaml_path()
            # Load dictionary from Singer Folder (Highest Priority)
            if self.singer is not None:
                file = self._singer_yaml_path()
                if file and os.path.isfile(file):
                    try:
                        g2ps.append(self._g2p_dictionary_from(file))
                    except Exception:  # noqa: BLE001 - Log.Error(e, $"Failed to load {file}")
                        pass
            # Load dictionary from Plugin Folder (Fallback Priority)
            if path is not None and os.path.isfile(path):
                try:
                    g2ps.append(self._g2p_dictionary_from(path))
                except Exception:  # noqa: BLE001
                    pass
        else:
            dictionary_name = self.get_dictionary_name()
            if dictionary_name:
                filename = os.path.join(self.dictionaries_path(), dictionary_name)
                if os.path.isfile(filename):
                    with open(filename, "rb") as f:
                        text = f.read().decode("utf-8-sig", errors="replace")
                    builder = G2pDictionary.new_builder()
                    for vowel in self.get_vowels():
                        builder.add_symbol(vowel, True)
                    for consonant in self.get_consonants():
                        builder.add_symbol(consonant, False)
                    builder.add_entry("a", ["a"])
                    self.parse_dictionary(text, builder)
                    g2ps.append(builder.build())
        child = self.get_base_g2ps()
        if child:
            g2ps.extend(child)
        return G2pFallbacks(g2ps)

    def parse_dictionary(self, dictionary_text, builder):
        """cmudict-like text: phonemes split by spaces, word and phonemes split by two spaces."""
        replacements = self.get_dictionary_phonemes_replacement()
        for line in re.split(r"\r\n|\n", dictionary_text):
            if not line:
                continue
            if line.startswith(";;;"):
                continue
            parts = trim(line).split("  ")
            if len(parts) != 2:
                continue
            key = parts[0]
            values = [replacements[n] if replacements is not None and n in replacements else n
                      for n in self.get_dictionary_word_phonemes(parts[1])]
            builder.add_entry(key, values)

    # ---- processing --------------------------------------------------------------------------------------
    def process(self, notes, prev, next, prev_neighbour, next_neighbour, prev_neighbours):
        self.error = ""
        if self.singer is None:
            return self.make_simple_result("")
        main_note = notes[0]
        if main_note.lyric.startswith(FORCED_ALIAS_SYMBOL):
            return self.make_simple_result(main_note.lyric[1:])
        if self.has_dictionary and self.is_dictionary_loading:
            return self.make_simple_result("")

        self.runtime_glides.clear()

        # lookahead to next ending if available
        next_ending = self.make_ending([next_neighbour]) if next_neighbour is not None else None
        syllables = self.make_syllables(notes, self.make_ending(prev_neighbours), next_ending)
        if syllables is None:
            return self._handle_error()

        predicted_bases = [None] * len(syllables)
        for i in range(len(syllables)):
            mod = self.apply_boundary_replacements_syllable(syllables[i])
            if mod.v in self.tails:
                predicted_bases[i] = mod.v
            else:
                temp = self.process_syllable(mod.copy())
                lastp = temp[-1] if temp else None
                predicted_bases[i] = lastp if lastp is not None else mod.v

        all_symbols = []
        buckets = []  # (symbols, duration, position, is_ending, tone, vowel)
        running_prev_base = ""
        for i in range(len(syllables)):
            syllable = syllables[i].copy()
            syllable.prev_base_phoneme_ = running_prev_base
            syllable.next_base_phoneme_ = predicted_bases[i + 1] if i + 1 < len(syllables) else ""

            is_slur = i < len(notes) and self.is_syllable_vowel_extension_note(notes[i])
            # a slur on the same vowel bypasses boundary replacements
            modified = syllable if (is_slur and syllable.prev_v == syllable.v) else self.apply_boundary_replacements_syllable(syllable)

            if modified.v in self.tails:
                ending = Ending(prev_v=modified.prev_v, cc=modified.cc, tail=modified.v, position=modified.position,
                                duration=modified.duration, tone=modified.tone, attr=modified.attr)
                ending_phonemes = self.process_ending(ending)
                if ending_phonemes:
                    buckets.append((ending_phonemes, modified.duration, modified.position, False, modified.tone, ""))
                    all_symbols.extend(ending_phonemes)
                running_prev_base = modified.v
                continue

            syllable_phonemes = self.process_syllable(modified.copy())
            if syllable_phonemes:
                buckets.append((syllable_phonemes, modified.duration, modified.position, False, modified.tone, modified.v))
                all_symbols.extend(syllable_phonemes)
                lp = syllable_phonemes[-1]
                running_prev_base = lp if lp is not None else ""

        if next_neighbour is None:
            try_ending = self.make_ending(notes)
            if try_ending is not None:
                ending = try_ending
                modified_ending = self.apply_boundary_replacements_ending(ending)
                ending_phonemes = self.process_ending(modified_ending.copy())
                if ending_phonemes:
                    buckets.append((ending_phonemes, modified_ending.duration, modified_ending.position, True, ending.tone, ""))
                    all_symbols.extend(ending_phonemes)

        working = [copy_attr(a) for a in main_note.phoneme_attributes] if main_note.phoneme_attributes is not None else []
        self.sync_attributes(notes, all_symbols, 0, working)

        phonemes = []
        global_index = 0
        for symbols, duration, position, is_ending, tone, vowel in buckets:
            made = [p for p in self._make_phonemes(symbols, duration, position, is_ending, tone, list(working), global_index)
                    if p.phoneme is not None]
            count = len(made)
            if not is_ending and made:
                base = made[-1]
                base_alias = base.phoneme or ""
                sustain = self.vowel_sustains.get(base_alias)
                if sustain is None and vowel:
                    sustain = self.vowel_sustains.get(vowel)
                if sustain is not None:
                    mapped_sustain = self.validate_alias(sustain[0], tone)
                    if self.has_oto(mapped_sustain, tone) or self.has_oto(sustain[0], tone):
                        offset_ticks = self.ms_to_tick(self.get_transition_basic_length_ms_by_constant() * sustain[1])
                        made.append(Phoneme(sustain[0], base.position + offset_ticks, global_index + count))
                        count += 1
            phonemes.extend(made)
            global_index += count

        for i, p in enumerate(phonemes):
            p.index = i

        return self.assign_all_affixes(list(phonemes), notes, prev_neighbours, working)

    def assign_all_affixes(self, phonemes, notes, prevs, dynamic_attributes=None):
        note_index = 0
        for i in range(len(phonemes)):
            if dynamic_attributes is not None:
                attr = find_attr(dynamic_attributes, i)
            else:
                attr = find_attr(notes[0].phoneme_attributes, i)
            phoneme = phonemes[i]

            alt_value = attr.alternate if attr.alternate is not None else self.get_parent_alternate()
            alt = None if alt_value is None else str(alt_value)
            if not alt and phoneme.expressions is not None:
                alt_expr = next((e for e in phoneme.expressions if e.abbr == "alt"), None)
                if alt_expr is not None and alt_expr.abbr == "alt" and alt_expr.value > 0:
                    alt_value = int(alt_expr.value)
                    alt = str(alt_value)
            if alt is None:
                alt = ""

            color = attr.voice_color if attr.voice_color is not None else self.get_parent_voice_color()
            tone_shift = attr.tone_shift if attr.tone_shift is not None else self.get_parent_tone_shift()

            while note_index < len(notes) - 1 and notes[note_index].position - notes[0].position < phoneme.position:
                note_index += 1

            note_start = notes[note_index].position - notes[0].position
            if phoneme.position < note_start:
                if note_index > 0:
                    tone = notes[note_index - 1].tone
                elif prevs is not None and len(prevs) > 0:
                    tone = prevs[-1].tone
                else:
                    tone = notes[note_index].tone
            else:
                tone = notes[note_index].tone

            validated = phoneme.phoneme
            if validated is not None:
                validated = self.validate_alias(validated, tone + tone_shift)
                mapped = self.map_phoneme(validated, tone + tone_shift, color, alt, self.singer)
                if alt and alt != "0" and mapped == validated:
                    alt_oto = self.singer.try_get_mapped_oto(f"{validated}{alt}", tone + tone_shift, color)
                    if alt_oto is not None:
                        mapped = alt_oto.alias
                phoneme.phoneme = mapped
                if alt_value is not None and alt_value > 0:
                    exprs = list(phoneme.expressions) if phoneme.expressions is not None else []
                    exprs = [e for e in exprs if e.abbr != "alt"]
                    exprs.append(PhonemeExpression("alt", alt_value))
                    phoneme.expressions = exprs
            else:
                phoneme.phoneme = None
                phoneme.position = 0
            phonemes[i] = phoneme
        return list(phonemes)

    def _handle_error(self):
        return [Phoneme(self.error)]

    # ---- symbols -----------------------------------------------------------------------------------------
    def tokenize_phonemes(self, raw):
        """greedy tokenization: longest known vowel/consonant/tail first, else one character."""
        tokens = []
        if not raw:
            return tokens
        known_vowels = self.get_vowels() or []
        if self.consonants is not None and len(self.consonants) > 0:
            known_consonants = self.consonants
        else:
            known_consonants = self.get_consonants() or []
        all_known = distinct([s for s in list(known_vowels) + list(known_consonants) + list(self.tails or []) if s])
        all_known = sorted(all_known, key=len, reverse=True)
        i = 0
        while i < len(raw):
            matched = False
            for symbol in all_known:
                if raw.startswith(symbol, i):
                    tokens.append(symbol)
                    i += len(symbol)
                    matched = True
                    break
            if not matched:
                tokens.append(raw[i])
                i += 1
        return tokens

    def _get_symbols_raw(self, lyrics):
        if not lyrics:
            return []
        if not self.enable_phoneme_tokenization:
            return [s for s in lyrics.split(" ") if s]
        if " " in lyrics:
            out = []
            for part in [s for s in lyrics.split(" ") if s]:
                out.extend(self.tokenize_phonemes(part))
            return out
        return self.tokenize_phonemes(lyrics)

    def get_symbols(self, note):
        """the symbols of a note: a tail, the phonetic hint, or the dictionary (None if a word is not found)."""
        if note.lyric in self.tails:
            return [note.lyric]
        if self.has_dictionary:
            if note.phonetic_hint:
                return self._get_symbols_raw(note.phonetic_hint)
            result = []
            for subword in [s for s in re.split(r"[ _]", trim(note.lyric)) if s]:
                sub = self.dictionary.query(subword)
                if sub is None:
                    sub = self.dictionary.query(to_lower_invariant(subword))
                if sub is None:
                    sub = self.handle_word_not_found(note)
                    if sub is None:
                        return None
                else:
                    for i in range(len(sub)):
                        if sub[i] in self.dictionary_replacements:
                            sub[i] = self.dictionary_replacements[sub[i]]
                result.extend(sub)
            return result
        return self._get_symbols_raw(note.lyric)

    def make_syllables(self, input_notes, prev_ending, next_ending=None):
        """separates symbols into syllables, without an ending."""
        symbols, vowel_ids, notes = self._get_symbols_and_vowels(input_notes)
        if symbols is None or vowel_ids is None or notes is None:
            return None
        first_vowel_id = vowel_ids[0]
        if len(notes) < len(vowel_ids):
            self.error = f"Not enough extension notes, {len(vowel_ids) - len(notes)} more expected"
            return None

        syllables = [None] * len(vowel_ids)
        if prev_ending is not None:
            beginning_cc = list(prev_ending.cc) + take(symbols, first_vowel_id)
            syllables[0] = Syllable(prev_v=prev_ending.prev_v, cc=beginning_cc, v=at(symbols, first_vowel_id), tone=prev_ending.tone,
                                    attr=prev_ending.attr, duration=prev_ending.duration, position=0, vowel_tone=notes[0].tone,
                                    vowel_attr=notes[0].phoneme_attributes, prev_word_consonants_count=len(prev_ending.cc))
        else:
            syllables[0] = Syllable(prev_v="", cc=take(symbols, first_vowel_id), v=at(symbols, first_vowel_id), tone=notes[0].tone,
                                    attr=notes[0].phoneme_attributes, duration=-1, position=0, vowel_tone=notes[0].tone,
                                    vowel_attr=notes[0].phoneme_attributes)

        note_i = 1
        ccs = []
        position = 0
        last_symbol_i = first_vowel_id + 1
        while last_symbol_i < len(symbols) and note_i < len(notes):
            if last_symbol_i not in vowel_ids:
                ccs.append(symbols[last_symbol_i])
            else:
                position += notes[note_i - 1].duration
                syllables[note_i] = Syllable(prev_v=syllables[note_i - 1].v, cc=list(ccs), v=symbols[last_symbol_i],
                                             tone=notes[note_i - 1].tone, attr=notes[note_i - 1].phoneme_attributes,
                                             duration=notes[note_i - 1].duration, position=position, vowel_tone=notes[note_i].tone,
                                             vowel_attr=notes[note_i].phoneme_attributes, can_alias_be_extended=True)
                ccs = []
                note_i += 1
            last_symbol_i += 1

        for i in range(len(syllables)):
            if i < len(syllables) - 1:
                syllables[i].next_v = syllables[i + 1].v
                syllables[i].next_cc_ = syllables[i + 1].cc if syllables[i + 1].cc is not None else []
            elif next_ending is not None:
                syllables[i].next_v = next_ending.prev_v
                syllables[i].next_cc_ = next_ending.cc if next_ending.cc is not None else []
            else:
                syllables[i].next_v = ""
                syllables[i].next_cc_ = []
        return syllables

    def make_ending(self, input_notes):
        """extracts the word ending"""
        if input_notes is None or len(input_notes) == 0 or input_notes[0].lyric.startswith(FORCED_ALIAS_SYMBOL):
            return None
        symbols, vowel_ids, notes = self._get_symbols_and_vowels(input_notes)
        if symbols is None or vowel_ids is None or notes is None:
            return None
        return Ending(prev_v=at(symbols, vowel_ids[-1]), cc=skip(symbols, vowel_ids[-1] + 1), tone=notes[-1].tone,
                      attr=notes[-1].phoneme_attributes, duration=sum(n.duration for n in skip(notes, len(vowel_ids) - 1)),
                      position=sum(n.duration for n in notes))

    def _get_symbols_and_vowels(self, notes):
        main_note = notes[0]
        symbols = self.get_symbols(main_note)
        if symbols is None:
            return None, None, None
        if len(symbols) == 0:
            symbols = [""]
        symbols = list(self.apply_replacements(list(symbols), False))
        symbols = self._apply_extensions(symbols, notes)
        vowel_ids = self._extract_vowels(symbols)
        if len(vowel_ids) == 0:
            vowel_ids.append(len(symbols) - 1)
        if len(notes) < len(vowel_ids):
            notes = self.handle_not_enough_notes(notes, vowel_ids)
        return symbols, vowel_ids, notes

    def handle_not_enough_notes(self, notes, vowel_ids):
        """more syllables than notes: split the last note evenly (in 15-tick steps)."""
        from .api import Note
        new_notes = list(notes[:-1])
        last_note = notes[-1]
        position = last_note.position
        notes_to_split = len(vowel_ids) - len(new_notes)
        duration = cs_div(cs_div(last_note.duration, notes_to_split), 15) * 15
        for i in range(notes_to_split):
            final = duration if i != notes_to_split - 1 else last_note.duration - duration * (notes_to_split - 1)
            new_notes.append(Note(lyric=None, tone=last_note.tone, position=position, duration=final,
                                  phoneme_attributes=last_note.phoneme_attributes))
            position += final
        return new_notes

    def handle_word_not_found(self, note):
        """override to convert unknown words; the base reports the error and gives up."""
        attr = find_attr(note.phoneme_attributes, 0) if note.phoneme_attributes is not None else PhonemeAttributes()
        alt_v = attr.alternate if attr.alternate is not None else self.get_parent_alternate()
        alt = "" if alt_v is None else str(alt_v)
        color = attr.voice_color if attr.voice_color is not None else self.get_parent_voice_color()
        tone_shift = attr.tone_shift if attr.tone_shift is not None else self.get_parent_tone_shift()
        mpdlyric = self.map_phoneme(note.lyric, note.tone + tone_shift, color, alt, self.singer)
        if self.has_oto(mpdlyric, note.tone):
            self.error = mpdlyric
        else:
            self.error = "word not found"
        return None

    @staticmethod
    def is_syllable_vowel_extension_note(note):
        return note.lyric.startswith("+~") or note.lyric.startswith("+*")

    def get_dictionary_word_phonemes(self, phonemes_string):
        return phonemes_string.split(" ")

    def replace_phoneme(self, phoneme, tone=0):
        if not phoneme:
            return ""
        return self.dictionary_replacements.get(phoneme, phoneme)

    def _apply_extensions(self, symbols, notes):
        new_symbols = []
        vowel_ids = self._extract_vowels(symbols)
        if len(vowel_ids) == 0:
            # no syllables or all consonants, the last phoneme will be interpreted as vowel
            vowel_ids.append(len(symbols) - 1)
        last_vowel_i = 0
        new_symbols.extend(take(symbols, vowel_ids[last_vowel_i] + 1))
        i = 1
        while i < len(notes) and last_vowel_i + 1 < len(vowel_ids):
            if not self.is_syllable_vowel_extension_note(notes[i]):
                prev_vowel = vowel_ids[last_vowel_i]
                last_vowel_i += 1
                vowel = vowel_ids[last_vowel_i]
                new_symbols.extend(take(skip(symbols, prev_vowel + 1), vowel - prev_vowel))
            else:
                new_symbols.append(at(symbols, vowel_ids[last_vowel_i]))
            i += 1
        new_symbols.extend(skip(symbols, vowel_ids[last_vowel_i] + 1))
        return new_symbols

    def _extract_vowels(self, symbols):
        vowels = self.get_vowels()
        return [i for i, s in enumerate(symbols) if s in vowels]

    # ---- validation and fallbacks ------------------------------------------------------------------------
    def get_hardcoded_fallback(self, alias, tone, suppressed_tokens):
        """the subclass's own fallbacks; must leave tokens in suppressed_tokens alone."""
        return None

    def validate_alias(self, alias, tone=0):
        """an alias the bank has: yaml fallbacks first ({from: x, to: x} suppresses fallbacks for x), then
        get_hardcoded_fallback, then get_aliases_fallback."""
        if not alias:
            return alias
        if self.singer is None:
            return alias
        if self.has_oto(alias, tone):
            return alias

        single_rules = sorted([r for r in self.yaml_fallbacks if len(r.from_list) == 1], key=lambda r: len(r.from_list[0]), reverse=True)
        suppressed = set()
        has_custom_override = False
        for rule in single_rules:
            from_token = rule.from_list[0].strip("()")
            if from_token in alias:
                if len(rule.to_list) == 1 and rule.to_list[0] == from_token:
                    suppressed.add(from_token)
                elif len(rule.to_list) > 0:
                    has_custom_override = True

        # direct YAML fallback substitution
        for rule in single_rules:
            from_str = rule.from_list[0].strip("()")
            if from_str in suppressed:
                continue
            if from_str in alias:
                for target in rule.to_list:
                    candidate = cs_replace(alias, from_str, target)
                    if self.has_oto(candidate, tone):
                        return candidate

        # cascaded YAML fallback
        cascaded = alias
        changed = False
        for rule in single_rules:
            from_str = rule.from_list[0].strip("()")
            if from_str in suppressed:
                continue
            if from_str in cascaded:
                for target in rule.to_list:
                    candidate = cs_replace(cascaded, from_str, target)
                    if self.has_oto(candidate, tone):
                        return candidate
                if len(rule.to_list) > 0:
                    cascaded = cs_replace(cascaded, from_str, rule.to_list[0])
                    changed = True

        if changed and self.has_oto(cascaded, tone):
            return cascaded

        if len(suppressed) > 0 and not has_custom_override:
            if any(t in alias for t in suppressed):
                return alias

        child = self.get_hardcoded_fallback(alias, tone, suppressed)
        if child and child != alias:
            if self.has_oto(child, tone):
                return child

        legacy = self.get_aliases_fallback()
        if legacy is not None and alias in legacy:
            if not any(t in alias for t in suppressed):
                if self.has_oto(legacy[alias], tone):
                    return legacy[alias]

        return cascaded if changed else alias

    # ---- timing ------------------------------------------------------------------------------------------
    def get_transition_basic_length_ms(self, alias=""):
        """GetTransitionBasicLengthMs(string alias = ""): basic transition length before tempo/note scaling."""
        return self.get_transition_basic_length_ms_by_constant()

    def get_transition_basic_length_ms_with_attr(self, alias, tone, attr):
        """GetTransitionBasicLengthMs(string alias, int tone, PhonemeAttributes attr): what MakePhonemes uses."""
        return self.get_transition_basic_length_ms(alias)

    def get_transition_basic_length_ms_by_constant(self):
        return self.transition_basic_length_ms * self.get_tempo_note_length_factor()

    def get_transition_multiplier(self, alias):
        if alias is not None and self.phoneme_overrides is not None and alias in self.phoneme_overrides:
            return self.phoneme_overrides[alias]
        return 1.0

    def get_transition_basic_length_ms_by_oto(self, alias, tone=0, attr=None):
        """the mapped oto's preutterance (plus a negative overlap)."""
        if attr is None:
            attr = PhonemeAttributes()
        if not alias:
            return self.get_transition_basic_length_ms_by_constant()
        color = attr.voice_color if attr.voice_color is not None else ""
        alt = str(attr.alternate) if attr.alternate is not None else ""
        tone_shift = attr.tone_shift if attr.tone_shift is not None else 0
        validated = self.validate_alias(alias, tone + tone_shift)
        mapped = self.map_phoneme(validated, tone + tone_shift, color, alt, self.singer)
        if alt and alt != "0" and mapped == validated:
            alt_oto = self.singer.try_get_mapped_oto(f"{validated}{alt}", tone + tone_shift, color)
            if alt_oto is not None:
                mapped = alt_oto.alias
        oto = self.singer.try_get_mapped_oto(mapped, tone + tone_shift)
        if oto is not None:
            if oto.overlap < 0:
                return oto.preutter - oto.overlap
            return oto.preutter
        return self.get_transition_basic_length_ms_by_constant()

    def get_tempo_note_length_factor(self):
        """a note length modifier from 1 to 0.3, shorter transitions on high tempo."""
        return (300 - min(max(self.bpm, 90), 300)) / (300 - 90) / 3 + 0.33

    # ---- attributes --------------------------------------------------------------------------------------
    def sync_attributes(self, notes, phoneme_symbols, start_index, attr_list):
        """lets subclasses fill per-phoneme attributes (alts, vel...) before timing."""
        for i in range(len(phoneme_symbols)):
            global_idx = start_index + i
            existing = next((k for k, a in enumerate(attr_list) if a.index == global_idx), -1)
            attr = copy_attr(attr_list[existing]) if existing >= 0 else PhonemeAttributes(index=global_idx)
            attr = self.get_dynamic_phoneme_attributes(phoneme_symbols[i], global_idx, attr, notes)
            if existing >= 0:
                attr_list[existing] = attr
            else:
                attr_list.append(attr)

    def get_dynamic_phoneme_attributes(self, alias, index, current_attr, notes):
        return current_attr

    # ---- helpers -----------------------------------------------------------------------------------------
    def is_short(self, syllable_or_ending):
        if isinstance(syllable_or_ending, Syllable):
            return syllable_or_ending.duration != -1 and self.tick_to_ms(syllable_or_ending.duration) < self.get_transition_basic_length_ms() * 2
        return self.tick_to_ms(syllable_or_ending.duration) < self.get_transition_basic_length_ms() * 2

    def has_oto(self, alias, tone):
        """is there an oto for the alias (mapped through the uncolored subbank, as is, or the '' color)?"""
        singer = self.singer
        if singer is None or not alias:
            return False
        if singer.try_get_mapped_oto(alias, tone) is not None:
            return True
        if singer.try_get_oto(alias) is not None:
            return True
        if singer.try_get_mapped_oto(alias, tone, "") is not None:
            return True
        return False

    def try_add_phoneme(self, source_phonemes, tone, *target_phonemes):
        """TryAddPhoneme(list, tone, params aliases) / TryAddPhoneme(list, tone, bool isGlide, params aliases):
        adds the first alias the bank has."""
        is_glide = False
        if target_phonemes and isinstance(target_phonemes[0], bool):
            is_glide = target_phonemes[0]
            target_phonemes = target_phonemes[1:]
        for phoneme in target_phonemes:
            if self.has_oto(phoneme, tone):
                source_phonemes.append(phoneme)
                if is_glide:
                    self.glides(phoneme)
                return True
        return False

    def can_make_alias_extension(self, syllable):
        """if true, the base phoneme may be None so the previous alias is extended."""
        return syllable.can_alias_be_extended and syllable.prev_v == syllable.v and len(syllable.cc) == 0

    def are_tones_from_the_same_subbank(self, tone1, tone2):
        subbanks = self.singer.subbanks
        if len(subbanks) == 1:
            return True
        if tone1 == tone2:
            return True
        for sb in subbanks:
            tones = sb["tones"]
            if tone1 in tones and tone2 in tones:
                return True
            if (tone1 in tones) != (tone2 in tones):
                return False
        return True

    # ---- yaml replacements -------------------------------------------------------------------------------
    def is_group_keyword(self, rule_phoneme):
        if not rule_phoneme:
            return False
        clean = rule_phoneme.strip("()")
        base_group = to_lower_invariant(re.split(r"[!=&]", clean)[0])
        return base_group in _GROUP_KEYWORDS

    def is_group_match(self, rule_phoneme, actual_phoneme):
        if not rule_phoneme or not actual_phoneme:
            return False
        clean = rule_phoneme.strip("()")
        base_group = to_lower_invariant(re.split(r"[!=&]", clean)[0])

        if "&" in clean:
            added = re.split(r"[!=]", clean[clean.index("&") + 1:])[0]
            for inc in added.split(","):
                t = trim(inc)
                if (self.is_group_match(t, actual_phoneme) if self.is_group_keyword(t) else t == actual_phoneme):
                    return True

        in_base = False
        if base_group in ("vowel", "vowels"):
            in_base = actual_phoneme in self.get_vowels()
        elif base_group in ("consonant", "consonants"):
            cons = self.consonants if len(self.consonants) > 0 else self.get_consonants()
            in_base = cons is not None and actual_phoneme in cons
        elif base_group == "affricate":
            in_base = actual_phoneme in self.affricate
        elif base_group == "fricative":
            in_base = actual_phoneme in self.fricative
        elif base_group == "aspirate":
            in_base = actual_phoneme in self.aspirate
        elif base_group == "semivowel":
            in_base = actual_phoneme in self.semivowel
        elif base_group == "liquid":
            in_base = actual_phoneme in self.liquid
        elif base_group == "nasal":
            in_base = actual_phoneme in self.nasal
        elif base_group == "stop":
            in_base = actual_phoneme in self.stop
        elif base_group == "tap":
            in_base = actual_phoneme in self.tap
        if not in_base:
            return False

        if "!" in clean:
            excluded = re.split(r"[=&]", clean[clean.index("!") + 1:])[0]
            if actual_phoneme in [trim(s) for s in excluded.split(",")]:
                return False
        if "=" in clean:
            restricted = re.split(r"[!&]", clean[clean.index("=") + 1:])[0]
            if actual_phoneme not in [trim(s) for s in restricted.split(",")]:
                return False
        return True

    def _rule_applies(self, r, is_boundary):
        return r.where == "all" or (not is_boundary and r.where == "inside") or (is_boundary and r.where == "boundary")

    def _rebuild(self, to_ph):
        """split a `to` item on '+' and find its first group keyword (the part a capture fills in)."""
        parts = to_ph.split("+")
        clean_parts = [None] * len(parts)
        base_group_to = None
        for k, part in enumerate(parts):
            no_parens = part.strip("()")
            m = re.search(r"[!=&]", no_parens)
            potential = no_parens[:m.start()] if m else no_parens
            if base_group_to is None and self.is_group_keyword(potential):
                base_group_to = potential
                clean_parts[k] = potential
            else:
                clean_parts[k] = no_parens
        return clean_parts, base_group_to

    def apply_replacements(self, input_phonemes, is_boundary):
        """the yaml `replacements` (merging and splitting rules, with group keywords) over a symbol list."""
        if not self.merging_replacements and not self.splitting_replacements:
            return input_phonemes
        final = []
        idx = 0
        valid_rules = [r for r in self.merging_replacements + self.splitting_replacements if self._rule_applies(r, is_boundary)]
        valid_rules = sorted(valid_rules, key=lambda r: (len(r.from_list), sum(len(s) for s in r.from_list)), reverse=True)
        valid_splits = [r for r in self.splitting_replacements if self._rule_applies(r, is_boundary)]
        valid_splits = sorted(valid_splits, key=lambda r: sum(len(s) for s in r.from_list), reverse=True)

        while idx < len(input_phonemes):
            replaced = False
            for rule in valid_rules:
                from_array = rule.from_list
                if from_array and idx + len(from_array) <= len(input_phonemes):
                    match = True
                    captures = {}
                    for j in range(len(from_array)):
                        rule_ph = from_array[j]
                        actual = input_phonemes[idx + j]
                        clean_rule = rule_ph.strip("()")
                        base_rule = re.split(r"[!=&]", clean_rule)[0]
                        if self.is_group_keyword(base_rule):
                            if self.is_group_match(rule_ph, actual):
                                captures.setdefault(base_rule, []).append(actual)
                            else:
                                match = False
                                break
                        elif rule_ph != actual:
                            match = False
                            break
                    if match:
                        to_array = rule.to_list
                        if to_array:
                            capture_indices = {}
                            for to_ph in to_array:
                                clean_parts, base_group_to = self._rebuild(to_ph)
                                if base_group_to is not None and base_group_to in captures and len(captures[base_group_to]) > 0:
                                    c_idx = capture_indices.setdefault(base_group_to, 0)
                                    if c_idx >= len(captures[base_group_to]):
                                        c_idx = len(captures[base_group_to]) - 1
                                    captured = captures[base_group_to][c_idx]
                                    final.append("".join(captured if p == base_group_to else p for p in clean_parts))
                                    capture_indices[base_group_to] += 1
                                else:
                                    final.append("".join(clean_parts))
                        idx += len(from_array)
                        replaced = True
                        break

            if not replaced and valid_splits:
                current = input_phonemes[idx]
                single_replaced = False
                for rule in valid_splits:
                    from_array = rule.from_list
                    if from_array is None or len(from_array) != 1:
                        continue
                    rule_ph = from_array[0]
                    clean_rule = rule_ph.strip("()")
                    base_rule = re.split(r"[!=&]", clean_rule)[0]
                    if self.is_group_match(rule_ph, current) if self.is_group_keyword(base_rule) else rule_ph == current:
                        to_array = rule.to_list
                        if to_array:
                            for to_ph in to_array:
                                clean_parts, base_group_to = self._rebuild(to_ph)
                                if base_group_to is not None:
                                    final.append("".join(current if p == base_group_to else p for p in clean_parts))
                                else:
                                    final.append("".join(clean_parts))
                            single_replaced = True
                            break
                if not single_replaced:
                    final.append(input_phonemes[idx])
                idx += 1
            elif not replaced:
                final.append(input_phonemes[idx])
                idx += 1
        return final

    def apply_boundary_replacements_syllable(self, syllable):
        """the yaml replacements across a syllable boundary: [prevV or "null"] [cc...] [v]. returns a copy."""
        syllable = syllable.copy()
        if not self.merging_replacements and not self.splitting_replacements:
            return syllable
        current = []
        has_prev_v = bool(syllable.prev_v)
        has_v = bool(syllable.v)
        current.append(syllable.prev_v if has_prev_v else "null")
        if syllable.cc is not None:
            current.extend(syllable.cc)
        if has_v:
            current.append(syllable.v)
        is_boundary = (has_prev_v and syllable.position == 0) or not has_prev_v
        final = self.apply_replacements(current, is_boundary)
        new_prev_v = ""
        new_v = ""
        new_cc = []
        if len(final) > 0:
            first = final[0]
            new_prev_v = "" if first == "null" else first
            final.pop(0)
            if has_v and len(final) > 0:
                vowels_list = self.get_vowels()
                v_index = len(final) - 1
                for i in range(len(final) - 1, -1, -1):
                    if final[i] in vowels_list:
                        v_index = i
                        break
                new_v = final[v_index]
                new_cc.extend(final[:v_index])
            else:
                new_cc.extend(final)
        syllable.prev_v = new_prev_v
        syllable.cc = new_cc
        syllable.v = new_v
        return syllable

    def apply_boundary_replacements_ending(self, ending):
        ending = ending.copy()
        if not self.merging_replacements and not self.splitting_replacements:
            return ending
        current = []
        has_prev_v = bool(ending.prev_v)
        current.append(ending.prev_v if has_prev_v else "null")
        if ending.cc is not None:
            current.extend(ending.cc)
        current.append(ending.tail if ending.has_tail else "null")
        final = self.apply_replacements(current, True)
        new_prev_v = ""
        new_tail = ""
        if len(final) > 0:
            new_prev_v = "" if final[0] == "null" else final[0]
            final.pop(0)
        if len(final) > 0:
            new_tail = "" if final[-1] == "null" else final[-1]
            final.pop()
        ending.prev_v = new_prev_v
        ending.cc = list(final)
        ending.tail = new_tail
        return ending

    # ---- making phonemes ---------------------------------------------------------------------------------
    def _make_phonemes(self, phoneme_symbols, container_length, position, is_ending, tone=0, attributes=None, global_start_index=0):
        n = len(phoneme_symbols)
        phonemes = [None] * n
        true_lengths = [0] * n
        for i in range(1, n):
            prev_phoneme_i = n - i
            current_phoneme_i = n - i - 1
            next_global_index = global_start_index + prev_phoneme_i
            next_attr = find_attr(attributes, next_global_index)
            next_alias = phoneme_symbols[prev_phoneme_i]
            current_alias = phoneme_symbols[current_phoneme_i]
            stretch = next_attr.consonant_stretch_ratio if next_attr.consonant_stretch_ratio is not None else 1.0
            override_ratio = self.get_transition_multiplier(current_alias) if current_alias is not None else 1.0
            if override_ratio != 1.0:
                base_length_ms = self.get_transition_basic_length_ms_by_constant()
                stretch *= override_ratio
            else:
                base_length_ms = self.get_transition_basic_length_ms_with_attr(next_alias, tone, next_attr)
            true_lengths[i] = self.ms_to_tick(base_length_ms * stretch)

        # IsGlide
        anchor_i = 0
        if not is_ending and n > 1:
            immediate = n - 2
            if phoneme_symbols[immediate] is not None and self.is_glide(phoneme_symbols[immediate]):
                anchor_i = 1  # anchor at most one glide (the one touching the vowel)

        for i in range(n):
            phoneme_i = n - i - 1
            global_index = global_start_index + phoneme_i
            validated = phoneme_symbols[phoneme_i]
            p_attr = find_attr(attributes, global_index)
            if validated is not None:
                exprs = []
                if p_attr.consonant_stretch_ratio is not None:
                    vel = 100.0 - 100.0 * math.log2(p_attr.consonant_stretch_ratio) if p_attr.consonant_stretch_ratio > 0 else math.inf
                    exprs.append(PhonemeExpression("vel", vel))
                if p_attr.alternate is not None and p_attr.alternate > 0:
                    exprs.append(PhonemeExpression("alt", p_attr.alternate))
                phonemes[phoneme_i] = Phoneme(validated, 0, global_index, None, exprs if exprs else None)
                if i == 0:
                    if is_ending:
                        stretch = p_attr.consonant_stretch_ratio if p_attr.consonant_stretch_ratio is not None else 1.0
                        override_ratio = self.get_transition_multiplier(validated)
                        if override_ratio != 1.0:
                            # YAML override: the multiplier, bypassing NoGap
                            base_length_ms = self.get_transition_basic_length_ms_by_constant()
                            phonemes[phoneme_i].position = self.ms_to_tick(base_length_ms * stretch * override_ratio)
                        else:
                            base_length_ms = self.get_transition_basic_length_ms_by_oto(validated, tone, p_attr)
                            if self.no_gap:
                                # snapped mode: a 50-tick anchor capped at 1/3 of the note
                                phonemes[phoneme_i].position = min(50, cs_div(container_length, 3))
                            else:
                                phonemes[phoneme_i].position = self.ms_to_tick(base_length_ms)
                    else:
                        phonemes[phoneme_i].position = -sum(true_lengths[1:anchor_i + 1])
                else:
                    # VC transitions keep their full stretched length
                    phonemes[phoneme_i].position = true_lengths[i]
            else:
                phonemes[phoneme_i] = Phoneme(None, 0, global_index)

        return self._scale_phonemes(phonemes, position, n - 1, container_length)

    def _scale_phonemes(self, phonemes, start_position, phonemes_count, container_length_tick=-1):
        offset = 0
        length_modifier = 1.0
        if container_length_tick > 0:
            all_transitions = sum(p.position for p in phonemes)
            max_allowed = int(container_length_tick * 0.8)
            if all_transitions > max_allowed:
                length_modifier = max_allowed / all_transitions
        for i in range(len(phonemes) - 1, -1, -1):
            if phonemes[i].phoneme is None:
                continue
            final_length = int(phonemes[i].position * length_modifier)
            phonemes[i].position = start_position - final_length - offset
            offset += final_length
        return [p for p in phonemes if p.phoneme is not None]


def cs_regex_word_boundary_match(alias, symbol):
    """Regex.IsMatch(alias, $@"(?<![a-zA-Z]){Regex.Escape(symbol)}(?![a-zA-Z])") (throws on a null alias)."""
    if alias is None:
        raise TypeError("Value cannot be null. (Parameter 'input')")
    return re.search(r"(?<![a-zA-Z])" + re.escape(symbol) + r"(?![a-zA-Z])", alias) is not None
