"""the mcp server and serve mode are generated from the cli's command table and stay identical."""

import io
import json

import pytest

from warble.cli import COMMANDS, build_parser
from warble.mcp_server import _arg_name, run, schema_for, serve_lines, to_argv


def _sample(p):
    if p.get("enum"):
        return p["enum"][0]
    return {"boolean": True, "integer": 3, "number": 1.5, "array": ["a", "b"]}.get(p["type"], "x")


@pytest.mark.parametrize("name", sorted(n for n in COMMANDS if n not in ("mcp", "serve")))
def test_every_argument_round_trips(name):
    spec = COMMANDS[name]
    schema = schema_for(spec)
    assert set(schema["properties"]) == {_arg_name(f, k) for f, k in spec["args"]}
    args = {k: _sample(p) for k, p in schema["properties"].items()}
    ns = vars(build_parser().parse_args(to_argv(name, args)))
    for k, v in args.items():
        got = ns[k]
        if isinstance(v, list) and not isinstance(got, list):
            got = [got]
        if isinstance(got, list) and not isinstance(v, list):
            v = [v]
        if isinstance(got, (int, float)) and not isinstance(got, bool):
            v = type(got)(v)
        assert got == v, (name, k, got, v)


def test_run_matches_cli_and_reports_errors(fixtures):
    r = run("probe", {"bank": fixtures["banks"]["utau_vcv"]})
    assert r["type"] == "utau" and r["reclist"]["style"] == "vcv"
    e = run("probe", {"nonsense": 1})
    assert e["error"] == "bad_arguments"


def test_serve_lines(fixtures, tmp_path):
    reqs = [
        {"id": 1, "command": "phonemize", "args": {"expr": "か:C4:1", "bank": fixtures["banks"]["utau_cv_sjis"]}},
        {"id": 2, "command": "nope"},
        {"command": "quit"},
        {"id": 3, "command": "banks"},
    ]
    out = io.StringIO()
    serve_lines(io.StringIO("\n".join(json.dumps(r) for r in reqs) + "\n"), out)
    lines = [json.loads(l) for l in out.getvalue().splitlines()]
    assert len(lines) == 2
    assert lines[0]["id"] == 1 and lines[0]["result"]["tracks"][0]["phrases"][0]["notes"][0]["phonemes"][0]["phoneme"] == "か"
    assert lines[1]["result"]["error"] == "unknown_command"
