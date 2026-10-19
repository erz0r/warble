"""render a score: split tracks into phrases, render each with the right engine, mix, write audio.

besides the audio, every render writes `<out>.render.json`: per-phrase phone timings, the intended
pitch curve and controls. `inspect` reads it to compare intent against what came out.
"""

import json
import os
import sys
import time

import numpy as np

from . import onnxrun
from .bank import common
from .errors import WarbleError
from .score import TPQ, phrases, pitch_name

_ENGINES = {}


def log(msg):
    print(f"warble: {msg}", file=sys.stderr)


def engine_for(bank_path, engine=None, vocoder_dirs=None, resampler=None, wavtool=None):
    kind, ev = common.detect(bank_path)
    if kind not in ("diffsinger", "utau"):
        from .score import bank_roots

        raise WarbleError("bank_unsupported", f"{bank_path} is not a diffsinger or utau bank", hint="; ".join(ev),
                          installed_banks=[os.path.relpath(r) for r in bank_roots()])
    want = engine or ("ds" if kind == "diffsinger" else "utau")
    if want == "ds" and kind != "diffsinger":
        raise WarbleError("engine_mismatch", f"--engine ds but {bank_path} is a {kind} bank")
    if want == "utau" and kind != "utau":
        raise WarbleError("engine_mismatch", f"--engine utau but {bank_path} is a {kind} bank")
    key = (os.path.abspath(bank_path), want, resampler, wavtool)
    if key not in _ENGINES:
        t0 = time.time()
        if want == "ds":
            from .bank.ds import DsBank
            from .ds.render import DsEngine

            _ENGINES[key] = DsEngine(DsBank(bank_path), vocoder_dirs)
        else:
            from .bank.utau import UtauBank
            from .utau.render import UtauEngine

            _ENGINES[key] = UtauEngine(UtauBank(bank_path), resampler=resampler, wavtool=wavtool)
        log(f"loaded {want} bank {bank_path} in {time.time() - t0:.2f}s")
    return _ENGINES[key]


def _note_attr(note, track, key):
    return note.controls.get(key) or getattr(track, key)


def split_phrases(track):
    """phrases at rests, and also where the bank or language changes mid-run."""
    out = []
    for ph in phrases(track.notes):
        cur = [ph[0]]
        for w in ph[1:]:
            a, b = cur[-1][0], w[0]
            if _note_attr(a, track, "bank") != _note_attr(b, track, "bank") or _note_attr(a, track, "lang") != _note_attr(b, track, "lang"):
                out.append(cur)
                cur = [w]
            else:
                cur.append(w)
        out.append(cur)
    return out


def sing(score, out_path, steps=None, depth=None, seed=None, sample_rate=44100, engine=None, phrase_filter=None,
         note_range=None, vocoder_dirs=None, allow_unknown=False, resampler=None, normalize_db=None, wavtool=None,
         use_cache=True, stems_dir=None, mix_preset=None, lufs=None, no_master=False):
    t_start = time.time()
    onnxrun.reset_stats()
    cached_phrases = 0
    tm = score.tempo_map
    timings = {}
    warnings = []
    unknown = []
    phrase_reports = []
    render_phrases = []
    rendered = []  # (track, start_ms, samples@sr)
    pidx = 0
    for track in score.tracks:
        if not track.notes:
            continue
        prev_end_ms = None
        for words in split_phrases(track):
            notes = [n for w in words for n in w]
            first = notes[0]
            pidx += 1
            if phrase_filter and pidx not in phrase_filter:
                prev_end_ms = tm.tick_to_ms(notes[-1].end)
                continue
            if note_range:
                gi = [track.notes.index(n) + 1 for n in notes]
                if max(gi) < note_range[0] or min(gi) > note_range[1]:
                    prev_end_ms = tm.tick_to_ms(notes[-1].end)
                    continue
            bank = _note_attr(first, track, "bank")
            if not bank:
                raise WarbleError("no_bank", f"track '{track.name}' has no bank", hint="add 'bank <path>' to the score or pass --bank")
            lang = _note_attr(first, track, "lang")
            # resampler / wavtool: per note (first note of the phrase), then per track, then the command line
            eng = engine_for(bank, engine or track.engine, vocoder_dirs, first.controls.get("resampler") or track.resampler or resampler,
                             first.controls.get("wavtool") or track.wavtool or wavtool)

            def voice_of(n, track=track):
                return n.controls.get("voice") or track.voice

            pkey = _phrase_key(eng, words, tm, lang, track, steps, depth, seed, prev_end_ms, allow_unknown) if use_cache else None
            res = _phrase_cache_get(pkey)
            if res is not None:
                cached_phrases += 1
            else:
                res = eng.render_phrase(words, tm, lang, voice_of, steps=steps, depth=depth, seed=seed, timings=timings, prev_end_ms=prev_end_ms,
                                        phonemizer=_note_attr(first, track, "phonemizer"), track=track,
                                        allow_unknown=allow_unknown)
                _phrase_cache_put(pkey, res)
            prev_end_ms = tm.tick_to_ms(notes[-1].end)
            ph = res["phonemes"]
            if ph.get("unknown"):
                for u in ph["unknown"]:
                    u["track"] = track.name
                    u["phrase"] = pidx
                unknown.extend(ph["unknown"])
                if not allow_unknown:
                    continue
            if "samples" not in res:
                continue
            warnings.extend(res.get("warnings", []))
            samples = res["samples"]
            if res["sample_rate"] != sample_rate:
                samples = _resample(samples, res["sample_rate"], sample_rate)
            if track.curves.get("dyn"):
                # openutau dynamics curve, in dB
                t_ms = res["start_ms"] + np.arange(len(samples)) * 1000.0 / sample_rate
                ticks = np.interp(t_ms, [tm.tick_to_ms(0), tm.tick_to_ms(score.end_tick + 4 * 480)], [0, score.end_tick + 4 * 480])
                samples = samples * (10 ** (track.curve_at("dyn", ticks) / 20)).astype(np.float32)
            rendered.append((track, res["start_ms"], samples))
            phrase_reports.append({
                "index": pidx,
                "track": track.name,
                "bank": bank,
                "start_ms": round(tm.tick_to_ms(first.position), 2),
                "end_ms": round(tm.tick_to_ms(notes[-1].end), 2),
                "notes": len(notes),
                "lyrics": " ".join(w[0].lyric for w in words),
                "phonemes": " ".join(p["phoneme"] for p in ph["phones"]),
                "durations": ph.get("durations"),
                "pitch_source": res.get("pitch_source"),
            })
            render_phrases.append(_sidecar_phrase(pidx, track, words, res, tm))
    if unknown and not allow_unknown:
        raise WarbleError(
            "unknown_lyrics",
            f"{len(unknown)} lyric(s) could not be turned into phonemes the bank can sing",
            hint="fix the lyric, give phonemes in [brackets], or pass --allow-unknown to render the rest; see details.unknown for closest symbols",
            unknown=unknown,
        )
    if not rendered:
        raise WarbleError("nothing_rendered", "no phrases were rendered", hint="check --phrase / --range against the score")

    t_mix = time.time()
    mix, channels, offset_ms, stems, mix_info = _mix(rendered, score, sample_rate, mix_preset, lufs, no_master, normalize_db)
    peak = float(np.max(np.abs(mix)))
    if peak > 1.0:
        warnings.append(f"mix peaked at {20 * np.log10(peak):.1f} dBFS and was clipped; lower track volume or set master ceiling")
        mix = np.clip(mix, -1, 1)
    import soundfile as sf

    out_path = os.path.abspath(out_path)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    subtype = "PCM_24" if out_path.lower().endswith(".flac") else "PCM_16"
    sf.write(out_path, mix, sample_rate, subtype=subtype)
    sidecar = out_path + ".render.json"
    with open(sidecar, "w", encoding="utf-8") as f:
        json.dump({"sample_rate": sample_rate, "score_offset_ms": offset_ms, "phrases": render_phrases, "score": score.to_json(), "tpq": TPQ}, f, ensure_ascii=False)
    stem_files = []
    if stems_dir:
        os.makedirs(stems_dir, exist_ok=True)
        for name, audio in stems.items():
            sp = os.path.join(os.path.abspath(stems_dir), f"{name}.wav")
            sf.write(sp, audio, sample_rate, subtype="PCM_16")
            with open(sp + ".render.json", "w", encoding="utf-8") as f:
                json.dump({"sample_rate": sample_rate, "score_offset_ms": offset_ms, "stem": name,
                           "phrases": [ph for ph in render_phrases if ph["track"] == name], "tpq": TPQ}, f, ensure_ascii=False)
            stem_files.append(sp)
    timings["mix"] = time.time() - t_mix
    stage = {k: round(v, 3) for k, v in timings.items()}
    stage["total"] = round(time.time() - t_start, 3)
    rms = float(np.sqrt(np.mean(mix ** 2))) if mix.size else 0.0
    report = {
        "output": out_path,
        "render_data": sidecar,
        "mix": mix_info,
        **({"stems": stem_files} if stem_files else {}),
        "duration_s": round(len(mix) / sample_rate, 3),
        "sample_rate": sample_rate,
        "channels": channels,
        # score time t ms is at (t + score_offset_ms) in the file; non-zero when a consonant or
        # padding starts before the first note
        "score_offset_ms": offset_ms,
        "phrase_count": len(phrase_reports),
        "phrases": phrase_reports,
        "peak_dbfs": round(20 * np.log10(max(peak, 1e-9)), 2),
        "rms_dbfs": round(20 * np.log10(max(rms, 1e-9)), 2),
        "timing_s": stage,
        "phrases_from_cache": cached_phrases,
        "model_runs": len(onnxrun.STATS["runs"]),
        "cache_hits": onnxrun.STATS["cache_hits"],
        "session_loads": onnxrun.STATS["session_loads"],
        "warnings": warnings,
    }
    if unknown:
        report["unknown_lyrics"] = unknown
    if rms < 1e-4:
        report["warnings"].append("render is silent (rms below -80 dBFS)")
    return report


PHRASE_CACHE = os.environ.get("WARBLE_PHRASE_CACHE", os.path.join(os.path.expanduser("~"), ".cache", "warble", "phrases"))
CACHE_VERSION = 3


def _phrase_key(eng, words, tm, lang, track, steps, depth, seed, prev_end_ms, allow_unknown):
    """everything a phrase's audio depends on. editing one phrase changes only its key."""
    import hashlib

    bank = eng.bank.root
    notes = [n for w in words for n in w]
    payload = {
        "v": CACHE_VERSION, "engine": type(eng).__name__, "bank": bank, "bank_files": _bank_fingerprint(eng),
        "resampler": getattr(eng, "resampler_name", None), "wavtool": getattr(eng, "wavtool_name", None),
        "lang": lang, "voice": track.voice, "phonemizer": track.phonemizer, "steps": steps, "depth": depth, "seed": seed,
        "curves": track.curves,
        "prev_end": round(prev_end_ms, 3) if prev_end_ms is not None else None, "allow_unknown": allow_unknown,
        "notes": [(n.lyric, n.hint, n.tone, round(tm.tick_to_ms(n.position), 3), round(tm.tick_to_ms(n.end), 3),
                   sorted((k, str(v)) for k, v in n.controls.items()), json.dumps(n.extra, sort_keys=True, default=str)) for n in notes],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()[:32]


def _bank_fingerprint(eng):
    """mtimes of the bank files a render depends on (oto.ini, prefix.map, character files, dsconfigs)."""
    fp = getattr(eng, "_fingerprint", None)
    if fp is None:
        root = eng.bank.root
        stamps = []
        for dirpath, _, files in os.walk(root):
            for f in files:
                if f.lower() in ("oto.ini", "prefix.map", "character.txt", "character.yaml", "dsconfig.yaml", "vocoder.yaml") or f.endswith((".onnx", ".emb")) or f.startswith("dsdict"):
                    p = os.path.join(dirpath, f)
                    stamps.append((os.path.relpath(p, root), os.path.getmtime(p)))
        fp = sorted(stamps)
        eng._fingerprint = fp
    return fp


def _phrase_cache_get(key):
    if not key:
        return None
    import pickle

    p = os.path.join(PHRASE_CACHE, key + ".pkl")
    if not os.path.isfile(p):
        return None
    try:
        with open(p, "rb") as f:
            return pickle.load(f)
    except Exception:  # noqa: BLE001 - a broken entry is simply re-rendered
        return None


def _phrase_cache_put(key, res):
    if not key or "samples" not in res:
        return
    import pickle

    os.makedirs(PHRASE_CACHE, exist_ok=True)
    tmp = os.path.join(PHRASE_CACHE, f".{key}.{os.getpid()}")
    with open(tmp, "wb") as f:
        pickle.dump(res, f, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(tmp, os.path.join(PHRASE_CACHE, key + ".pkl"))


def _resample(x, sr_in, sr_out):
    from math import gcd

    from scipy.signal import resample_poly

    g = gcd(sr_in, sr_out)
    return resample_poly(x, sr_out // g, sr_in // g).astype(np.float32)


def _mix(rendered, score, sr, preset=None, lufs=None, no_master=False, normalize_db=None):
    """per-track buffers -> effects -> bus + shared reverb + backing -> loudness -> limiter.
    returns (mix, channels, score_offset_ms, stems {name: audio}, info)."""
    from scipy.signal import fftconvolve

    from . import mix as mx

    tm = score.tempo_map
    master = mx.master_settings(score, preset)
    if lufs is not None:
        master["lufs"] = lufs
    starts = [int(round(s_ms / 1000.0 * sr)) for _, s_ms, _ in rendered]
    first = min(starts)
    offset = -first if first < 0 else 0
    end = max(st + len(x) for st, (_, _, x) in zip(starts, rendered)) + offset
    backings = []
    for b in score.backings:
        audio = mx.load_backing(b["path"], sr) * 10 ** (b.get("gain_db", 0) / 20)
        at_ms = b.get("at_ms") if b.get("at_ms") is not None else tm.tick_to_ms(b.get("at_tick", 0))
        st = int(round(at_ms / 1000 * sr)) + offset
        backings.append((b["path"], st, audio))
        end = max(end, st + len(audio))
    tracks = []
    for tr in score.tracks:
        if any(t is tr for t, _, _ in rendered):
            tracks.append(tr)
    fx_used = any(mx.track_fx(t, master) for t in tracks)
    stereo = bool(backings) or len(tracks) > 1 or any(abs(t.pan) > 1e-6 for t in tracks) or fx_used
    reverb_tail = int(sr * min(6.0, float(master.get("room", 1.6)) * 1.2)) if any(float(mx.track_fx(t, master).get("reverb", 0) or 0) > 0 for t in tracks) else 0
    n = end + reverb_tail
    stems = {}
    bus = np.zeros((n, 2)) if stereo else np.zeros(n)
    send_bus = np.zeros(n)
    for tr in tracks:
        mono = np.zeros(n)
        for (t, s_ms, x) in rendered:
            if t is tr:
                mx.place(mono, x.astype(np.float64), int(round(s_ms / 1000.0 * sr)) + offset)
        if stereo:
            dry, send = mx.process_track(mono, sr, tr, master)
            send_bus += send
        else:
            dry = mono * 10 ** (tr.volume_db / 20)
        bus += dry
        stems[tr.name] = dry
    info = {"preset": master.get("preset"), "stereo": stereo, "tracks": [t.name for t in tracks]}
    if reverb_tail and stereo and np.any(send_bus):
        ir = mx.reverb_ir(sr, float(master.get("room", 1.6)))
        wet = np.stack([fftconvolve(send_bus, ir[:, c])[:n] for c in range(2)], axis=1)
        bus += wet
        stems["reverb"] = wet
        info["reverb_room_s"] = float(master.get("room", 1.6))
    for path, st, audio in backings:
        mx.place(bus, audio if stereo else audio.mean(axis=1), st)
        stems["backing"] = stems.get("backing", np.zeros_like(bus))
        mx.place(stems["backing"], audio if stereo else audio.mean(axis=1), st)
        info.setdefault("backing", []).append(path)
    # trim silent tail beyond the reverb
    peak_env = np.abs(bus).max(axis=1) if bus.ndim == 2 else np.abs(bus)
    nz = np.nonzero(peak_env > 1e-5)[0]
    if len(nz):
        cut = min(len(bus), nz[-1] + int(0.05 * sr))
        bus = bus[:cut]
        stems = {k: v[:cut] for k, v in stems.items()}
    if master.get("chain") and stereo:
        from .plugins import run_chain

        bus = run_chain(bus, sr, master["chain"])
        info["master_chain"] = master["chain"]
    if not no_master:
        if master.get("lufs") is not None:
            bus, before = mx.normalize_lufs(bus, sr, float(master["lufs"]))
            info["lufs_before"] = round(float(before), 2)
            info["lufs_target"] = float(master["lufs"])
        if normalize_db is not None:
            pk = float(np.max(np.abs(bus))) or 1.0
            bus = bus * (10 ** (normalize_db / 20) / pk)
        if master.get("ceiling") is not None or np.max(np.abs(bus)) > 1.0:
            ceiling = float(master.get("ceiling", -0.3))
            bus = mx.limiter(bus, sr, ceiling)
            info["limiter_ceiling_db"] = ceiling
        info["lufs"] = round(float(mx.loudness(bus, sr)), 2)
    return bus.astype(np.float32), (2 if stereo else 1), round(offset / sr * 1000.0, 3), stems, info


def _sidecar_phrase(pidx, track, words, res, tm):
    notes = [n for w in words for n in w]
    ph = res["phonemes"]
    fm = res.get("frame_ms")
    out = {
        "index": pidx,
        "track": track.name,
        "start_ms": res["start_ms"],
        "notes": [
            {
                "index": track.notes.index(n) + 1,
                "lyric": n.lyric,
                "pitch": pitch_name(n.tone),
                "tone": n.tone,
                "start_ms": tm.tick_to_ms(n.position),
                "end_ms": tm.tick_to_ms(n.end),
                "controls": n.controls,
            }
            for n in notes
        ],
        "phones": [{k: v for k, v in p.items() if k != "mix"} for p in ph["phones"]],
        "pitch_source": res.get("pitch_source"),
    }
    if "pitch_midi" in res:
        out["pitch"] = {"start_ms": res.get("pitch_start_ms", res["start_ms"]), "frame_ms": fm, "midi": [round(float(v), 4) for v in res["pitch_midi"]]}
    return out
