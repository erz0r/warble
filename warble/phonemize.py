"""`phonemize`: what each note will sing, with timings, without rendering audio."""

from .score import pitch_name
from .sing import _note_attr, engine_for, split_phrases


def phonemize(score, engine=None, seed=None, vocoder_dirs=None):
    tm = score.tempo_map
    out = {"tracks": [], "unknown": []}
    for track in score.tracks:
        tr = {"track": track.name, "phrases": []}
        prev_end = None
        for pi, words in enumerate(split_phrases(track), start=1):
            first = words[0][0]
            bank = _note_attr(first, track, "bank")
            lang = _note_attr(first, track, "lang")
            eng = engine_for(bank, engine or track.engine, vocoder_dirs)

            def voice_of(n, track=track):
                return n.controls.get("voice") or track.voice

            res = eng.phonemize_phrase(words, tm, lang, voice_of, seed=seed, prev_end_ms=prev_end,
                                       phonemizer=_note_attr(first, track, "phonemizer"))
            prev_end = tm.tick_to_ms(words[-1][-1].end)
            if hasattr(eng, "voice"):
                from .utau.render import _jsonable

                res = _jsonable(res)
            fm = res.get("frame_ms")
            notes = []
            for wi, w in enumerate(words):
                head = w[0]
                phs = [p for p in res["phones"] if p.get("word") == wi]
                entry = {
                    "note": track.notes.index(head) + 1,
                    "lyric": head.lyric,
                    "pitch": pitch_name(head.tone),
                    "start_ms": round(tm.tick_to_ms(head.position), 2),
                    "end_ms": round(tm.tick_to_ms(w[-1].end), 2),
                    "phonemes": [
                        {
                            "phoneme": p["phoneme"],
                            "start_ms": round(p["position_ms"], 2),
                            "duration_ms": round(p["duration_ms"], 2),
                            **({"start_frame": round(p["position_ms"] / fm, 2), "frames": round(p["duration_ms"] / fm, 2)} if fm else {}),
                            **({k: p[k] for k in ("oto", "preutter", "overlap", "envelope") if k in p}),
                        }
                        for p in phs
                    ],
                }
                info = res.get("words", [{}])[wi] if wi < len(res.get("words", [])) else {}
                if info.get("source"):
                    entry["lookup"] = info["source"]
                notes.append(entry)
            entry = {"phrase": pi, "durations": res.get("durations"), "notes": notes}
            if res.get("phonemizer"):
                entry["phonemizer"] = res["phonemizer"]
                entry["phonemizer_choice"] = res.get("phonemizer_choice")
            if res.get("warnings"):
                entry["warnings"] = res["warnings"]
            tr["phrases"].append(entry)
            for u in res.get("unknown", []):
                u["track"] = track.name
                out["unknown"].append(u)
        out["tracks"].append(tr)
    return out
