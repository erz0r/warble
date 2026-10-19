"""per-note pitch controls on top of an engine's base curve. the model lives in warble.tuning.curve."""

from .tuning.curve import VIBRATO_STYLES, compose  # noqa: F401 - VIBRATO_STYLES re-exported for docs


def apply_note_controls(midi, frame_t, notes, spans=None, tm=None, track=None):
    return compose(frame_t, notes, tm, midi, track)
