import pytest

from warble.errors import WarbleError
from warble.lang import ja
from warble.lyrics import assign, split
from warble.score import Note, parse_inline, parse_text, phrases
from warble.utau.resampler import decode_pitchbend, encode_pitchbend, fmt


def test_text_roundtrip_and_positions():
    s = parse_text("bpm 120\ntime 3/4\nら C#4 1  # c\n+ D4 1/2\nr 1\nか A4 350ms @ 3:1\nbpm 60 @ bar 4\nさ Bb4 1 @ bar 4 vel=120\n")
    n = s.tracks[0].notes
    assert [x.tone for x in n] == [61, 62, 69, 70]
    assert n[2].position == 2 * 3 * 480 and n[2].duration == 336
    assert n[3].position == 3 * 3 * 480 and n[3].controls["vel"] == 120
    assert parse_text(s.to_text()).to_json() == s.to_json()
    assert [len(p) for p in phrases(n)] == [1, 1, 1]


def test_overlap_and_bad_input_errors():
    with pytest.raises(WarbleError) as e:
        parse_text("ら C4 1\nか D4 1 @ beat 0.5\n")
    assert e.value.code == "overlapping_notes"
    with pytest.raises(WarbleError):
        parse_text("ら H4 1\n")


def test_inline():
    s = parse_inline("ら:C4:1 r:1 か:D4:1/2")
    assert [(x.lyric, x.position, x.duration) for x in s.tracks[0].notes] == [("ら", 0, 480), ("か", 960, 240)]


def test_japanese_frontend():
    assert ja.kana_to_romaji("きゃっと") == "kyatto"
    assert ja.kana_to_romaji("ん") == "N"
    assert ja.kana_to_romaji("あー") == "aa"
    assert ja.split_mora("きゃっとー") == ["きゃ", "っ", "と", "ー"]
    assert ja.to_hiragana("ヴァ") == "ゔぁ" and ja.to_hiragana("う゛") == "ゔ"


def test_lyrics_split_and_assign():
    units, readings = split("茶摘み", "ja")
    assert [u["lyric"] for u in units] == ["ちゃ", "つ", "み"] and readings[0]["reading"] == "ちゃつ"
    units, _ = split("hello world", "en")
    assert [(u["lyric"], u["notes"]) for u in units] == [("hello", 2), ("world", 1)]
    notes = [Note("a", 60, i * 480, 480) for i in range(5)]
    rep = assign(notes, units)
    assert [n.lyric for n in notes] == ["hello", "+", "world", "+", "+"] and "mismatch" in rep


def test_pitchbend_encoding_matches_openutau():
    # values from openutau's Base64EncodeInt12: two chars each, repeats as #n#
    assert encode_pitchbend([0, 0, 0, 5]) == "AA#2#AF"
    assert encode_pitchbend([-1]) == "//"
    assert encode_pitchbend([10, 10]) == "AK#1#"
    vals = [0, -400, -400, 12, 2047, -2048, 7, 7, 7]
    assert decode_pitchbend(encode_pitchbend(vals)) == vals
    assert fmt(12.0) == "12" and fmt(846.574) == "846.574" and fmt(5) == "5"


def test_musicxml_round_trip(tmp_path):
    from warble.formats import musicxml
    from warble.score import load

    s = parse_text("bpm 100\ntime 3/4\nさ C4 1\nく D4 1/2\n+ E4 1/2\nら F#4 2\nr 1\nか G4 4\nbpm 130 @ bar 4\nき A4 1\n")
    p = str(tmp_path / "t.musicxml")
    musicxml.save(s, p)
    s2 = load(p)
    assert [(n.lyric, n.tone, n.position, n.duration) for n in s2.tracks[0].notes] == [(n.lyric, n.tone, n.position, n.duration) for n in s.tracks[0].notes]
    assert s2.tempos == [(0, 100.0), (4320, 130.0)] and s2.time_signatures == [(0, 3, 4)]
