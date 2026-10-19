"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Plugin.Builtin/GermanDiphonePhonemizer.cs

simple german diphone phonemizer, works like arpasing. based on the german cmusphinx dictionary."""

from ...g2p import G2pDictionary, G2pFallbacks, GermanG2p
from .api import phonemizer
from .arpasing import singer_file, vowel_fallbacks
from .latin_diphone import LatinDiphonePhonemizer
from .phoneme_based import plugin_file, read_all_text


@phonemizer("German Diphone Phonemizer", "DE DIPHONE", language="DE", openutau_class="OpenUtau.Plugin.Builtin.GermanDiphonePhonemizer", author="Lotte V")
class GermanDiphonePhonemizer(LatinDiphonePhonemizer):
    def load_g2p(self):
        g2ps = []

        # Load dictionary from plugin folder.
        path = plugin_file("german.yaml")
        g2ps.append(G2pDictionary.new_builder().load(read_all_text(path)).build())

        # Load dictionary from singer folder.
        file = singer_file(self.singer, "german.yaml")
        if file is not None:
            try:
                g2ps.append(G2pDictionary.new_builder().load(read_all_text(file)).build())
            except Exception:  # noqa: BLE001
                pass

        # Load base g2p.
        g2ps.append(GermanG2p())

        return G2pFallbacks(g2ps)

    def load_vowel_fallbacks(self):
        return vowel_fallbacks("aa=ex;ex=aa;ah=ax,aa;ae=eh;eh=ae,ee;ee=eh;ao=ooh;ooh=ao;er=ex,ax;ih=iy;iy=ih;uh=uw;uw=uh;yy=ue;ue=yy;ohh=oe;oe=ohh;ax=eh;cc=x;x=cc;dh=z;jh=ch;r=rr;th=s;w=v;zh=sh")
