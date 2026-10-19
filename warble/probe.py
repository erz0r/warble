"""`probe` and `probe --check`: describe a bank from its own files, and qa it."""

import os
import statistics
import unicodedata

from . import onnxinfo
from .bank import common, ds, signatures, utau


class Issues:
    def __init__(self, limit_per_code=40):
        self.items = []
        self.counts = {}
        self.limit = limit_per_code

    def add(self, severity, code, message, **where):
        self.counts[code] = self.counts.get(code, 0) + 1
        if self.counts[code] <= self.limit:
            self.items.append({"severity": severity, "code": code, "message": message, **where})

    def summary(self):
        by_sev = {"error": 0, "warning": 0, "info": 0}
        for it in self.items:
            by_sev[it["severity"]] += 1
        truncated = {k: v - self.limit for k, v in self.counts.items() if v > self.limit}
        out = {"by_severity": by_sev, "by_code": dict(sorted(self.counts.items()))}
        if truncated:
            out["not_listed"] = truncated
        return out


def probe(path, check=False, vocoder_dirs=None):
    path = os.path.abspath(path)
    kind, evidence = common.detect(path)
    base = {"bank": path, "type": kind, "detected_by": evidence}
    if kind == "diffsinger":
        base.update(probe_ds(path, check, vocoder_dirs))
    elif kind == "utau":
        base.update(probe_utau(path, check))
    else:
        base["supported"] = False
        if os.path.isdir(path):
            base["tree"] = common.tree(path, max_depth=2)
    return base


# ---- diffsinger ----------------------------------------------------------------------------

def _rel(root, p):
    return os.path.relpath(p, root) if p else None


def probe_ds(root, check, vocoder_dirs=None):
    issues = Issues()
    bank = ds.DsBank(root)
    out = {
        "name": bank.name,
        "readme_files": common.find_readmes(root),
        "character_yaml": _character_summary(bank.character),
        "tree": common.tree(root, max_depth=3),
    }
    if bank.character.get("_error"):
        issues.add("error", "character_yaml", bank.character["_error"], file=bank.character_yaml_path)

    configs = {}
    languages_all = set()
    for role, cfg in bank.all_configs():
        configs[role] = _probe_ds_config(root, role, cfg, bank, issues)
        languages_all |= set(configs[role].get("languages", {}).get("ids", {}) or {})
    out["configs"] = configs

    # dictionaries: root and per-submodel folders
    dicts = {}
    for role, cfg in bank.all_configs():
        folder = cfg.dir
        for p in ds.find_dicts(folder):
            rel = _rel(root, p)
            if rel in dicts:
                continue
            dicts[rel] = _probe_dict(root, p, cfg, issues)
    out["dictionaries"] = dicts
    if not dicts:
        issues.add("warning", "no_dictionary", "no dsdict*.yaml found; lyrics must be given as explicit phonemes", file=root)

    out["languages"] = sorted(languages_all) or sorted({ds.dict_language(p) for p in dicts if ds.dict_language(p)})
    out["voice_modes"] = _voice_modes(bank, issues)
    out["vocoder"] = ds.resolve_vocoder(root, bank.config, vocoder_dirs)
    voc = out["vocoder"]
    if voc["source"] == "missing":
        issues.add("error", "vocoder_missing", voc["error"])
    else:
        if not voc.get("model_exists"):
            issues.add("error", "vocoder_model_missing", f"vocoder model file not found: {voc['model_path']}")
        for mm in voc.get("mismatches", []):
            issues.add("error", "vocoder_mismatch", f"vocoder vs acoustic dsconfig mismatch on {mm}", file=voc["dir"])
        if voc.get("mel_base_scale", 1.0) != 1.0:
            issues.add("info", "mel_base_scaled", f"mel_base differs; acoustic mel will be scaled by {voc['mel_base_scale']}")
        if voc.get("model_exists"):
            voc["model"] = onnxinfo.describe(voc["model_path"])
            names = [i["name"] for i in voc["model"].get("inputs", [])]
            cmp = signatures.compare({"mel", "f0"}, names)
            if cmp["graph_needs_but_flags_omit"] or cmp["flags_feed_but_graph_lacks"]:
                issues.add("warning", "vocoder_inputs", f"vocoder inputs {names} differ from mel+f0: {cmp}")

    missing_deps = []
    if voc["source"] == "missing":
        missing_deps.append({"kind": "vocoder", "name": voc.get("named"), "detail": voc["error"]})
    out["missing_dependencies"] = missing_deps
    out["capabilities"] = {
        "durations": "model" if "dsdur" in bank.submodels else "rule (no dsdur)",
        "pitch": "model" if "dspitch" in bank.submodels else "rule (no dspitch)",
        "variance": "model" if "dsvariance" in bank.submodels else "none (no dsvariance)",
    }
    if "dsvariance" not in bank.submodels:
        needed = [v for v in ("energy", "breathiness", "voicing", "tension") if bank.config[f"use_{v}_embed"]]
        if needed:
            issues.add("warning", "variance_needed", f"acoustic model takes {needed} but there is no dsvariance; they will be fed as user curves around a neutral default")
    out["default_phonemizer"] = bank.character.get("default_phonemizer")
    out["issues"] = issues.items
    out["issue_summary"] = issues.summary()
    if not check:
        # probe without --check keeps only errors that block loading
        out["issues"] = [i for i in issues.items if i["severity"] == "error"]
    return out


def _character_summary(cy):
    if not cy:
        return None
    keep = ("name", "singer_type", "author", "voice", "web", "version", "default_phonemizer", "text_file_encoding")
    out = {k: cy[k] for k in keep if k in cy}
    if cy.get("subbanks"):
        out["subbanks"] = cy["subbanks"]
    return out


def _probe_ds_config(root, role, cfg, bank, issues):
    rel_cfg = _rel(root, cfg.path)
    info = {
        "path": rel_cfg,
        "explicit": cfg.explicit,
        "frame_ms": round(cfg.frame_ms, 4),
        "use_variable_depth": cfg.use_variable_depth,
        "max_depth_normalized": cfg.max_depth,
    }
    if cfg.unknown:
        info["unknown_keys"] = sorted(cfg.unknown)
        issues.add("info", "dsconfig_unknown_keys", f"keys not read by openutau: {sorted(cfg.unknown)}", file=rel_cfg)
    ksr = cfg.key_shift_range()
    if ksr:
        info["key_shift_range"] = ksr

    # phonemes
    ppath = cfg.file("phonemes")
    if ppath and os.path.isfile(ppath):
        table, fmt = ds.load_phonemes(ppath)
        prefixes = sorted({ds.phoneme_language(p) for p in table if "/" in p})
        info["phonemes"] = {
            "file": _rel(root, ppath),
            "format": fmt + (" (line index)" if fmt == "txt" else " (name -> id)"),
            "count": len(table),
            "language_prefixes": prefixes,
            "sample": list(table)[:24],
        }
        if fmt == "txt":
            with open(ppath, encoding="utf-8-sig") as f:
                lines = f.read().splitlines()
            if len(lines) != len(table):
                issues.add("warning", "phoneme_duplicates", f"{len(lines) - len(table)} duplicate lines in phoneme list; later index wins", file=_rel(root, ppath))
            if "" in table:
                issues.add("info", "phoneme_blank", f"blank line at index {table['']} in phoneme list (usually the <PAD> slot)", file=_rel(root, ppath))
        cfg._phoneme_table = table
    else:
        cfg._phoneme_table = None
        issues.add("error", "phonemes_missing", f"phoneme list not found: {ppath}", file=rel_cfg)

    # languages
    if cfg["use_lang_id"] or cfg.get("languages"):
        lpath = cfg.file("languages")
        if lpath and os.path.isfile(lpath):
            ids = ds.load_languages(lpath)
            info["languages"] = {"file": _rel(root, lpath), "ids": ids}
            if cfg._phoneme_table:
                used = {ds.phoneme_language(p) for p in cfg._phoneme_table if "/" in p}
                unknown = sorted(used - set(ids))
                if unknown:
                    issues.add("warning", "language_prefix_unknown", f"phoneme prefixes {unknown} are not in the languages file", file=_rel(root, lpath))
        elif cfg["use_lang_id"]:
            issues.add("error", "languages_missing", f"use_lang_id is true but the languages file is missing ({lpath})", file=rel_cfg)

    # speakers
    if cfg.get("speakers"):
        hs = int(cfg["hidden_size"])
        spk = []
        for s in cfg["speakers"]:
            p = os.path.join(cfg.dir, f"{s}.emb")
            entry = {"name": s, "file": _rel(root, p), "exists": os.path.isfile(p)}
            if entry["exists"]:
                _, n = ds.read_speaker_embed(p, hs)
                entry["floats"] = n
                if n != hs:
                    issues.add("error", "speaker_size", f"{s}.emb has {n} float32 values, hidden_size is {hs}", file=entry["file"])
            else:
                issues.add("error", "speaker_missing", f"speaker embedding {s}.emb not found", file=entry["file"])
            spk.append(entry)
        info["speakers"] = {"hidden_size": hs, "list": spk}

    # models
    roles = {"": "acoustic"} if role == "acoustic" else {}
    models = {}
    model_keys = {"acoustic": ["acoustic"], "dsdur": ["linguistic", "dur"], "dspitch": ["linguistic", "pitch"], "dsvariance": ["linguistic", "variance"]}[role]
    for key in model_keys:
        mpath = cfg.file(key)
        if not mpath:
            issues.add("error", "model_unset", f"'{key}' is not set in {rel_cfg}", file=rel_cfg)
            continue
        if not os.path.isfile(mpath):
            issues.add("error", "model_missing", f"{key} model not found: {mpath}", file=rel_cfg)
            continue
        desc = onnxinfo.describe(mpath)
        desc["file"] = _rel(root, mpath)
        if "error" in desc:
            issues.add("error", "model_unreadable", desc["error"], file=desc["file"])
        else:
            sig_role = key if key != "linguistic" else f"linguistic_{role[2:]}"
            if sig_role == "linguistic_dur":
                sig_role = "linguistic_dur"
            actual = [i["name"] for i in desc["inputs"]]
            exp = signatures.expected_inputs(sig_role, cfg, dur_inputs=actual if key == "dur" else None)
            cmp = signatures.compare(exp, actual)
            desc["flags_vs_graph"] = cmp
            if cmp["graph_needs_but_flags_omit"]:
                issues.add("warning", "model_inputs", f"{key} graph has inputs the dsconfig flags don't account for: {cmp['graph_needs_but_flags_omit']}; they will be fed from the graph signature", file=desc["file"])
            if cmp["flags_feed_but_graph_lacks"]:
                issues.add("info", "model_inputs", f"dsconfig flags imply inputs the {key} graph lacks: {cmp['flags_feed_but_graph_lacks']}; they will not be fed", file=desc["file"])
        models[key] = desc
    info["models"] = models
    del roles

    # submodel frame rate vs acoustic
    if role != "acoustic" and abs(cfg.frame_ms - bank.config.frame_ms) > 1e-6:
        issues.add("info", "frame_rate_differs", f"{role} frame is {cfg.frame_ms:.3f} ms vs acoustic {bank.config.frame_ms:.3f} ms; curves will be resampled per padded segment", file=rel_cfg)
    return info


def _probe_dict(root, path, cfg, issues):
    rel = _rel(root, path)
    try:
        d = ds.DsDict(path)
    except Exception as e:  # noqa: BLE001
        issues.add("error", "dict_unreadable", f"cannot parse: {e}", file=rel)
        return {"error": str(e)}
    types = {}
    for t in d.symbols.values():
        types[t] = types.get(t, 0) + 1
    info = {
        "language": ds.dict_language(path) or None,
        "symbols": len(d.symbols),
        "symbol_types": types,
        "entries": len(d.entries),
        "sample_entries": dict(list(d.entries.items())[:6]),
    }
    if d.other_keys:
        info["other_keys"] = d.other_keys
    if d.dropped:
        sample = d.dropped[:10]
        issues.add("warning", "dict_unknown_symbol", f"{len(d.dropped)} entry phonemes are not declared in symbols and openutau would silently drop them, e.g. {sample}", file=rel)
    table = getattr(cfg, "_phoneme_table", None)
    if table:
        lang = ds.dict_language(path)
        not_in_model = []
        for s in d.symbols:
            if s in ("SP", "AP"):
                continue
            if s not in table and not (lang and f"{lang}/{s}" in table):
                not_in_model.append(s)
        if not_in_model:
            issues.add("warning", "dict_symbol_not_in_model", f"{len(not_in_model)} dictionary symbols are not in the phoneme list: {not_in_model[:20]}", file=rel)
        info["symbols_not_in_model"] = len(not_in_model)
    bad_types = sorted({t for t in d.symbols.values() if t not in ("vowel", "consonant", "semivowel", "liquid", "")})
    if bad_types:
        issues.add("warning", "dict_symbol_type", f"unknown symbol types {bad_types} (expected vowel/consonant/semivowel/liquid)", file=rel)
    return info


def _voice_modes(bank, issues):
    subs = bank.subbanks()
    speakers = bank.config.get("speakers") or []
    modes = []
    if not subs:
        if speakers:
            for s in speakers:
                modes.append({"name": os.path.basename(s), "speaker": s, "source": "dsconfig speakers"})
        else:
            modes.append({"name": "default", "speaker": None, "source": "single-speaker model"})
        return modes
    for i, sb in enumerate(subs):
        if not isinstance(sb, dict):
            continue
        sb = {common.camel_to_snake(k): v for k, v in sb.items()}
        suffix = sb.get("suffix") or ""
        entry = {"index": i + 1, "name": sb.get("color") or suffix or f"mode{i + 1}", "suffix": suffix, "tone_ranges": sb.get("tone_ranges") or []}
        if speakers:
            match = _speaker_for_suffix(speakers, suffix)
            entry["speaker"] = match
            if match is None:
                issues.add("warning", "voice_mode_no_speaker", f"subbank '{entry['name']}' suffix '{suffix}' matches no dsconfig speaker; openutau falls back to the first speaker")
        modes.append(entry)
    return modes


def _speaker_for_suffix(speakers, suffix):
    """DiffSingerSpeakerEmbedManager.getSpeakerIndexBySuffix: exact match, then path-tail match."""
    if suffix in speakers:
        return suffix
    sf = [s for s in suffix.replace("\\", "/").split("/")]
    for s in speakers:
        sp = s.replace("\\", "/").split("/")
        if len(sf) <= len(sp) and sp[-len(sf):] == sf:
            return s
    return None


# ---- utau -----------------------------------------------------------------------------------

def _wav_info(path):
    import soundfile as sf

    try:
        info = sf.info(path)
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}
    bits = {"PCM_16": 16, "PCM_24": 24, "PCM_32": 32, "PCM_U8": 8, "PCM_S8": 8, "FLOAT": 32, "DOUBLE": 64}.get(info.subtype)
    return {"sr": info.samplerate, "channels": info.channels, "subtype": info.subtype, "bits": bits, "ms": 1000.0 * info.frames / info.samplerate}


def probe_utau(root, check):
    issues = Issues()
    bank = utau.UtauBank(root)
    prefixes, suffixes = bank.affixes()
    all_aliases = [o.alias for s in bank.oto_sets for o in s.otos if o.valid]
    style, per_set_style, evidence = utau.bank_reclist(bank)
    out = {
        "name": bank.name,
        "readme_files": common.find_readmes(root),
        "character_txt": bank.character_txt,
        "character_yaml": _character_summary(bank.character),
        "default_phonemizer": bank.character.get("default_phonemizer"),
        "tree": common.tree(root, max_depth=2),
        "reclist": {"style": style, "per_oto_set": per_set_style, "evidence": evidence},
        "config_files": common.config_files(root),
        "prefix_map": None,
        "subbanks": bank.subbanks,
        "presamp_ini": os.path.isfile(os.path.join(root, "presamp.ini")),
    }
    if bank.prefix_map is not None:
        out["prefix_map"] = {
            "encoding": bank.prefix_map_encoding,
            "groups": [{"prefix": p, "suffix": s, "tones": utau.tone_ranges(t)} for (p, s), t in bank.prefix_map.items()],
        }
    sets = []
    wav_cache = {}
    for s in bank.oto_sets:
        valid = [o for o in s.otos if o.valid and not o.synthesized]
        entry = {
            "folder": s.name or ".",
            "encoding": s.encoding,
            "encoding_how": s.encoding_how,
            "lines": len([o for o in s.otos if not o.synthesized]),
            "valid": len(valid),
            "invalid": len([o for o in s.otos if not o.valid]),
            "aliases_from_unlisted_wavs": len([o for o in s.otos if o.synthesized]),
            "sample_aliases": [o.alias for o in valid[:10]],
        }
        if s.encoding_how in ("guessed", "fallback-with-replacement"):
            issues.add("warning", "encoding_guess", f"oto.ini encoding was {s.encoding_how}: {s.encoding}. add '#Charset:<name>' or character.yaml text_file_encoding to pin it", file=_rel(root, s.path))
        if check:
            fmt = _check_oto_set(root, s, issues, wav_cache)
            entry["wav_formats"] = fmt
        sets.append(entry)
    out["oto_sets"] = sets
    out["alias_count"] = len(set(all_aliases))
    if not bank.oto_sets:
        issues.add("error", "no_oto", "no oto.ini found", file=root)
    if check:
        _check_aliases(root, bank, issues)
        _check_gaps(bank, style, evidence, prefixes, suffixes, issues, out)
        _check_bank_formats(wav_cache, issues)
    out["issues"] = issues.items
    out["issue_summary"] = issues.summary()
    return out


def _check_oto_set(root, s, issues, wav_cache):
    fmts = {}
    pre_vals = []
    short_regions = []
    for o in s.otos:
        where = {"file": _rel(root, s.path), "line": o.line_no + 1 if o.line_no >= 0 else None, "alias": o.alias}
        if not o.valid:
            code = "wav_missing" if o.error.startswith("sound file missing") else "oto_unparsable"
            issues.add("error", code, o.error, **where)
            continue
        wpath = os.path.join(s.dir, o.wav)
        if wpath not in wav_cache:
            wav_cache[wpath] = _wav_info(wpath)
        wi = wav_cache[wpath]
        if "error" in wi:
            issues.add("error", "wav_unreadable", f"cannot open {o.wav}: {wi['error']}", **where)
            continue
        key = f"{wi['sr']}Hz/{wi['bits']}bit/{wi['channels']}ch"
        fmts[key] = fmts.get(key, 0) + 1
        if o.synthesized:
            continue
        _check_oto_values(o, wi["ms"], issues, where, short_regions)
        pre_vals.append((o.preutter, o, where))
        if o.alias != o.alias.strip():
            issues.add("info", "alias_space", "alias starts or ends with a space", **where)
        elif o.alias.count(" ") > 1:
            issues.add("info", "alias_spaces", "alias has more than one space", **where)
        if "　" in o.alias:
            issues.add("info", "alias_fullwidth_space", "alias contains a full-width space", **where)
        if unicodedata.normalize("NFC", o.alias) != o.alias:
            issues.add("info", "alias_nfd", "alias is not nfc-normalized (common after mac zips)", **where)
    # outlier preutterances, compared within the same alias shape (heads vs pairs vs singles)
    groups = {}
    for p, o, where in pre_vals:
        groups.setdefault(_alias_shape(o.alias), []).append((p, o, where))
    for shape, items in groups.items():
        if len(items) < 8:
            continue
        vals = [p for p, _, _ in items]
        med = statistics.median(vals)
        mad = statistics.median([abs(v - med) for v in vals]) or 1.0
        value_counts = {}
        for v in vals:
            value_counts[v] = value_counts.get(v, 0) + 1
        for p, o, where in items:
            # a value shared by several aliases is a deliberate setting, not a slip
            if value_counts[p] >= 3:
                continue
            if abs(p - med) > 8 * mad and abs(p - med) > 120:
                issues.add("info", "preutter_outlier", f"preutterance {p:.0f} ms is far from the median {med:.0f} ms of this set's {shape} aliases", **where)
    if short_regions:
        issues.add(
            "info",
            "short_stretch_region",
            f"{len(short_regions)} aliases have under 30 ms between the fixed region and cutoff. fine for consonant-only or transition samples, a problem if they carry a sustained vowel. e.g. {short_regions[:10]}",
            file=_rel(root, s.path),
        )
    # duplicates within the set
    seen = {}
    for o in s.otos:
        if o.valid and not o.synthesized:
            if o.alias in seen:
                issues.add("error", "duplicate_alias", f"alias '{o.alias}' also on line {seen[o.alias] + 1}; the first one wins", file=_rel(root, s.path), line=o.line_no + 1, alias=o.alias)
            else:
                seen[o.alias] = o.line_no
    return fmts


def _alias_shape(alias):
    toks = alias.split(" ")
    if len(toks) == 1:
        return "single"
    if toks[0] == "-":
        return "head"
    if toks[-1] in ("-", "R"):
        return "tail"
    return "pair"


def _check_oto_values(o, file_ms, issues, where, short_regions=None):
    """VoicebankErrorChecker.CheckOto, plus a few heuristics on top."""
    def err(code, msg):
        issues.add("error", code, msg, **where)

    if o.offset < 0:
        err("offset_negative", f"offset {o.offset} < 0")
    if o.offset > file_ms:
        err("offset_out_of_file", f"offset {o.offset:.1f} ms is past the end of the file ({file_ms:.1f} ms)")
    if o.preutter < 0:
        err("preutter_negative", f"preutterance {o.preutter} < 0")
    if o.preutter + o.offset > file_ms:
        err("preutter_out_of_file", f"offset+preutterance {o.offset + o.preutter:.1f} ms > file {file_ms:.1f} ms")
    if o.consonant < 0:
        err("consonant_negative", f"consonant {o.consonant} < 0")
    if o.consonant + o.offset > file_ms:
        err("consonant_out_of_file", f"offset+consonant {o.offset + o.consonant:.1f} ms > file {file_ms:.1f} ms")
    if o.overlap + o.offset > file_ms:
        err("overlap_out_of_file", f"offset+overlap {o.offset + o.overlap:.1f} ms > file {file_ms:.1f} ms")
    cut = o.cutoff_ms(file_ms)
    if cut < o.offset + o.preutter:
        err("cutoff_before_preutter", f"cutoff ends at {cut:.1f} ms, before the preutterance point {o.offset + o.preutter:.1f} ms")
    if cut < o.offset + o.overlap:
        err("cutoff_before_overlap", f"cutoff ends at {cut:.1f} ms, before the overlap point {o.offset + o.overlap:.1f} ms")
    if cut <= o.offset + o.consonant:
        err("cutoff_before_consonant", f"cutoff ends at {cut:.1f} ms, at or before the end of the fixed region {o.offset + o.consonant:.1f} ms; nothing is left to stretch")
    if cut > file_ms + 50:
        err("cutoff_out_of_file", f"cutoff ends at {cut:.1f} ms, {cut - file_ms:.0f} ms past the file end {file_ms:.1f} ms")
    elif cut > file_ms + 0.5:
        issues.add("warning", "cutoff_past_end", f"cutoff ends {cut - file_ms:.0f} ms past the file end; resamplers clamp this, but the oto is off", **where)
    # heuristics
    if o.overlap > o.preutter and o.preutter > 0:
        issues.add("info", "overlap_gt_preutter", f"overlap {o.overlap:.0f} ms > preutterance {o.preutter:.0f} ms: the crossfade starts after the note onset", **where)
    if o.preutter > 600:
        issues.add("warning", "preutter_large", f"preutterance {o.preutter:.0f} ms is unusually long", **where)
    if o.consonant < o.preutter and o.consonant >= 0:
        issues.add("info", "consonant_lt_preutter", f"fixed region {o.consonant:.0f} ms ends before the preutterance {o.preutter:.0f} ms; part of the consonant will be stretched", **where)
    stretch = cut - (o.offset + o.consonant)
    if 0 < stretch < 30 and short_regions is not None:
        short_regions.append((o.alias, round(stretch)))


def _check_aliases(root, bank, issues):
    owner = {}
    for s in bank.oto_sets:
        for o in s.otos:
            if not o.valid:
                continue
            if o.alias in owner and owner[o.alias] is not s:
                first = owner[o.alias]
                issues.add(
                    "warning",
                    "shadowed_alias",
                    f"alias '{o.alias}' exists in '{first.name or '.'}' and '{s.name or '.'}'; '{first.name or '.'}' is used",
                    file=_rel(root, s.path),
                    alias=o.alias,
                )
            else:
                owner.setdefault(o.alias, s)
    # wav names that collide ignoring case (breaks on case-insensitive file systems)
    for s in bank.oto_sets:
        names = {}
        for o in s.otos:
            if o.wav:
                names.setdefault(o.wav.lower(), set()).add(o.wav)
        for group in names.values():
            if len(group) > 1:
                issues.add("error", "wav_case_collision", f"wav names differ only by case: {sorted(group)}", file=_rel(root, s.path))


def _check_gaps(bank, style, evidence, prefixes, suffixes, issues, out):
    """aliases the bank's own pattern implies but lacks. derived from the bank's aliases, not a
    hardcoded reclist: for vcv, every '<vowel> <unit>' for each unit sung after '-'; for cvvc,
    every '<vowel> <consonant>' across seen vowels and consonants; for multi-pitch banks, every
    base alias in every pitch subbank."""
    amap = bank.alias_map()
    aliases = set(amap)
    base_aliases = {utau.strip_affixes(a, prefixes, suffixes) for a in aliases}
    missing = []
    pairs = [a.split(" ") for a in base_aliases if a.count(" ") == 1]
    units = {a for a in base_aliases if " " not in a} | {r for l, r in pairs if l == "-"}
    # vowels: left tokens of pairs that are themselves sung units ('a' and '- a' exist)
    vowels = {l for l, r in pairs if l in units and l != "-"}
    styles = set(style.split("+"))
    if "vcv" in styles:
        covered = {r for l, r in pairs if l in vowels and r in units}
        for v in sorted(vowels):
            for h in sorted(covered):
                if f"{v} {h}" not in base_aliases:
                    missing.append(f"{v} {h}")
    if "cvvc" in styles:
        cons = {r for l, r in pairs if l in vowels and r not in units and r not in ("-", "R")}
        for v in sorted(vowels):
            for c in sorted(cons):
                if f"{v} {c}" not in base_aliases:
                    missing.append(f"{v} {c}")
    gaps = {"style_pattern": missing[:200], "style_pattern_count": len(missing)}
    if missing:
        issues.add("info", "pattern_gaps", f"{len(missing)} aliases implied by this bank's own {style} pattern are missing, e.g. {missing[:12]}; a phonemizer will substitute or fail on these")
    # pitch subbanks: every base alias should exist with every suffix
    subs = [s for s in bank.subbanks if s["suffix"] or s["prefix"]]
    if len(subs) > 1:
        per_sub = {}
        for sb in subs:
            lacking = []
            for b in sorted(base_aliases):
                if f"{sb['prefix']}{b}{sb['suffix']}" not in aliases:
                    lacking.append(b)
            if lacking:
                per_sub[f"{sb['prefix']}*{sb['suffix']}"] = {"count": len(lacking), "sample": lacking[:12]}
        if per_sub:
            gaps["per_subbank"] = per_sub
            for k, v in per_sub.items():
                issues.add("warning", "subbank_gaps", f"subbank {k} lacks {v['count']} aliases present elsewhere, e.g. {v['sample']}")
    out["alias_gaps"] = gaps


def _check_bank_formats(wav_cache, issues):
    infos = [w for w in wav_cache.values() if "error" not in w]
    if not infos:
        return
    srs = {}
    for w in infos:
        srs[(w["sr"], w["bits"], w["channels"])] = srs.get((w["sr"], w["bits"], w["channels"]), 0) + 1
    main = max(srs, key=srs.get)
    for (sr, bits, ch), n in srs.items():
        if (sr, bits, ch) != main:
            issues.add("warning", "format_mismatch", f"{n} wavs are {sr} Hz/{bits}-bit/{ch}ch while most are {main[0]} Hz/{main[1]}-bit/{main[2]}ch")
    if main[0] != 44100:
        issues.add("warning", "sample_rate", f"bank is {main[0]} Hz; classic resamplers expect 44100 Hz")
    if main[1] != 16:
        issues.add("info", "bit_depth", f"bank is {main[1]}-bit; classic resamplers expect 16-bit")
    if main[2] != 1:
        issues.add("info", "channels", f"bank wavs have {main[2]} channels; only the first is used")


# ---- banks listing ---------------------------------------------------------------------------

def list_banks(dirs, vocoder_dirs=None):
    out = []
    for d in dirs:
        d = os.path.abspath(d)
        is_root = common.has_marker(d) or os.path.isfile(os.path.join(d, "oto.ini"))
        roots = [d] if is_root else common.scan(d)
        for r in roots:
            kind, ev = common.detect(r)
            entry = {"path": r, "type": kind}
            try:
                if kind == "diffsinger":
                    b = ds.DsBank(r)
                    entry["name"] = b.name
                    langs = set()
                    for _, cfg in b.all_configs():
                        lp = cfg.file("languages")
                        if cfg["use_lang_id"] and lp and os.path.isfile(lp):
                            langs |= set(ds.load_languages(lp))
                    for p in ds.find_dicts(r):
                        if ds.dict_language(p):
                            langs.add(ds.dict_language(p))
                    entry["languages"] = sorted(langs)
                    entry["voice_modes"] = [m["name"] for m in _voice_modes(b, Issues())]
                    voc = ds.resolve_vocoder(r, b.config, vocoder_dirs)
                    entry["missing_dependencies"] = [voc["error"]] if voc["source"] == "missing" else []
                    entry["submodels"] = sorted(b.submodels)
                elif kind == "utau":
                    b = utau.UtauBank(r, check_wavs=False)
                    entry["name"] = b.name
                    entry["reclist"], _, _ = utau.bank_reclist(b)
                    entry["voice_modes"] = sorted({s["color"] for s in b.subbanks if s["color"]}) or ["default"]
                    entry["oto_sets"] = len(b.oto_sets)
                    entry["missing_dependencies"] = []
                else:
                    entry["why"] = ev
            except Exception as e:  # noqa: BLE001
                entry["error"] = f"{type(e).__name__}: {e}"
            out.append(entry)
    return out
