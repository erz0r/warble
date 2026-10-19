"""run a phonemizer over note groups exactly as openutau's PhonemizerRunner does."""

from .api import Note, Phoneme


def run(pz, groups):
    """groups: list of lists of api.Note (absolute tick positions). returns per-group phoneme lists
    with absolute positions. groups go in reverse; each group's end is pushed back to where the next
    group's first phoneme starts; errors become an 'error' phoneme like openutau."""
    pz.set_up(groups)
    out = []
    for i in range(len(groups) - 1, -1, -1):
        g = groups[i]
        prevs = prev = nxt = None
        prev_nb = next_nb = False
        if i > 0:
            prevs = groups[i - 1]
            prev = groups[i - 1][0]
            pl = groups[i - 1][-1]
            prev_nb = pl.position + pl.duration >= g[0].position
        if i < len(groups) - 1:
            nxt = groups[i + 1][0]
            tl = g[-1]
            next_nb = tl.position + tl.duration >= nxt.position
        if nxt is not None and out and out[0]:
            end = g[-1].position + g[-1].duration
            push = min(0, out[0][0].position - end)
            g[-1].duration += push
        try:
            res = pz.process(g, prev, nxt, prev if prev_nb else None, nxt if next_nb else None, (prevs if prev_nb else None) or [])
        except Exception as e:  # noqa: BLE001 - openutau turns a phonemizer exception into an error phoneme
            res = [Phoneme("error", error=f"{type(e).__name__}: {e}")]
        res = [Phoneme(p.phoneme, p.position, p.index, p.error, p.expressions) for p in res]
        if pz.legacy_mapping:
            for p in res:
                o = pz.singer.try_get_mapped_oto(p.phoneme, g[0].tone)
                if o is not None:
                    p.phoneme = o.alias
        for p in res:
            p.position += g[0].position
        out.insert(0, res)
    pz.clean_up()
    return out


def notes_from_case(case, tone_of):
    """harness case json -> groups of api.Note, laid out exactly like the c# harness."""
    from .api import PhonemeAttributes

    groups, group = [], []
    position = 480
    for nn in case["notes"]:
        lyric = nn["lyric"]
        duration = nn.get("duration", 480)
        tone = nn["tone"] if isinstance(nn["tone"], int) else tone_of(nn["tone"])
        if nn.get("position") is not None:
            position = nn["position"]
        if not lyric.startswith("+") and group:
            groups.append(group)
            group = []
        attrs = []
        for a in nn.get("attrs") or [{"index": 0}]:
            alt = a.get("alt", 0)
            attrs.append(PhonemeAttributes(index=a.get("index", 0), consonant_stretch_ratio=1.0, tone_shift=a.get("shift", 0) if "attrs" in nn else None,
                                           alternate=None if not alt else alt, voice_color=a.get("color", "")))
        group.append(Note(lyric=lyric, tone=tone, position=position, duration=duration, phonetic_hint=nn.get("hint"), phoneme_attributes=attrs))
        position += duration + nn.get("gap_after", 0)
    if group:
        groups.append(group)
    return groups
