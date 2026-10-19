"""generate phonemizer goldens with openutau itself.

each tests/parity/cases/<name>.json is {"phonemizer": "<openutau class>", "bank": "<dir under
tests/parity/banks, or absolute>", "bpm": 120, "cases": [...]} (case format: see ref/harness).
this runs ref/harness (dotnet) on it and writes tests/parity/goldens/<name>.json with the outputs.

usage: python tests/parity/gen_goldens.py [names...]
"""

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DOTNET = os.environ.get("DOTNET", os.path.join(ROOT, "ref", "dotnet", "dotnet"))
HARNESS = os.path.join(ROOT, "ref", "harness", "bin", "out", "Harness.dll")


def bank_path(bank):
    return bank if os.path.isabs(bank) else os.path.join(HERE, "banks", bank)


def generate(name):
    with open(os.path.join(HERE, "cases", name + ".json"), encoding="utf-8") as f:
        spec = json.load(f)
    req = {"bank": bank_path(spec["bank"]), "phonemizer": spec["phonemizer"], "bpm": spec.get("bpm", 120), "cases": spec["cases"]}
    env = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT="1", DOTNET_NOLOGO="1")
    p = subprocess.run([DOTNET, HARNESS], input=json.dumps(req, ensure_ascii=False).encode(), capture_output=True, env=env, timeout=300)
    if p.returncode != 0:
        raise SystemExit(f"{name}: harness failed\n{p.stderr.decode()[-2000:]}")
    out = json.loads(p.stdout.decode())
    if "error" in out:
        raise SystemExit(f"{name}: {out['error']}")
    golden = {**spec, "results": out["results"]}
    with open(os.path.join(HERE, "goldens", name + ".json"), "w", encoding="utf-8") as f:
        json.dump(golden, f, ensure_ascii=False, indent=1)
    errs = sum(1 for r in out["results"] if r.get("error"))
    print(f"{name}: {len(out['results'])} cases ({errs} raised in openutau)")


if __name__ == "__main__":
    names = sys.argv[1:] or sorted(os.path.splitext(f)[0] for f in os.listdir(os.path.join(HERE, "cases")) if f.endswith(".json"))
    for n in names:
        generate(n)
