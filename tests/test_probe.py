import os

import pytest
from conftest import real_banks

from warble.bank import common, utau
from warble.probe import list_banks, probe
from warble.textenc import decode_bytes


@pytest.mark.parametrize("name", ["ds_full", "ds_minimal", "ds_rel", "utau_cv_sjis", "utau_vcv", "utau_cvvc", "utau_multipitch"])
def test_mock_probe_check_is_clean(fixtures, name):
    out = probe(fixtures["banks"][name], check=True, vocoder_dirs=[fixtures["vocoders"]])
    assert out["type"] in ("diffsinger", "utau")
    errors = [i for i in out["issues"] if i["severity"] in ("error", "warning")]
    assert errors == []


def test_ds_full_details(fixtures):
    out = probe(fixtures["banks"]["ds_full"], check=True)
    assert out["languages"] == ["en", "ja"]
    assert [m["speaker"] for m in out["voice_modes"]] == ["files/alto", "files/soprano"]
    assert out["vocoder"]["source"] == "bundled"
    ac = out["configs"]["acoustic"]["models"]["acoustic"]
    names = {i["name"] for i in ac["inputs"]}
    assert {"tokens", "languages", "durations", "f0", "gender", "velocity", "energy", "breathiness", "spk_embed", "steps", "depth"} == names
    assert out["configs"]["acoustic"]["phonemes"]["format"].startswith("json")


def test_ds_minimal_named_vocoder_and_mel_base(fixtures):
    out = probe(fixtures["banks"]["ds_minimal"], vocoder_dirs=[fixtures["vocoders"]])
    assert out["vocoder"]["source"] == "named"
    assert out["vocoder"]["mel_base_scale"] == pytest.approx(2.30259)
    assert out["capabilities"]["pitch"].startswith("rule")
    # without the vocoder dir the named vocoder is missing and says what to install
    missing = probe(fixtures["banks"]["ds_minimal"], vocoder_dirs=[])
    if missing["vocoder"]["source"] == "missing":
        assert "mock_vocoder" in missing["vocoder"]["error"]
        assert missing["missing_dependencies"]


def test_dsconfig_flag_vs_graph_mismatch_is_reported(fixtures, tmp_path):
    import shutil

    import yaml

    bank = tmp_path / "bank"
    shutil.copytree(fixtures["banks"]["ds_full"], bank)
    cfg = yaml.safe_load(open(bank / "dsconfig.yaml"))
    cfg["use_breathiness_embed"] = False  # graph still has the input
    cfg["use_tension_embed"] = True  # graph lacks it
    yaml.safe_dump(cfg, open(bank / "dsconfig.yaml", "w"))
    out = probe(str(bank), check=True)
    fv = out["configs"]["acoustic"]["models"]["acoustic"]["flags_vs_graph"]
    assert fv["graph_needs_but_flags_omit"] == ["breathiness"]
    assert fv["flags_feed_but_graph_lacks"] == ["tension"]


def test_utau_mock_styles(fixtures):
    styles = {n: probe(fixtures["banks"][n])["reclist"]["style"] for n in ["utau_cv_sjis", "utau_vcv", "utau_cvvc", "utau_multipitch"]}
    assert styles == {"utau_cv_sjis": "cv", "utau_vcv": "vcv", "utau_cvvc": "cvvc", "utau_multipitch": "cv"}


def test_sjis_and_prefix_map(fixtures):
    b = utau.UtauBank(fixtures["banks"]["utau_multipitch"])
    assert {s.encoding for s in b.oto_sets} == {"cp932"}
    assert b.prefix_map_encoding == "cp932"
    sufs = {s["suffix"]: s["tone_ranges"] for s in b.subbanks}
    assert sufs == {"↑": ["G4-B7"], "": ["C1-F#4"]}
    assert "か↑" in b.alias_map()


def test_planted_oto_faults(fixtures, tmp_path):
    import shutil

    bank = tmp_path / "cv"
    shutil.copytree(fixtures["banks"]["utau_cvvc"], bank)
    with open(bank / "oto.ini", "a") as f:
        f.write("ka.wav=ka,0,50,-99999,30,10\n")  # duplicate alias, cutoff far past the end
        f.write("nothere.wav=zz,0,50,-100,30,10\n")  # missing wav
        f.write("ka.wav=kb,99999,50,-100,30,10\n")  # offset past the end
        f.write("garbage line\n")
    out = probe(str(bank), check=True)
    codes = {i["code"] for i in out["issues"]}
    assert {"duplicate_alias", "cutoff_out_of_file", "wav_missing", "offset_out_of_file", "oto_unparsable"} <= codes


def test_encoding_detection():
    assert decode_bytes("か".encode("cp932"))[1] == "cp932"
    assert decode_bytes("か".encode("utf-8"))[1] == "utf-8"
    assert decode_bytes("↑".encode("cp932"), preferred="cp932")[0] == "↑"
    assert decode_bytes("#Charset:utf-8\n".encode(), declared="shift_jis")[1] == "cp932"


def test_oto_cutoff_semantics():
    o = utau.parse_oto_line("a.wav=a,100,50,-300,40,10", 0)
    assert o.cutoff_ms(1000) == 400  # negative: measured from offset
    o = utau.parse_oto_line("a.wav=a,100,50,200,40,10", 0)
    assert o.cutoff_ms(1000) == 800  # positive: from the file end
    o = utau.parse_oto_line("a.wav=,,,,,", 0)
    assert o.alias == "a" and o.valid


def test_tone_names():
    assert utau.name_to_tone("C4") == 60
    assert utau.name_to_tone("A#3") == 58
    assert utau.tone_to_name(61) == "C#4"
    assert utau.tone_ranges([60, 61, 62, 70]) == ["C4-D4", "A#4"]


def test_detect_and_scan(fixtures):
    for name, path in fixtures["banks"].items():
        assert common.detect(path)[0] == ("diffsinger" if name.startswith("ds") else "utau")
    listed = list_banks([os.path.join(fixtures["base"], "banks")], [fixtures["vocoders"]])
    assert len(listed) == len(fixtures["banks"])
    assert all(not b.get("error") for b in listed)


@pytest.mark.parametrize("path", real_banks() or [pytest.param(None, marks=pytest.mark.skip("no real banks in ./banks"))])
def test_real_banks_probe_without_crashing(path):
    out = probe(path, check=True)
    assert out["type"] in ("diffsinger", "utau")
    assert "issue_summary" in out
