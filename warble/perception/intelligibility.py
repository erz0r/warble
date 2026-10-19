"""can the words be understood? transcribe each phrase with a local speech recognizer and compare
it to the lyrics. this is the nearest thing to the agent hearing the words. uses faster-whisper or
openai-whisper when installed; otherwise says so."""

import os

import numpy as np

_MODEL = None


def _load():
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    size = os.environ.get("WARBLE_ASR_MODEL", "small")
    try:
        from faster_whisper import WhisperModel

        _MODEL = ("faster", WhisperModel(size, device="cpu", compute_type="int8"))
        return _MODEL
    except ImportError:
        pass
    try:
        import whisper

        _MODEL = ("openai", whisper.load_model(size))
        return _MODEL
    except ImportError:
        return None


FOLD = str.maketrans({"を": "お", "づ": "ず", "ぢ": "じ", "ゐ": "い", "ゑ": "え"})


def _norm_ja(text):
    from ..lang import ja
    from ..lyrics import japanese_reading

    try:
        text, _ = japanese_reading(text)  # recognizers answer in kanji
    except Exception:  # noqa: BLE001
        pass
    h = ja.to_hiragana(text).translate(FOLD)
    out = []
    for ch in h:
        if "぀" <= ch <= "ゟ" or ch.isalpha():
            out.append(ch)
    return "".join(out)


def _syllables(text, lang):
    from ..lang import ja

    if lang == "ja" or any("぀" <= c <= "ヿ" for c in text):
        return ja.split_mora(_norm_ja(text))
    import re

    return [w for w in re.findall(r"[a-z0-9]+", text.lower().replace("'", ""))]


def _align_score(ref, hyp):
    """levenshtein alignment; returns matched count and the reference units that came out wrong."""
    n, m = len(ref), len(hyp)
    d = np.zeros((n + 1, m + 1), int)
    d[:, 0] = np.arange(n + 1)
    d[0, :] = np.arange(m + 1)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            d[i, j] = min(d[i - 1, j] + 1, d[i, j - 1] + 1, d[i - 1, j - 1] + (ref[i - 1] != hyp[j - 1]))
    i, j, wrong, ok = n, m, [], 0
    while i > 0 and j > 0:
        if ref[i - 1] == hyp[j - 1] and d[i, j] == d[i - 1, j - 1]:
            ok += 1
            i, j = i - 1, j - 1
        elif d[i, j] == d[i - 1, j - 1] + 1:
            wrong.append(ref[i - 1])
            i, j = i - 1, j - 1
        elif d[i, j] == d[i - 1, j] + 1:
            wrong.append(ref[i - 1])
            i -= 1
        else:
            j -= 1
    wrong += ref[:i]
    return ok, list(reversed(wrong))


def check(a, intent, note_filter=None):
    model = _load()
    if model is None:
        return {"available": False, "reason": "no local speech recognizer (pip install faster-whisper to enable)"}
    kind, m = model
    phrases = {}
    for n in intent.notes:
        if note_filter and n["index"] not in note_filter:
            continue
        phrases.setdefault((n.get("track"), n.get("phrase")), []).append(n)
    total = good = 0
    out = []
    misheard = []
    from scipy.signal import resample_poly

    for key, ns in phrases.items():
        s, e = ns[0]["start_ms"] - 150, ns[-1]["end_ms"] + 150
        seg = a.x[int(max(0, s) / 1000 * a.sr): int(e / 1000 * a.sr)]
        y = resample_poly(seg, 16000, a.sr).astype(np.float32)
        words = [n["lyric"] for n in ns if not n["lyric"].startswith("+")]
        cjk = any("぀" <= c <= "ヿ" or "一" <= c <= "鿿" or "가" <= c <= "힣" for w in words for c in w)
        # kana/hanzi/hangul lyrics are syllables to join; anything else is words to keep apart
        lyric = "".join(words) if cjk else " ".join(words)
        lang = "ja" if any("぀" <= c <= "ヿ" for c in lyric) else None
        if kind == "faster":
            segs, _ = m.transcribe(y, language=lang, beam_size=1)
            text = "".join(x.text for x in segs)
        else:
            text = m.transcribe(y, language=lang)["text"]
        ref = _syllables(lyric, lang)
        hyp = _syllables(text, lang)
        ok, wrong = _align_score(ref, hyp)
        total += len(ref)
        good += ok
        misheard += wrong
        out.append({"phrase": key[1], "lyrics": lyric, "heard": text.strip(), "syllables": len(ref), "recognized": ok, "wrong": wrong})
    return {"available": True, "engine": kind, "syllable_accuracy_pct": round(100 * good / max(1, total), 1), "phrases": out, "misheard": misheard}
