"""the phonemizer api, mirroring openutau's OpenUtau.Api.Phonemizer so ports stay line-by-line close.

ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Core/Api/Phonemizer.cs,
Api/PhonemizerRunner.cs, Util/TimeAxis.cs, Classic/ClassicSinger.cs.

naming: c# PascalCase members become snake_case (TryGetMappedOto -> try_get_mapped_oto). nullable
c# values are None. a port subclasses Phonemizer, decorates itself with @phonemizer(...), and
lives in its own module in this package (modules are discovered automatically).
"""

import math
import os
import re
import unicodedata
from dataclasses import dataclass, field

REGISTRY = {}


def phonemizer(name, tag, language=None, openutau_class=None, author=None):
    def deco(cls):
        cls.name = name
        cls.tag = tag
        cls.language = language
        cls.openutau_class = openutau_class
        cls.author = author
        REGISTRY[tag] = cls
        return cls

    return deco


@dataclass
class PhonemeAttributes:
    index: int = 0
    consonant_stretch_ratio: float = None
    tone_shift: int = None
    alternate: int = None
    voice_color: str = None


@dataclass
class Note:
    lyric: str
    tone: int
    position: int
    duration: int
    phonetic_hint: str = None
    phoneme_attributes: list = field(default_factory=list)

    def attr(self, index):
        """phonemeAttributes?.FirstOrDefault(attr => attr.index == index) ?? default"""
        for a in self.phoneme_attributes or []:
            if a.index == index:
                return a
        return PhonemeAttributes(index=index)


@dataclass
class Phoneme:
    phoneme: str
    position: int = 0
    index: int = None
    error: str = None
    expressions: list = None


class TimeAxis:
    """tempo segments over ticks (480 per beat), with openutau's rounding."""

    def __init__(self, tempos=((0, 120.0),)):
        self.tempos = sorted((int(t), float(b)) for t, b in tempos)
        if self.tempos[0][0] != 0:
            self.tempos.insert(0, (0, self.tempos[0][1]))
        self.segs = []
        ms = 0.0
        for i, (t, b) in enumerate(self.tempos):
            if i:
                pt, pb = self.tempos[i - 1]
                ms += (t - pt) * 60000.0 / (pb * 480)
            self.segs.append((t, ms, b))

    def _seg_tick(self, tick):
        s = self.segs[0]
        for x in self.segs:
            if x[0] <= tick:
                s = x
        return s

    def _seg_ms(self, ms):
        s = self.segs[0]
        for x in self.segs:
            if x[1] <= ms:
                s = x
        return s

    def tick_pos_to_ms_pos(self, tick):
        t0, ms0, bpm = self._seg_tick(tick)
        return ms0 + (tick - t0) * 60000.0 / (bpm * 480)

    def ms_pos_to_non_exact_tick_pos(self, ms):
        t0, ms0, bpm = self._seg_ms(ms)
        return t0 + (ms - ms0) * bpm * 480 / 60000.0

    def ms_pos_to_tick_pos(self, ms):
        v = self.ms_pos_to_non_exact_tick_pos(ms)
        if not math.isfinite(v):
            return self._seg_ms(ms)[0]
        return int(round(v))  # Math.Round: banker's rounding, like python's round

    def ticks_between_ms_pos(self, ms_pos, ms_end):
        return self.ms_pos_to_tick_pos(ms_end) - self.ms_pos_to_tick_pos(ms_pos)

    def ms_between_tick_pos(self, tick_pos, tick_end):
        return self.tick_pos_to_ms_pos(tick_end) - self.tick_pos_to_ms_pos(tick_pos)

    def get_bpm_at_tick(self, tick):
        return self._seg_tick(tick)[2]

    def ms_to_tick_at(self, offset_ms, ref_tick_pos):
        ref_ms = self.tick_pos_to_ms_pos(ref_tick_pos)
        return self.ms_pos_to_tick_pos(ref_ms + offset_ms) - ref_tick_pos


_GRAPHEME = re.compile(r"\r\n|.[̀-゙゚ͯ゛゜︀-️‍]*", re.S)


def to_unicode_elements(lyric):
    """StringInfo text elements: a base character with its combining marks."""
    out = []
    for m in _GRAPHEME.finditer(lyric or ""):
        s = m.group(0)
        if out and s and unicodedata.category(s[0]).startswith("M"):
            out[-1] += s
        else:
            out.append(s)
    return out


class Phonemizer:
    name = "base"
    tag = "base"
    language = None
    openutau_class = None
    legacy_mapping = False

    def __init__(self):
        self.singer = None
        self.time_axis = TimeAxis()
        self.bpm = 120.0

    # ---- lifecycle ---------------------------------------------------------------------------
    def set_singer(self, singer):
        self.singer = singer

    def set_timing(self, time_axis):
        self.time_axis = time_axis
        self.bpm = time_axis.get_bpm_at_tick(0)

    def set_up(self, groups):
        pass

    def process(self, notes, prev, next, prev_neighbour, next_neighbour, prev_neighbours):
        raise NotImplementedError

    def clean_up(self):
        pass

    # ---- helpers from the c# base class ----------------------------------------------------------
    def tick_to_ms(self, tick):
        return self.time_axis.tick_pos_to_ms_pos(tick)

    def ms_to_tick(self, ms):
        return self.time_axis.ms_pos_to_tick_pos(ms)

    @staticmethod
    def to_unicode_elements(lyric):
        return to_unicode_elements(lyric)

    def get_parent_consonant_stretch_ratio(self):
        return 1.0

    def get_parent_tone_shift(self):
        return 0

    def get_parent_alternate(self):
        return None

    def get_parent_voice_color(self):
        return ""

    def make_simple_result(self, phoneme):
        return [Phoneme(phoneme)]

    @staticmethod
    def map_phoneme(phoneme, tone, color, alt, singer):
        oto = singer.try_get_mapped_oto(f"{phoneme}{alt if alt is not None else ''}", tone, color)
        if oto is not None:
            return oto.alias
        oto = singer.try_get_mapped_oto(phoneme, tone, color)
        if oto is not None:
            return oto.alias
        return phoneme

    def dictionaries_path(self):
        return os.path.join(os.path.dirname(__file__), "data")


def alt_str(alt):
    """c# string interpolation of an int?: null prints as ''."""
    return "" if alt is None else str(alt)
