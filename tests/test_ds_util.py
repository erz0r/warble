"""timing math ported from openutau's DiffSingerUtils and the phonemizer alignment."""

import numpy as np
import pytest

from warble.ds import util
from warble.ds.phonemizer import _stretch
from warble.ds.pitch import fill_rest_midi


def test_frame_rounding_is_cumulative_and_bankers():
    fm = 10.0
    # cum 15 -> round(2.0)=2 ; cum 25 -> round(3.0)=3 ; boundaries land in the frame that contains them
    assert util.durations_ms_to_frames([15, 10], fm) == [2, 1]
    # cum 5 -> 5/10+0.5 = 1.0 -> 1 ; banker's rounding on exact .5: 2.5 -> 2, 3.5 -> 4
    assert util.durations_ms_to_frames([5], fm) == [1]
    assert util.durations_ms_to_frames([20], fm) == [round(2.5)]
    assert util.durations_ms_to_frames([30], fm) == [4]
    # many small durations never drift: total equals the rounding of the total
    d = [11.61] * 100
    assert sum(util.durations_ms_to_frames(d, 11.61)) == round(sum(d) / 11.61 + 0.5)


def test_padded_segments_insert_gap_sp():
    phones = [
        {"phoneme": "k", "position_ms": 0, "duration_ms": 50},
        {"phoneme": "a", "position_ms": 50, "duration_ms": 200},
        {"phoneme": "s", "position_ms": 300, "duration_ms": 50},
    ]
    segs = util.padded_segments(phones, 10.0)
    assert [s[0] for s in segs] == ["SP", "k", "a", "SP", "s", "SP"]
    assert segs[0][1] == 80 and segs[-1][1] == 80
    assert segs[3][1] == 50 and segs[3][2] == -1


def test_word_div_splits_at_vowels():
    segs = [("SP", 80, -1), ("k", 50, 0), ("a", 200, 1), ("s", 50, 2), ("a", 100, 3), ("SP", 80, -1)]
    ph_dur = [8, 5, 20, 5, 10, 8]
    div, dur = util.padded_word_div_and_dur(segs, ph_dur, lambda p: p == "a")
    assert div == [2, 2, 2] and sum(div) == len(segs)
    assert dur == [13, 25, 18] and sum(dur) == sum(ph_dur)


def test_fit_duration_sum_borrows_backwards():
    assert util.fit_duration_sum([3, 3, 3], 10) == [3, 3, 4]
    assert util.fit_duration_sum([3, 3, 3], 5) == [3, 2, 0]
    with pytest.raises(ValueError):
        util.fit_duration_sum([1, 1], -1)


def test_rest_midi_fill_splits_at_middle():
    midi = [0, 60, 0, 0, 0, 64, 0]
    rest = [True, False, True, True, True, False, True]
    assert fill_rest_midi(midi, rest) == [60, 60, 60, 60, 64, 64, 64]
    assert fill_rest_midi([1, 2], [True, True]) == [60.0, 60.0]


def test_stretch_ends_exactly_at_target():
    pos = _stretch([2, 3, 5], 10.0, 1000.0)
    assert pos == [900.0, 920.0, 950.0]
    pos = _stretch([1, 1], 0.5, 10.0)
    assert pos[-1] + 0.5 == pytest.approx(10.0)


def test_resample_padded_curve_keeps_padding_aligned():
    c = np.array([0] * 8 + list(range(10)) + [0] * 8, np.float32)
    out = util.resample_padded_curve(c, 8 + 20 + 8, 8, 8, 8, 8, 10.0, 5.0)
    assert len(out) == 36 and np.all(out[:8] == 0) and np.all(out[-8:] == 0)


def test_speedup_divides_1000():
    for steps in (1, 3, 7, 20, 33, 1000, 5000):
        s = util.speedup_for_steps(steps)
        assert 1000 % s == 0 and s <= max(1, 1000 // steps)
