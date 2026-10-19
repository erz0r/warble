"""pitch for a diffsinger phrase: the dspitch model when the bank has one, else a rule curve.

model path ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Core/DiffSinger/DiffSingerPitch.cs.
returns midi pitch per frame on the given frame grid, starting head frames before the first phone.
"""

import numpy as np

from .. import onnxrun
from . import util

PITCH_STEPS = 10
RULE_TRANSITION_MS = 90.0


def note_spans(notes, tm):
    return [(tm.tick_to_ms(n.position), tm.tick_to_ms(n.end)) for n in notes]


def model_pitch(md, phones, notes, tm, mixes_by_frame=None, expr=None, steps=PITCH_STEPS, seed=None):
    """run dspitch. md is the dspitch ModelDir. returns (midi[T], frame_ms, start_ms)."""
    fm = md.frame_ms
    head, tail = util.HEAD_FRAMES, util.TAIL_FRAMES
    start_ms = phones[0]["position_ms"] - head * fm
    segs = util.padded_segments(phones, fm)
    ph_dur = util.padded_durations(segs, fm)
    T = int(sum(ph_dur))
    d = md.dict()
    for ph in phones:
        if d is not None and ph["phoneme"] not in d.symbols:
            from ..errors import WarbleError

            raise WarbleError("symbol_type_missing", f"phoneme '{ph['phoneme']}' has no type in the pitch model's dictionary {d.path}")
    is_vowel = (lambda p: d.is_vowel(p)) if d is not None else (lambda p: False)
    tokens = np.array([[md.token(s[0]) for s in segs]], np.int64)
    feeds = {"tokens": tokens}
    if md.cfg["predict_dur"]:
        wdiv, wdur = util.padded_word_div_and_dur(segs, ph_dur, is_vowel)
        feeds["word_div"] = np.array([wdiv], np.int64)
        feeds["word_dur"] = np.array([wdur], np.int64)
    else:
        feeds["ph_dur"] = np.array([ph_dur], np.int64)
    if md.cfg["use_lang_id"]:
        feeds["languages"] = np.array([[md.lang_id(phones[s[2]]["phoneme"]) if s[2] >= 0 else 0 for s in segs]], np.int64)
    lin = onnxrun.run(md.model_path("linguistic"), feeds, "pitch-linguistic")

    # notes with head/gap/tail rests (DiffSingerPitch.Process)
    spans = note_spans(notes, tm)
    dur_ms, midi, rest = [max(0.0, spans[0][0] - start_ms)], [notes[0].tone], [True]
    prev_end = spans[0][0]
    for n, (s, e) in zip(notes, spans):
        if s - prev_end > 0:
            dur_ms.append(s - prev_end)
            midi.append(n.tone)
            rest.append(True)
        dur_ms.append(e - s)
        midi.append(n.tone)
        if n.lyric.startswith("+"):
            rest.append(rest[-1])
        else:
            phs = [p for p in phones if p["position_ms"] + p["duration_ms"] > s + 1e-3 and p["position_ms"] < e - 1e-3]
            rest.append(not phs or all(p["phoneme"] in ("AP", "SP") or not is_vowel(p["phoneme"]) for p in phs))
        prev_end = e
    dur_ms.append(tail * fm)
    midi.append(notes[-1].tone)
    rest.append(True)
    midi = fill_rest_midi(midi, rest)
    note_dur = util.fit_duration_sum(util.durations_ms_to_frames(dur_ms, fm), T)

    pf = {
        "encoder_out": lin["encoder_out"],
        "note_midi": np.array([midi], np.float32),
        "note_dur": np.array([note_dur], np.int64),
        "ph_dur": np.array([ph_dur], np.int64),
        "pitch": np.full((1, T), 60.0, np.float32),
        "retake": np.ones((1, T), bool),
    }
    ppath = md.model_path("pitch")
    names = set(onnxrun.input_names(ppath))
    pf.update(_pitch_sampling(md.cfg, steps, names))
    if md.cfg["use_expr"] or "expr" in names:
        pf["expr"] = (np.clip(expr, 0, 1).astype(np.float32)[None, :T] if expr is not None else np.ones((1, T), np.float32))
    if md.cfg["use_note_rest"] or "note_rest" in names:
        pf["note_rest"] = np.array([rest], bool)
    if md.speakers():
        pf["spk_embed"] = md.spk_embed(mixes_by_frame(start_ms, fm, T) if mixes_by_frame else [{md.speakers()[0]: 1.0}] * T)
    out = onnxrun.run(ppath, pf, "pitch", seed=seed)
    return next(iter(out.values())).reshape(-1)[:T].astype(np.float64), fm, start_ms


def fill_rest_midi(midi, rest):
    """rest notes take the pitch of the nearest non-rest neighbour; a rest run between two notes is
    split at its middle."""
    midi = list(midi)
    n = len(rest)
    if all(rest):
        return [60.0] * n
    i = 0
    while i < n:
        if not rest[i]:
            i += 1
            continue
        j = i
        while j < n and rest[j]:
            j += 1
        if i == 0:
            for k in range(0, j):
                midi[k] = midi[j]
        elif j == n:
            for k in range(i, n):
                midi[k] = midi[i - 1]
        else:
            mid = (i + j + 1) // 2
            for k in range(i, mid):
                midi[k] = midi[i - 1]
            for k in range(mid, j):
                midi[k] = midi[j]
        i = j
    return midi


def _pitch_sampling(cfg, steps, names):
    """AddPitchSamplingInputs for integer steps."""
    if cfg["use_continuous_acceleration"] or "steps" in names:
        feeds = {"steps": np.int64(max(1, round(steps)))}
        if "depth" in names:
            feeds["depth"] = np.float32(1.0)
        return feeds
    speedup = util.speedup_for_steps(steps)
    feeds = {"speedup": np.int64(speedup)}
    if "depth" in names:
        feeds["depth"] = np.int64(1000 // speedup * speedup)
    return feeds


def rule_pitch(notes, tm, start_ms, frame_ms, T, transition_ms=RULE_TRANSITION_MS):
    """note grid with s-curve transitions centred a little before each boundary, rests holding the
    neighbouring pitch. what the engine sings when a bank has no pitch model."""
    t = start_ms + np.arange(T) * frame_ms
    spans = note_spans(notes, tm)
    idx = util.frame_note_index(t, spans)
    tones = np.array([n.tone for n in notes], np.float64)
    base = tones[idx]
    out = base.copy()
    for i in range(1, len(notes)):
        a, b = tones[i - 1], tones[i]
        if a == b:
            continue
        boundary = spans[i][0]
        # bend starts a bit before the boundary and lands shortly after it
        lo, hi = boundary - 0.6 * transition_ms, boundary + 0.4 * transition_ms
        m = (t >= lo) & (t <= hi)
        x = (t[m] - lo) / (hi - lo)
        out[m] = a + (b - a) * (0.5 - 0.5 * np.cos(np.pi * x))
    return out
