"""diffsinger phonemizer parity: warble's ports of openutau's diffsinger phonemizers (warble/ds/g2p_phonemizers.py
driving warble/ds/phonemizer.py) must reproduce openutau's own output on the goldens made by ref/harness_ds with
tests/parity/gen_goldens_ds.py: the same phoneme symbols, at positions within POS_TOL ticks (the duration model
runs in a different onnxruntime build, so its numbers can differ by a hair), and an error on the same notes.

the goldens use a real bank that isn't committed; each golden is skipped when its bank folder is missing."""

import glob
import json
import os

import pytest

HERE = os.path.dirname(__file__)
ROOT = os.path.dirname(HERE)
GOLDENS = sorted(glob.glob(os.path.join(HERE, "parity", "goldens_ds", "*.json")))
POS_TOL = 5

_MODELS = {}


def _bank(path):
    from warble.bank.ds import DsBank
    from warble.ds.models import DsModels

    if path not in _MODELS:
        bank = DsBank(path)
        _MODELS[path] = (bank, DsModels(bank))
    return _MODELS[path]


def case_groups(case):
    """the case's notes as score note groups, laid out exactly like ref/harness_ds (start at tick 480)."""
    from warble.score import Note, parse_pitch

    groups, pos = [], 480
    for nn in case["notes"]:
        tone = nn["tone"] if isinstance(nn["tone"], int) else int(parse_pitch(nn["tone"]))
        if "position" in nn:
            pos = nn["position"]
        n = Note(lyric=nn["lyric"], tone=tone, position=pos, duration=nn.get("duration", 480), hint=nn.get("hint"))
        if n.lyric.startswith("+") and groups:
            groups[-1].append(n)
        else:
            groups.append([n])
        pos += n.duration + nn.get("gap_after", 0)
    return groups


def _msg(err):
    """an error message without the onnxruntime binding's prefix (c# and python word it differently)."""
    i = err.find("Status Message:")
    return err[i:] if i >= 0 else err


def compare(golden_path, tol=POS_TOL):
    """-> {"golden", "phonemizer", "cases", "mismatches": [{"id", "group", "want", "got"}]} or None when the bank
    is missing."""
    from warble.ds.phonemizer import Phonemizer
    from warble.score import TempoMap

    with open(golden_path, encoding="utf-8") as f:
        g = json.load(f)
    bank_dir = g["bank"] if os.path.isabs(g["bank"]) else os.path.join(ROOT, g["bank"])
    if not os.path.isdir(bank_dir):
        return None
    bank, models = _bank(bank_dir)
    ph = Phonemizer(bank, models, g.get("lang") or None, phonemizer=g["phonemizer"], frontend_fallbacks=False)
    assert ph.phonemizer_class == g["phonemizer"], ph.describe()
    tm = TempoMap([(0, float(g.get("bpm", 120)))])
    mismatches = []
    for case in g["results"]:
        spec = next(c for c in g["cases"] if c["id"] == case["id"])
        groups = case_groups(spec)
        got = ph.process_groups(groups, tm)
        if case.get("error"):
            mismatches.append({"id": case["id"], "group": None, "want": case["error"], "got": "openutau raised"})
            continue
        want = {}
        for p in case["phonemes"]:
            want.setdefault(p["group"], []).append(p)
        for gi, res in enumerate(got):
            w = want.get(gi, [])
            werr = [p for p in w if p.get("error")]
            if werr or res["error"]:
                if not (werr and res["error"]):
                    mismatches.append({"id": case["id"], "group": gi, "want": [(p["phoneme"], p["position"], p.get("error")) for p in w],
                                       "got": res})
                elif _msg(werr[0]["error"]) != _msg(res["error"]):
                    mismatches.append({"id": case["id"], "group": gi, "want": werr[0]["error"], "got": res["error"]})
                continue
            ws = [(p["phoneme"], p["position"]) for p in w]
            gs = res["phonemes"]
            if [s for s, _ in ws] != [s for s, _ in gs] or any(abs(a[1] - b[1]) > tol for a, b in zip(ws, gs)):
                mismatches.append({"id": case["id"], "group": gi, "want": ws, "got": gs})
    return {"golden": os.path.basename(golden_path), "phonemizer": g["phonemizer"], "cases": len(g["results"]), "mismatches": mismatches}


@pytest.mark.parametrize("golden", GOLDENS, ids=[os.path.basename(p)[:-5] for p in GOLDENS])
def test_parity_ds(golden):
    r = compare(golden)
    if r is None:
        pytest.skip("diffsinger bank for this golden is not present")
    assert not r["mismatches"], r["mismatches"][:3]


# ---- selection and helpers (no bank needed) --------------------------------------------------------------

def test_choose_language_phonemizer(tmp_path):
    from warble.ds import g2p_phonemizers as gp
    from warble.ds.phonemizer import choose
    from warble.errors import WarbleError

    assert type(choose("en")[0]) is gp.DiffSingerEnglishPhonemizer
    assert type(choose("en", "DiffSingerARPAPlusEnglishPhonemizer")[0]) is gp.DiffSingerARPAPlusEnglishPhonemizer
    assert type(choose("en-plus")[0]) is gp.DiffSingerARPAPlusEnglishPhonemizer
    assert type(choose("zh_yue")[0]) is gp.DiffSingerJyutpingPhonemizer
    assert type(choose("ko")[0]) is gp.DiffSingerKoreanG2PPhonemizer
    # german: the marzipan phonemizer when the bank ships its dictionary
    assert type(choose("de", dict_dir=str(tmp_path))[0]) is gp.DiffSingerGermanPhonemizer
    (tmp_path / "dsdict-de-marzipan.yaml").write_text("symbols: []\n")
    assert type(choose("de", dict_dir=str(tmp_path))[0]) is gp.DiDiffSingerGermanMarzipanPhonemizerr
    # character.yaml default_phonemizer: honoured when it is a diffsinger class for the language (or no language)
    ja = "OpenUtau.Core.DiffSinger.DiffSingerJapanesePhonemizer"
    assert type(choose(None, None, ja)[0]) is gp.DiffSingerJapanesePhonemizer
    assert type(choose("en", None, ja)[0]) is gp.DiffSingerEnglishPhonemizer
    plus = "OpenUtau.Core.DiffSinger.DiffSingerARPAPlusEnglishPhonemizer"
    assert type(choose("en", None, plus)[0]) is gp.DiffSingerARPAPlusEnglishPhonemizer
    assert type(choose(None, None, "OpenUtau.Plugin.Builtin.DiffSingerPhonemizer")[0]) is gp.DiffSingerPhonemizer
    # languages openutau has no diffsinger phonemizer for: the generic one with dsdict-<lang>.yaml
    th = choose("th")[0]
    assert type(th) is gp.DiffSingerPhonemizer and th.get_dictionary_name() == "dsdict-th.yaml" and th.get_lang_code() == "th"
    # a utau phonemizer name on the track is ignored; an unknown diffsinger one is an error
    assert type(choose("ja", "OpenUtau.Plugin.Builtin.JapaneseVCVPhonemizer")[0]) is gp.DiffSingerJapanesePhonemizer
    with pytest.raises(WarbleError):
        choose("ja", "DiffSingerKlingonPhonemizer")


def test_romanizers():
    from warble.ds import g2p_phonemizers as gp

    assert gp.DiffSingerJapanesePhonemizer().romanize(["か", "ン", "ん", "きゃ", "かな", "ー", "a"]) == ["ka", "n", "N", "kya", "かな", "ー", "a"]
    assert gp.DiffSingerChinesePhonemizer().romanize(["长", "大", "x", "很", "长"]) == ["zhang", "da", "x", "hen", "chang"]
    assert gp.DiffSingerJyutpingPhonemizer().romanize(["你", "好", "a"]) == ["nei", "hou", "a"]
    g = gp.RuleBasedFilipinoG2p()
    assert g.query("bahay") == ["b", "a", "h", "a", "Y"]
    assert g.query("mga") == ["m", "a", "ng", "a"]
    assert g.query("!") is None


def test_render_path_matches_part():
    """phonemize_phrase (what rendering uses) gives the same phonemes and ticks as the SetUp + Process path."""
    from warble.ds.phonemizer import Phonemizer
    from warble.score import Note, TempoMap

    bank_dir = os.path.join(ROOT, "banks", "adachi_rei", "足立レイ_DS_v111.1")
    if not os.path.isdir(bank_dir):
        pytest.skip("diffsinger bank not present")
    bank, models = _bank(bank_dir)
    tm = TempoMap()
    for lang, lyrics in (("en-plus", ["'", "uh", "winner"]), ("zh", ["长", "大", "了"]), ("ja", ["さ", "く", "ら"])):
        ph = Phonemizer(bank, models, lang, frontend_fallbacks=False)
        groups = [[Note(lyric=l, tone=60 + i, position=480 * (i + 1), duration=480)] for i, l in enumerate(lyrics)]
        part = ph.process_groups(groups, tm)
        res = ph.phonemize_phrase(groups, tm, lambda n: None, context=groups)
        assert not res["unknown"], res["unknown"]
        for wi, (g, r) in enumerate(zip(groups, part)):
            got = [(p["phoneme"], p["tick"] - g[0].position) for p in res["phones"] if p["word"] == wi]
            assert got == [tuple(x) for x in r["phonemes"]], (lang, wi, got, r)
