"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Plugin.Builtin/LatinDiphonePhonemizer.cs"""

from .phoneme_based import PhonemeBasedPhonemizer


class LatinDiphonePhonemizer(PhonemeBasedPhonemizer):
    """a base diphone phonemizer for latin languages."""

    def get_phoneme_or_fallback(self, prev_symbol, symbol, tone, color, alt):
        if alt:
            oto = self.singer.try_get_mapped_oto(f"{prev_symbol} {symbol}{alt}", tone, color)
            if oto is not None:
                return oto.alias
        oto1 = self.singer.try_get_mapped_oto(f"{prev_symbol} {symbol}", tone, color)
        if oto1 is not None:
            return oto1.alias
        fallbacks = self.vowel_fallback.get(symbol)
        if fallbacks is not None:
            for fallback in fallbacks:
                oto2 = self.singer.try_get_mapped_oto(f"{prev_symbol} {fallback}", tone, color)
                if oto2 is not None:
                    return oto2.alias
        oto3 = self.singer.try_get_mapped_oto(f"- {symbol}", tone, color)
        if oto3 is not None:
            return oto3.alias
        return f"{prev_symbol} {symbol}{alt}"
