"""images an agent can read: big labels, the lyric and note name on everything, consistent colors,
zoomed crops instead of one huge plot."""

import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from .analysis import frames_in  # noqa: E402

import logging  # noqa: E402

from matplotlib import font_manager  # noqa: E402

logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
_WANT = ["Hiragino Sans", "Noto Sans CJK JP", "Noto Sans JP", "IPAexGothic", "IPAGothic", "Yu Gothic", "Arial Unicode MS", "DejaVu Sans"]
_HAVE = {f.name for f in font_manager.fontManager.ttflist}
plt.rcParams["font.family"] = [f for f in _WANT if f in _HAVE] or ["DejaVu Sans"]
plt.rcParams["font.size"] = 13
plt.rcParams["axes.titlesize"] = 15
plt.rcParams["axes.labelsize"] = 13

COL = {
    "intended": "#1f77b4",
    "measured": "#d62728",
    "note": "#c7dcef",
    "note_edge": "#5b8db8",
    "phone": "#7f7f7f",
    "join": "#9467bd",
    "artifact": "#ff7f0e",
}
NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
MAX_CROP_MS = 8000


def _name(m):
    m = int(round(m))
    return f"{NAMES[m % 12]}{m // 12 - 1}"


def crops(a, intent, notes_filter=None):
    """time windows to draw: one per phrase (split if long), or the selected notes."""
    if intent and intent.notes:
        notes = intent.notes
        if notes_filter:
            notes = [n for n in notes if n["index"] in notes_filter]
            if not notes:
                return []
            return [(max(0, notes[0]["start_ms"] - 250), notes[-1]["end_ms"] + 150, "notes")]
        groups = {}
        for n in notes:
            groups.setdefault((n.get("track"), n.get("phrase")), []).append(n)
        out = []
        for (tr, ph), ns in sorted(groups.items(), key=lambda kv: kv[1][0]["start_ms"]):
            s, e = max(0, ns[0]["start_ms"] - 250), min(a.duration_ms, ns[-1]["end_ms"] + 150)
            while e - s > MAX_CROP_MS:
                out.append((s, s + MAX_CROP_MS, f"phrase{ph}"))
                s += MAX_CROP_MS - 500
            out.append((s, e, f"phrase{ph}" if ph else "notes"))
        return out
    out, s = [], 0.0
    while s < a.duration_ms:
        out.append((s, min(a.duration_ms, s + MAX_CROP_MS), "audio"))
        s += MAX_CROP_MS
    return out


def _notes_in(intent, s, e):
    return [n for n in (intent.notes if intent else []) if n["end_ms"] > s and n["start_ms"] < e]


def _phones_in(intent, s, e):
    return [p for p in (intent.phones if intent else []) if p["end_ms"] > s and p["start_ms"] < e]


def _mark_artifacts(ax, artifacts, s, e, y):
    for ev in artifacts:
        if s <= ev["t_ms"] <= e and ev["severity"] != "info":
            ax.axvline(ev["t_ms"], color=COL["artifact"], lw=1.5, alpha=0.8)
            ax.annotate(ev["kind"], (ev["t_ms"], y), fontsize=10, color=COL["artifact"], rotation=90, va="top", ha="right")


def pianoroll(a, intent, s, e, path, artifacts=()):
    fig, ax = plt.subplots(figsize=(16, 7))
    notes = _notes_in(intent, s, e)
    m = frames_in(a, s, e)
    meas = np.where(a.voiced[m], a.midi[m], np.nan)
    vals = [n["tone"] for n in notes] + list(meas[np.isfinite(meas)])
    lo = int(np.floor(min(vals) - 2)) if vals else 48
    hi = int(np.ceil(max(vals) + 2)) if vals else 72
    for k in range(lo, hi + 1):
        ax.axhline(k, color="#000" if k % 12 == 0 else "#ddd", lw=1.2 if k % 12 == 0 else 0.6, zorder=0)
    ax.set_yticks(range(lo, hi + 1))
    ax.set_yticklabels([_name(k) for k in range(lo, hi + 1)], fontsize=10)
    for n in notes:
        ax.add_patch(plt.Rectangle((n["start_ms"], n["tone"] - 0.45), n["end_ms"] - n["start_ms"], 0.9, fc=COL["note"], ec=COL["note_edge"], lw=1.2, zorder=1))
        ax.text(n["start_ms"] + 8, n["tone"] + 0.55, f"{n['index']}:{n['lyric']} {n['pitch']}", fontsize=12, va="bottom", zorder=4)
    for p in _phones_in(intent, s, e):
        ax.axvline(p["start_ms"], color=COL["phone"], lw=0.6, ls=":", zorder=1)
        ax.text(p["start_ms"] + 3, lo + 0.2, p["phoneme"], fontsize=10, color="#555", rotation=90, va="bottom")
    if intent is not None and intent.pitch_t_ms is not None:
        it = intent.pitch_at(a.t_ms[m])
        ax.plot(a.t_ms[m], it, color=COL["intended"], lw=2, ls="--", label="intended", zorder=2)
    # inside consonants the tracker output is noise: draw it faint so the eye goes to the vowels
    cons = np.zeros(m.sum(), bool)
    tm_ = a.t_ms[m]
    for p in _phones_in(intent, s, e):
        if not p["vowel"]:
            cons |= (tm_ >= p["start_ms"]) & (tm_ < p["end_ms"])
    ax.plot(tm_, np.where(cons, np.nan, meas), color=COL["measured"], lw=2, label="measured f0", zorder=3)
    if cons.any():
        ax.plot(tm_, np.where(cons, meas, np.nan), color=COL["measured"], lw=1, alpha=0.3, zorder=3, label="measured (consonant)")
    _mark_artifacts(ax, artifacts, s, e, hi)
    ax.set_xlim(s, e)
    ax.set_ylim(lo, hi)
    ax.set_xlabel("time (ms, audio)")
    ax.set_title(f"piano roll {s / 1000:.2f}-{e / 1000:.2f} s: notes, intended (dashed) vs measured pitch")
    ax.legend(loc="upper right")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path


def spectrogram(a, intent, s, e, path, kind="linear", artifacts=()):
    fig, ax = plt.subplots(figsize=(16, 7))
    m = (a.spec_t_ms >= s) & (a.spec_t_ms < e)
    if kind == "mel":
        img = a.mel_db[:, m]
        ext = [s, e, 0, len(a.mel_hz)]
        ax.imshow(img, origin="lower", aspect="auto", extent=ext, cmap="magma", vmin=img.max() - 80, vmax=img.max())
        ticks = [100, 200, 400, 800, 1600, 3200, 6400, 12800]
        pos = [np.argmin(np.abs(a.mel_hz - t)) for t in ticks if t < a.mel_hz[-1]]
        ax.set_yticks(pos)
        ax.set_yticklabels([f"{int(a.mel_hz[p])}" for p in pos])
        f0y = np.interp(a.f0, a.mel_hz, np.arange(len(a.mel_hz)))
    else:
        fm = (a.spec_f > 40) & (a.spec_f < min(16000, a.sr / 2))
        img = a.spec_db[fm][:, m]
        ax.pcolormesh(a.spec_t_ms[m], a.spec_f[fm], img, cmap="magma", vmin=img.max() - 80, vmax=img.max(), shading="auto")
        ax.set_yscale("log")
        ax.set_ylim(60, min(16000, a.sr / 2))
        f0y = a.f0
    fmask = frames_in(a, s, e)
    ax.plot(a.t_ms[fmask], np.where(a.voiced[fmask], f0y[fmask], np.nan), color="cyan", lw=1.5, label="f0")
    ymax = ax.get_ylim()[1]
    for p in _phones_in(intent, s, e):
        ax.axvline(p["start_ms"], color="white", lw=0.7, ls=":")
        ax.text(p["start_ms"] + 3, ymax * (0.9 if kind == "linear" else 1) - (0 if kind == "linear" else 6), p["phoneme"], color="white", fontsize=11, va="top")
    for n in _notes_in(intent, s, e):
        ax.text(n["start_ms"] + 3, ax.get_ylim()[0] * (1.05 if kind == "linear" else 1) + (0 if kind == "linear" else 2), f"{n['lyric']} {n['pitch']}", color="yellow", fontsize=12, va="bottom")
    _mark_artifacts(ax, artifacts, s, e, ymax)
    ax.set_xlim(s, e)
    ax.set_xlabel("time (ms, audio)")
    ax.set_ylabel("Hz" + (" (mel scale)" if kind == "mel" else " (log)"))
    ax.set_title(f"{kind} spectrogram {s / 1000:.2f}-{e / 1000:.2f} s with f0, phones and lyrics")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path


def cents_strip(a, intent, s, e, path):
    fig, ax = plt.subplots(figsize=(16, 3.6))
    m = frames_in(a, s, e) & a.voiced
    err = (a.midi[m] - intent.pitch_at(a.t_ms[m])) * 100
    ok = np.isfinite(err)
    sc = ax.scatter(a.t_ms[m][ok], err[ok], c=np.clip(np.abs(err[ok]), 0, 100), cmap="RdYlGn_r", vmin=0, vmax=100, s=10)
    for lim in (-20, 20):
        ax.axhline(lim, color="#888", ls="--", lw=0.8)
    ax.axhline(0, color="#000", lw=0.8)
    for n in _notes_in(intent, s, e):
        ax.axvspan(n["start_ms"], n["end_ms"], color="#eee", zorder=0)
        ax.text(n["start_ms"] + 5, 95, f"{n['lyric']} {n['pitch']}", fontsize=11, va="top")
    ax.set_ylim(-110, 110)
    ax.set_xlim(s, e)
    ax.set_ylabel("cents vs intent")
    ax.set_xlabel("time (ms, audio)")
    ax.set_title("pitch error: measured minus intended (green = within 20 cents)")
    fig.colorbar(sc, ax=ax, label="|cents|", pad=0.01)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path


def vibrato(a, intent, note, metrics, path):
    s, e = note["start_ms"], note["end_ms"]
    m = frames_in(a, s, e)
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(a.t_ms[m], np.where(a.voiced[m], (a.midi[m] - note["tone"]) * 100, np.nan), color=COL["measured"], lw=2, label="measured")
    if intent.pitch_t_ms is not None:
        ax.plot(a.t_ms[m], (intent.pitch_at(a.t_ms[m]) - note["tone"]) * 100, color=COL["intended"], lw=2, ls="--", label="intended")
    ax.axhline(0, color="#000", lw=0.8)
    vm, vi = metrics.get("vibrato"), metrics.get("intended_vibrato")
    t = f"note {note['index']} {note['lyric']} {note['pitch']} vibrato: "
    t += f"measured {vm['rate_hz']} Hz / ±{vm['depth_cents']}c" if vm else "measured none"
    t += f", intended {vi['rate_hz']} Hz / ±{vi['depth_cents']}c" if vi else ", intended none"
    ax.set_title(t)
    ax.set_ylabel("cents vs note")
    ax.set_xlabel("time (ms, audio)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path


def lanes(a, intent, s, e, path, formant_tracks=None):
    m = frames_in(a, s, e)
    fig, axs = plt.subplots(5, 1, figsize=(16, 12), sharex=True)
    t = a.t_ms[m]
    axs[0].plot(t, a.rms_db[m], color="#333", label="rms dBFS")
    stm = (a.st_t * 1000 >= s) & (a.st_t * 1000 < e)
    axs[0].plot(a.st_t[stm] * 1000, a.st_lufs[stm], color="#2ca02c", label="short-term LUFS")
    axs[0].set_ylabel("loudness")
    axs[0].legend(loc="upper right")
    axs[1].plot(t, np.where(a.voiced[m], a.breath_db[m], np.nan), color="#8c564b")
    axs[1].set_ylabel("breathiness\n(ap dB, 1-5k)")
    axs[2].plot(t, np.where(a.voiced[m], a.hnr_db[m], np.nan), color="#17becf")
    axs[2].set_ylabel("HNR dB")
    axs[3].plot(t, a.centroid[m], color="#bcbd22")
    axs[3].set_ylabel("centroid Hz")
    if formant_tracks is not None:
        ft, fv = formant_tracks
        fm = (ft >= s) & (ft < e)
        for k, c in zip(range(3), ("#1f77b4", "#ff7f0e", "#2ca02c")):
            axs[4].scatter(ft[fm], fv[fm, k], s=6, color=c, label=f"F{k + 1}")
        axs[4].legend(loc="upper right")
    axs[4].set_ylabel("formants Hz")
    axs[4].set_xlabel("time (ms, audio)")
    for ax in axs:
        for n in _notes_in(intent, s, e):
            ax.axvline(n["start_ms"], color="#ccc", lw=0.6)
    for n in _notes_in(intent, s, e):
        axs[0].text(n["start_ms"] + 3, axs[0].get_ylim()[1], f"{n['lyric']} {n['pitch']}", fontsize=11, va="top")
    axs[0].set_title(f"loudness and timbre lanes {s / 1000:.2f}-{e / 1000:.2f} s")
    axs[0].set_xlim(s, e)
    fig.tight_layout()
    fig.savefig(path, dpi=100)
    plt.close(fig)
    return path


def joins(a, intent, path, limit=24):
    js = intent.joins[:limit]
    if not js:
        return None
    cols = 4
    rows = int(np.ceil(len(js) / cols))
    fig, axs = plt.subplots(rows * 2, cols, figsize=(16, 3.4 * rows), squeeze=False)
    for k, j in enumerate(js):
        r, c = (k // cols) * 2, k % cols
        t = j["t_ms"]
        i0, i1 = int(max(0, (t - 40) / 1000 * a.sr)), int(min(len(a.x), (t + 40) / 1000 * a.sr))
        tt = np.arange(i0, i1) * 1000 / a.sr
        axs[r][c].plot(tt, a.x[i0:i1], color="#333", lw=0.6)
        axs[r][c].axvline(t, color=COL["join"])
        axs[r][c].set_title(f"{j['from']} → {j['to']}  {t:.0f}ms", fontsize=11)
        axs[r][c].set_xticks([])
        sm = (a.spec_t_ms >= t - 40) & (a.spec_t_ms < t + 40)
        fm = a.spec_f < 8000
        axs[r + 1][c].pcolormesh(a.spec_t_ms[sm], a.spec_f[fm], a.spec_db[fm][:, sm], cmap="magma", shading="auto")
        axs[r + 1][c].axvline(t, color="cyan", lw=0.8)
        axs[r + 1][c].set_yticks([])
    for k in range(len(js), rows * cols):
        axs[(k // cols) * 2][k % cols].axis("off")
        axs[(k // cols) * 2 + 1][k % cols].axis("off")
    fig.suptitle("sample joins (utau): waveform and spectrogram ±40 ms around each crossfade")
    fig.tight_layout()
    fig.savefig(path, dpi=100)
    plt.close(fig)
    return path


def ab(a, b, path_prefix, path_aligned=None):
    """side by side spectrograms plus the difference after dtw alignment on log-mel frames."""
    from .compare import dtw_path

    pa = path_prefix + "_ab.png"
    fig, axs = plt.subplots(3, 1, figsize=(16, 12))
    for ax, x, label in ((axs[0], a, "A"), (axs[1], b, "B")):
        ax.imshow(x.mel_db, origin="lower", aspect="auto", cmap="magma", vmin=x.mel_db.max() - 80, vmax=x.mel_db.max(),
                  extent=[0, x.spec_t_ms[-1], 0, len(x.mel_hz)])
        ax.set_title(f"{label}: {os.path.basename(x.path)}")
        ax.set_ylabel("mel bin")
    ia, ib = dtw_path(a.mel_db, b.mel_db)
    diff = b.mel_db[:, ib] - a.mel_db[:, ia]
    t = a.spec_t_ms[ia]
    axs[2].imshow(diff, origin="lower", aspect="auto", cmap="RdBu_r", vmin=-20, vmax=20, extent=[t[0], t[-1], 0, len(a.mel_hz)])
    axs[2].set_title("B minus A (dB) after dtw time alignment; red = louder in B")
    axs[2].set_xlabel("time (ms, A's timeline)")
    fig.tight_layout()
    fig.savefig(pa, dpi=100)
    plt.close(fig)
    return pa


def ab_pitch(a, b, intent, path):
    fig, ax = plt.subplots(figsize=(16, 6))
    ax.plot(a.t_ms, np.where(a.voiced, a.midi, np.nan), color="#d62728", lw=1.6, label=f"A {os.path.basename(a.path)}")
    ax.plot(b.t_ms, np.where(b.voiced, b.midi, np.nan), color="#2ca02c", lw=1.6, label=f"B {os.path.basename(b.path)}")
    if intent is not None:
        for n in intent.notes:
            ax.add_patch(plt.Rectangle((n["start_ms"], n["tone"] - 0.45), n["end_ms"] - n["start_ms"], 0.9, fc=COL["note"], ec=COL["note_edge"], zorder=0))
            ax.text(n["start_ms"] + 5, n["tone"] + 0.5, f"{n['lyric']} {n['pitch']}", fontsize=11)
    lo, hi = ax.get_ylim()
    ax.set_yticks(range(int(lo), int(hi) + 1))
    ax.set_yticklabels([_name(k) for k in range(int(lo), int(hi) + 1)], fontsize=9)
    ax.grid(axis="y", color="#eee")
    ax.legend()
    ax.set_title("pitch: A vs B")
    ax.set_xlabel("time (ms)")
    fig.tight_layout()
    fig.savefig(path, dpi=100)
    plt.close(fig)
    return path
