# syllable based phonemizer templates

copied unchanged from openutau (MIT license, Copyright (c) 2014 StAkira and contributors,
https://github.com/stakira/OpenUtau), `OpenUtau.Plugin.Builtin/`. each is the yaml openutau writes into its
plugin folder on first use (the `YamlTemplate` resource of the phonemizer); warble reads them in place of that
folder.

- arpasing.template.yaml (`Data/`): plugin-folder `arpasing.yaml` (ArpasingPlusPhonemizer)
- envccv.template.yaml (`Data/`): plugin-folder `envccv.yaml` (EnglishVCCVPhonemizer)
- en_cPv.template.yaml (`Data/`): plugin-folder `en-cPv.yaml` (EnglishCpVPhonemizer)
- en-xsampa.template.yaml (`Resources/`, which is what `Resources.resx` embeds as `en_xsampa_template`; the copy
  in `Data/` differs and is not used): plugin-folder `en-xsampa.yaml` (EnXSampaPhonemizer)
- filipino-template.yaml (`Data/`): plugin-folder `filipino.yaml` (FilipinoPhonemizer)
