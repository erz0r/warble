"""mock classic utau banks from synthesized samples.

vowels are a glottal pulse train through formant resonators at a fixed pitch, consonants are
noise bursts, taps or nasal murmurs. every sample comes with an oto entry whose numbers point at
the real regions of the sample, so the utau path has something honest to cut and stretch.
"""

import os

import numpy as np
import soundfile as sf
from scipy.signal import lfilter

SR = 44100
FORMANTS = {
    "a": (800, 1200, 2500),
    "i": (300, 2300, 3000),
    "u": (350, 1250, 2300),
    "e": (450, 1900, 2600),
    "o": (500, 850, 2400),
    "n": (250, 1500, 2500),  # nasal ん
}
ROMA = {
    "あ": ("", "a"), "い": ("", "i"), "う": ("", "u"), "え": ("", "e"), "お": ("", "o"), "ん": ("", "n"),
    "か": ("k", "a"), "き": ("k", "i"), "く": ("k", "u"), "け": ("k", "e"), "こ": ("k", "o"),
    "さ": ("s", "a"), "し": ("s", "i"), "す": ("s", "u"), "せ": ("s", "e"), "そ": ("s", "o"),
    "ら": ("r", "a"), "り": ("r", "i"), "る": ("r", "u"), "れ": ("r", "e"), "ろ": ("r", "o"),
    "な": ("n", "a"), "ま": ("m", "a"),
}
CONS_MS = {"": 0, "k": 45, "s": 110, "r": 30, "n": 60, "m": 60}


def _resonator(x, f, bw):
    r = np.exp(-np.pi * bw / SR)
    c = 2 * r * np.cos(2 * np.pi * f / SR)
    return lfilter([1 - r], [1, -c, r * r], x)


def vowel(v, ms, f0, rng):
    n = int(SR * ms / 1000)
    t = np.arange(n) / SR
    # slight natural drift so pitch trackers have something real to follow
    inst = f0 * (1 + 0.004 * np.sin(2 * np.pi * 5.5 * t))
    phase = np.cumsum(inst / SR)
    pulses = (np.diff(np.floor(phase), prepend=0) > 0).astype(float)
    src = lfilter([1], [1, -0.97], pulses) + 0.01 * rng.standard_normal(n)
    y = sum(_resonator(src, f, 80 + 0.05 * f) * g for f, g in zip(FORMANTS[v], (1.0, 0.6, 0.3)))
    return y


def consonant(c, rng, f0):
    ms = CONS_MS[c]
    n = int(SR * ms / 1000)
    if c == "k":
        y = np.zeros(n)
        burst = rng.standard_normal(int(SR * 0.02)) * np.hanning(int(SR * 0.02))
        y[int(SR * 0.02):int(SR * 0.02) + len(burst)] = burst * 0.6
        return _resonator(y, 1800, 600)
    if c == "s":
        y = rng.standard_normal(n) * np.hanning(n)
        return _resonator(y, 5500, 2500) * 0.8
    if c == "r":
        return vowel("e", ms, f0, rng) * np.linspace(0.2, 0.8, n)
    if c in ("n", "m"):
        return vowel("n", ms, f0, rng) * 0.6
    return np.zeros(0)


def _fade(y, ms=8):
    k = int(SR * ms / 1000)
    if len(y) > 2 * k:
        y[:k] *= np.linspace(0, 1, k)
        y[-k:] *= np.linspace(1, 0, k)
    return y


def sample(parts, f0, rng, lead_ms=60, tail_ms=40):
    """parts: list of ('c', cons) / ('v', vowel, ms). returns (audio, marks) where marks has the
    ms position where each part starts."""
    chunks = [np.zeros(int(SR * lead_ms / 1000))]
    marks = []
    pos = lead_ms
    for p in parts:
        if p[0] == "c":
            y = consonant(p[1], rng, f0)
        else:
            y = vowel(p[1], p[2], f0, rng)
        marks.append(pos)
        chunks.append(_fade(np.asarray(y, float), 4))
        pos += 1000 * len(y) / SR
    chunks.append(np.zeros(int(SR * tail_ms / 1000)))
    y = np.concatenate(chunks)
    y = 0.5 * y / (np.max(np.abs(y)) + 1e-9)
    return y, marks, pos


def write_wav(path, y):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    sf.write(path, y, SR, subtype="PCM_16")


def oto_line(wav, alias, offset, consonant, cutoff, preutter, overlap):
    return f"{wav}={alias},{offset:.1f},{consonant:.1f},{cutoff:.1f},{preutter:.1f},{overlap:.1f}"


def build_cv(root, encoding="cp932", suffix="", f0=261.63, kana=None, write_character=True):
    """single-sound (単独音) bank: one sample per kana, '- ' less aliases."""
    rng = np.random.default_rng(3)
    lines = []
    for k, (c, v) in (kana or ROMA).items():
        parts = ([("c", c)] if c else []) + [("v", v, 700)]
        y, marks, end = sample(parts, f0, rng)
        fn = f"{k}{suffix}.wav"
        write_wav(os.path.join(root, fn), y)
        vstart = marks[-1]
        offset = max(0.0, (marks[0] if c else vstart) - 20)
        pre = vstart - offset
        lines.append(oto_line(fn, f"{k}{suffix}", offset, pre + 60, -(end - 30 - offset), pre, min(pre, 15) if c else 5))
    os.makedirs(root, exist_ok=True)
    with open(os.path.join(root, "oto.ini"), "wb") as f:
        f.write(("\r\n".join(lines) + "\r\n").encode(encoding))
    if write_character:
        with open(os.path.join(root, "character.txt"), "wb") as f:
            f.write("name=モックCV\r\nauthor=warble tests\r\n".encode(encoding))
        with open(os.path.join(root, "readme.txt"), "wb") as f:
            f.write("テスト用のモック音源です。\r\n".encode(encoding))
    return root


def build_vcv(root):
    """vcv bank: '- か' heads and 'a か' transitions, utf-8 with #Charset."""
    rng = np.random.default_rng(4)
    lines = ["#Charset:utf-8"]
    vowels = ["a", "i", "u", "e", "o"]
    kana = {k: cv for k, cv in ROMA.items() if k != "ん"}
    for k, (c, v) in kana.items():
        for left in ["-"] + vowels:
            parts = ([] if left == "-" else [("v", left, 250)]) + ([("c", c)] if c else []) + [("v", v, 600)]
            y, marks, end = sample(parts, 261.63, rng)
            stem = ("_" if left == "-" else left) + "_" + (c + v)
            fn = f"{stem}.wav"
            write_wav(os.path.join(root, fn), y)
            vstart = marks[-1]
            cstart = marks[-2] if c else vstart
            offset = (cstart - 60) if left != "-" else max(0.0, cstart - 20)
            pre = vstart - offset
            ovl = (cstart - offset) if left != "-" else 5
            lines.append(oto_line(fn, f"{left} {k}", offset, pre + 50, -(end - 30 - offset), pre, ovl))
    with open(os.path.join(root, "oto.ini"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    with open(os.path.join(root, "character.txt"), "w", encoding="utf-8") as f:
        f.write("name=Mock VCV\n")
    with open(os.path.join(root, "character.yaml"), "w", encoding="utf-8") as f:
        f.write("text_file_encoding: utf-8\nsinger_type: utau\n")
    return root


def build_cvvc(root):
    """cvvc bank with romaji aliases: '- ka', 'ka', 'a k', 'a R'."""
    rng = np.random.default_rng(5)
    lines = []
    vowels = ["a", "i", "u", "e", "o"]
    cons = ["k", "s", "r", "n", "m"]
    for c in [""] + cons:
        for v in vowels:
            if c in ("n", "m") and v != "a":
                continue
            parts = ([("c", c)] if c else []) + [("v", v, 600)]
            y, marks, end = sample(parts, 261.63, rng)
            cv = c + v
            write_wav(os.path.join(root, f"{cv}.wav"), y)
            vstart = marks[-1]
            offset = max(0.0, marks[0] - 20)
            pre = vstart - offset
            lines.append(oto_line(f"{cv}.wav", f"- {cv}", offset, pre + 60, -(end - 30 - offset), pre, 5))
            lines.append(oto_line(f"{cv}.wav", cv, offset, pre + 60, -(end - 30 - offset), pre, min(pre, 20)))
    for v in vowels:
        for c in cons + ["R"]:
            parts = [("v", v, 300)] + ([("c", c)] if c != "R" else [])
            y, marks, end = sample(parts, 261.63, rng, tail_ms=200)
            # "R" (ending) gets its own name: a_R.wav and a_r.wav collide on case-insensitive disks
            fn = f"{v}_{c}.wav" if c != "R" else f"{v}_end.wav"
            write_wav(os.path.join(root, fn), y)
            cstart = marks[-1] if c != "R" else end
            offset = cstart - 120
            pre = 120
            lines.append(oto_line(fn, f"{v} {c}", offset, pre + 30, -(cstart + 100 - offset), pre, 40))
    with open(os.path.join(root, "oto.ini"), "w", encoding="ascii") as f:
        f.write("\n".join(lines) + "\n")
    with open(os.path.join(root, "character.txt"), "w", encoding="ascii") as f:
        f.write("name=Mock CVVC\n")
    return root


def build_multipitch(root):
    """cv bank in two pitch folders with a prefix.map that picks the suffix by note."""
    small = {k: ROMA[k] for k in ["あ", "い", "う", "か", "さ", "ら"]}
    build_cv(os.path.join(root, "C4"), encoding="cp932", suffix="", f0=261.63, kana=small, write_character=False)
    build_cv(os.path.join(root, "A4"), encoding="cp932", suffix="↑", f0=440.0, kana=small, write_character=False)
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    lines = []
    for tone in range(107, 23, -1):
        name = f"{names[tone % 12]}{tone // 12 - 1}"
        suffix = "↑" if tone >= 67 else ""  # G4 and up use the A4 folder
        lines.append(f"{name}\t\t{suffix}")
    with open(os.path.join(root, "prefix.map"), "wb") as f:
        f.write(("\r\n".join(lines) + "\r\n").encode("cp932"))
    with open(os.path.join(root, "character.txt"), "wb") as f:
        f.write("name=モック多音階\r\n".encode("cp932"))
    return root


def build_all(base):
    banks = os.path.join(base, "banks")
    return {
        "utau_cv_sjis": build_cv(os.path.join(banks, "utau_cv_sjis")),
        "utau_vcv": build_vcv(os.path.join(banks, "utau_vcv")),
        "utau_cvvc": build_cvvc(os.path.join(banks, "utau_cvvc")),
        "utau_multipitch": build_multipitch(os.path.join(banks, "utau_multipitch")),
    }


if __name__ == "__main__":
    import json
    import sys

    print(json.dumps(build_all(sys.argv[1] if len(sys.argv) > 1 else "tests/fixtures"), indent=2))
