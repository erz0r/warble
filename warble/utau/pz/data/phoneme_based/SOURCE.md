# phoneme based phonemizer dictionaries

copied unchanged from openutau (MIT license, Copyright (c) 2014 StAkira and contributors,
https://github.com/stakira/OpenUtau), `OpenUtau.Plugin.Builtin/Data/`:

- arpasing.template.yaml: the plugin-folder `arpasing.yaml` openutau writes on first use (ArpasingPhonemizer)
- german.template.yaml: the plugin-folder `german.yaml` openutau writes on first use (GermanDiphonePhonemizer)

openutau reads `french.yaml` (FrenchCMUSphinxPhonemizer) and `zhcvv.yaml` (ChineseCVVMonophonePhonemizer) from
its plugin folder only when a user put them there; it ships no template for either.
