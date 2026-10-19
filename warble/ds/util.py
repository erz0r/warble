"""timing and tensor helpers for the diffsinger pipeline.

ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Core/DiffSinger/DiffSingerUtils.cs
and DiffSingerSpeakerEmbedManager.cs.
"""

import math

import numpy as np

HEAD_FRAMES = 8
TAIL_FRAMES = 8


def round_half_even(x):
    """c#'s Math.Round(x, MidpointRounding.ToEven); python's round() already does banker's rounding."""
    return int(round(x))


def durations_ms_to_frames(durations_ms, frame_ms):
    """cumulative rounding: frame = round(cum_ms / frame_ms + 0.5) half-to-even; durations are deltas.
    the +0.5 makes every boundary land on the frame that contains it."""
    out, acc, prev = [], 0.0, 0
    for d in durations_ms:
        if d < 0:
            raise ValueError(f"negative diffsinger duration: {d} ms")
        acc += d
        frame = round_half_even(acc / frame_ms + 0.5)
        out.append(frame - prev)
        prev = frame
    return out


def padded_segments(phones, frame_ms, head=HEAD_FRAMES, tail=TAIL_FRAMES):
    """[(phoneme, duration_ms, phone_index)]: head SP, phones with an SP per gap, tail SP.
    phones are dicts with 'phoneme', 'position_ms', 'duration_ms'."""
    out = [("SP", head * frame_ms, -1)]
    for i, ph in enumerate(phones):
        if i > 0:
            gap = ph["position_ms"] - (phones[i - 1]["position_ms"] + phones[i - 1]["duration_ms"])
            if gap > 0:
                out.append(("SP", gap, -1))
        out.append((ph["phoneme"], ph["duration_ms"], i))
    out.append(("SP", tail * frame_ms, -1))
    return out


def padded_durations(segments, frame_ms):
    return durations_ms_to_frames([s[1] for s in segments], frame_ms)


def padded_word_div_and_dur(segments, ph_dur, is_vowel):
    """word mode inputs for the pitch/variance linguistic encoders (PaddedWordDivAndDur)."""
    if len(ph_dur) != len(segments):
        raise ValueError(f"word mode duration length mismatch: {len(ph_dur)} durations for {len(segments)} padded tokens")
    vowel_ids = [i for i, s in enumerate(segments) if s[2] >= 0 and is_vowel(s[0])]
    if not vowel_ids:
        vowel_ids = [len(segments) - 2]
    word_div = [vowel_ids[0]] + [b - a for a, b in zip(vowel_ids, vowel_ids[1:])] + [len(segments) - vowel_ids[-1]]
    if any(d <= 0 for d in word_div):
        raise ValueError("word mode generated an empty word division")
    word_dur, off = [], 0
    for n in word_div:
        word_dur.append(int(sum(ph_dur[off:off + n])))
        off += n
    return word_div, word_dur


def fit_duration_sum(durations, total):
    """make durations sum to total by adjusting the last entry, borrowing backwards if it goes negative."""
    res = list(durations)
    if not res:
        return res
    res[-1] += total - sum(res)
    if res[-1] < 0:
        deficit = -res[-1]
        res[-1] = 0
        for i in range(len(res) - 2, -1, -1):
            if deficit <= 0:
                break
            take = min(res[i], deficit)
            res[i] -= take
            deficit -= take
        if deficit > 0:
            raise ValueError(f"cannot fit durations to {total} frames")
    return res


def resample_curve(curve, length, source_frame_ms=None, target_frame_ms=None):
    """linear resample. with frame sizes, maps frame i at target rate to time i*target/source."""
    curve = np.asarray(curve, dtype=np.float32)
    if curve.size == 0:
        return None
    if length == len(curve) and (source_frame_ms is None or abs(source_frame_ms - target_frame_ms) < 1e-3):
        return curve
    if length == 1:
        return curve[:1].copy()
    if source_frame_ms and target_frame_ms and len(curve) > 1:
        x = np.arange(length) * target_frame_ms / source_frame_ms
    else:
        x = np.arange(length) / (length - 1) * (len(curve) - 1)
    return np.interp(x, np.arange(len(curve)), curve).astype(np.float32)


def resample_padded_curve(curve, length, src_head, src_tail, dst_head, dst_tail, src_frame_ms, dst_frame_ms):
    """resample head, body and tail separately so padding lines up across models with different hops."""
    curve = np.asarray(curve, dtype=np.float32)
    if length == len(curve) and src_head == dst_head and src_tail == dst_tail and abs(src_frame_ms - dst_frame_ms) < 1e-3:
        return curve
    src_body = len(curve) - src_head - src_tail
    dst_body = length - dst_head - dst_tail
    if src_body < 0 or dst_body < 0:
        return resample_curve(curve, length, src_frame_ms, dst_frame_ms)
    out = np.zeros(length, np.float32)

    def seg(s0, sn, d0, dn):
        if dn <= 0:
            return
        if sn <= 0:
            out[d0:d0 + dn] = 0
            return
        out[d0:d0 + dn] = resample_curve(curve[s0:s0 + sn], dn, src_frame_ms, dst_frame_ms)

    seg(0, src_head, 0, dst_head)
    seg(src_head, src_body, dst_head, dst_body)
    seg(len(curve) - src_tail, src_tail, length - dst_tail, dst_tail)
    return out


def tone_to_freq(tone):
    return 440.0 * 2.0 ** ((np.asarray(tone, dtype=np.float64) - 69.0) / 12.0)


def freq_to_tone(freq):
    f = np.asarray(freq, dtype=np.float64)
    with np.errstate(divide="ignore"):
        return np.where(f > 0, 69.0 + 12.0 * np.log2(np.maximum(f, 1e-9) / 440.0), np.nan)


def speedup_for_steps(steps):
    """largest divisor of 1000 that is <= 1000/steps."""
    speedup = max(1, 1000 // max(1, int(steps)))
    while 1000 % speedup != 0 and speedup > 1:
        speedup -= 1
    return speedup


def sampling_feeds(cfg, steps, depth, input_names):
    """acoustic sampling inputs, as DiffSingerRenderer.InvokeDiffsinger builds them, but decided by
    which inputs the graph actually has."""
    feeds = {}
    if cfg["use_continuous_acceleration"] or "steps" in input_names:
        if "depth" in input_names:
            feeds["depth"] = np.float32(depth)
        feeds["steps"] = np.int64(steps)
    else:
        if "depth" in input_names:
            d = int(round(depth * 1000))
            speedup = max(1, d // steps)
            d = d // speedup * speedup
            feeds["depth"] = np.int64(d)
        else:
            speedup = speedup_for_steps(steps)
        feeds["speedup"] = np.int64(speedup)
    return feeds


def frame_note_index(frame_times_ms, notes_ms):
    """for each frame time, the index of the note covering it (nearest note for rests/padding).
    notes_ms: list of (start_ms, end_ms)."""
    starts = np.array([s for s, _ in notes_ms])
    ends = np.array([e for _, e in notes_ms])
    idx = np.searchsorted(starts, frame_times_ms, side="right") - 1
    idx = np.clip(idx, 0, len(notes_ms) - 1)
    # inside a gap after note idx: pick the nearer neighbour
    for k, t in enumerate(frame_times_ms):
        i = idx[k]
        if t >= ends[i] and i + 1 < len(notes_ms) and (starts[i + 1] - t) < (t - ends[i]):
            idx[k] = i + 1
    return idx


def mix_speakers(weights, embeds):
    """weights: [T, S] per-frame speaker weights; rows are normalized like openutau
    (sum > 1 divides, sum < 1 is topped up on the default speaker by the caller). embeds: [S, H]."""
    w = np.asarray(weights, dtype=np.float32)
    return (w @ np.asarray(embeds, dtype=np.float32))[None, :, :]


def isclose(a, b):
    return math.isclose(a, b, abs_tol=1e-6)
