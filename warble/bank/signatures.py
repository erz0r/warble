"""what each diffsinger model is expected to take, from dsconfig flags.

the pipeline never trusts these alone: it compares them to the onnx session's real inputs and
feeds the union it can build. probe uses the same comparison to flag disagreements early.
mirrors the inputs assembled in openutau's DiffSingerBasePhonemizer, DiffSingerPitch,
DiffSingerVariance and DiffSingerRenderer.
"""

SAMPLING = {"steps", "speedup", "depth"}


def sampling_inputs(cfg):
    names = {"steps"} if cfg["use_continuous_acceleration"] else {"speedup"}
    if cfg.use_variable_depth:
        names.add("depth")
    return names


def expected_inputs(role, cfg, root_cfg=None, dur_inputs=None):
    """role: linguistic_dur, linguistic_pitch, linguistic_variance, dur, pitch, variance, acoustic, vocoder.
    root_cfg is the bank's root dsconfig (speakers are declared per sub-config)."""
    speakers = bool(cfg.get("speakers"))
    if role.startswith("linguistic"):
        names = {"tokens"}
        word_mode = role == "linguistic_dur" or cfg["predict_dur"]
        names |= {"word_div", "word_dur"} if word_mode else {"ph_dur"}
        if cfg["use_lang_id"]:
            names.add("languages")
        return names
    if role == "dur":
        names = {"encoder_out", "x_masks", "ph_midi"}
        if cfg.get("dur_type") == "rel" or (dur_inputs and "word_div" in dur_inputs):
            names |= {"word_div", "word_dur"}
        if speakers:
            names.add("spk_embed")
        return names
    if role == "pitch":
        names = {"encoder_out", "note_midi", "note_dur", "ph_dur", "pitch", "retake"} | sampling_inputs(cfg)
        if cfg["use_expr"]:
            names.add("expr")
        if cfg["use_note_rest"]:
            names.add("note_rest")
        if speakers:
            names.add("spk_embed")
        return names
    if role == "variance":
        names = {"encoder_out", "ph_dur", "pitch", "retake"} | sampling_inputs(cfg)
        for v in ("energy", "breathiness", "voicing", "tension"):
            if cfg[f"predict_{v}"]:
                names.add(v)
        if speakers:
            names.add("spk_embed")
        return names
    if role == "acoustic":
        names = {"tokens", "durations", "f0"} | sampling_inputs(cfg)
        if cfg["use_lang_id"]:
            names.add("languages")
        if speakers:
            names.add("spk_embed")
        if cfg["use_key_shift_embed"]:
            names.add("gender")
        if cfg["use_speed_embed"]:
            names.add("velocity")
        for v in ("energy", "breathiness", "voicing", "tension"):
            if cfg[f"use_{v}_embed"]:
                names.add(v)
        return names
    if role == "vocoder":
        return {"mel", "f0"}
    raise ValueError(role)


def compare(expected, actual):
    """missing: the graph wants it but the flags don't produce it. extra: flags say feed it but
    the graph has no such input. sampling inputs are a soft mismatch because the runtime picks
    steps/speedup/depth from the graph."""
    actual = set(actual)
    missing = sorted(actual - expected)
    extra = sorted(expected - actual)
    soft = [n for n in missing + extra if n in SAMPLING]
    return {
        "graph_needs_but_flags_omit": [n for n in missing if n not in SAMPLING],
        "flags_feed_but_graph_lacks": [n for n in extra if n not in SAMPLING],
        "sampling_differences": soft,
    }
