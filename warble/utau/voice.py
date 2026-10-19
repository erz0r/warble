"""alias lookup for a classic bank, with subbank prefix/suffix chosen by tone and voice color.

ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Core/Classic/ClassicSinger.cs
(TryGetMappedOto).
"""

from ..bank.utau import name_to_tone


def _tone_set(ranges):
    tones = set()
    for r in ranges or []:
        parts = str(r).split("-")
        lo = name_to_tone(parts[0])
        hi = name_to_tone(parts[-1]) if len(parts) > 1 else lo
        if lo is not None and hi is not None:
            tones |= set(range(lo, hi + 1))
    return tones


class Voice:
    def __init__(self, bank):
        self.bank = bank
        self.alias_map = bank.alias_map()  # alias -> (oto_set, oto)
        self.subbanks = []
        for s in bank.subbanks:
            ts = _tone_set(s["tone_ranges"])
            # a subbank without ranges covers every tone (openutau loads it as all tones)
            self.subbanks.append({**s, "tones": ts or set(range(0, 128))})

    def colors(self):
        return sorted({s["color"] for s in self.subbanks if s["color"]})

    def lookup(self, alias, tone, color=None):
        """-> (oto_set, oto, mapped_alias) or None."""
        tone = int(round(tone))
        if color:
            for s in self.subbanks:
                if s["color"] == color and tone in s["tones"]:
                    hit = self.alias_map.get(f"{s['prefix']}{alias}{s['suffix']}")
                    if hit:
                        return hit[0], hit[1], f"{s['prefix']}{alias}{s['suffix']}"
                    break
        for s in self.subbanks:
            if not s["color"] and tone in s["tones"]:
                hit = self.alias_map.get(f"{s['prefix']}{alias}{s['suffix']}")
                if hit:
                    return hit[0], hit[1], f"{s['prefix']}{alias}{s['suffix']}"
                break
        hit = self.alias_map.get(alias)
        if hit:
            return hit[0], hit[1], alias
        return None

    def exists(self, alias, tone, color=None):
        return self.lookup(alias, tone, color) is not None
