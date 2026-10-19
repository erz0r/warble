"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Core/DefaultPhonemizer.cs"""

from .api import Phonemizer, alt_str, phonemizer


@phonemizer("Default Phonemizer", "DEFAULT", openutau_class="OpenUtau.Core.DefaultPhonemizer")
class DefaultPhonemizer(Phonemizer):
    def process(self, notes, prev, next, prev_neighbour, next_neighbour, prev_neighbours):
        alias = notes[0].lyric
        attr0 = notes[0].attr(0)
        color = attr0.voice_color if attr0.voice_color is not None else self.get_parent_voice_color()
        shift = attr0.tone_shift if attr0.tone_shift is not None else self.get_parent_tone_shift()
        alt = attr0.alternate if attr0.alternate is not None else self.get_parent_alternate()
        oto = self.singer.try_get_mapped_oto(notes[0].lyric + alt_str(alt), notes[0].tone + shift, color)
        if oto is not None:
            alias = oto.alias
        return self.make_simple_result(alias)
