"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Plugin.Builtin/ArpasingPhonemizer.cs

the english arpasing phonemizer: cmudict (via the arpabet g2p) turns words into arpabet symbols, sung as
diphones "<prev> <symbol>". the dictionary chain is the plugin arpasing.yaml (openutau's template), then the
singer's own arpasing.yaml, then the arpabet g2p pack."""

import os

from ...g2p import ArpabetG2p, G2pDictionary, G2pFallbacks
from .api import phonemizer
from .latin_diphone import LatinDiphonePhonemizer
from .phoneme_based import plugin_file, read_all_text


def vowel_fallbacks(spec):
    """"a=b,c;d=e".Split(';').Select(e => e.Split('=')).ToDictionary(p => p[0], p => p[1].Split(','))"""
    out = {}
    for entry in spec.split(";"):
        parts = entry.split("=")
        if parts[0] in out:
            raise ValueError(f"An item with the same key has already been added. Key: {parts[0]}")
        out[parts[0]] = parts[1].split(",")
    return out


def singer_file(singer, name):
    """Path.Combine(singer.Location, name) if the singer is found and loaded and the file exists."""
    if singer is None or not getattr(singer, "location", None):
        return None
    path = os.path.join(singer.location, name)
    return path if os.path.isfile(path) else None


@phonemizer("English Arpasing Phonemizer", "EN ARPA", language="EN", openutau_class="OpenUtau.Plugin.Builtin.ArpasingPhonemizer")
class ArpasingPhonemizer(LatinDiphonePhonemizer):
    def load_g2p(self):
        g2ps = []

        # Load dictionary from plugin folder.
        path = plugin_file("arpasing.yaml")
        g2ps.append(G2pDictionary.new_builder().load(read_all_text(path)).build())

        # Load dictionary from singer folder.
        file = singer_file(self.singer, "arpasing.yaml")
        if file is not None:
            try:
                g2ps.append(G2pDictionary.new_builder().load(read_all_text(file)).build())
            except Exception:  # noqa: BLE001 - Log.Error(e, $"Failed to load {file}")
                pass

        # Load base g2p.
        g2ps.append(ArpabetG2p())

        return G2pFallbacks(g2ps)

    def load_vowel_fallbacks(self):
        return vowel_fallbacks("aa=ah,ae;ae=ah,aa;ah=aa,ae;ao=ow;ow=ao;eh=ae;ih=iy;iy=ih;uh=uw;uw=uh;aw=ao")
