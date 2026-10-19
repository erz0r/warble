"""tuning ops change exactly what they claim; history round-trips; caches and imports work."""

import json
import os

import numpy as np
import pytest

from warble.score import parse_text
from warble.tuning import auto, curve, ops
from warble.tuning.project import Project

BASE = "bpm 60\nら C4 1\nら E4 1\nら D4 2\nら C4 1\n"  # 1 beat = 1000 ms


def _curve(score, t):
    tr = score.tracks[0]
    return curve.compose(np.asarray(t, float), tr.notes, score.tempo_map, None, tr)


def test_transition_numbers():
    s = parse_text(BASE)
    ops.apply(s, [{"op": "transition", "notes": "2", "dur_ms": 100, "start_ms": -50, "overshoot_cents": 20, "settle_ms": 60}])
    c = _curve(s, [940, 950, 1050, 1110, 1300])
    assert c[0] == pytest.approx(60) and c[1] == pytest.approx(60)  # before the bend, the previous note
    assert c[2] == pytest.approx(64.2)  # overshoot point
    assert c[3] == pytest.approx(64.0, abs=1e-6)  # settled
    assert c[4] == 64
    other = _curve(s, [3500])[0]
    assert other == 62  # other notes untouched


def test_scoop_fall_fry_offset_flat_unbend():
    s = parse_text(BASE)
    ops.apply(s, [{"op": "scoop", "notes": "1", "cents": -100, "dur_ms": 100},
                  {"op": "fall", "notes": "1", "cents": -200, "dur_ms": 100},
                  {"op": "offset", "notes": "3", "cents": 30}])
    c = _curve(s, [0, 100, 500, 900, 999, 2500])
    assert c[0] == pytest.approx(59.0) and c[1] == pytest.approx(60) and c[2] == 60
    assert c[3] == pytest.approx(60) and c[4] < 58.1
    assert c[5] == pytest.approx(62.3)
    ops.apply(s, [{"op": "flat", "notes": "1-3"}])
    assert np.allclose(_curve(s, [0, 999, 1500, 2500]), [60, 60, 64, 62])
    ops.apply(s, [{"op": "unbend", "notes": "1-3"}])
    assert "pts" not in s.tracks[0].notes[0].controls


def test_vibrato_preset_and_fields():
    s = parse_text(BASE)
    ops.apply(s, [{"op": "vibrato", "notes": "3", "preset": "pop", "depth_cents": 40, "rate_hz": 5.0}])
    v = curve.note_vibrato(s.tracks[0].notes[2])
    assert v["depth"] == 40 and v["period"] == pytest.approx(200)
    t = np.arange(2000, 4000, 5.0)
    c = _curve(s, t)
    seg = c[(t > 3000) & (t < 3700)] - 62
    assert 0.3 < seg.max() < 0.42 and -0.42 < seg.min() < -0.3  # ±40 cents once faded in
    assert np.allclose(c[t < 2600], 62)  # onset at 35% of the note
    ops.apply(s, [{"op": "copy_vibrato", "notes": "4", "source": 3}, {"op": "vibrato", "notes": "3", "preset": "none"}])
    assert curve.note_vibrato(s.tracks[0].notes[3]) and not curve.note_vibrato(s.tracks[0].notes[2])


def test_drift_seeded_and_bounded():
    s = parse_text(BASE)
    ops.apply(s, [{"op": "drift", "notes": "3", "depth_cents": 10, "seed": 4}])
    t = np.arange(2000, 4000, 5.0)
    a = _curve(s, t)
    b = _curve(s, t)
    assert np.array_equal(a, b) and np.max(np.abs(a - 62)) <= 0.101 and np.std(a) > 0.01
    assert a[0] == pytest.approx(62)  # faded in at the edge


def test_selection_filters():
    s = parse_text(BASE)
    _, idx = ops.select(s, interval="abs>=3")
    assert idx == [1]
    _, idx = ops.select(s, min_beats=2)
    assert idx == [2]
    _, idx = ops.select(s, interval="<0")
    assert [i + 1 for i in idx] == [3, 4]


def test_set_ramp_nudge():
    s = parse_text(BASE)
    ops.apply(s, [{"op": "ramp", "key": "vol", "start": 80, "end": 110, "notes": "1-4"},
                  {"op": "set", "key": "flags", "value": "g-5", "notes": "2"},
                  {"op": "nudge", "notes": "2", "ms": -100}])
    n = s.tracks[0].notes
    assert [x.controls["vol"] for x in n] == [80, 90, 100, 110]
    assert n[1].controls["flags"] == "g-5"
    assert n[1].position == 480 - 48 and n[0].end == n[1].position and n[1].end == 960


def test_auto_tuners_run():
    for name in ("flat", "utau_mode1", "utau_mode2", "openutau", "rule"):
        s = parse_text(BASE)
        notes = auto.run(s, name)
        assert notes == [1, 2, 3, 4]
        c = _curve(s, np.arange(0, 5000, 5.0))
        assert np.all(np.isfinite(c)) and np.median(np.abs(c - np.repeat([60, 64, 62, 62, 60], 200))) < 0.5


def test_project_history(tmp_path):
    p = tmp_path / "song.txt"
    p.write_text(BASE)
    proj = Project(str(p))
    s = proj.score()
    ops.apply(s, [{"op": "offset", "notes": "1", "cents": 10}])
    proj.save_score(s, "offset")
    proj.snapshot("a")
    s = proj.score()
    ops.apply(s, [{"op": "offset", "notes": "2", "cents": -10}])
    proj.save_score(s, "offset2")
    d = proj.diff("a", "current")
    assert d["notes"] == [{"track": "main", "note": 2, "lyric": "ら", "changes": {"cents": [None, -10.0]}}]
    proj.undo()
    assert "cents" not in proj.score().tracks[0].notes[1].controls
    proj.redo()
    assert proj.score().tracks[0].notes[1].controls["cents"] == -10
    proj.restore("a")
    assert "cents" not in proj.score().tracks[0].notes[1].controls
    p.write_text(p.read_text() + "ら C4 1\n")  # an outside edit becomes a version
    assert Project(str(p)).history()["log"][-1]["op"] == "external edit"


def test_phrase_cache_rerenders_only_changed_phrase(fixtures, tmp_path, monkeypatch):
    from warble import sing as singmod

    monkeypatch.setattr(singmod, "PHRASE_CACHE", str(tmp_path / "pc"))
    s = parse_text(f"bank {fixtures['banks']['ds_full']}\nlang ja\nbpm 120\nか C4 1\nら D4 1\nr 1\nさ E4 1\nあ G4 1\n")
    r1 = singmod.sing(s, str(tmp_path / "a.wav"), seed=1)
    ops.apply(s, [{"op": "vibrato", "notes": "4", "preset": "opera"}])
    r2 = singmod.sing(s, str(tmp_path / "b.wav"), seed=1)
    assert r1["phrases_from_cache"] == 0 and r2["phrases_from_cache"] == 1


def test_ustx_round_trip(tmp_path):
    from warble.formats import ustx
    from warble.score import load

    s = parse_text(BASE + "curve pitd 0:0,480:20\n")
    ops.apply(s, [{"op": "transition", "notes": "2"}, {"op": "vibrato", "notes": "3", "preset": "pop"},
                  {"op": "drift", "notes": "3"}, {"op": "set", "key": "gender", "value": "10", "notes": "1"}])
    ustx.save(s, str(tmp_path / "a.ustx"))
    s2 = load(str(tmp_path / "a.ustx"))

    def sig(sc):
        return [(n.lyric, n.tone, n.position, n.duration, n.controls) for n in sc.tracks[0].notes], sc.tracks[0].curves

    assert sig(s) == sig(s2)


def test_import_pitch_from_reference(fixtures, tmp_path):
    """a ds render stands in for a real singer: its pitch, imported onto a flat score, comes back."""
    from warble.perception.analysis import analyze_audio
    from warble.sing import sing
    from warble.tuning.refpitch import import_pitch

    ref = parse_text(f"bank {fixtures['banks']['ds_full']}\nlang ja\nbpm 120\nら C4 1\nら E4 1 vib=pop\nら D4 2 cents=-30\n")
    sing(ref, str(tmp_path / "ref.wav"), seed=1)
    tgt = parse_text(f"bank {fixtures['banks']['utau_cv_sjis']}\nbpm 120\nら C4 1\nら E4 1\nら D4 2\n")
    info = import_pitch(tgt, str(tmp_path / "ref.wav"))
    assert abs(info["notes"][2]["median_cents_vs_note"] + 30) < 8
    sing(tgt, str(tmp_path / "copy.wav"))
    a = analyze_audio(str(tmp_path / "copy.wav"))
    side = json.load(open(str(tmp_path / "copy.wav") + ".render.json"))
    off = side["score_offset_ms"]
    m = (a.t_ms - off > 1200) & (a.t_ms - off < 1900) & a.voiced
    assert abs(np.median(a.midi[m]) - 61.7) < 0.1


def test_dspitch_tuner_borrows_a_pitch_model(fixtures):
    s = parse_text(f"bank {fixtures['banks']['utau_cv_sjis']}\nlang ja\nbpm 120\nか C4 1\nら E4 1\nさ D4 2\n")
    notes = auto.run(s, "dspitch", ds_bank=fixtures["banks"]["ds_full"])
    assert notes == [1, 2, 3]
    raw = curve.note_raw(s.tracks[0].notes[1])
    assert raw and len(raw["cents"]) > 50
    # the mock pitch model follows the note grid, so the borrowed curve sits on the notes
    c = _curve(s, np.arange(650, 950, 5.0))  # inside note 2 (500-1000 ms at 120 bpm)
    assert np.allclose(c, 64, atol=0.05)
