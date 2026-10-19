"""`tune show`: the tuning state as a compact table an agent can read without an image."""

from ..score import TPQ, fmt_beats, phrases, pitch_name
from . import curve, ops

SHOW_SKIP = {"pts", "snap", "vbr", "vib", "raw", "drift", "cents"}


def describe_note(score, tr, i):
    n = tr.notes[i]
    tm = score.tempo_map
    s = tm.tick_to_ms(n.position)
    L = tm.tick_to_ms(n.end) - s
    row = {"note": i + 1, "lyric": n.lyric, "pitch": pitch_name(n.tone), "start_ms": round(s, 1), "len_ms": round(L, 1),
           "len_beats": fmt_beats(n.duration)}
    prev = ops._prev_adjacent(tr.notes, i)
    if prev is not None:
        row["from_prev"] = f"{(n.tone - prev.tone) * 100:+.0f}c"
    pts = curve.note_points(n)
    if pts:
        row["points"] = curve.format_points(pts) + ("" if str(n.controls.get("snap", "1")) != "0" else " (no snap)")
        head = [p for p in pts if p[0] < L / 2]
        if prev is not None and len(head) >= 2:
            row["transition"] = f"{head[-1][0] - head[0][0]:.0f}ms from {head[0][0]:+.0f}ms {head[0][2]}"
    elif "raw" in n.controls or (n.extra or {}).get("pitchbend"):
        r = curve.note_raw(n)
        row["points"] = f"raw layer: {len(r['cents'])} values from {r['start_ms']:+.0f}ms, range {min(r['cents']):+.0f}..{max(r['cents']):+.0f}c"
    else:
        row["points"] = "engine curve"
    v = curve.note_vibrato(n)
    if v:
        row["vibrato"] = f"{1000 / v['period']:.1f}Hz ±{v['depth']:.0f}c from {100 - v['length']:.0f}% in{v['in']:.0f}/out{v['out']:.0f}"
    if n.controls.get("drift"):
        row["drift"] = n.controls["drift"]
    if n.controls.get("cents"):
        row["offset"] = f"{float(n.controls['cents']):+.0f}c"
    ex = {k: v for k, v in n.controls.items() if k not in SHOW_SKIP}
    if ex:
        row["expressions"] = ex
    return row


def show(score, track=None, notes=None):
    tr, idx = ops.select(score, track=track, notes=notes)
    ph_of = {}
    for k, ph in enumerate(phrases(tr.notes), start=1):
        for w in ph:
            for n in w:
                ph_of[id(n)] = k
    rows = []
    for i in idx:
        r = describe_note(score, tr, i)
        r["phrase"] = ph_of.get(id(tr.notes[i]))
        rows.append(r)
    lines = []
    for r in rows:
        bits = [f"{r['note']:>3} p{r['phrase']:<2} {r['lyric']:<4} {r['pitch']:<6} {r['len_beats']:>6}b {r['len_ms']:>6.0f}ms"]
        if r.get("from_prev"):
            bits.append(f"from {r['from_prev']}")
        bits.append(r["points"])
        for k in ("vibrato", "drift", "offset"):
            if r.get(k):
                bits.append(f"{k} {r[k]}")
        if r.get("expressions"):
            bits.append(" ".join(f"{k}={v}" for k, v in r["expressions"].items()))
        lines.append(" | ".join(bits))
    return {"track": tr.name, "bank": tr.bank, "notes": rows, "table": "\n".join(lines), "tpq": TPQ}
