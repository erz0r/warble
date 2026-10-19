"""a classic bank seen the way openutau's phonemizers see a USinger / ClassicSinger."""

import os
from dataclasses import dataclass

from ...bank.utau import UtauBank, name_to_tone


@dataclass
class UOto:
    alias: str
    phonetic: str
    set: str
    color: str
    prefix: str
    suffix: str
    file: str
    offset: float
    consonant: float
    cutoff: float
    preutter: float
    overlap: float

    def is_color_match(self, color):
        """UOto.IsColorMatch: a subbank color ('' matches '')."""
        return (self.color or "") == (color or "")


def _tones(ranges):
    tones = set()
    for r in ranges or []:
        parts = str(r).split("-")
        lo = name_to_tone(parts[0])
        hi = name_to_tone(parts[-1]) if len(parts) > 1 else lo
        if lo is not None and hi is not None:
            tones |= set(range(lo, hi + 1))
    return tones or set(range(0, 128))


class Singer:
    def __init__(self, bank):
        if isinstance(bank, str):
            bank = UtauBank(bank, check_wavs=False)
        self.bank = bank
        self.location = bank.root
        self.subbanks = [{"color": s["color"], "prefix": s["prefix"], "suffix": s["suffix"], "tones": _tones(s["tone_ranges"])}
                         for s in bank.subbanks]
        self.oto_map = {}
        for oset in bank.oto_sets:
            for o in oset.otos:
                if not o.valid or o.alias in self.oto_map:
                    continue
                color, prefix, suffix = self._subbank_of(o.alias)
                self.oto_map[o.alias] = UOto(alias=o.alias, phonetic=o.alias, set=oset.name, color=color, prefix=prefix, suffix=suffix,
                                             file=os.path.join(oset.dir, o.wav), offset=o.offset, consonant=o.consonant, cutoff=o.cutoff,
                                             preutter=o.preutter, overlap=o.overlap)

    def _subbank_of(self, alias):
        for s in self.subbanks:
            if (s["prefix"] or s["suffix"]) and alias.startswith(s["prefix"]) and alias.endswith(s["suffix"]):
                return s["color"], s["prefix"], s["suffix"]
        return "", "", ""

    @property
    def name(self):
        return self.bank.name

    @property
    def otos(self):
        return list(self.oto_map.values())

    def try_get_oto(self, alias):
        return self.oto_map.get(alias)

    def try_get_mapped_oto(self, phoneme, tone, color=None):
        """ClassicSinger.TryGetMappedOto: the colored subbank for this tone, then the uncolored one,
        then the bare alias."""
        tone = int(tone)
        if color is not None:
            sb = next((s for s in self.subbanks if s["color"] == color and tone in s["tones"]), None)
            if sb is not None:
                o = self.oto_map.get(f"{sb['prefix']}{phoneme}{sb['suffix']}")
                if o is not None:
                    return o
        sb = next((s for s in self.subbanks if not s["color"] and tone in s["tones"]), None)
        if sb is not None:
            o = self.oto_map.get(f"{sb['prefix']}{phoneme}{sb['suffix']}")
            if o is not None:
                return o
        return self.oto_map.get(phoneme)

    def find_file(self, name):
        """a bank file (presamp.ini, yaml dictionaries) by name, case-insensitively at the root."""
        for fn in os.listdir(self.location):
            if fn.lower() == name.lower():
                return os.path.join(self.location, fn)
        return None
