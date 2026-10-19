"""finishing: harmony, mix effects, backing, loudness, stems, plugin hosting, check."""

import os

import numpy as np
import pytest
import soundfile as sf

from warble.harmony import parse_key, shift_diatonic
from warble.score import parse_text
from warble.sing import sing


def test_diatonic_harmony():
    _, c, _ = parse_key("C")
    assert [shift_diatonic(t, 2, c) for t in (60, 62, 64, 65, 67, 69, 71)] == [64, 65, 67, 69, 71, 72, 74]
    assert [shift_diatonic(t, -2, c) for t in (60, 64, 67)] == [57, 60, 64]
    _, am, _ = parse_key("Am")
    assert shift_diatonic(57, 5, am) == 65


def test_harmonize_directive_and_mix(fixtures, tmp_path):
    sr = 44100
    pad = (0.05 * np.sin(2 * np.pi * 130.8 * np.arange(sr * 3) / sr)).astype(np.float32)
    sf.write(tmp_path / "pad.wav", pad, sr)
    s = parse_text(
        f"key C\nmaster lufs=-16 ceiling=-1\nbacking pad.wav @ 0.5s gain=-3\n"
        f"track lead\nbank {fixtures['banks']['ds_full']}\nlang ja\nfx eq=low:-2,high:2 comp=-20:3 reverb=0.3 delay=200:0.3:0.2\n"
        "か C4 1\nら E4 1\nさ G4 2\n"
        f"track harm\nbank {fixtures['banks']['utau_cv_sjis']}\npan 0.4\nvolume -4\nharmonize lead 3\n",
        base_dir=str(tmp_path))
    assert [n.tone for n in s.track("harm").notes] == [64, 67, 71]
    out = str(tmp_path / "mix.wav")
    rep = sing(s, out, seed=1, stems_dir=str(tmp_path / "stems"))
    assert rep["channels"] == 2 and abs(rep["mix"]["lufs"] + 16) < 0.6
    assert rep["peak_dbfs"] <= -0.9
    names = {os.path.basename(p) for p in rep["stems"]}
    assert {"lead.wav", "harm.wav", "reverb.wav", "backing.wav"} <= names
    from warble.perception.inspect import inspect

    r = inspect(str(tmp_path / "stems" / "harm.wav"), images=False, asr=False)
    assert r["overall"]["median_abs_cents_error"] < 10 and len(r["notes"]) == 3
    x, _ = sf.read(tmp_path / "stems" / "harm.wav")
    assert x.shape[1] == 2 and np.abs(x[:, 1]).sum() > np.abs(x[:, 0]).sum()  # panned right


def test_check_command(fixtures):
    from warble.check import check

    ok = check(parse_text(f"bank {fixtures['banks']['utau_multipitch']}\nか C4 1\nら C8 1\n"))
    assert any("outside" in p["message"] for p in ok["problems"])
    bad = check(parse_text(f"bank {fixtures['banks']['ds_full']}\nlang ja\nzzq C4 1\n"))
    assert not bad["ok"] and bad["problems"][0]["lyric"] == "zzq"


PLUG = "/Library/Audio/Plug-Ins/VST3/OTT.vst3"


@pytest.mark.skipif(not os.path.isdir(PLUG), reason="OTT not installed")
def test_vst_chain(fixtures, tmp_path):
    from warble import plugins

    assert plugins.find("ott")["format"] == "vst3"
    x = (0.1 * np.sin(2 * np.pi * 220 * np.arange(44100) / 44100)).astype(np.float32)
    y = plugins.run_chain(x, 44100, "OTT(depth=100;time=10)")
    assert y.shape == (44100, 2) and not np.allclose(y[:, 0], x)
    with pytest.raises(Exception) as e:
        plugins.run_chain(x, 44100, "OTT(nonsense=1)")
    assert "no parameter" in str(e.value)
