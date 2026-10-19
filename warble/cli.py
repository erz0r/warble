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
]


def load_score(a):
    from .errors import WarbleError
    from .score import apply_defaults, load

    if a.expr:
        s = load(a.expr, inline=True, defaults={"bank": a.bank, "lang": a.lang, "voice": a.voice, "bpm": a.bpm})
    elif a.score:
        s = load(a.score, defaults={"lyrics": a.lyrics, "lang": a.lang} if a.score.lower().endswith((".mid", ".midi")) else None)
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
        arg("--provider", choices=["cpu", "coreml", "cuda"], help="onnxruntime execution provider"),
        VOCODER_ARG,
    ],
)
def cmd_sing(a):
    from . import onnxrun
    from .sing import sing

    if a.provider:
        onnxrun.set_provider(a.provider)
    score = load_score(a)
    rng = None
    if a.range:
        r = sorted(_ranges(a.range))
        rng = (r[0], r[-1])
    return sing(score, a.out, steps=a.steps, depth=a.depth, seed=a.seed, sample_rate=a.sample_rate, engine=a.engine,
                phrase_filter=_ranges(a.phrase) if a.phrase else None, note_range=rng, vocoder_dirs=a.vocoders,
                allow_unknown=a.allow_unknown, resampler=a.resampler)


@command(
    "phonemize",
    "phonemes (diffsinger) or aliases (utau) per note with timings in ms and frames. no audio.",
    SCORE_ARGS + [arg("--engine", choices=["ds", "utau"]), arg("--seed", type=int), VOCODER_ARG],
)
def cmd_phonemize(a):
    from .phonemize import phonemize

    return phonemize(load_score(a), engine=a.engine, seed=a.seed, vocoder_dirs=a.vocoders)


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
