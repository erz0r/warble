"""classic utau rendering: phonemizer -> phones with oto timing -> resampler -> wavtool.

phone timing (auto preutterance/overlap, envelopes) is ported from openutau (MIT, Copyright (c)
2014 StAkira): OpenUtau.Core/Ustx/UPhoneme.cs; concatenation from Classic/SharpWavtool.cs.
"""

import difflib
import os
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from .. import pitchctl
from ..bank import utau as utaubank
from ..ds import pitch as dspitch
from ..errors import WarbleError
from . import phonemizers, resampler
from .voice import Voice

SR = resampler.SR


class UtauEngine:
    def __init__(self, bank, resampler=None, phonemizer=None, wavtool=None):
        self.bank = bank
        self.voice = Voice(bank)
        self.style, _, _ = utaubank.bank_reclist(bank)
        self.resampler_name = resampler or "builtin"
        self.resampler_exe = None if self.resampler_name == "builtin" else resampler_find(self.resampler_name)
        self.wavtool_name = wavtool or "builtin"
        self.wavtool_exe = None if self.wavtool_name == "builtin" else resampler_find(self.wavtool_name)
        self._requested_phonemizer = phonemizer

    def phonemizer(self, name=None):
        pname, how, warn = phonemizers.choose(self.bank, self.style, name or self._requested_phonemizer)
        return phonemizers.REGISTRY[pname], pname, how, warn

    # ---- phones ---------------------------------------------------------------------------

    def phonemize_phrase(self, words, tm, lang, voice_of, seed=None, prev_end_ms=None, phonemizer=None, **_):
        cls, pname, how, warn = self.phonemizer(phonemizer)
        def color_of(n):
            v = n.controls.get("color") or voice_of(n)
            return None if v in (None, "default") else v

        ph = cls(self.voice, tm, color_of)
        notes = [n for w in words for n in w]
        raw = []
        unknown = []
        for wi, w in enumerate(words):
            head = w[0]
            prev_nb = words[wi - 1][-1] if wi > 0 else None
            next_nb = words[wi + 1][0] if wi + 1 < len(words) else None
            out = ph.process(w, prev_nb, next_nb, prev_nb, next_nb)
            for k, p in enumerate(out):
                tick = head.position + p["position"]
                note = next((n for n in w if n.position <= tick < n.end), w[0])
                hit = self.voice.lookup(p["alias"], note.tone + note.controls.get("shift", 0), color_of(note))
                if hit is None:
                    unknown.append({
                        "lyric": head.lyric, "alias": p["alias"], "position": head.position, "line": head.line,
                        "closest": _closest_aliases(p["alias"], self.voice.alias_map),
                    })
                    continue
                oset, oto, mapped = hit
                raw.append({"alias": mapped, "requested": p["alias"], "tick": tick, "word": wi, "note": note, "oto": oto,
                            "wav_path": os.path.join(oset.dir, oto.wav), "oto_set": oset.name or "."})
        raw.sort(key=lambda r: r["tick"])
        end_tick = notes[-1].end
        phones = []
        for i, r in enumerate(raw):
            note = r["note"]
            nxt_tick = raw[i + 1]["tick"] if i + 1 < len(raw) else end_tick
            c = note.controls
            phones.append({
                "phoneme": r["alias"],
                "alias": r["alias"],
                "word": r["word"],
                "note_index": notes.index(note),
                "tone": note.tone + c.get("shift", 0),
                "position_ms": tm.tick_to_ms(r["tick"]),
                "end_ms": tm.tick_to_ms(nxt_tick),
                "duration_ticks": nxt_tick - r["tick"],
                "tempo": tm.bpm_at(r["tick"]),
                "oto": r["oto"],
                "wav_path": r["wav_path"],
                "oto_set": r["oto_set"],
                "vel": c.get("vel", 100.0),
                "vol": c.get("vol", 100.0),
                "mod": c.get("mod", 0.0),
                "atk": c.get("atk", 100.0),
                "dec": c.get("dec", 0.0),
                "flags": c.get("flags", ""),
                # 'pre'/'ovl' are deltas in ms; 'preutter'/'overlap' are absolute overrides (ust PreUtterance=)
                "pre_delta": c.get("pre", (c["preutter"] - r["oto"].preutter) if "preutter" in c else None),
                "ovl_delta": c.get("ovl", (c["overlap"] - r["oto"].overlap) if "overlap" in c else None),
            })
        for p in phones:
            p["duration_ms"] = p["end_ms"] - p["position_ms"]
            p["vowel"] = _alias_is_voiced(p["alias"])
        _fit_overlaps(phones, prev_end_ms)
        return {
            "phones": phones,
            "unknown": unknown,
            "phonemizer": pname,
            "phonemizer_choice": how,
            "warnings": [warn] if warn else [],
            "words": [{"lyric": w[0].lyric, "source": pname} for w in words],
            "durations": "oto",
        }

    # ---- audio ----------------------------------------------------------------------------

    def render_phrase(self, words, tm, lang, voice_of, steps=None, depth=None, seed=None, timings=None, prev_end_ms=None, allow_unknown=False,
                      phonemizer=None, **_):
        timings = timings if timings is not None else {}
        t0 = time.time()
        res = self.phonemize_phrase(words, tm, lang, voice_of, prev_end_ms=prev_end_ms, phonemizer=phonemizer)
        timings["phonemize"] = timings.get("phonemize", 0) + time.time() - t0
        if res["unknown"] and not allow_unknown:
            return {"phonemes": res, "error": "unknown_aliases"}
        phones = res["phones"]
        if not phones:
            return {"phonemes": res, "error": "no_phones"}
        notes = [n for w in words for n in w]
        # pitch: rule curve on a 5 ms grid plus note controls (the tuning layer replaces this later)
        t0 = time.time()
        start_ms = min(p["position_ms"] - p["preutter"] for p in phones) - 50
        end_ms = max(p["end_ms"] for p in phones) + 100
        fm = 5.0
        T = int((end_ms - start_ms) / fm) + 2
        grid = start_ms + np.arange(T) * fm
        spans = dspitch.note_spans(notes, tm)
        midi = dspitch.rule_pitch(notes, tm, start_ms, fm, T)
        midi = pitchctl.apply_note_controls(midi, grid, notes, spans, tm)

        def cents_at(ms):
            return float(np.interp(ms, grid, midi)) * 100.0

        items = [resampler.Item(p, tm, cents_at, self.resampler_name) for p in phones]
        timings["pitch"] = timings.get("pitch", 0) + time.time() - t0

        t0 = time.time()
        warn = set()
        outputs = [None] * len(items)
        errors = []

        def work(i):
            it = items[i]
            if self.resampler_exe:
                y, args = resampler.external(it, self.resampler_exe, resampler.CACHE_DIR)
                phones[i]["resampler_args"] = args
                return y
            return resampler.builtin(it, warn)

        with ThreadPoolExecutor(max_workers=min(8, os.cpu_count() or 2)) as ex:
            futs = {ex.submit(work, i): i for i in range(len(items))}
            for f, i in futs.items():
                try:
                    outputs[i] = f.result()
                except WarbleError as e:
                    errors.append(e.to_json() | {"note": phones[i]["note_index"], "alias": phones[i]["alias"]})
        if errors:
            raise WarbleError("resampler_errors", f"{len(errors)} resampler call(s) failed", errors=errors)
        timings["resample"] = timings.get("resample", 0) + time.time() - t0

        t0 = time.time()
        origin = min(p["position_ms"] - p["preutter"] for p in phones)
        if self.wavtool_exe:
            import soundfile as sf

            from . import wavtool

            paths = []
            for it, y in zip(items, outputs):
                path = os.path.join(resampler.CACHE_DIR, f"note-{it.key()}.wav")
                if not os.path.exists(path):
                    os.makedirs(resampler.CACHE_DIR, exist_ok=True)
                    sf.write(path, y, SR, subtype="PCM_16")
                paths.append(path)
            out, calls = wavtool.concatenate(items, paths, self.wavtool_exe, resampler.CACHE_DIR, origin)
            for p, c in zip(phones, calls):
                p["wavtool_args"] = c
            timings["wavtool"] = timings.get("wavtool", 0) + time.time() - t0
            return self._result(out, origin, res, grid, midi, warn)
        # built-in wavtool: place each sample at position - preutterance (minus skipped audio), apply envelope, sum
        segs = []
        for it, y in zip(items, outputs):
            y = it.apply_envelope(y.copy())
            pos = it.phone["position_ms"] - it.phone["preutter"] - origin
            pos_s = int(round(pos * SR / 1000))
            skip = int(round(it.skip_over * SR / 1000))
            segs.append((pos_s, skip, y))
        total = max(p + len(y) - s for p, s, y in segs)
        out = np.zeros(max(total, 1), np.float32)
        for p, s, y in segs:
            lo = max(0, -s)
            chunk = y[s + lo:] if s >= 0 else y
            out[p + lo:p + lo + len(chunk)] += chunk[: max(0, len(out) - (p + lo))]
        timings["wavtool"] = timings.get("wavtool", 0) + time.time() - t0
        return self._result(out, origin, res, grid, midi, warn)

    def _result(self, out, origin, res, grid, midi, warn):
        return {
            "samples": out,
            "sample_rate": SR,
            "start_ms": origin,
            "phonemes": _jsonable(res),
            "frame_ms": float(grid[1] - grid[0]),
            "frame_times_ms": grid,
            "pitch_start_ms": float(grid[0]),
            "pitch_midi": midi,
            "pitch_source": "rule",
            "warnings": sorted(warn) + res["warnings"],
            "resampler": self.resampler_name,
            "wavtool": self.wavtool_name,
        }


UNVOICED_TAILS = {"R", "-", "br", "息", "吸", "k", "s", "t", "p", "h", "f", "sh", "ch", "ts", "ky", "py", "hy", "q", "cl", "・"}


def _alias_is_voiced(alias):
    """whether an alias is expected to end voiced, judged from its last token. vc parts ('a k'),
    endings ('a R') and breaths are not; cv, vcv and vowels are."""
    tok = alias.split(" ")[-1] if alias else ""
    tok = tok.rstrip("0123456789↑↓_")
    return bool(tok) and tok not in UNVOICED_TAILS and tok not in ("息", "吸")


def _closest_aliases(alias, alias_map, n=8):
    """difflib can't rank one-kana aliases, so aliases that contain the request come first."""
    pool = list(alias_map)
    contains = sorted((a for a in pool if alias and alias in a), key=len)[:n]
    fuzzy = [a for a in difflib.get_close_matches(alias, pool, n=n, cutoff=0.3) if a not in contains]
    return (contains + fuzzy)[:n]


def resampler_find(name):
    return resampler.find_resampler(name)


def _fit_overlaps(phones, prev_end_ms):
    """UPhoneme.ValidateOverlap + ValidateEnvelope over a phrase."""
    prev = None
    for p in phones:
        oto = p["oto"]
        stretch = 2 ** (1.0 - p["vel"] / 100.0)
        auto_ovl = oto.overlap * stretch
        auto_pre = oto.preutter * stretch
        p["adjacent"] = False
        p["tail_intrude"] = 0.0
        p["tail_overlap"] = 0.0
        if prev is not None or prev_end_ms is not None:
            prev_end = prev["end_ms"] if prev is not None else prev_end_ms
            gap = p["position_ms"] - prev_end
            max_pre = auto_pre
            if prev is not None and gap <= 0:
                p["adjacent"] = True
                prev_dur = prev["duration_ms"]
                if auto_ovl > 0 and auto_pre - auto_ovl > prev_dur * 0.5:
                    max_pre = prev_dur * 0.5 / (auto_pre - auto_ovl) * auto_pre
                max_pre = min(max_pre, prev_dur)
                if prev["preutter"] < 5:
                    max_pre = min(max_pre, prev_dur + prev["preutter"] - 5)
            elif gap < auto_pre:
                max_pre = gap
            if auto_pre > max_pre:
                ratio = max_pre / auto_pre if auto_pre > 0 else 0.0
                auto_pre = max_pre
                auto_ovl *= ratio
            if auto_ovl < 0 and prev is not None:
                auto_ovl = max(auto_ovl, min(0.0, 35 - prev["duration_ms"] + auto_pre))
        p["auto_preutter"] = auto_pre
        p["auto_overlap"] = auto_ovl
        p["preutter"] = max(0.0, auto_pre + (p["pre_delta"] or 0))
        p["overlap"] = auto_ovl + (p["ovl_delta"] or 0)
        p["overlapped"] = False
        if prev is not None:
            if prev["duration_ms"] - p["preutter"] < 5:
                p["overlap"] = max(p["overlap"], 5 - (prev["duration_ms"] - p["preutter"]))
            prev["tail_intrude"] = max(p["preutter"], p["preutter"] - p["overlap"]) if p["adjacent"] else 0.0
            prev["tail_overlap"] = max(p["overlap"], 0.0) if p["adjacent"] else 0.0
            p["overlapped"] = p["adjacent"] and p["overlap"] > 0
        prev = p
    for i, p in enumerate(phones):
        nxt = phones[i + 1] if i + 1 < len(phones) else None
        fade_in = p["overlap"] if p["overlapped"] else 5.0
        fade_out = p["tail_overlap"] if (nxt is not None and nxt["overlapped"]) else 35.0
        vol = 100.0
        x0 = -p["preutter"]
        x1 = max(x0 + 5, x0 + fade_in)
        x2 = max(0.0, x1)
        x4 = p["duration_ms"] - p["tail_intrude"] + p["tail_overlap"]
        x3 = max(x2, x4 - fade_out)
        p["envelope"] = [(x0, 0.0), (x1, p["atk"] * vol / 100.0), (x2, vol), (x3, vol * (1 - p["dec"] / 100.0)), (x4, 0.0)]


def _jsonable(res):
    out = dict(res)
    out["phones"] = []
    for p in res["phones"]:
        q = {k: v for k, v in p.items() if k not in ("oto", "note")}
        o = p["oto"]
        q["oto"] = {"wav": o.wav, "offset": o.offset, "consonant": o.consonant, "cutoff": o.cutoff, "preutter": o.preutter, "overlap": o.overlap, "set": p["oto_set"]}
        q["envelope"] = [list(e) for e in p["envelope"]]
        out["phones"].append(q)
    return out
