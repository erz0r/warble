"""what a render was supposed to be: notes, phones, joins and the intended pitch, in audio time.

read from the `<wav>.render.json` sidecar that `sing` writes. score time t is at
t + score_offset_ms in the file.
"""

import json
import os

import numpy as np

from ..errors import WarbleError


class Intent:
    def __init__(self, notes, phones, pitch_t_ms, pitch_midi, joins, source):
        self.notes = notes
        self.phones = phones
        self.pitch_t_ms = pitch_t_ms
        self.pitch_midi = pitch_midi
        self.joins = joins
        self.source = source

    def pitch_at(self, t_ms):
        if self.pitch_t_ms is None or len(self.pitch_t_ms) == 0:
            return np.full(np.shape(t_ms), np.nan)
        out = np.interp(t_ms, self.pitch_t_ms, self.pitch_midi, left=np.nan, right=np.nan)
        # outside any phrase's curve the intent is undefined (rests)
        return np.where(self._covered(t_ms), out, np.nan)

    def _covered(self, t_ms):
        t = np.asarray(t_ms, float)
        m = np.zeros(t.shape, bool)
        for a, b in self._spans:
            m |= (t >= a) & (t <= b)
        return m

    def note_at(self, t_ms):
        for n in self.notes:
            if n["start_ms"] <= t_ms < n["end_ms"]:
                return n
        return None

    def rests(self, total_ms, min_ms=120.0):
        """time ranges with no note and no phone, where the render should be silent."""
        busy = sorted([(min(p["start_ms"], p.get("audio_start_ms", p["start_ms"])), p["end_ms"]) for p in self.phones]
                      + [(n["start_ms"], n["end_ms"]) for n in self.notes])
        out, cur = [], 0.0
        for a, b in busy:
            if a - cur >= min_ms:
                out.append((cur + 40, a - 40))
            cur = max(cur, b)
        if total_ms - cur >= min_ms:
            out.append((cur + 60, total_ms - 20))
        return [(a, b) for a, b in out if b - a > 40]


# onsets that keep the voice flowing through a join (vowels, nasals, liquids, glides). stops and
# fricatives, voiced or not, close or narrow the tract, so a level dip there is natural.
SONORANT_KANA = set("あいうえおをんなにぬねのまみむめもらりるれろやゆよわゐゑぁぃぅぇぉゃゅょ")
SONORANT_ROMAJI = ("a", "i", "u", "e", "o", "n", "m", "r", "l", "y", "w", "N")


def starts_voiced(alias):
    """does this alias's own sound begin with a sonorant? 'a か' begins on the vowel a; 'か' on k."""
    toks = alias.split(" ")
    if len(toks) == 2 and toks[0] not in ("-", "*"):
        head = toks[0]  # vcv / vc: starts on the previous vowel
    else:
        head = toks[-1]
    if not head:
        return False
    from ..lang import ja

    h = ja.to_hiragana(head)
    if h[0] in SONORANT_KANA:
        return True
    return head.startswith(SONORANT_ROMAJI)


def from_sidecar(wav_path, side_path=None):
    side_path = side_path or wav_path + ".render.json"
    if not os.path.isfile(side_path):
        return None
    with open(side_path, encoding="utf-8") as f:
        side = json.load(f)
    off = float(side.get("score_offset_ms", 0.0))
    notes, phones, joins = [], [], []
    pts, pms, spans = [], [], []
    for ph in side["phrases"]:
        for n in ph["notes"]:
            notes.append({
                "index": n["index"], "lyric": n["lyric"], "pitch": n["pitch"], "tone": n["tone"],
                "start_ms": n["start_ms"] + off, "end_ms": n["end_ms"] + off, "controls": n.get("controls", {}),
                "phrase": ph["index"], "track": ph.get("track"),
            })
        prev = None
        for p in ph["phones"]:
            start = p["position_ms"] + off
            end = start + p.get("duration_ms", 0.0)
            q = {"phoneme": p["phoneme"], "start_ms": start, "end_ms": end, "vowel": p.get("vowel", True),
                 "phrase": ph["index"], "word": p.get("word")}
            if "preutter" in p:
                q["audio_start_ms"] = start - p["preutter"]
                q["overlap"] = p.get("overlap", 0.0)
                q["oto"] = p.get("oto")
                # the next sample's preutterance overlays this one's tail: the sung vowel ends there
                q["solo_end_ms"] = end - p.get("tail_intrude", 0.0)
            phones.append(q)
            if prev is not None and "preutter" in p:
                # a utau join: the next sample fades in over [start - preutter, start - preutter + overlap]
                joins.append({"t_ms": start - p["preutter"] + max(0.0, p.get("overlap", 0.0)) / 2, "from": prev["phoneme"], "to": p["phoneme"],
                              "crossfade_ms": max(0.0, p.get("overlap", 0.0)), "phrase": ph["index"],
                              "voiced_onset": starts_voiced(p["phoneme"])})
            prev = q
        if "pitch" in ph:
            pc = ph["pitch"]
            t = pc["start_ms"] + off + np.arange(len(pc["midi"])) * pc["frame_ms"]
            pts.append(t)
            pms.append(np.asarray(pc["midi"], float))
            ph_notes = [n for n in notes if n["phrase"] == ph["index"]]
            spans.append((min(n["start_ms"] for n in ph_notes) - 150, max(n["end_ms"] for n in ph_notes) + 20))
    notes.sort(key=lambda n: n["start_ms"])
    if pts:
        order = np.argsort(np.concatenate(pts))
        pt, pm = np.concatenate(pts)[order], np.concatenate(pms)[order]
    else:
        pt, pm = None, None
    it = Intent(notes, phones, pt, pm, joins, side_path)
    it._spans = spans
    it.offset_ms = off
    it.sample_rate = side.get("sample_rate")
    return it


def from_score(score_path, offset_ms=0.0):
    """intent from a bare score (no render data): notes only, pitch = note grid."""
    from ..score import load, pitch_name

    s = load(score_path)
    tm = s.tempo_map
    notes = []
    for tr in s.tracks:
        for i, n in enumerate(tr.notes, start=1):
            notes.append({"index": i, "lyric": n.lyric, "pitch": pitch_name(n.tone), "tone": n.tone,
                          "start_ms": tm.tick_to_ms(n.position) + offset_ms, "end_ms": tm.tick_to_ms(n.end) + offset_ms,
                          "controls": n.controls, "phrase": None, "track": tr.name})
    if not notes:
        raise WarbleError("score_empty", f"{score_path} has no notes")
    t = np.arange(0, max(n["end_ms"] for n in notes) + 50, 5.0)
    midi = np.full(len(t), np.nan)
    for n in notes:
        m = (t >= n["start_ms"]) & (t < n["end_ms"])
        midi[m] = n["tone"]
    ok = np.isfinite(midi)
    it = Intent(notes, [], t[ok], midi[ok], [], score_path)
    it._spans = [(n["start_ms"], n["end_ms"]) for n in notes]
    it.offset_ms = offset_ms
    return it
