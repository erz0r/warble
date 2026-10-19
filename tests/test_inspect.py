"""perception: planted faults are found at the right time; a clean render reports none."""

import json
import os
import shutil

import numpy as np
import pytest
import soundfile as sf

from warble.perception.inspect import compare, inspect, pitch_extract
from warble.score import parse_text
from warble.sing import sing

SCORE = "bpm 120\nlang ja\nか C4 1\nら D4 1\nさ E4 1\nあ G4 2 vib=pop\nr 2\nか A4 1\nら G4 1\n"


@pytest.fixture(scope="module")
def clean(fixtures, tmp_path_factory):
    d = tmp_path_factory.mktemp("inspect")
    s = parse_text(f"bank {fixtures['banks']['ds_full']}\n" + SCORE)
    out = str(d / "clean.wav")
    rep = sing(s, out, seed=1)
    return {"dir": d, "wav": out, "report": rep, "fixtures": fixtures}


def _variant(clean, name, edit_score=None, edit_audio=None):
    """a faulty take that is judged against the clean take's intent (its sidecar)."""
    d = clean["dir"]
    out = str(d / f"{name}.wav")
    if edit_score:
        s = parse_text(f"bank {clean['fixtures']['banks']['ds_full']}\n" + edit_score)
        sing(s, out, seed=1)
    else:
        shutil.copy(clean["wav"], out)
    if edit_audio:
        x, sr = sf.read(out)
        x = edit_audio(x, sr)
        sf.write(out, x, sr, subtype="FLOAT")
    shutil.copy(clean["wav"] + ".render.json", out + ".render.json")
    return out


def _off(clean):
    return json.load(open(clean["wav"] + ".render.json"))["score_offset_ms"]


def _hard(rep):
    return [a for a in rep["artifacts"] if a["severity"] != "info"]


def test_clean_render_has_no_artifacts(clean):
    rep = inspect(clean["wav"], asr=False)
    assert _hard(rep) == [], _hard(rep)
    assert rep["overall"]["median_abs_cents_error"] < 5
    v = [n for n in rep["notes"] if n.get("vibrato")]
    assert len(v) == 1 and 5.0 < v[0]["vibrato"]["rate_hz"] < 6.8 and v[0]["note"] == 4
    assert os.path.isfile(rep["images"][0])


def test_click_found_at_time(clean):
    t = 1250.0 + _off(clean)

    def plant(x, sr):
        x[int(t / 1000 * sr)] += 0.6
        return x

    rep = inspect(_variant(clean, "click", edit_audio=plant), images=False, asr=False)
    hits = [a for a in rep["artifacts"] if a["kind"] == "click"]
    assert hits and abs(hits[0]["t_ms"] - t) < 5


def test_flat_note_found(clean):
    bad = SCORE.replace("ら D4 1", "ら D4 1 cents=-50", 1)
    rep = inspect(_variant(clean, "flat", edit_score=bad), images=False, asr=False)
    n2 = next(n for n in rep["notes"] if n["note"] == 2)
    assert -60 < n2["median_cents_error"] < -40
    others = [abs(n["median_cents_error"]) for n in rep["notes"] if n["note"] != 2 and n.get("median_cents_error") is not None]
    assert max(others) < 10
    assert "note 2" in rep["listening_notes"] and "flat" in rep["listening_notes"]


def test_octave_jump_found(clean):
    bad = SCORE.replace("か A4 1", "か A4 1 cents=1200", 1)
    rep = inspect(_variant(clean, "octave", edit_score=bad), images=False, asr=False)
    oct_ = [a for a in rep["artifacts"] if a["kind"] == "octave_error"]
    assert oct_ and abs(oct_[0]["t_ms"] - (3500 + _off(clean))) < 200 and oct_[0].get("note") == 5


def test_noise_in_rest_found(clean):
    s_ms, e_ms = 3100 + _off(clean), 3400 + _off(clean)

    def plant(x, sr):
        rng = np.random.default_rng(0)
        i, j = int(s_ms / 1000 * sr), int(e_ms / 1000 * sr)
        x[i:j] += rng.normal(0, 0.03, j - i)
        return x

    rep = inspect(_variant(clean, "noise", edit_audio=plant), images=False, asr=False)
    hits = [a for a in rep["artifacts"] if a["kind"] == "rest_noise"]
    assert hits and s_ms - 50 <= hits[0]["t_ms"] <= e_ms + 50


def test_clipping_found(clean):
    t = 600.0 + _off(clean)

    def plant(x, sr):
        i = int(t / 1000 * sr)
        x[i:i + 30] = 1.0
        return x

    rep = inspect(_variant(clean, "clip", edit_audio=plant), images=False, asr=False)
    hits = [a for a in rep["artifacts"] if a["kind"] == "clipping"]
    assert hits and abs(hits[0]["t_ms"] - t) < 5


def test_compare_and_pitch_extract(clean):
    bad = _variant(clean, "flat2", edit_score=SCORE.replace("ら D4 1", "ら D4 1 cents=-50", 1))
    rep = compare(clean["wav"], bad, images=True)
    d2 = next(d for d in rep["notes"] if d["note"] == 2)
    assert d2["median_cents_error"]["delta"] < -40
    assert rep["verdict"]["notes_further_from_intent"] >= 1
    assert all(os.path.isfile(p) for p in rep["images"])
    pe = pitch_extract(clean["wav"])
    assert set(pe["per_extractor"]) >= {"harvest", "dio"} and os.path.isfile(pe["curves_file"])


def test_intent_carries_lang_for_the_recognizer(clean):
    from warble.perception import intelligibility
    from warble.perception.intent import from_sidecar

    it = from_sidecar(clean["wav"])
    assert {n["lang"] for n in it.notes} == {"ja"}

    class Model:
        supported_languages = ["en", "ja", "tl", "zh"]

    m = Model()
    assert intelligibility._asr_lang("en-plus", "faster", m) == "en"
    assert intelligibility._asr_lang("fil", "faster", m) == "tl"
    assert intelligibility._asr_lang("th", "faster", m) is None
    assert intelligibility._asr_lang(None, "faster", m) is None
