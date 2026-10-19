"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Plugin.Builtin/CantoneseCVVCPhonemizer.cs"""

from ._pinyin import CanTone, Jyutping
from .api import phonemizer
from .chinese_cvvc import ChineseCVVCPhonemizer


@phonemizer("Cantonese CVVC Phonemizer", "ZH-YUE CVVC", language="ZH-YUE", openutau_class="OpenUtau.Plugin.Builtin.CantoneseCVVCPhonemizer", author="Lotte V")
class CantoneseCVVCPhonemizer(ChineseCVVCPhonemizer):
    """works like the chinese cvvc phonemizer (presamp.ini required) but romanizes hanzi to jyutping."""

    def romanize(self, lyrics):
        return [res.pinyin for res in Jyutping.instance().hanzi_to_pinyin(list(lyrics), CanTone.NORMAL, 0)]
