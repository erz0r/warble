"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Plugin.Builtin/MonophonePhonemizer.cs"""

from .phoneme_based import PhonemeBasedPhonemizer


class MonophonePhonemizer(PhonemeBasedPhonemizer):
    add_tail = False  # MonophonePhonemizer() { addTail = false; }

    def get_phoneme_or_fallback(self, prev_symbol, symbol, tone, color, alt):
        if alt:
            oto = self.singer.try_get_mapped_oto(f"{symbol}{alt}", tone, color)
            if oto is not None:
                return oto.alias
        oto1 = self.singer.try_get_mapped_oto(symbol, tone, color)
        if oto1 is not None:
            return oto1.alias
        fallbacks = self.vowel_fallback.get(symbol)
        if fallbacks is not None:
            for fallback in fallbacks:
                oto2 = self.singer.try_get_mapped_oto(fallback, tone, color)
                if oto2 is not None:
                    return oto2.alias
        return f"{symbol}{alt}"
