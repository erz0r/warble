"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Core/Api/G2pDictionaryData.cs

the yaml dictionary format: {symbols: [{symbol, type}], entries: [{grapheme, phonemes: [...]}]}.
yaml is read the way openutau's YamlDotNet deserializer reads it into string fields: every scalar stays a
string (no yaml 1.1 booleans or numbers), unknown keys are ignored."""

from dataclasses import dataclass, field

import yaml


@dataclass
class SymbolData:
    symbol: str = None
    type: str = None


@dataclass
class Entry:
    grapheme: str = None
    phonemes: list = None


@dataclass
class G2pDictionaryData:
    symbols: list = None
    entries: list = None

    @staticmethod
    def deserialize(text):
        if text.startswith("﻿"):
            text = text[1:]
        raw = yaml.load(text, Loader=yaml.BaseLoader)
        data = G2pDictionaryData()
        if not isinstance(raw, dict):
            return data
        if raw.get("symbols") not in (None, "", "~", "null"):
            data.symbols = [SymbolData(symbol=_s(s.get("symbol")), type=_s(s.get("type"))) for s in raw["symbols"]]
        if raw.get("entries") not in (None, "", "~", "null"):
            data.entries = []
            for e in raw["entries"]:
                ph = e.get("phonemes")
                if isinstance(ph, str):
                    if ph in ("", "~", "null"):
                        ph = None
                    else:
                        raise ValueError(f"phonemes of {e.get('grapheme')} is not a sequence")
                data.entries.append(Entry(grapheme=_s(e.get("grapheme")), phonemes=None if ph is None else [_s(p) for p in ph]))
        return data


def _s(v):
    """a plain null scalar deserializes to a null string in YamlDotNet."""
    if v is None or v in ("~", "null", "Null", "NULL"):
        return None
    return v
