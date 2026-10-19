# porting openutau phonemizers to warble

warble ports openutau's phonemizers to python and proves each port with **parity goldens**:
openutau itself runs on a set of cases and the python port must produce the same aliases at the
same tick positions.

## layout

- `ref/OpenUtau/` is the openutau checkout (read only). phonemizers live in
  `ref/OpenUtau/OpenUtau.Plugin.Builtin/*.cs`; the api in `ref/OpenUtau/OpenUtau.Core/Api/`;
  g2p in `ref/OpenUtau/OpenUtau.Core/G2p/` and `ref/OpenUtau/OpenUtau.Core/Api/G2p*.cs`.
- `warble/utau/pz/` holds the python ports, **one module per c# file** (base classes too).
  modules are discovered automatically: just add a file. don't edit another family's modules.
  - `api.py`: `Phonemizer` (c# `Phonemizer` with snake_case names), `Note`, `PhonemeAttributes`,
    `Phoneme`, `TimeAxis`, `to_unicode_elements`, `alt_str`, the `@phonemizer(name, tag,
    language=..., openutau_class="<full c# type name>")` decorator. read it first.
  - `singer.py`: the bank as a `USinger` (`try_get_mapped_oto(phoneme, tone, color)`,
    `try_get_oto(alias)`, `subbanks`, `otos`, `location`, `find_file(name)`).
  - `runner.py`: runs a phonemizer like openutau's `PhonemizerRunner` (groups in reverse order,
    end pushback, prev = previous group's first note, neighbours when touching).
  - examples: `japanese_vcv.py`, `japanese_cvvc.py`, `default.py`.
- shared data a port needs (yaml templates, dictionaries, g2p models) goes under
  `warble/utau/pz/data/<family>/` (copy from the openutau checkout; it is MIT licensed, keep a
  `SOURCE.md` saying where each file came from). never read from `ref/` at runtime.
- `tests/parity/banks/` has openutau's test voicebanks (oto.ini etc, no wavs needed).
  if a phonemizer has no fitting test bank, make a minimal one in
  `tests/parity/banks/<family>_<style>/` (character.txt + oto.ini listing the aliases the
  phonemizer can produce, plus any yaml/presamp file it reads; wav files are not needed).
- `tests/parity/cases/<name>.json`: `{"phonemizer": "<full c# class>", "bank": "<dir under
  tests/parity/banks>", "bpm": 120, "cases": [{"id": "...", "notes": [{"lyric": "...", "tone":
  "C4", "duration": 480, "hint": null, "gap_after": 0, "attrs": [{"index": 0, "shift": 0, "alt":
  0, "color": ""}]}]}]}`. write cases that exercise the phonemizer's branches: phrase starts and
  ends, rests (`gap_after`), `+` extensions, phonetic hints, every vowel/consonant class, short
  notes, pitch and color subbanks when the bank has them.
- `python tests/parity/gen_goldens.py <name>` runs openutau (via `ref/harness`, already built)
  and writes `tests/parity/goldens/<name>.json`.
- `.venv/bin/python -m pytest -q tests/test_parity.py -k <name>` compares your port with the golden.
  `from warble.utau.pz.parity import compare; compare("tests/parity/goldens/<name>.json",
  "tests/parity/banks")` gives the mismatching cases for debugging.

## rules

- port faithfully: same branches, same string tables, same fallbacks, same rounding (c#
  `Math.Round` and `Convert.ToInt32` round half to even, like python `round`; `(int)` truncates
  toward zero; integer `/` truncates toward zero, unlike python `//` on negatives). keep the c#
  structure so a reader can diff the two. put the attribution line at the top of every module:
  `"""ported from openutau (MIT, Copyright (c) 2014 StAkira): <path of the .cs file>"""`.
- c# `Dictionary` built with `ToDictionary` throws on duplicate keys; c# `string.Normalize()` is
  NFC; `ToUnicodeElements` is in api.py.
- a port counts as done only when its goldens pass. if something truly can't be ported (a .net-only
  library, a resource that can't be read from python), stop and report exactly why.
- don't modify `api.py`, `runner.py`, `singer.py`, `parity.py` or other families' modules. if
  the api is missing something you need, add a small helper in your own module and mention it in
  your report.
- don't commit; don't touch files outside your family's modules, data, banks, cases and goldens.
- before finishing, run `.venv/bin/python -m pytest -q tests/test_parity.py` and make sure
  nothing that passed before fails now.
