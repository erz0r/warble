"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Plugin.Builtin/FrenchCMUSphinxPhonemizer.cs

a french diphone phonemizer that uses the cmusphinx dictionary (the french g2p pack)."""

from ...g2p import FrenchG2p, G2pDictionary, G2pFallbacks
from .api import phonemizer
from .arpasing import singer_file
from .latin_diphone import LatinDiphonePhonemizer
from .phoneme_based import plugin_file, read_all_text


@phonemizer("French CMUSphinx Phonemizer", "FR SPHINX", language="FR", openutau_class="OpenUtau.Plugin.Builtin.FrenchCMUSphinxPhonemizer")
class FrenchCMUSphinxPhonemizer(LatinDiphonePhonemizer):
    def load_g2p(self):
        g2ps = []

        # Load dictionary from plugin folder (openutau ships no french.yaml template).
        path = plugin_file("french.yaml")
        if path is not None:
            try:
                g2ps.append(G2pDictionary.new_builder().load(read_all_text(path)).build())
            except Exception:  # noqa: BLE001
                pass

        # Load dictionary from singer folder.
        file = singer_file(self.singer, "french.yaml")
        if file is not None:
            try:
                g2ps.append(G2pDictionary.new_builder().load(read_all_text(file)).build())
            except Exception:  # noqa: BLE001
                pass

        # Load base g2p.
        g2ps.append(FrenchG2p())

        return G2pFallbacks(g2ps)

    def load_vowel_fallbacks(self):
        return {}
