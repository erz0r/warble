"""built-in tuning presets: op batches applied to whatever selection is given."""

BUILTIN = {
    "gentle": [
        {"op": "transition", "dur_ms": 90, "start_ms": -50},
        {"op": "vibrato", "preset": "subtle", "min_beats": 1.5},
        {"op": "drift", "depth_cents": 5, "rate_hz": 0.6, "min_beats": 1},
    ],
    "pop": [
        {"op": "transition", "dur_ms": 70, "start_ms": -40, "overshoot_cents": 15, "settle_ms": 60, "interval": "abs>=3"},
        {"op": "transition", "dur_ms": 60, "start_ms": -35, "interval": "abs<3"},
        {"op": "vibrato", "preset": "pop", "min_beats": 1.5},
        {"op": "drift", "depth_cents": 6, "rate_hz": 0.7, "min_beats": 1},
    ],
    "ballad": [
        {"op": "transition", "dur_ms": 130, "start_ms": -80, "prep_cents": 20, "interval": "abs>=4"},
        {"op": "transition", "dur_ms": 100, "start_ms": -60, "interval": "abs<4"},
        {"op": "vibrato", "preset": "ballad", "min_beats": 1},
        {"op": "drift", "depth_cents": 8, "rate_hz": 0.5, "min_beats": 1},
    ],
    "robot": [
        {"op": "flat"},
    ],
}
