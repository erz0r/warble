"""command-line entry point. every command is declared once in COMMANDS so the mcp server can be
generated from the same table and stay feature-identical.

stdout is always one json document; logs and progress go to stderr.
"""

import argparse
import json
import sys

from .errors import WarbleError

COMMANDS = {}


def command(name, help, args=()):
    """register a command. args are (flags, kwargs) pairs for argparse, also used for the mcp schema."""

    def deco(fn):
        COMMANDS[name] = {"fn": fn, "help": help, "args": list(args)}
        return fn

    return deco


def arg(*flags, **kwargs):
    return (flags, kwargs)


VOCODER_ARG = arg("--vocoders", action="append", default=None, help="extra folder of installed vocoders (repeatable)")


@command(
    "probe",
    "describe a bank from its own files (json). --check adds bank qa.",
    [arg("bank", help="path to a voicebank folder"), arg("--check", action="store_true", help="run bank qa"), VOCODER_ARG],
)
def cmd_probe(a):
    from .probe import probe

    return probe(a.bank, check=a.check, vocoder_dirs=a.vocoders)


@command(
    "banks",
    "list detected banks with type, languages, voice modes and missing dependencies.",
    [arg("dirs", nargs="*", default=["banks"], help="folders to scan (default: ./banks)"), VOCODER_ARG],
)
def cmd_banks(a):
    from .probe import list_banks

    return {"banks": list_banks(a.dirs, a.vocoders)}


SCORE_ARGS = [
    arg("score", nargs="?", help="score file (.txt, .json, .ust, .ustx, .mid, .musicxml)"),
    arg("-e", "--expr", help="inline notes instead of a file, e.g. \"ら:C4:1 ら:D4:1/2 r:1\""),
    arg("--bank", help="bank for tracks that don't name one"),
    arg("--lang", help="language for tracks that don't name one"),
    arg("--voice", help="voice mode for tracks that don't name one"),
    arg("--bpm", type=float, help="tempo for inline scores"),
    arg("--lyrics", help="lyrics to assign to an imported midi (see `lyrics`)"),
    arg("--midi-track", help="midi import: track index or name (default: the one with most notes)"),
    arg("--quantize", type=int, help="midi import: snap to this many ticks (480 = a beat, 120 = a 16th)"),
]


def load_score(a):
    from .errors import WarbleError
    from .score import apply_defaults, load

    if a.expr:
        s = load(a.expr, inline=True, defaults={"bank": a.bank, "lang": a.lang, "voice": a.voice, "bpm": a.bpm})
    elif a.score:
        midi = a.score.lower().endswith((".mid", ".midi"))
        s = load(a.score, defaults={"lyrics": a.lyrics, "lang": a.lang, "track": a.midi_track, "quantize": a.quantize} if midi else None)
    else:
        raise WarbleError("no_score", "give a score file or -e \"notes\"")
    return apply_defaults(s, bank=a.bank, lang=a.lang, voice=a.voice)


def _ranges(text):
    """'3' -> {3}; '2,5-7' -> {2,5,6,7}."""
    out = set()
    for part in (text or "").split(","):
        if "-" in part:
            lo, hi = part.split("-", 1)
            out |= set(range(int(lo), int(hi) + 1))
        elif part.strip():
            out.add(int(part))
    return out


@command(
    "sing",
    "render a score to audio. stdout: json report (paths, duration, phrases, per-stage timing, warnings).",
    SCORE_ARGS + [
        arg("-o", "--out", default="out/sing.wav", help="output .wav or .flac"),
        arg("--steps", type=int, help="diffusion steps (acoustic); default 20"),
        arg("--depth", type=float, help="shallow diffusion depth 0..1, capped by the bank's max_depth"),
        arg("--seed", type=int, help="seed the diffusion noise for reproducible a/b renders"),
        arg("--engine", choices=["ds", "utau"], help="force an engine when a bank could go either way"),
        arg("--phrase", help="render only these phrases, e.g. 3 or 2,5-7"),
        arg("--range", help="render only phrases touching these note numbers, e.g. 10-20"),
        arg("--sample-rate", type=int, default=44100),
        arg("--allow-unknown", action="store_true", help="render what it can and list unknown lyrics instead of failing"),
        arg("--resampler", help="utau: resampler name from resamplers/ (default: built-in)"),
        arg("--wavtool", help="utau: wavtool name from resamplers/ (default: built-in)"),
        arg("--provider", choices=["cpu", "coreml", "cuda"], help="onnxruntime execution provider"),
        arg("--no-cache", action="store_true", help="re-render everything (phrase and tensor caches off)"),
        VOCODER_ARG,
    ],
)
def cmd_sing(a):
    from . import onnxrun
    from .sing import sing

    if a.provider:
        onnxrun.set_provider(a.provider)
    if a.no_cache:
        onnxrun.CACHE_ENABLED = False
    score = load_score(a)
    rng = None
    if a.range:
        r = sorted(_ranges(a.range))
        rng = (r[0], r[-1])
    report = sing(score, a.out, steps=a.steps, depth=a.depth, seed=a.seed, sample_rate=a.sample_rate, engine=a.engine,
                  phrase_filter=_ranges(a.phrase) if a.phrase else None, note_range=rng, vocoder_dirs=a.vocoders,
                  allow_unknown=a.allow_unknown, resampler=a.resampler, wavtool=a.wavtool, use_cache=not a.no_cache)
    if getattr(score, "import_report", None):
        report["import"] = score.import_report
    return report


@command(
    "lyrics",
    "split text into syllables/mora for a language; with a score, assign them to its notes and write the result.",
    [
        arg("text", help="lyric text (japanese may include kanji; readings are reported)"),
        arg("--lang", required=True, help="ja, en, zh, or other (whitespace tokens)"),
        arg("--score", help="score to assign onto (.txt, .json, .ust, .mid, ...)"),
        arg("-o", "--out", help="write the assigned score here (.txt score format, or .mid)"),
        arg("--sokuon", choices=["separate", "attach"], default="separate", help="japanese っ: its own note, or attached to the previous mora"),
        arg("--midi-track"),
        arg("--quantize", type=int),
    ],
)
def cmd_lyrics(a):
    from .lyrics import assign, split
    from .score import load

    units, readings = split(a.text, a.lang, a.sokuon)
    out = {"units": [u["lyric"] if u["notes"] == 1 else f"{u['lyric']}x{u['notes']}" for u in units], "kanji_readings": readings}
    if a.score:
        midi = a.score.lower().endswith((".mid", ".midi"))
        s = load(a.score, defaults={"track": a.midi_track, "quantize": a.quantize, "lang": a.lang} if midi else None)
        notes = s.tracks[0].notes
        out["assignment"] = assign(notes, units)
        out["notes"] = [f"{n.lyric}" for n in notes]
        if a.out:
            if a.out.lower().endswith((".mid", ".midi")):
                from .formats import midi as midifmt

                midifmt.save(s, a.out)
            else:
                for t in s.tracks:
                    t.lang = t.lang or a.lang
                with open(a.out, "w", encoding="utf-8") as f:
                    f.write(s.to_text())
            out["written"] = a.out
    return out


@command(
    "export",
    "convert a score to another format: .txt (score text), .json, .mid, .ust, .ustx, .musicxml.",
    SCORE_ARGS + [arg("-o", "--out", required=True)],
)
def cmd_export(a):
    import json as _json

    score = load_score(a)
    ext = a.out.lower().rsplit(".", 1)[-1]
    if ext in ("mid", "midi"):
        from .formats import midi as midifmt

        midifmt.save(score, a.out)
    elif ext == "ust":
        from .formats import ust as ustfmt

        ustfmt.save(score, a.out)
    elif ext == "ustx":
        from .formats import ustx as ustxfmt

        ustxfmt.save(score, a.out)
    elif ext in ("musicxml", "xml"):
        from .formats import musicxml as mxfmt

        mxfmt.save(score, a.out)
    elif ext == "json":
        with open(a.out, "w", encoding="utf-8") as f:
            _json.dump(score.to_json(), f, ensure_ascii=False, indent=1)
    else:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(score.to_text())
    return {"written": a.out, "tracks": len(score.tracks), "notes": sum(len(t.notes) for t in score.tracks)}


@command(
    "phonemize",
    "phonemes (diffsinger) or aliases (utau) per note with timings in ms and frames. no audio.",
    SCORE_ARGS + [arg("--engine", choices=["ds", "utau"]), arg("--seed", type=int), VOCODER_ARG],
)
def cmd_phonemize(a):
    from .phonemize import phonemize

    return phonemize(load_score(a), engine=a.engine, seed=a.seed, vocoder_dirs=a.vocoders)


def _notes_arg(text):
    return sorted(_ranges(text)) if text else None


@command(
    "inspect",
    "images plus a json report describing a render: pitch vs intent per note, transitions, vibrato, loudness, timbre, artifacts, listening notes.",
    [
        arg("wav"),
        arg("--score", help="score or .render.json for intent (default: <wav>.render.json written by sing)"),
        arg("--notes", help="only these notes, e.g. 12-20"),
        arg("--ref", help="another wav to compare against (a/b images and numeric diff)"),
        arg("-o", "--out-dir", help="where to write images and report.json (default: <wav>_inspect/)"),
        arg("--no-images", action="store_true"),
        arg("--no-asr", action="store_true", help="skip the speech-recognition intelligibility check"),
        arg("--extractors", default="harvest,dio", help="comma-separated f0 extractors"),
    ],
)
def cmd_inspect(a):
    from .perception.inspect import inspect

    return inspect(a.wav, score=a.score, notes=_notes_arg(a.notes), ref=a.ref, out_dir=a.out_dir, images=not a.no_images,
                   extractors=tuple(a.extractors.split(",")), asr=not a.no_asr)


@command(
    "analyze",
    "run the inspect pipeline on any audio (a real singer too): notes are segmented from the pitch when there is no score.",
    [arg("wav"), arg("--score"), arg("-o", "--out-dir"), arg("--no-images", action="store_true")],
)
def cmd_analyze(a):
    from .perception.inspect import analyze

    return analyze(a.wav, score=a.score, out_dir=a.out_dir, images=not a.no_images)


@command(
    "compare",
    "a/b two renders: images, global diff (dtw-aligned mel distance, pitch, timing, loudness), per-note metric deltas and a verdict.",
    [arg("a"), arg("b"), arg("-o", "--out-dir"), arg("--no-images", action="store_true")],
)
def cmd_compare(a):
    from .perception.inspect import compare

    return compare(a.a, a.b, out_dir=a.out_dir, images=not a.no_images)


@command(
    "pitch",
    "pitch tools. `pitch extract <wav>`: f0 from every available extractor, where they disagree, and a curves file.",
    [arg("action", choices=["extract"]), arg("wav"), arg("--extractors", help="comma-separated (default: all available)"), arg("-o", "--out")],
)
def cmd_pitch(a):
    from .perception.inspect import pitch_extract

    return pitch_extract(a.wav, a.extractors.split(",") if a.extractors else None, a.out)


@command("resamplers", "utau resamplers and wavtools found in ./resamplers (or $WARBLE_RESAMPLERS), how they run, and their flags.", [])
def cmd_resamplers(a):
    from .utau.resampler import list_tools

    return {"tools": list_tools()}


@command("phonemizers", "available phonemizers with language and which detected banks they fit.", [arg("dirs", nargs="*", default=["banks"])])
def cmd_phonemizers(a):
    from .phonemizer_catalog import catalog

    return catalog(a.dirs)


TUNE_ACTIONS = ["show", "op", "apply", "auto", "undo", "redo", "snapshot", "restore", "diff", "history", "ops",
                "preset-save", "preset-apply", "presets", "import-pitch"]


def _params(pairs):
    out = {}
    for p in pairs or []:
        if "=" not in p:
            from .errors import WarbleError

            raise WarbleError("bad_param", f"-p expects key=value, got '{p}'")
        k, v = p.split("=", 1)
        out[k.strip()] = v
    return out


@command(
    "tune",
    "edit tuning in a project (a score text file) with versioned history. actions: show, op <name>, apply <ops.json>, "
    "auto <tuner>, undo, redo, snapshot <name>, restore <name>, diff [a] [b], history, ops, preset-save <name> <ops.json>, "
    "preset-apply <name>, presets, import-pitch <wav>",
    [
        arg("action", choices=TUNE_ACTIONS),
        arg("project", nargs="?", help="the project file (score text)"),
        arg("args", nargs="*", help="op name / tuner / ops json (file or inline) / snapshot name / versions / wav"),
        arg("-p", "--param", action="append", help="op parameter key=value (repeatable)"),
        arg("--notes", help="selection: note numbers, e.g. 3-7,12"),
        arg("--lyric"), arg("--phrase", help="phrase numbers"), arg("--interval", help="e.g. '>=3' or 'abs>=4'"),
        arg("--min-beats", type=float), arg("--max-beats", type=float), arg("--track"),
        arg("--steps", type=int, help="undo/redo steps"),
    ],
)
def cmd_tune(a):
    import json as _json
    import os as _os

    from .errors import WarbleError
    from .tuning import auto, ops
    from .tuning.project import Project
    from .tuning.show import show

    if a.action == "ops":
        return {"ops": ops.describe(), "tuners": sorted(auto.TUNERS)}
    if a.action == "presets":
        return {"presets": _list_presets(a.project)}
    if not a.project:
        raise WarbleError("no_project", "give the project file")
    proj = Project(a.project)
    sel = {k: v for k, v in {"notes": a.notes, "lyric": a.lyric, "phrase": a.phrase, "interval": a.interval,
                             "min_beats": a.min_beats, "max_beats": a.max_beats, "track": a.track}.items() if v is not None}
    if a.action == "show":
        return show(proj.score(), track=a.track, notes=a.notes)
    if a.action == "history":
        return proj.history()
    if a.action == "undo":
        return proj.undo(a.steps or 1)
    if a.action == "redo":
        return proj.redo(a.steps or 1)
    if a.action == "snapshot":
        return proj.snapshot(a.args[0] if a.args else "snap")
    if a.action == "restore":
        return proj.restore(a.args[0])
    if a.action == "diff":
        return proj.diff(*(a.args[:2] or ["prev", "current"]))
    score = proj.score()
    if a.action == "op":
        if not a.args:
            raise WarbleError("no_op", "name the op", hint=f"ops: {sorted(ops.OPS)}")
        batch = [{"op": a.args[0], **sel, **_params(a.param)}]
    elif a.action in ("apply", "preset-apply"):
        if not a.args:
            raise WarbleError("no_ops", "give a json op list (file or inline) or a preset name")
        if a.action == "preset-apply":
            batch = _load_preset(a.project, a.args[0])
        else:
            src = a.args[0]
            batch = _json.load(open(src, encoding="utf-8")) if _os.path.isfile(src) else _json.loads(src)
        if sel:
            batch = [{**b, **{k: v for k, v in sel.items() if k not in b}} for b in batch]
    elif a.action == "preset-save":
        if len(a.args) < 2:
            raise WarbleError("bad_args", "preset-save <name> <ops.json or inline json>")
        src = a.args[1]
        batch = _json.load(open(src, encoding="utf-8")) if _os.path.isfile(src) else _json.loads(src)
        return {"saved": _save_preset(a.project, a.args[0], batch)}
    elif a.action == "auto":
        if not a.args:
            raise WarbleError("no_tuner", "name the tuner", hint=f"tuners: {sorted(auto.TUNERS)}")
        notes = auto.run(score, a.args[0], track=a.track, notes=a.notes, **_params(a.param))
        res = proj.save_score(score, f"auto {a.args[0]}", {"notes": a.notes, **_params(a.param)})
        return {**res, "tuner": a.args[0], "notes": notes, "show": show(score, track=a.track, notes=a.notes)["table"]}
    elif a.action == "import-pitch":
        from .tuning.refpitch import import_pitch

        if not a.args:
            raise WarbleError("no_wav", "give the reference wav")
        p = _params(a.param)
        info = import_pitch(score, a.args[0], track=a.track, notes=a.notes,
                            offset_ms=float(p["offset_ms"]) if "offset_ms" in p else None)
        res = proj.save_score(score, "import-pitch", {"wav": a.args[0], **p})
        return {**res, **info}
    log = ops.apply(score, batch)
    res = proj.save_score(score, ", ".join(b["op"] for b in batch), {"batch": batch})
    touched = sorted({n for e in log for n in e["notes"]})
    return {**res, "log": log, "show": show(score, track=a.track, notes=",".join(map(str, touched)) if touched else None)["table"]}


def _preset_dirs(project):
    import os as _os

    dirs = []
    if project and _os.path.exists(project):
        dirs.append(_os.path.join(_os.path.dirname(_os.path.abspath(project)), ".warble", "presets"))
    dirs.append(_os.path.join(_os.path.expanduser("~"), ".config", "warble", "presets"))
    return dirs


def _save_preset(project, name, batch):
    import json as _json
    import os as _os

    d = _preset_dirs(project)[0]
    _os.makedirs(d, exist_ok=True)
    p = _os.path.join(d, f"{name}.json")
    with open(p, "w", encoding="utf-8") as f:
        _json.dump(batch, f, ensure_ascii=False, indent=1)
    return p


def _load_preset(project, name):
    import json as _json
    import os as _os

    from .errors import WarbleError
    from .tuning.presets import BUILTIN

    for d in _preset_dirs(project):
        p = _os.path.join(d, f"{name}.json")
        if _os.path.isfile(p):
            return _json.load(open(p, encoding="utf-8"))
    if name in BUILTIN:
        return BUILTIN[name]
    raise WarbleError("preset_missing", f"no preset '{name}'", hint=f"presets: {_list_presets(project)}")


def _list_presets(project):
    import os as _os

    from .tuning.presets import BUILTIN

    names = set(BUILTIN)
    for d in _preset_dirs(project):
        if _os.path.isdir(d):
            names |= {f[:-5] for f in _os.listdir(d) if f.endswith(".json")}
    return sorted(names)


def build_parser():
    p = argparse.ArgumentParser(prog="warble", description=__doc__.splitlines()[0])
    p.add_argument("--pretty", action="store_true", help="indent json output")
    sub = p.add_subparsers(dest="command", required=True)
    for name, spec in COMMANDS.items():
        sp = sub.add_parser(name, help=spec["help"], description=spec["help"])
        sp.add_argument("--pretty", action="store_true", default=argparse.SUPPRESS, help="indent json output")
        for flags, kwargs in spec["args"]:
            sp.add_argument(*flags, **kwargs)
    return p


def emit(obj, pretty=False):
    json.dump(obj, sys.stdout, ensure_ascii=False, indent=2 if pretty else None, default=str)
    sys.stdout.write("\n")


def main(argv=None):
    parser = build_parser()
    a = parser.parse_args(argv)
    try:
        result = COMMANDS[a.command]["fn"](a)
    except WarbleError as e:
        emit(e.to_json(), a.pretty)
        return 2
    emit(result, a.pretty)
    return 0


if __name__ == "__main__":
    sys.exit(main())
