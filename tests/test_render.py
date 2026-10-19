"""end-to-end renders on the mock banks: pitch lands on the notes and errors are specific."""

import json
import os
import warnings

import numpy as np
import pytest

from warble.errors import WarbleError
from warble.score import parse_text
from warble.sing import sing

MELODY = "bpm 120\nか C4 1\nら D4 1\nさ E4 1/2\nあ G4 1\nr 1\nか A4 1\n"


def measure(path):
    import pyworld as pw
    import soundfile as sf

    warnings.filterwarnings("ignore")
    x, sr = sf.read(path)
    x = x.astype(np.float64)
    f0, t = pw.harvest(x, sr, frame_period=5.0, f0_floor=80, f0_ceil=1000)
    # harvest can return 0 on perfectly stationary synthetic tones (the mock vocoder); dio doesn't
    f0d, td = pw.dio(x, sr, frame_period=5.0, f0_floor=80, f0_ceil=1000)
    f0d = pw.stonemask(x, f0d, td, sr)
    n = min(len(f0), len(f0d))
    f0 = np.where(f0[:n] > 0, f0[:n], f0d[:n])
    t = t[:n]
    side = json.load(open(path + ".render.json"))
    tt = t * 1000 - side["score_offset_ms"]
    errs = []
    for ph in side["phrases"]:
        for n in ph["notes"]:
            m = (tt >= n["start_ms"] + 60) & (tt < n["end_ms"] - 30) & (f0 > 0)
            errs.append(float(np.median((69 + 12 * np.log2(f0[m] / 440) - n["tone"]) * 100)) if m.any() else None)
    return errs, side


@pytest.mark.parametrize("name", ["ds_full", "ds_minimal", "ds_rel", "utau_cv_sjis", "utau_vcv", "utau_cvvc", "utau_multipitch"])
def test_mock_sings_on_pitch(fixtures, tmp_path, name):
    s = parse_text(f"bank {fixtures['banks'][name]}\nlang ja\n" + MELODY)
    out = str(tmp_path / f"{name}.wav")
    rep = sing(s, out, seed=1, vocoder_dirs=[fixtures["vocoders"]])
    assert rep["phrase_count"] == 2
    assert rep["rms_dbfs"] > -40
    errs, side = measure(out)
    assert all(e is not None and abs(e) < 15 for e in errs), errs


def test_seed_makes_renders_identical(fixtures, tmp_path, monkeypatch):
    from warble import onnxrun

    monkeypatch.setattr(onnxrun, "CACHE_DIR", str(tmp_path / "cache"))
    s = parse_text(f"bank {fixtures['banks']['ds_full']}\nlang ja\n" + MELODY)
    import soundfile as sf

    sing(s, str(tmp_path / "a.wav"), seed=5)
    monkeypatch.setattr(onnxrun, "CACHE_DIR", str(tmp_path / "cache2"))
    sing(s, str(tmp_path / "b.wav"), seed=5)
    a, _ = sf.read(tmp_path / "a.wav")
    b, _ = sf.read(tmp_path / "b.wav")
    assert np.array_equal(a, b)


def test_unknown_lyric_names_closest_symbols(fixtures, tmp_path):
    s = parse_text(f"bank {fixtures['banks']['ds_full']}\nlang ja\nか C4 1\nzzq D4 1\n")
    with pytest.raises(WarbleError) as e:
        sing(s, str(tmp_path / "x.wav"))
    assert e.value.code == "unknown_lyrics"
    assert e.value.details["unknown"][0]["lyric"] == "zzq"


def test_unknown_alias_lists_closest(fixtures, tmp_path):
    s = parse_text(f"bank {fixtures['banks']['utau_cv_sjis']}\nか C4 1\nぬ D4 1\nら E4 1\n")
    with pytest.raises(WarbleError) as e:
        sing(s, str(tmp_path / "x.wav"))
    rep = sing(s, str(tmp_path / "y.wav"), allow_unknown=True)
    assert rep["unknown_lyrics"][0]["lyric"] == "ぬ" and rep["phrase_count"] == 1


def test_explicit_phonemes_and_voice_mix(fixtures, tmp_path):
    s = parse_text(f"bank {fixtures['banks']['ds_full']}\nlang ja\n[ja/k ja/a] C4 1 voice=files/alto:0.5,files/soprano:0.5\n")
    rep = sing(s, str(tmp_path / "m.wav"))
    assert rep["phrases"][0]["phonemes"] == "ja/k ja/a"


def test_midi_with_lyrics(fixtures, tmp_path):
    import mock_midi

    from warble.score import load

    mid = mock_midi.build(str(tmp_path / "m.mid"))
    s = load(mid, defaults={"lyrics": "かきくけこさしす", "lang": "ja"})
    assert s.import_report["notes"] == 8
    assert [n.lyric for n in s.tracks[0].notes] == list("かきくけこさしす")
    assert s.tempos[0][1] == 100 and len(s.tempos) == 2
    mid2 = mock_midi.build(str(tmp_path / "l.mid"), with_lyrics=True)
    s2 = load(mid2)
    assert s2.import_report["lyrics_placed"] == 8 and s2.tracks[0].notes[0].lyric == "ちゃ"
