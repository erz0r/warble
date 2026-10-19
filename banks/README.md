# adding voicebanks

warble doesn't ship any voicebanks. bring your own and put them here, one folder per bank,
grouped however you like (by character is handy):

```
banks/
  adachi_rei/
    足立レイ_DS_v111.1/        <- a diffsinger bank (has dsconfig.yaml)
    足立レイver3.5.0/          <- a classic utau bank (has oto.ini)
  some_other_singer/
    ...
```

1. download the bank from its author and unzip it here. zips made on windows often have
   shift-jis file names; if names come out garbled, unzip with a tool that lets you pick the
   encoding (or `python -c "import zipfile..."` decoding names as cp932).
2. run `warble banks` to see that it was detected, then `warble probe --check banks/<...>`.
   probe tells you the bank type, languages, voice modes, the readme/terms files, and anything
   broken (bad oto entries, missing wavs, dictionary gaps, a missing vocoder).
3. diffsinger banks need a vocoder. most bundle one in `dsvocoder/`; if `probe` says the named
   vocoder is missing, download it (often openvpi's pc_nsf_hifigan,
   https://github.com/openvpi/vocoders/releases) and put its folder (with `vocoder.yaml`) in
   `vocoders/` at the project root.
4. use it from a score with `bank banks/<...>` or just a few words of its name: `bank rei ds`.

other places to keep banks: set `WARBLE_BANKS` to more folders (separated by `:`).

read each bank's readme and terms before publishing anything you make with it. many diffsinger
banks ask for credit and "DiffSinger" in titles, some forbid commercial use, and none of them may
be redistributed. everything in this folder except this file is ignored by git so a bank can't be
committed by accident.
