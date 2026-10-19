"""phonemizer parity: every python port must reproduce openutau's own output (goldens made by
ref/harness with tests/parity/gen_goldens.py). goldens for phonemizers not ported yet are skipped."""

import glob
import os

import pytest

from warble.utau.pz.parity import compare

HERE = os.path.dirname(__file__)
GOLDENS = sorted(glob.glob(os.path.join(HERE, "parity", "goldens", "*.json")))


@pytest.mark.parametrize("golden", GOLDENS, ids=[os.path.basename(g)[:-5] for g in GOLDENS])
def test_parity(golden):
    r = compare(golden, os.path.join(HERE, "parity", "banks"))
    if r["status"] == "not ported":
        pytest.skip(f"{r['phonemizer']} is not ported yet")
    assert r["passed"], r["mismatches"][:3]
