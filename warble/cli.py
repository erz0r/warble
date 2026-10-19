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
