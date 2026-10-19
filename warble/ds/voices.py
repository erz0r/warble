"""voice modes: character.yaml subbanks (color + suffix + tone ranges) mapped to dsconfig speakers.

a voice spec is a name ('soft'), a mix ('soft:0.7,power:0.3'), or None for the default. names match
a subbank color, a subbank suffix, or a speaker's file name, in that order.
"""

from ..bank.common import camel_to_snake
from ..bank.utau import name_to_tone
from ..errors import WarbleError


def _subbanks(bank):
    subs = []
    for sb in bank.subbanks():
        if isinstance(sb, dict):
            sb = {camel_to_snake(k): v for k, v in sb.items()}
            subs.append({"color": sb.get("color") or "", "suffix": sb.get("suffix") or "", "tone_ranges": sb.get("tone_ranges") or []})
    if not subs:
        for s in bank.config.get("speakers") or []:
            subs.append({"color": s.replace("\\", "/").split("/")[-1], "suffix": s, "tone_ranges": []})
    return subs


def _in_ranges(tone, ranges):
    if not ranges:
        return True
    for r in ranges:
        parts = str(r).split("-")
        lo = name_to_tone(parts[0])
        hi = name_to_tone(parts[-1]) if len(parts) > 1 else lo
        if lo is not None and hi is not None and lo <= tone <= hi:
            return True
    return False


def names(bank):
    return [s["color"] or s["suffix"] for s in _subbanks(bank)]


def _pick(subs, name, tone):
    """GetSpeakerAtIndex: color and tone range, then color alone, then first subbank."""
    for key in ("color", "suffix"):
        cands = [s for s in subs if s[key] == name]
        for s in cands:
            if _in_ranges(tone, s["tone_ranges"]):
                return s
        if cands:
            return cands[0]
    for s in subs:
        if s["suffix"].replace("\\", "/").split("/")[-1] == name:
            return s
    return None


def resolve(bank, spec, tone):
    """-> {speaker_suffix: weight}; empty dict for single-speaker banks."""
    if not bank.config.get("speakers"):
        if spec and spec not in ("default",):
            raise WarbleError("voice_unknown", f"voice '{spec}' requested but {bank.name} has a single speaker", hint="drop the voice directive")
        return {}
    subs = _subbanks(bank)
    if not spec or spec == "default":
        for s in subs:
            if s["color"] == "" and _in_ranges(tone, s["tone_ranges"]):
                return {s["suffix"]: 1.0}
        for s in subs:
            if _in_ranges(tone, s["tone_ranges"]):
                return {s["suffix"]: 1.0}
        return {subs[0]["suffix"]: 1.0}
    mix = {}
    for part in str(spec).split(","):
        part = part.strip()
        if not part:
            continue
        name, _, w = part.partition(":")
        s = _pick(subs, name.strip(), tone)
        if s is None:
            raise WarbleError("voice_unknown", f"voice '{name}' not found in {bank.name}", hint=f"available voices: {names(bank)}")
        mix[s["suffix"]] = mix.get(s["suffix"], 0.0) + (float(w) if w else 1.0)
    total = sum(mix.values())
    return {k: v / total for k, v in mix.items()} if total > 0 else mix


def dominant(mix):
    return max(mix, key=mix.get) if mix else ""
