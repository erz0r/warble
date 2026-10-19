"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Plugin.Builtin/ChineseCVVPlusPhonemizer.cs"""

import os

import yaml

from .api import Phoneme, alt_str, phonemizer
from .base_chinese import BaseChinesePhonemizer


class ChineseCVVPlusConfigYaml:
    """zhcvvplus.yaml"""

    FIELDS = {
        # name: kind
        "VowelTailPrefix": "str",
        "UseSingleNasalVowel": "bool",
        "UseSingleMultipleVowel": "bool",
        "UseRetan": "bool",
        "SupportedTailBreath": "list",
        "ConsonantDict": "list",
        "SingleVowelDict": "list",
        "NasalVowelDict": "list",
        "MultipleVowelDict": "list",
        "FastTailVowelTimingTick": "int",
        "SingleVowelsReferenceTimimgTick": "int",
        "FastTailVowelDict": "dict",
        "SlowTailVowelDict": "dict",
    }

    def __init__(self):
        self.VowelTailPrefix = "_"  # prefix of affix vowel
        self.UseSingleNasalVowel = False  # use a long nasal vowel without a tail vowel
        self.UseSingleMultipleVowel = False  # use a long multiple vowel without a tail vowel
        self.UseRetan = False  # if true, "- " is added to the first note's lyric
        self.SupportedTailBreath = ["-"]
        self.ConsonantDict = ["zh", "ch", "sh", "b", "p", "m", "f", "d", "t", "n", "l", "z", "c", "s", "r", "j", "q", "x", "g", "k", "h"]
        self.SingleVowelDict = ["a", "o", "e", "i", "u", "v", "er"]
        self.NasalVowelDict = ["an", "en", "ang", "eng", "ong", "ian", "iang", "ing", "iong", "uan", "uen", "un", "uang", "ueng", "van", "vn"]
        self.MultipleVowelDict = ["ai", "ei", "ao", "ou", "ia", "iao", "ie", "iou", "ua", "uo", "uai", "uei", "ui", "ve"]
        self.FastTailVowelTimingTick = 100  # position of fast tail vowel (ticks)
        self.SingleVowelsReferenceTimimgTick = 480
        self.FastTailVowelDict = {"ia": "ia", "ie": "ie", "ua": "ua", "uo": "uo", "ve": "ve"}
        self.SlowTailVowelDict = {
            "ai": "ai", "ei": "ei", "ao": "ao", "ou": "ou", "an": "an", "en": "en", "ang": "ang", "eng": "eng", "ong": "ong",
            "iao": "ao", "iu": "ou", "iou": "ou", "ian": "ian", "in": "in", "iang": "ang", "ing": "ing", "iong": "ong",
            "uai": "ai", "ui": "ei", "uei": "ei", "uan": "an", "un": "uen", "uang": "ang", "ueng": "eng", "van": "en", "vn": "vn",
        }

    @property
    def TailVowels(self):
        out = {}
        for k, v in list(self.FastTailVowelDict.items()) + list(self.SlowTailVowelDict.items()):
            if k in out:
                raise ValueError(f"An item with the same key has already been added. Key: {k}")  # ToDictionary
            out[k] = v
        return out

    @property
    def Consonants(self):
        return sorted(self.ConsonantDict, key=len, reverse=True)  # OrderByDescending is stable, so is sorted

    # ---- a small YamlDotNet-like deserializer: field names as written, unknown keys throw -----------
    @classmethod
    def deserialize(cls, text):
        node = yaml.compose(text)
        if node is None:
            return None  # empty document -> default(T)
        if not isinstance(node, yaml.MappingNode):
            raise ValueError("expected a mapping")
        cfg = cls()
        for knode, vnode in node.value:
            name = knode.value
            kind = cls.FIELDS.get(name)
            if kind is None:
                raise ValueError(f"Property '{name}' not found on type ChineseCVVPlusConfigYaml")
            setattr(cfg, name, cls._convert(vnode, kind))
        return cfg

    @staticmethod
    def _is_null(n):
        return isinstance(n, yaml.ScalarNode) and n.tag == "tag:yaml.org,2002:null" and n.style is None

    @classmethod
    def _convert(cls, n, kind):
        if kind == "str":
            if cls._is_null(n):
                return None
            if not isinstance(n, yaml.ScalarNode):
                raise ValueError("expected scalar")
            return n.value
        if kind == "bool":
            if not isinstance(n, yaml.ScalarNode):
                raise ValueError("expected scalar")
            v = n.value
            if v in ("true", "True", "TRUE", "y", "Y", "yes", "Yes", "YES", "on", "On", "ON"):
                return True
            if v in ("false", "False", "FALSE", "n", "N", "no", "No", "NO", "off", "Off", "OFF"):
                return False
            raise ValueError(f"cannot convert {v!r} to bool")
        if kind == "int":
            if not isinstance(n, yaml.ScalarNode):
                raise ValueError("expected scalar")
            return int(n.value)
        if kind == "list":
            if cls._is_null(n):
                return None
            if not isinstance(n, yaml.SequenceNode):
                raise ValueError("expected sequence")
            return [cls._convert(x, "str") for x in n.value]
        if kind == "dict":
            if cls._is_null(n):
                return None
            if not isinstance(n, yaml.MappingNode):
                raise ValueError("expected mapping")
            out = {}
            for k, v in n.value:
                key = cls._convert(k, "str")
                if key in out:
                    raise ValueError(f"An item with the same key has already been added. Key: {key}")
                out[key] = cls._convert(v, "str")
            return out
        raise ValueError(kind)


def _is_letter(c):
    return c.isalpha()  # char.IsLetter: unicode letter categories


@phonemizer("Chinese CVV Plus Phonemizer", "ZH CVV+", language="ZH", openutau_class="OpenUtau.Plugin.Builtin.ChineseCVVPlusPhonemizer", author="2xxbin")
class ChineseCVVPlusPhonemizer(BaseChinesePhonemizer):
    def __init__(self):
        super().__init__()
        self.config = None

    def set_singer(self, singer):
        if singer is None:
            return
        config_path = os.path.join(singer.location, "zhcvvplus.yaml")
        # openutau writes a default zhcvvplus.yaml into the bank when it is missing (and when it fails to
        # parse); warble never writes into a bank, it just uses the defaults that file would hold.
        if os.path.exists(config_path):
            try:
                with open(config_path, "rb") as f:
                    data = f.read()
                text = data.decode("utf-8-sig", errors="replace")  # File.ReadAllText: utf-8 with bom detection
                self.config = ChineseCVVPlusConfigYaml.deserialize(text)
            except Exception:  # noqa: BLE001 - "Failed to load zhcvvplus.yaml"
                pass
        else:
            self.config = ChineseCVVPlusConfigYaml.deserialize(_default_yaml())
        self.singer = singer
        if self.config is None:
            self.config = ChineseCVVPlusConfigYaml()

    def get_lyric_vowel(self, lyric):
        initial_prefix = ""
        # strip leading non-letters ("- qian")
        if lyric is None:
            raise AttributeError("Object reference not set to an instance of an object.")
        if not lyric:
            raise ValueError("Sequence contains no elements")  # lyric.First()
        while not _is_letter(lyric[0]):
            initial_prefix += lyric[0]
            lyric = lyric[1:]
            if len(lyric) == 0:
                return lyric
        prefix = lyric[:min(2, len(lyric))]
        suffix = lyric[2:] if len(lyric) > 2 else ""
        for consonant in self.config.Consonants:
            if prefix.startswith(consonant):
                prefix = prefix.replace(consonant, "")
        return f"{initial_prefix}{(prefix + suffix).replace('yu', 'v').replace('y', 'i').replace('w', 'u').strip()}"

    def _attr(self, note):
        attr = note.attr(0)
        color = attr.voice_color if attr.voice_color is not None else self.get_parent_voice_color()
        shift = attr.tone_shift if attr.tone_shift is not None else self.get_parent_tone_shift()
        alt = attr.alternate if attr.alternate is not None else self.get_parent_alternate()
        return color, shift, alt

    def is_exist_phoneme_in_oto(self, phoneme, note):
        color, shift, alt = self._attr(note)
        if phoneme == "":
            return False
        if self.singer.try_get_mapped_oto(phoneme + alt_str(alt), note.tone + shift, color) is not None:
            return True
        if self.singer.try_get_mapped_oto(phoneme, note.tone + shift, color) is not None:
            return True
        if self.singer.try_get_mapped_oto(phoneme, note.tone, color) is not None:
            return True
        return False

    def get_oto_alias(self, phoneme, note):
        color, shift, alt = self._attr(note)
        for p, t in ((phoneme + alt_str(alt), note.tone + shift), (phoneme, note.tone + shift), (phoneme, note.tone)):
            o = self.singer.try_get_mapped_oto(p, t, color)
            if o is not None:
                return o.alias
        return phoneme

    def process(self, notes, prev, next, prev_neighbour, next_neighbour, prev_neighbours):
        try:
            return self._process(notes, prev_neighbour)
        except Exception:  # noqa: BLE001 - "An error occurred during the phoneme processing in zh cvv+ module."
            return [Phoneme("ERROR")]

    def _process(self, notes, prev_neighbour):
        cfg = self.config
        total_duration = sum(n.duration for n in notes)
        phoneme = notes[0].lyric
        lryic_vowel = self.get_lyric_vowel(notes[0].lyric)

        # phonetic hints are separated by commas, spread evenly over the note
        if notes[0].phonetic_hint is not None:
            hints = notes[0].phonetic_hint.split(",")
            n = len(hints)
            return [Phoneme(self.get_oto_alias(h.strip(), notes[0]), position=total_duration - ((total_duration // n) * (n - i)))
                    for i, h in enumerate(hints)]

        # end breath note
        if phoneme in cfg.SupportedTailBreath and prev_neighbour is not None:
            phoneme = self.get_oto_alias(f"{self.get_lyric_vowel(prev_neighbour.lyric)} {phoneme}", notes[0])
            return [Phoneme(phoneme)]

        if cfg.UseRetan and prev_neighbour is None and self.is_exist_phoneme_in_oto(f"- {phoneme}", notes[0]):
            phoneme = f"- {phoneme}"
            phoneme = self.get_oto_alias(phoneme, notes[0])

        if lryic_vowel in cfg.TailVowels:
            tail_phoneme = f"{cfg.VowelTailPrefix}{cfg.TailVowels[lryic_vowel]}"
            if ((total_duration <= cfg.SingleVowelsReferenceTimimgTick
                 and (cfg.UseSingleNasalVowel and lryic_vowel in cfg.NasalVowelDict
                      or cfg.UseSingleMultipleVowel and lryic_vowel in cfg.MultipleVowelDict))
                    or (not cfg.UseSingleNasalVowel and lryic_vowel in cfg.NasalVowelDict)
                    or (not cfg.UseSingleMultipleVowel and lryic_vowel in cfg.MultipleVowelDict)):
                # the tail vowel sits at 1/3 of the note from the end
                tail_vowel_position = total_duration - total_duration // 3
                if lryic_vowel in cfg.FastTailVowelDict:
                    tail_vowel_position = cfg.FastTailVowelTimingTick
                phoneme = self.get_oto_alias(phoneme, notes[0])
                tail_phoneme = self.get_oto_alias(tail_phoneme, notes[0])
                return [Phoneme(phoneme), Phoneme(tail_phoneme, position=tail_vowel_position)]

        return [Phoneme(self.get_oto_alias(phoneme, notes[0]))]


def _default_yaml():
    return ""  # a missing file means the default config (openutau serializes and re-reads the defaults)
