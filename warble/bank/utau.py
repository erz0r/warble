"""classic utau bank loading.

ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Core/Classic/VoicebankLoader.cs,
VoicebankErrorChecker.cs.
"""

import os
import re
import unicodedata
from dataclasses import dataclass, field

from ..textenc import decode_bytes, oto_declared_charset
from .common import load_character_yaml, parse_character_txt

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def tone_to_name(tone):
    return f"{NOTE_NAMES[tone % 12]}{tone // 12 - 1}"


def name_to_tone(name):
    """'C4' -> 60, 'C#4'/'Db4' -> 61. returns None when it isn't a note name."""
    m = re.fullmatch(r"\s*([A-Ga-g])([#b]?)(-?\d+)\s*", name or "")
    if not m:
        return None
    base = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}[m.group(1).upper()]
    acc = {"#": 1, "b": -1, "": 0}[m.group(2)]
    return (int(m.group(3)) + 1) * 12 + base + acc


@dataclass
class Oto:
    wav: str
    alias: str
    offset: float = 0.0
    consonant: float = 0.0
    cutoff: float = 0.0
    preutter: float = 0.0
    overlap: float = 0.0
    line_no: int = -1  # 0-based, -1 for synthesized entries
    line: str = ""
    valid: bool = True
    error: str = ""
    synthesized: str = ""  # why openutau would add this alias without an oto line

    def cutoff_ms(self, file_ms):
        """absolute end position in ms. negative cutoff is measured from offset, positive from the file end."""
        return self.offset - self.cutoff if self.cutoff < 0 else file_ms - self.cutoff


@dataclass
class OtoSet:
    path: str
    name: str  # relative folder, '' for root
    encoding: str = ""
    encoding_how: str = ""
    otos: list = field(default_factory=list)

    @property
    def dir(self):
        return os.path.dirname(self.path)


def _parse_float(s):
    s = (s or "").strip()
    if not s:
        return 0.0
    return float(s)


def parse_oto_line(line, line_no):
    fmt = "<wav>=<alias>,<offset>,<consonant>,<cutoff>,<preutter>,<overlap>"
    if "=" not in line:
        return Oto(wav="", alias="", line_no=line_no, line=line, valid=False, error=f"line does not match {fmt}")
    wav, rest = line.split("=", 1)
    wav = wav.strip()
    parts = rest.split(",")
    alias = parts[0] if parts else ""
    if not alias:
        alias = os.path.splitext(wav)[0]
    oto = Oto(wav=wav, alias=alias, line_no=line_no, line=line)
    for i, key in enumerate(["offset", "consonant", "cutoff", "preutter", "overlap"], start=1):
        try:
            setattr(oto, key, _parse_float(parts[i] if i < len(parts) else ""))
        except ValueError:
            oto.valid = False
            oto.error = f"cannot parse {key} '{parts[i]}'; format is {fmt}"
            break
    return oto


def parse_oto_set(path, bank_root, declared_encoding=None, check_wavs=True):
    with open(path, "rb") as f:
        data = f.read()
    charset = oto_declared_charset(data)
    text, enc, how = decode_bytes(data, charset or declared_encoding)
    if charset and how == "declared":
        how = "#Charset"
    elif declared_encoding and how == "declared":
        how = "character.yaml text_file_encoding"
    name = os.path.relpath(os.path.dirname(path), bank_root)
    oset = OtoSet(path=path, name="" if name == "." else name, encoding=enc, encoding_how=how)
    for i, raw in enumerate(text.splitlines()):
        line = raw.strip()
        if not line or line.startswith("#Charset:"):
            continue
        oset.otos.append(parse_oto_line(line, i))
    if check_wavs:
        _fix_nfd_and_missing(oset)
    _add_alias_for_missing_files(oset)
    return oset


def _fix_nfd_and_missing(oset):
    """openutau maps oto wav names onto nfd-normalized filenames (mac zips) before declaring them missing."""
    try:
        files = set(os.listdir(oset.dir))
    except OSError:
        files = set()
    nfc_map = {unicodedata.normalize("NFC", f): f for f in files}
    for oto in oset.otos:
        if not oto.valid:
            continue
        if oto.wav in files:
            continue
        alt = nfc_map.get(unicodedata.normalize("NFC", oto.wav))
        if alt:
            oto.wav = alt
        else:
            oto.valid = False
            oto.error = f"sound file missing: {os.path.join(oset.dir, oto.wav)}"


def _add_alias_for_missing_files(oset):
    known = {o.wav for o in oset.otos if o.valid}
    try:
        names = sorted(os.listdir(oset.dir))
    except OSError:
        names = []
    for fn in names:
        if fn.lower().endswith(".wav") and fn not in known:
            oset.otos.append(Oto(wav=fn, alias=os.path.splitext(fn)[0], synthesized="wav has no oto line; alias = filename"))


def find_oto_files(root):
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        if "oto.ini" in filenames:
            out.append(os.path.join(dirpath, "oto.ini"))
    return out


def parse_prefix_map(path, declared_encoding=None):
    """prefix.map lines are 'NOTE<tab>prefix<tab>suffix'. returns {(prefix, suffix): sorted tones}
    plus the raw per-tone table."""
    with open(path, "rb") as f:
        text, enc, how = decode_bytes(f.read(), declared_encoding)
    groups, per_tone = {}, {}
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        tone = name_to_tone(parts[0])
        if tone is None:
            continue
        per_tone[tone] = (parts[1], parts[2])
        groups.setdefault((parts[1], parts[2]), set()).add(tone)
    return {k: sorted(v) for k, v in groups.items()}, per_tone, enc


def tone_ranges(tones):
    """[60,61,62,70] -> ['C4-D4', 'A#4'], the same compaction openutau shows for subbanks."""
    out, run = [], []
    for t in sorted(tones):
        if run and t == run[-1] + 1:
            run.append(t)
        else:
            if run:
                out.append(tone_to_name(run[0]) if len(run) == 1 else f"{tone_to_name(run[0])}-{tone_to_name(run[-1])}")
            run = [t]
    if run:
        out.append(tone_to_name(run[0]) if len(run) == 1 else f"{tone_to_name(run[0])}-{tone_to_name(run[-1])}")
    return out


class UtauBank:
    def __init__(self, root, check_wavs=True):
        self.root = os.path.abspath(root)
        self.character_yaml_path, cy = load_character_yaml(self.root)
        self.character = cy or {}
        self.declared_encoding = self.character.get("text_file_encoding")
        self.character_txt = parse_character_txt(self.root, self.declared_encoding)
        self.oto_sets = [parse_oto_set(p, self.root, self.declared_encoding, check_wavs) for p in find_oto_files(self.root)]
        self.prefix_map = None
        self.prefix_map_per_tone = {}
        self.prefix_map_encoding = None
        pm = os.path.join(self.root, "prefix.map")
        if os.path.isfile(pm):
            self.prefix_map, self.prefix_map_per_tone, self.prefix_map_encoding = parse_prefix_map(pm, self.declared_encoding)
        self.subbanks = self._subbanks()
        self._alias_map = None

    @property
    def name(self):
        return self.character.get("name") or (self.character_txt or {}).get("name") or os.path.basename(self.root)

    def _subbanks(self):
        """character.yaml subbanks win; otherwise prefix.map (and prefix/*.map) become subbanks,
        as in VoicebankLoader.LoadSubbanks."""
        subs = self.character.get("subbanks")
        if subs:
            return [
                {
                    "color": s.get("color") or "",
                    "prefix": s.get("prefix") or "",
                    "suffix": s.get("suffix") or "",
                    "tone_ranges": s.get("tone_ranges") or [],
                }
                for s in subs
                if isinstance(s, dict)
            ]
        out = []
        if self.prefix_map:
            for (pre, suf), tones in self.prefix_map.items():
                out.append({"color": "", "prefix": pre, "suffix": suf, "tone_ranges": tone_ranges(tones)})
        mapdir = os.path.join(self.root, "prefix")
        if os.path.isdir(mapdir):
            for fn in sorted(os.listdir(mapdir)):
                if fn.endswith(".map"):
                    color = os.path.splitext(fn)[0]
                    groups, _, _ = parse_prefix_map(os.path.join(mapdir, fn), self.declared_encoding)
                    for (pre, suf), tones in groups.items():
                        out.append({"color": color, "prefix": pre, "suffix": color + suf, "tone_ranges": tone_ranges(tones)})
        return out or [{"color": "", "prefix": "", "suffix": "", "tone_ranges": []}]

    def alias_map(self):
        """alias -> first valid oto, in load order (root first, then subfolders)."""
        if self._alias_map is None:
            m = {}
            for s in self.oto_sets:
                for o in s.otos:
                    if o.valid and o.alias not in m:
                        m[o.alias] = (s, o)
            self._alias_map = m
        return self._alias_map

    def affixes(self):
        """every prefix and suffix the bank's subbanks use, longest first."""
        pre = sorted({s["prefix"] for s in self.subbanks if s["prefix"]}, key=len, reverse=True)
        suf = sorted({s["suffix"] for s in self.subbanks if s["suffix"]}, key=len, reverse=True)
        return pre, suf


# ---- reclist style detection -------------------------------------------------------------

def strip_affixes(alias, prefixes, suffixes):
    for p in prefixes:
        if alias.startswith(p) and len(alias) > len(p):
            alias = alias[len(p):]
            break
    for s in suffixes:
        if alias.endswith(s) and len(alias) > len(s):
            alias = alias[: -len(s)]
            break
    return alias


_PITCH_SUFFIX = re.compile(r"(_?[A-G][#b]?\d|_[↑↓]|↑|↓)$")


def detect_reclist(aliases, prefixes=(), suffixes=(), units=None):
    """classify a bank's aliases by shape, without assuming a language.

    shapes: 'single' (か / ka), 'head' (- か), 'tail' (a -, a R), 'pair' (x y).
    for pairs we look at whether the right token is itself a sung unit (it appears as a single
    alias or after '-'); that separates vcv ('a か') from cvvc's vc parts ('a k').
    """
    base = set()
    for a in aliases:
        b = strip_affixes(a, prefixes, suffixes)
        b2 = _PITCH_SUFFIX.sub("", b)
        base.add(b2 if b2 else b)
    singles, heads, tails, pairs, multi = set(), set(), set(), [], []
    for a in base:
        toks = a.split(" ")
        if len(toks) == 1:
            singles.add(a)
        elif len(toks) == 2:
            l, r = toks
            if l == "-":
                heads.add(r)
            elif r in ("-", "R", "r", "息", "br"):
                tails.add(l)
            else:
                pairs.append((l, r))
        else:
            multi.append(a)
    units = (singles | heads) | set(units or ())
    left_counts = {}
    for l, r in pairs:
        left_counts[l] = left_counts.get(l, 0) + 1
    pair_right_is_unit = sum(1 for l, r in pairs if r in units)
    n_pairs = len(pairs)
    frac_unit = pair_right_is_unit / n_pairs if n_pairs else 0.0
    n_left = len(left_counts)
    evidence = {
        "unique_base_aliases": len(base),
        "single_token": len(singles),
        "head_aliases": len(heads),
        "tail_aliases": len(tails),
        "pair_aliases": n_pairs,
        "pair_right_token_is_a_unit": round(frac_unit, 3),
        "distinct_pair_left_tokens": n_left,
        "top_pair_left_tokens": sorted(left_counts, key=lambda k: -left_counts[k])[:12],
        "three_plus_token_aliases": len(multi),
        "examples": {
            "single": sorted(singles)[:8],
            "head": sorted(f"- {h}" for h in heads)[:8],
            "pair": [f"{l} {r}" for l, r in sorted(pairs)[:8]],
        },
    }
    evidence["_units"] = sorted(units)
    edge_marked = sum(1 for a in singles if a[:1] in "-_" or a.endswith("-"))
    evidence["single_token_with_edge_marks"] = edge_marked
    if singles and edge_marked > 0.2 * len(singles) and n_pairs < len(singles):
        # vccv lists write transitions without spaces: '-ka', 'ka', 'ak', 'k-', '_ka'
        style = "vccv"
    elif n_pairs == 0 or n_pairs < 0.1 * len(base):
        style = "cv"
    elif frac_unit >= 0.6 and n_left <= 12:
        style = "vcv"
    elif n_left <= 12:
        # vowel-ish lefts with consonant-ish rights: vc pieces of cvvc
        style = "cvvc"
    else:
        # many different left tokens: phoneme-diphone banks (arpasing, vccv, etc.)
        style = "diphone"
    return style, evidence


def bank_reclist(bank):
    """classify each oto set on its own, then combine. banks often mix styles per folder
    (a vcv folder next to a cvvc one), and a single global label hides that."""
    prefixes, suffixes = bank.affixes()
    per_set = []
    weights = {}
    all_aliases = [o.alias for s in bank.oto_sets for o in s.otos if o.valid]
    _, evidence = detect_reclist(all_aliases, prefixes, suffixes)
    units = set(evidence["_units"])
    for s in bank.oto_sets:
        aliases = [o.alias for o in s.otos if o.valid and not o.synthesized]
        if not aliases:
            continue
        style, ev = detect_reclist(aliases, prefixes, suffixes, units)
        per_set.append({"folder": s.name or ".", "style": style, "aliases": len(aliases)})
        weights[style] = weights.get(style, 0) + len(aliases)
    combined = "+".join(sorted(weights, key=lambda k: -weights[k])) or "unknown"
    evidence.pop("_units", None)
    return combined, per_set, evidence
