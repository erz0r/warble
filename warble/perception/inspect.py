"""`inspect`, `analyze`, `compare`, `pitch extract`: images plus a json report that describe a
render the way a listener would, so an agent without ears can judge it."""

import json
import os

import numpy as np

from ..errors import WarbleError
from . import artifacts as art
from . import f0 as f0mod
from . import intelligibility, metrics, plots
from .analysis import analyze_audio, frames_in
from .intent import from_score, from_sidecar


def _out_dir(wav, out_dir):
    d = out_dir or os.path.splitext(wav)[0] + "_inspect"
    os.makedirs(d, exist_ok=True)
    return d


def _load_intent(wav, score):
    if score and score.endswith(".render.json"):
        return from_sidecar(wav, score)
    it = from_sidecar(wav)
    if it is None and score:
        it = from_score(score)
    return it


def inspect(wav, score=None, notes=None, ref=None, out_dir=None, images=True, extractors=("harvest", "dio"), asr=True):
    if not os.path.isfile(wav):
        raise WarbleError("wav_missing", f"no such file: {wav}")
    a = analyze_audio(wav, extractors)
    intent = _load_intent(wav, score)
    out_dir = _out_dir(wav, out_dir)
    report = {
        "wav": os.path.abspath(wav),
        "out_dir": out_dir,
        "summary": sanity(a),
        "intent_source": intent.source if intent else None,
        "extractors": list(extractors),
        "extractor_disagreements": a.extractor_disagreements[:40],
    }
    note_filter = set(notes) if notes else None
    note_reports = []
    if intent and intent.notes:
        prev = None
        for n in intent.notes:
            if note_filter is None or n["index"] in note_filter:
                note_reports.append(metrics.note_metrics(a, intent, n, prev))
            prev = n
        report["notes"] = note_reports
        report["overall"] = overall(note_reports)
    arts = art.detect_all(a, intent)
    if note_filter and intent:
        ns = [n for n in intent.notes if n["index"] in note_filter]
        if ns:
            s, e = ns[0]["start_ms"] - 100, ns[-1]["end_ms"] + 100
            arts = [x for x in arts if s <= x["t_ms"] <= e or x["kind"] in ("silent", "dc_offset", "hf_energy")]
    _attach_notes(arts, intent)
    report["artifacts"] = arts
    report["artifact_counts"] = _counts(arts)
    report["top_band_db"] = getattr(a, "top_band_db", None)
    if asr and intent and intent.notes:
        report["intelligibility"] = intelligibility.check(a, intent, note_filter)
    if ref:
        from .compare import global_diff

        b = analyze_audio(ref, extractors)
        report["reference"] = {"wav": os.path.abspath(ref), **global_diff(a, b)}
    report["listening_notes"] = listening_notes(report, intent)
    if images:
        report["images"] = make_images(a, intent, note_reports, arts, out_dir, note_filter, ref)
    with open(os.path.join(out_dir, "report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1, default=float)
    return report


def sanity(a):
    x = a.raw
    peak = float(np.max(np.abs(x))) if x.size else 0.0
    rms = float(np.sqrt(np.mean(x ** 2))) if x.size else 0.0
    loud = a.rms_db > -40
    return {
        "duration_s": round(a.duration_ms / 1000, 3),
        "sample_rate": a.sr,
        "channels": a.channels,
        "peak_dbfs": round(20 * np.log10(peak + 1e-12), 2),
        "rms_dbfs": round(20 * np.log10(rms + 1e-12), 2),
        "lufs": round(a.lufs, 2),
        "voiced_pct_of_loud_frames": round(float(np.mean(a.voiced[loud]) * 100), 1) if loud.any() else 0.0,
        "silent": rms < 10 ** (-70 / 20),
    }


def overall(nrs):
    errs = [n["median_cents_error"] for n in nrs if n.get("median_cents_error") is not None]
    within = [n["within_20c_pct"] for n in nrs if n.get("within_20c_pct") is not None]
    vib = [n["vibrato"]["rate_hz"] for n in nrs if n.get("vibrato")]
    return {
        "notes": len(nrs),
        "median_abs_cents_error": round(float(np.median(np.abs(errs))), 1) if errs else None,
        "worst_note_cents_error": max(errs, key=abs) if errs else None,
        "mean_within_20c_pct": round(float(np.mean(within)), 1) if within else None,
        "notes_with_vibrato": len(vib),
        "median_vibrato_rate_hz": round(float(np.median(vib)), 2) if vib else None,
    }


def _counts(arts):
    c = {}
    for x in arts:
        c[x["kind"]] = c.get(x["kind"], 0) + 1
    return c


def _attach_notes(arts, intent):
    if not intent:
        return
    for x in arts:
        n = intent.note_at(x["t_ms"])
        if n is not None:
            x.setdefault("note", n["index"])
            x["lyric"] = n["lyric"]


def listening_notes(report, intent):
    """a short plain-text gist, generated from the numbers."""
    lines = []
    s = report["summary"]
    if s["silent"]:
        return "the render is silent."
    lines.append(f"{s['duration_s']} s, {s['lufs']} LUFS, peak {s['peak_dbfs']} dBFS.")
    nrs = report.get("notes", [])
    ov = report.get("overall") or {}
    if ov.get("median_abs_cents_error") is not None:
        lines.append(f"pitch: notes sit a median {ov['median_abs_cents_error']} cents from intent; {ov['mean_within_20c_pct']}% of sung frames within 20 cents.")
    phrase_of = {n["index"]: n.get("phrase") for n in (intent.notes if intent else [])}
    for n in nrs:
        e = n.get("median_cents_error")
        where = f"phrase {phrase_of.get(n['note'])}: " if phrase_of.get(n["note"]) else ""
        label = f"note {n['note']} ({n['lyric']}, {n['pitch']})"
        if e is not None and abs(e) >= 25:
            tr = n.get("transition") or {}
            slow = tr.get("settle_ms_after_boundary")
            extra = f" after a slow transition ({slow:.0f} ms to settle)" if slow and slow > 120 else ""
            lines.append(f"{where}{label} lands {abs(e):.0f} cents {'flat' if e < 0 else 'sharp'}{extra}.")
        if n.get("voiced_ratio") is not None and n["voiced_ratio"] < 0.7 and n.get("expected_voiced_ms", 0) > 80:
            lines.append(f"{where}{label} is only {n['voiced_ratio'] * 100:.0f}% voiced where a vowel should be.")
        tr = n.get("transition") or {}
        if tr.get("overshoot_cents") and tr["overshoot_cents"] > 60:
            io = tr.get("intended_overshoot_cents")
            chosen = " (the intended curve does this too)" if io is not None and abs(io - tr["overshoot_cents"]) < 30 else ""
            lines.append(f"{where}{label} overshoots by {tr['overshoot_cents']:.0f} cents on the way in{chosen}.")
    rates = [n["vibrato"]["rate_hz"] for n in nrs if n.get("vibrato")]
    if rates:
        med = np.median(rates)
        for n in nrs:
            v = n.get("vibrato")
            if v and abs(v["rate_hz"] - med) > 1.2 and len(rates) > 2:
                lines.append(f"vibrato on note {n['note']} is {v['rate_hz']} Hz, {'faster' if v['rate_hz'] > med else 'slower'} than the rest ({med:.1f} Hz).")
        if len(rates) <= 2 or all(abs(r - med) <= 1.2 for r in rates):
            lines.append(f"vibrato on {len(rates)} note(s), around {med:.1f} Hz.")
    for x in report.get("artifacts", []):
        if x["severity"] == "info":
            continue
        where = f" in note {x['note']} ({x.get('lyric')})" if x.get("note") else ""
        lines.append(f"{x['kind'].replace('_', ' ')} at {x['t_ms'] / 1000:.2f} s{where}: {x['message']}.")
        if len(lines) > 40:
            lines.append("(more artifacts in the json)")
            break
    flat = [x for x in report.get("artifacts", []) if x["kind"] == "robotic_flatness"]
    if flat:
        lines.append(f"{len(flat)} long note(s) hold dead-flat pitch; consider drift or vibrato.")
    if not [x for x in report.get("artifacts", []) if x["severity"] != "info"]:
        lines.append("no artifacts detected.")
    ii = report.get("intelligibility")
    if ii and ii.get("available"):
        lines.append(f"intelligibility: {ii.get('syllable_accuracy_pct')}% of syllables recognized" + (f"; misheard: {ii['misheard'][:6]}" if ii.get("misheard") else "") + ".")
    elif ii:
        lines.append(f"intelligibility check unavailable: {ii.get('reason')}.")
    return "\n".join(lines)


def make_images(a, intent, nrs, arts, out_dir, note_filter=None, ref=None):
    imgs = []
    for k, (s, e, label) in enumerate(plots.crops(a, intent, note_filter), start=1):
        tag = f"{k:02d}_{label}"
        imgs.append(plots.pianoroll(a, intent, s, e, os.path.join(out_dir, f"pianoroll_{tag}.png"), arts))
        imgs.append(plots.spectrogram(a, intent, s, e, os.path.join(out_dir, f"spec_linear_{tag}.png"), "linear", arts))
        imgs.append(plots.spectrogram(a, intent, s, e, os.path.join(out_dir, f"spec_mel_{tag}.png"), "mel", arts))
        if intent and intent.pitch_t_ms is not None:
            imgs.append(plots.cents_strip(a, intent, s, e, os.path.join(out_dir, f"cents_error_{tag}.png")))
        # formant tracks on voiced frames in the crop
        from . import features as fx

        m = frames_in(a, s, e) & a.voiced
        ts = a.t_ms[m][::4] / 1000.0
        ft = (ts * 1000, fx.formants(a.x, a.sr, ts)) if len(ts) else None
        imgs.append(plots.lanes(a, intent, s, e, os.path.join(out_dir, f"lanes_{tag}.png"), ft))
    by_index = {n["index"]: n for n in (intent.notes if intent else [])}
    for nr in nrs:
        if nr.get("vibrato") or nr.get("intended_vibrato"):
            imgs.append(plots.vibrato(a, intent, by_index[nr["note"]], nr, os.path.join(out_dir, f"vibrato_note{nr['note']:03d}.png")))
    if intent and intent.joins:
        p = plots.joins(a, intent, os.path.join(out_dir, "joins.png"))
        if p:
            imgs.append(p)
    if ref:
        b = analyze_audio(ref)
        imgs.append(plots.ab(a, b, os.path.join(out_dir, "ref")))
        imgs.append(plots.ab_pitch(a, b, intent, os.path.join(out_dir, "ref_pitch.png")))
    return [i for i in imgs if i]


def analyze(wav, score=None, out_dir=None, images=True):
    """inspect for any audio, including a real singer: segments notes from the pitch itself when
    there is no score, then reports the same metrics."""
    a = analyze_audio(wav)
    intent = _load_intent(wav, score) if score else None
    if intent is None:
        intent = segment_notes(a)
    out_dir = _out_dir(wav, out_dir)
    rep = inspect(wav, score=None, out_dir=out_dir, images=False, asr=False) if from_sidecar(wav) else None
    if rep is None:
        note_reports = []
        prev = None
        for n in intent.notes:
            note_reports.append(metrics.note_metrics(a, intent, n, prev))
            prev = n
        arts = [x for x in art.detect_all(a, None)]
        rep = {"wav": os.path.abspath(wav), "out_dir": out_dir, "summary": sanity(a), "intent_source": "segmented from pitch",
               "notes": note_reports, "overall": overall(note_reports), "artifacts": arts, "artifact_counts": _counts(arts),
               "extractor_disagreements": a.extractor_disagreements[:40]}
        rep["listening_notes"] = listening_notes(rep, intent)
        if images:
            rep["images"] = make_images(a, intent, note_reports, arts, out_dir)
        with open(os.path.join(out_dir, "report.json"), "w", encoding="utf-8") as f:
            json.dump(rep, f, ensure_ascii=False, indent=1, default=float)
    return rep


def segment_notes(a, tol_cents=70, min_ms=80):
    """split voiced pitch into note-like segments: a new note starts when pitch stays more than
    tol_cents away from the current note's running median for 30 ms."""
    from .intent import Intent

    notes, cur, pending = [], [], []

    def close(seg):
        if len(seg) * 5 >= min_ms:
            notes.append(seg)

    for i in range(len(a.t_ms)):
        if not a.voiced[i]:
            close(cur + pending)
            cur, pending = [], []
            continue
        if not cur:
            cur.append(i)
            continue
        med = np.median(a.midi[cur[-20:]])
        if abs(a.midi[i] - med) * 100 > tol_cents:
            pending.append(i)
            if len(pending) >= 6:
                close(cur)
                cur, pending = pending, []
        else:
            cur += pending + [i]
            pending = []
    close(cur + pending)
    from ..score import pitch_name

    out = []
    for k, idx in enumerate(notes, start=1):
        tone = float(np.median(a.midi[idx]))
        out.append({"index": k, "lyric": "?", "pitch": pitch_name(round(tone)), "tone": tone,
                    "start_ms": float(a.t_ms[idx[0]]), "end_ms": float(a.t_ms[idx[-1]] + 5), "controls": {}, "phrase": None, "track": None})
    t = a.t_ms
    pm = np.full(len(t), np.nan)
    for n in out:
        m = (t >= n["start_ms"]) & (t < n["end_ms"])
        pm[m] = n["tone"]
    ok = np.isfinite(pm)
    it = Intent(out, [], t[ok], pm[ok], [], "segmented from pitch")
    it._spans = [(n["start_ms"], n["end_ms"]) for n in out]
    it.offset_ms = 0.0
    return it


def pitch_extract(wav, methods=None, out=None):
    a_methods = tuple(methods or f0mod.available())
    import soundfile as sf

    x, sr = sf.read(wav, dtype="float64", always_2d=True)
    x = x.mean(1)
    res = f0mod.extract(x, sr, a_methods)
    t = res["t"] * 1000
    curves = {m: f0mod.to_midi(c) for m, c in res["curves"].items()}
    summary = {}
    for m, c in curves.items():
        v = np.isfinite(c)
        summary[m] = {"voiced_pct": round(float(np.mean(v) * 100), 1), "median_midi": round(float(np.nanmedian(c)), 2) if v.any() else None}
    data = {"t_ms": [round(float(v), 1) for v in t], "merged_midi": [None if not np.isfinite(v) else round(float(v), 3) for v in f0mod.to_midi(res["f0"])]}
    for m, c in curves.items():
        data[m] = [None if not np.isfinite(v) else round(float(v), 3) for v in c]
    path = out or os.path.splitext(wav)[0] + ".f0.json"
    with open(path, "w") as f:
        json.dump(data, f)
    return {"wav": os.path.abspath(wav), "extractors": list(a_methods), "available": f0mod.available(), "frame_ms": 5.0,
            "per_extractor": summary, "disagreements": res["disagreements"][:100], "curves_file": path,
            "note": "where extractors disagree, a pitch 'error' may be a tracking error rather than a tuning error"}


def compare(a_wav, b_wav, out_dir=None, images=True):
    from .compare import global_diff, note_deltas, verdict

    out_dir = out_dir or os.path.splitext(b_wav)[0] + "_vs_" + os.path.splitext(os.path.basename(a_wav))[0]
    os.makedirs(out_dir, exist_ok=True)
    ra = inspect(a_wav, out_dir=os.path.join(out_dir, "a"), images=False, asr=False)
    rb = inspect(b_wav, out_dir=os.path.join(out_dir, "b"), images=False, asr=False)
    a = analyze_audio(a_wav)
    b = analyze_audio(b_wav)
    rep = {"a": a_wav, "b": b_wav, "out_dir": out_dir, "global": global_diff(a, b), "notes": note_deltas(ra, rb), "verdict": verdict(ra, rb),
           "artifacts": {"a": ra["artifact_counts"], "b": rb["artifact_counts"]},
           "overall": {"a": ra.get("overall"), "b": rb.get("overall")}}
    if images:
        intent = from_sidecar(a_wav)
        rep["images"] = [plots.ab(a, b, os.path.join(out_dir, "compare")), plots.ab_pitch(a, b, intent, os.path.join(out_dir, "compare_pitch.png"))]
    with open(os.path.join(out_dir, "compare.json"), "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1, default=float)
    return rep
