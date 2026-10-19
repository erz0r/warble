"""standard midi import and export.

import picks one track (or the busiest), makes it monophonic (highest note wins a chord, a note
is cut where the next one starts), reads tempo, time signature and key, and attaches lyric meta
events to the notes they land on. `lyrics` text can be assigned afterwards (see warble.lyrics).
"""

import os

from ..errors import WarbleError
from ..score import TPQ, Note, Score, Track

KEYS = {}


def _decode_meta_text(s):
    """mido decodes meta text as latin-1; undo that and try utf-8 then shift-jis."""
    try:
        raw = s.encode("latin-1")
    except UnicodeEncodeError:
        return s
    for enc in ("utf-8", "cp932"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass
    return s


def load(path, track=None, quantize=None, lyrics=None, lang=None, **_):
    import mido

    try:
        mf = mido.MidiFile(path)
    except Exception as e:  # noqa: BLE001
        raise WarbleError("midi_unreadable", f"cannot read midi {path}: {e}")
    scale = TPQ / mf.ticks_per_beat
    score = Score(base_dir=os.path.dirname(os.path.abspath(path)))
    tempos, sigs = {}, {}
    per_track = []
    for ti, tr in enumerate(mf.tracks):
        t = 0
        on = {}
        notes = []
        lyr, texts = [], []
        name = tr.name or f"track{ti}"
        for msg in tr:
            t += msg.time
            tick = int(round(t * scale))
            if msg.type == "set_tempo":
                tempos[tick] = round(mido.tempo2bpm(msg.tempo), 4)
            elif msg.type == "time_signature":
                sigs[tick] = (msg.numerator, msg.denominator)
            elif msg.type == "key_signature":
                score.key = msg.key
            elif msg.type == "lyrics":
                lyr.append((tick, _decode_meta_text(msg.text).strip()))
            elif msg.type == "text" and not msg.text.startswith(("@", "%")):
                # some files carry lyrics as plain text events; only used when there are no lyric events
                texts.append((tick, _decode_meta_text(msg.text).strip()))
            elif msg.type == "note_on" and msg.velocity > 0:
                on.setdefault(msg.note, []).append((tick, msg.velocity))
            elif msg.type in ("note_off", "note_on"):
                if on.get(msg.note):
                    st, vel = on[msg.note].pop(0)
                    if tick > st:
                        notes.append((st, tick, msg.note, vel))
        use = lyr if lyr else (texts if notes else [])
        per_track.append({"index": ti, "name": name, "notes": sorted(notes), "lyrics": [l for l in use if l[1]]})
    candidates = [p for p in per_track if p["notes"]]
    if not candidates:
        raise WarbleError("midi_no_notes", f"{path} has no notes")
    if track is not None:
        sel = [p for p in candidates if str(p["index"]) == str(track) or p["name"] == track]
        if not sel:
            raise WarbleError("midi_track_missing", f"no track '{track}' with notes", hint=f"tracks: {[(p['index'], p['name'], len(p['notes'])) for p in candidates]}")
        src = sel[0]
    else:
        src = max(candidates, key=lambda p: len(p["notes"]))
    q = int(quantize) if quantize else None

    def qz(x):
        return int(round(x / q) * q) if q else x

    # monophonic: at equal starts keep the highest pitch; cut overlaps at the next start
    by_start = {}
    for st, en, pitch, vel in src["notes"]:
        st, en = qz(st), qz(en)
        if en <= st:
            en = st + (q or 1)
        if st not in by_start or pitch > by_start[st][1]:
            by_start[st] = (en, pitch, vel)
    starts = sorted(by_start)
    tr = Track(name=src["name"] or "midi", lang=lang)
    for i, st in enumerate(starts):
        en, pitch, vel = by_start[st]
        if i + 1 < len(starts):
            en = min(en, starts[i + 1])
        tr.notes.append(Note(lyric="a", tone=float(pitch), position=st, duration=en - st))
    lyrs = src["lyrics"] or [l for p in per_track for l in p["lyrics"]]
    placed = 0
    for tick, text in lyrs:
        tick = qz(tick)
        hit = next((n for n in tr.notes if n.position <= tick < n.end), None)
        if hit is not None:
            hit.lyric = text
            placed += 1
    score.tempos = sorted(tempos.items()) or [(0, 120.0)]
    score.time_signatures = sorted((t, a, b) for t, (a, b) in sigs.items()) or [(0, 4, 4)]
    score.tracks.append(tr)
    score.import_report = {
        "source": path,
        "track": {"index": src["index"], "name": src["name"]},
        "tracks_with_notes": [(p["index"], p["name"], len(p["notes"])) for p in candidates],
        "notes": len(tr.notes),
        "lyric_events": len(lyrs),
        "lyrics_placed": placed,
    }
    if not lyrs and not lyrics:
        score.import_report["warning"] = "no lyric events; every note sings 'a' until lyrics are assigned (--lyrics or the lyrics command)"
    if lyrics:
        from ..lyrics import assign, split

        units, readings = split(lyrics, lang or "ja")
        score.import_report["lyrics"] = assign(tr.notes, units)
        if readings:
            score.import_report["lyrics"]["kanji_readings"] = readings
    return score


def save(score, path, track_names=None):
    import mido

    mf = mido.MidiFile(ticks_per_beat=TPQ)
    meta = mido.MidiTrack()
    events = [(t, mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(b), time=0)) for t, b in score.tempos]
    events += [(t, mido.MetaMessage("time_signature", numerator=n, denominator=d, time=0)) for t, n, d in score.time_signatures]
    _write(meta, events)
    mf.tracks.append(meta)
    for ch, tr in enumerate(score.tracks):
        mt = mido.MidiTrack()
        mt.append(mido.MetaMessage("track_name", name=tr.name, time=0))
        ev = []
        for n in tr.notes:
            ev.append((n.position, mido.MetaMessage("lyrics", text=n.lyric, time=0)))
            ev.append((n.position, mido.Message("note_on", note=int(round(n.tone)), velocity=100, channel=ch % 16, time=0)))
            ev.append((n.end, mido.Message("note_off", note=int(round(n.tone)), velocity=0, channel=ch % 16, time=0)))
        # note_off before note_on at the same tick
        ev.sort(key=lambda e: (e[0], 0 if e[1].type == "note_off" else 1))
        _write(mt, ev)
        mf.tracks.append(mt)
    mf.save(path)
    return path


def _write(track, events):
    last = 0
    for tick, msg in sorted(events, key=lambda e: e[0]):
        msg.time = tick - last
        track.append(msg)
        last = tick
