"""generate diffsinger phonemizer goldens with openutau itself.

each tests/parity/cases_ds/<name>.json is {"phonemizer": "<openutau class>", "bank": "<bank dir, relative to
the repo root or absolute>", "lang": "<warble language code>", "bpm": 120, "cases": [...]} (case format: see
ref/harness_ds/Program.cs; same as tests/parity/cases). this runs ref/harness_ds (dotnet), which loads the bank
as a DiffSingerSinger and runs the phonemizer (its duration model included) through SetUp + Process like
PhonemizerRunner, and writes tests/parity/goldens_ds/<name>.json.

build the harness once: cd ref/harness_ds && DOTNET_CLI_TELEMETRY_OPTOUT=1 ../dotnet/dotnet build -c Release -o bin/out

usage: python tests/parity/gen_goldens_ds.py [names...]
"""

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DOTNET = os.environ.get("DOTNET", os.path.join(ROOT, "ref", "dotnet", "dotnet"))
HARNESS = os.path.join(ROOT, "ref", "harness_ds", "bin", "out", "HarnessDs.dll")


def bank_path(bank):
    return bank if os.path.isabs(bank) else os.path.join(ROOT, bank)


def generate(name):
    with open(os.path.join(HERE, "cases_ds", name + ".json"), encoding="utf-8") as f:
        spec = json.load(f)
    bank = bank_path(spec["bank"])
    if not os.path.isdir(bank):
        raise SystemExit(f"{name}: bank not found: {bank}")
    req = {"bank": bank, "phonemizer": spec["phonemizer"], "bpm": spec.get("bpm", 120), "cases": spec["cases"]}
    env = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT="1", DOTNET_NOLOGO="1")
    p = subprocess.run([DOTNET, HARNESS], input=json.dumps(req, ensure_ascii=False).encode(), capture_output=True, env=env, timeout=900)
    if p.returncode != 0:
        raise SystemExit(f"{name}: harness failed\n{p.stderr.decode()[-2000:]}")
    out = json.loads(p.stdout.decode().strip().splitlines()[-1])
    if "error" in out:
        raise SystemExit(f"{name}: {out['error']}")
    golden = {**spec, "results": out["results"]}
    os.makedirs(os.path.join(HERE, "goldens_ds"), exist_ok=True)
    with open(os.path.join(HERE, "goldens_ds", name + ".json"), "w", encoding="utf-8") as f:
        json.dump(golden, f, ensure_ascii=False, indent=1)
    errs = sum(1 for r in out["results"] if r.get("error"))
    notes_err = sum(1 for r in out["results"] for ph in r.get("phonemes") or [] if ph.get("error"))
    print(f"{name}: {len(out['results'])} cases ({errs} raised, {notes_err} notes with errors in openutau)")


if __name__ == "__main__":
    names = sys.argv[1:] or sorted(os.path.splitext(f)[0] for f in os.listdir(os.path.join(HERE, "cases_ds")) if f.endswith(".json"))
    for n in names:
        generate(n)
