"""midi fixtures: a melody with a tempo change, a time signature, a chord to monophonize, and
optionally lyric meta events."""

import os


def build(path, with_lyrics=False, tpb=96):
    import mido

    mf = mido.MidiFile(ticks_per_beat=tpb)
    meta = mido.MidiTrack()
    meta.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(100), time=0))
    meta.append(mido.MetaMessage("time_signature", numerator=3, denominator=4, time=0))
    meta.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(140), time=tpb * 6))
    mf.tracks.append(meta)
    mel = mido.MidiTrack()
    mel.append(mido.MetaMessage("track_name", name="melody", time=0))
    # (pitch, beats) with a rest after the 4th note
    tune = [(60, 1), (62, 1), (64, 1), (65, 1), (None, 1), (67, 1), (69, 0.5), (71, 0.5), (72, 2)]
    lyr = ["ちゃ", "つ", "み", "な", None, "つ", "も", "ち", "か"]
    pending = 0
    for (p, beats), ly in zip(tune, lyr):
        ticks = int(beats * tpb)
        if p is None:
            pending += ticks
            continue
        if with_lyrics:
            mel.append(mido.MetaMessage("lyrics", text=ly.encode("utf-8").decode("latin-1"), time=pending))
            pending = 0
        mel.append(mido.Message("note_on", note=p, velocity=90, time=pending))
        if p == 64:
            mel.append(mido.Message("note_on", note=p - 12, velocity=60, time=0))  # a chord to drop
        mel.append(mido.Message("note_off", note=p, velocity=0, time=ticks))
        if p == 64:
            mel.append(mido.Message("note_off", note=p - 12, velocity=0, time=0))
        pending = 0
    mf.tracks.append(mel)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    mf.save(path)
    return path


if __name__ == "__main__":
    import sys

    base = sys.argv[1] if len(sys.argv) > 1 else "tests/fixtures"
    print(build(os.path.join(base, "melody.mid")), build(os.path.join(base, "melody_lyrics.mid"), with_lyrics=True))
