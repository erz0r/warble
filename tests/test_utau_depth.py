"""utau depth: the external resampler/wavtool bridge, mode2 pitch, ust round trips."""

import json
import os
import shutil

import numpy as np
import pytest

from warble.errors import WarbleError
from warble.formats import ust
from warble.score import parse_text
from warble.sing import _ENGINES, sing
from warble.tuning import curve
from warble.utau import resampler as rs

HERE = os.path.dirname(__file__)
ROOT = os.path.dirname(HERE)


@pytest.fixture
def mock_tools(tmp_path, monkeypatch):
    d = tmp_path / "resamplers"
    d.mkdir()
    shutil.copy(os.path.join(HERE, "tools", "mock_resampler.py"), d / "mock_resampler.py")
    monkeypatch.setenv("WARBLE_RESAMPLERS", str(d))
    monkeypatch.setenv("MOCK_RESAMPLER_LOG", str(tmp_path / "calls.jsonl"))
    monkeypatch.setattr(rs, "CACHE_DIR", str(tmp_path / "rescache"))
    _ENGINES.clear()
    yield tmp_path
    _ENGINES.clear()


def test_resampler_receives_utau_arguments(fixtures, mock_tools):
    s = parse_text(f"bank {fixtures['banks']['utau_cv_sjis']}\nbpm 120\nか C4 1\nら D4 1 flags=g-10\n")
    rep = sing(s, str(mock_tools / "o.wav"), resampler="mock_resampler")
    calls = [json.loads(l) for l in open(mock_tools / "calls.jsonl")]
    assert len(calls) == 2 and rep["phrase_count"] == 1
    a = next(c for c in calls if c[2] == "D4")  # calls run in parallel; find the second note's
    assert len(a) == 13
    assert a[3] == "100" and a[4] == "g-10" and a[11] == "!120"
    assert float(a[6]) % 50 == 0  # length is rounded up to a 50 ms grid like openutau
    pb = rs.decode_pitchbend(a[12])
    assert len(pb) > 10 and abs(pb[-1]) <= 5  # sits on the note at the end
    assert pb[0] < -100  # starts below: the transition up from C4


def test_resampler_crash_is_a_clear_error(fixtures, mock_tools):
    s = parse_text(f"bank {fixtures['banks']['utau_cv_sjis']}\nか C4 1 flags=crash\n")
    with pytest.raises(WarbleError) as e:
        sing(s, str(mock_tools / "o.wav"), resampler="mock_resampler")
    assert e.value.code == "resampler_errors"
    assert e.value.details["errors"][0]["alias"] == "か"


def test_item_matches_openutau_formulas(fixtures):
    from warble.bank.utau import Oto

    oto = Oto(wav="x.wav", alias="か", offset=20.0, consonant=100.0, cutoff=-300.0, preutter=60.0, overlap=10.0)
    phone = {"oto": oto, "wav_path": "x.wav", "tone": 60, "alias": "か", "position_ms": 1000.0, "end_ms": 1500.0,
             "preutter": 40.0, "overlap": 5.0, "tail_intrude": 30.0, "tail_overlap": 5.0, "tempo": 120.0,
             "envelope": [(-40, 0), (-35, 100), (0, 100), (440, 100), (475, 0)]}
    it = rs.Item(phone, None, lambda ms: 6000.0)
    # skipOver = oto.preutter - preutter (velocity 100), durRequired on the 50 grid
    assert it.skip_over == pytest.approx(20.0)
    assert it.offset == 20.0 and it.consonant == 100.0 and it.cutoff == -300.0
    need = 500 + (40 - 30 + 5) + 20
    assert it.dur_required == np.ceil(need / 50 + 0.5) * 50
    assert set(it.pitches) == {0}
    assert it.args("in", "out")[2] == "C4"


def test_mode2_points_and_vibrato_numbers():
    pts = ust.mode2_points("-30;0", "60", "0", "")
    assert pts == [[-30.0, 0.0, "io"], [30.0, 0.0, "io"]]
    s = parse_text(f"bpm 60\nら C4 1\nか D4 1 pts={curve.format_points(pts)}\n")
    n = s.tracks[0].notes
    t = np.array([970.0, 1000.0, 1030.0, 1200.0])
    m = curve.compose(t, n, s.tempo_map)
    # snapped first point starts at C4, s-curve reaches D4 60 ms later; midpoint is halfway
    assert m[0] == pytest.approx(60.0) and m[1] == pytest.approx(61.0) and m[2] == pytest.approx(62.0) and m[3] == 62.0
    v = curve.parse_vibrato("100,200,50,0,0,0,0")
    s2 = parse_text(f"bpm 60\nあ C4 1 vbr={curve.format_vibrato(v)}\n")  # 1000 ms note
    m2 = curve.compose(np.array([50.0, 150.0]), s2.tracks[0].notes, s2.tempo_map)
    assert (m2[0] - 60) * 100 == pytest.approx(50, abs=0.5) and (m2[1] - 60) * 100 == pytest.approx(-50, abs=0.5)


def _write_ust(path):
    body = (
        "[#VERSION]\r\nUST Version1.2\r\n[#SETTING]\r\nTempo=120.00\r\nTracks=1\r\nMode2=True\r\n"
        "[#0000]\r\nLength=480\r\nLyric=R\r\nNoteNum=60\r\n"
        "[#0001]\r\nLength=480\r\nLyric=さ\r\nNoteNum=60\r\nIntensity=90\r\nModulation=0\r\nFlags=g-5\r\nPBS=-30;0\r\nPBW=60\r\nPBY=0\r\nPBM=\r\n"
        "[#0002]\r\nLength=960\r\nLyric=く\r\nNoteNum=64\r\nVelocity=120\r\nPreUtterance=50\r\nVoiceOverlap=20\r\nPBS=-40;-40\r\nPBW=50,30\r\nPBY=10,0\r\nPBM=s,r\r\n"
        "VBR=65,180,35,20,20,0,0\r\nEnvelope=0,5,35,0,100,100,0\r\nPBType=5\r\nPitchBend=0,0,5,10\r\nPBStart=-20\r\n"
        "[#0003]\r\nLength=480\r\nLyric=ら\r\nNoteNum=62\r\nTempo=140\r\n[#TRACKEND]\r\n"
    )
    with open(path, "wb") as f:
        f.write(body.encode("cp932"))


def test_ust_round_trip_keeps_tuning(tmp_path):
    p = tmp_path / "a.ust"
    _write_ust(p)
    from warble.score import load

    s = load(str(p))
    n = s.tracks[0].notes
    assert [x.lyric for x in n] == ["さ", "く", "ら"]
    assert n[0].controls["vol"] == 90 and n[0].controls["flags"] == "g-5"
    assert n[1].controls["vel"] == 120 and n[1].controls["preutter"] == 50 and n[1].controls["overlap"] == 20
    assert curve.parse_points(n[1].controls["pts"]) == [[-40.0, -400.0, "l"], [10.0, 100.0, "o"], [40.0, 0.0, "io"]]
    assert curve.parse_vibrato(n[1].controls["vbr"])["period"] == 180
    assert n[1].extra.get("ust_mode1")  # mode1 kept but not sung in a mode2 project
    assert s.tempos == [(0, 120.0), (1920, 140.0)]
    out = tmp_path / "b.ust"
    ust.save(s, str(out))
    s2 = load(str(out))

    def sig(sc):
        return [(x.lyric, x.tone, x.position, x.duration, x.controls, x.extra.get("ust_mode1")) for x in sc.tracks[0].notes], sc.tempos

    assert sig(s) == sig(s2)
    s3 = parse_text(s.to_text())
    assert [(x.lyric, x.tone, x.position, x.duration, x.controls) for x in s3.tracks[0].notes] == [(x.lyric, x.tone, x.position, x.duration, x.controls) for x in n]


REAL_RES = os.path.join(ROOT, "resamplers")


@pytest.mark.skipif(not os.path.isfile(os.path.join(REAL_RES, "straycat-rs", "straycat-rs")), reason="straycat-rs not installed")
def test_real_straycat_and_yawu(fixtures, tmp_path, monkeypatch):
    monkeypatch.setenv("WARBLE_RESAMPLERS", REAL_RES)
    monkeypatch.setattr(rs, "CACHE_DIR", str(tmp_path / "rescache"))
    _ENGINES.clear()
    s = parse_text(f"bank {fixtures['banks']['utau_cv_sjis']}\nbpm 120\nか C4 1\nら E4 1\nさ G4 1\n")
    wt = "wavtool-yawu" if os.path.isdir(os.path.join(REAL_RES, "wavtool-yawu")) else None
    out = str(tmp_path / "s.wav")
    rep = sing(s, out, resampler="straycat-rs", wavtool=wt)
    _ENGINES.clear()
    assert rep["rms_dbfs"] > -40
    from warble.perception.inspect import inspect

    r = inspect(out, images=False, asr=False)
    assert r["overall"]["median_abs_cents_error"] < 15
