"""diffsinger phonemizer: lyrics -> phonemes -> timed phones.

ported from openutau (MIT, Copyright (c) 2014 StAkira):
OpenUtau.Core/DiffSinger/DiffSingerBasePhonemizer.cs, MachineLearningPhonemizer.cs.

lookup priority: explicit [phonetic hint], then the dictionary (lyric, its language front-end
spellings, lowercase), then the lyric read as space-separated phonemes (with and without the
language prefix). unlike openutau, unknown symbols are never dropped silently: they are reported
with the closest valid symbols.
"""

import bisect
import difflib

import numpy as np

from .. import lang as langs
from .. import onnxrun
from ..errors import WarbleError
from . import voices
from .util import durations_ms_to_frames  # noqa: F401 - re-exported for tests

LEAD_PADDING_MS = 500.0
RULE_CONSONANT_MS = 70.0


class Phonemizer:
    def __init__(self, bank, models, lang=None):
        self.bank = bank
        self.models = models
        self.lang = lang or ""
        self.dur = models.get("dsdur")
        # symbol types come from the duration model's dictionary when there is one
        src = self.dur or models.get("acoustic")
        self.dict = src.dict(self.lang) or models.get("acoustic").dict(self.lang)
        if self.dict is None:
            raise WarbleError(
                "dictionary_missing",
                f"{bank.name} has no dsdict-{self.lang}.yaml or dsdict.yaml in {src.dir}",
                hint="give lyrics as explicit phonemes in [brackets], or add a dictionary",
            )
        self.tokens = src.tokens

    # ---- symbols ---------------------------------------------------------------------

    def _valid(self, ph):
        """ValidatePhoneme: a known symbol that the model can tokenize, else try '<lang>/<ph>'."""
        if ph in self.dict.symbols and ph in self.tokens:
            return ph
        if self.lang:
            pref = f"{self.lang}/{ph}"
            if pref in self.dict.symbols and pref in self.tokens:
                return pref
        return None

    def closest(self, ph, n=6):
        pool = [s for s in self.dict.symbols if s in self.tokens]
        if self.lang:
            pool += [s.split("/", 1)[1] for s in pool if s.startswith(self.lang + "/")]
        return difflib.get_close_matches(ph, sorted(set(pool)), n=n, cutoff=0.4)

    def symbols_for(self, note):
        """-> (symbols, rejected, source). rejected lists symbols the bank can't sing."""
        if note.hint:
            raw = note.hint.split()
            ok = [self._valid(s) for s in raw]
            return [s for s in ok if s], [r for r, s in zip(raw, ok) if not s], "hint"
        for cand in langs.candidates(self.lang, note.lyric):
            if cand in self.dict.entries:
                phs = self.dict.entries[cand]
                good = [p for p in phs if p in self.tokens and p in self.dict.symbols]
                bad = [p for p in phs if p not in good]
                return good, bad, f"dict:{cand}"
        raw = note.lyric.split()
        ok = [self._valid(s) for s in raw]
        if any(ok):
            return [s for s in ok if s], [r for r, s in zip(raw, ok) if not s], "as-phonemes"
        return [], [note.lyric], "unknown"

    def is_vowel(self, ph):
        return self.dict.is_vowel(ph)

    def is_glide(self, ph):
        return self.dict.is_glide(ph)

    # ---- words -----------------------------------------------------------------------

    def process_word(self, notes, symbols, mixes):
        """distribute a word's phonemes across its notes (ProcessWord). returns a list of
        [note_or_None, tone, [(phoneme, mix)]]; the first entry (note None) holds the leading
        consonants that belong before the word's first vowel."""
        for s in symbols:
            if s not in self.dict.symbols:
                raise WarbleError("symbol_type_missing", f"symbol '{s}' has no type in {self.dict.path}", hint="add it to the dictionary's symbols list")
        out = [[None, notes[0].tone, []]]
        isv = [self.is_vowel(s) for s in symbols]
        isg = [self.is_glide(s) for s in symbols]
        non_ext = [n for n in notes if not (n.lyric.startswith("+~") or n.lyric.startswith("+*"))]
        start = [False] * len(symbols)
        if not any(isv):
            start[0] = True
        for i in range(len(symbols)):
            if isv[i]:
                # consonant-glide-vowel: the glide starts the note
                if i >= 2 and isg[i - 1] and not isv[i - 2]:
                    start[i - 1] = True
                else:
                    start[i] = True
        ni = 0
        for i, s in enumerate(symbols):
            if start[i] and ni < len(non_ext):
                out.append([non_ext[ni], non_ext[ni].tone, []])
                ni += 1
            out[-1][2].append((s, mixes[0]))
        return out

    # ---- phrases ---------------------------------------------------------------------

    def phonemize_phrase(self, words, tm, voice_of, seed=None):
        """words: list of note groups (one phrase, no rests inside). voice_of(note) -> voice spec.
        returns {"phones": [...], "words": [...], "unknown": [...], "durations": "model"|"rule"}."""
        frame_ms = (self.dur or self.models.get("acoustic")).frame_ms
        groups = [[None, words[0][0].tone, [("SP", voices.resolve(self.bank, voice_of(words[0][0]), words[0][0].tone))]]]
        note_ph_index = [1]
        found = []
        unknown = []
        word_info = []
        for w in words:
            head = w[0]
            syms, rejected, source = self.symbols_for(head)
            mix = voices.resolve(self.bank, voice_of(head), head.tone)
            if rejected or not syms:
                unknown.append({
                    "lyric": head.lyric, "position": head.position, "line": head.line,
                    "rejected": rejected or [head.lyric],
                    "closest": {r: self.closest(r) for r in (rejected or [head.lyric])},
                })
            if not syms:
                syms = ["SP"]
                found.append(False)
            else:
                found.append(True)
            wp = self.process_word(w, syms, [mix])
            groups[-1][2].extend(wp[0][2])
            groups.extend(wp[1:])
            note_ph_index.append(note_ph_index[-1] + sum(len(g[2]) for g in wp))
            word_info.append({"lyric": head.lyric, "symbols": syms, "source": source})
        last = words[-1][-1]
        end_ms = tm.tick_to_ms(last.end)
        pos = [None] + [tm.tick_to_ms(g[0].position) for g in groups[1:]] + [end_ms]
        pos[0] = pos[1] - LEAD_PADDING_MS
        groups.append([last, last.tone, []])

        flat = [(ph, mix) for g in groups for ph, mix in g[2]]
        if self.dur is not None:
            frames = self._predict(groups, flat, pos, frame_ms, seed)
            how = "model"
        else:
            frames = self._rule_frames(groups, pos, frame_ms)
            how = "rule"

        # alignment: leading consonants keep their length and end at the first note; each later
        # group is stretched to exactly fill its span
        counts = [len(g[2]) for g in groups]
        cum = list(np.cumsum(counts))
        align = list(zip(cum[:-1], pos[1:]))
        positions = []
        lead = frames[1:align[0][0]]
        positions += _stretch(lead, frame_ms, align[0][1])
        for (ai, ams), (bi, bms) in zip(align, align[1:]):
            grp = frames[ai:bi]
            total = sum(grp)
            ratio = (bms - ams) / total if total > 0 else 0.0
            positions += _stretch(grp, ratio, bms)

        phones = []
        for k, (ph, mix) in enumerate(flat[1:], start=1):
            phones.append({"phoneme": ph, "position_ms": float(positions[k - 1]), "mix": mix})
        # word index per phone: word w owns flat indices [note_ph_index[w], note_ph_index[w+1]),
        # which includes its leading consonants even though they sit in the previous note's group
        for k in range(len(phones)):
            phones[k]["word"] = min(len(words) - 1, bisect.bisect_right(note_ph_index, k + 1) - 1)
        for k, ph in enumerate(phones):
            nxt = phones[k + 1]["position_ms"] if k + 1 < len(phones) else end_ms
            ph["duration_ms"] = max(0.0, nxt - ph["position_ms"])
        # tone per phone: the note sounding at the phone's start (leading consonants take the next note)
        notes = [n for w in words for n in w]
        for ph in phones:
            t = ph["position_ms"]
            tone = notes[0].tone
            for n in notes:
                if tm.tick_to_ms(n.position) <= t + 1e-6:
                    tone = n.tone
            ph["tone"] = tone
        for i, f in enumerate(found):
            word_info[i]["found"] = f
        return {"phones": phones, "words": word_info, "unknown": unknown, "durations": how, "frame_ms": frame_ms,
                "start_ms": pos[1], "end_ms": end_ms}

    def _predict(self, groups, flat, pos, frame_ms, seed):
        dur = self.dur
        tokens = np.array([[dur.token(ph) for ph, _ in flat]], np.int64)
        word_div = np.array([[len(g[2]) for g in groups[:-1]]], np.int64)
        word_dur = np.array([[int(b / frame_ms) - int(a / frame_ms) for a, b in zip(pos[:-1], pos[1:])]], np.int64)
        feeds = {"tokens": tokens, "word_div": word_div, "word_dur": word_dur}
        if dur.cfg["use_lang_id"]:
            feeds["languages"] = np.array([[dur.lang_id(ph) for ph, _ in flat]], np.int64)
        lpath = dur.model_path("linguistic")
        lin = onnxrun.run(lpath, feeds, "dur-linguistic")
        enc = lin.get("encoder_out")
        xm = lin.get("x_masks")
        ph_midi = np.array([[int(round(g[1])) for g in groups for _ in g[2]]], np.int64)
        dpath = dur.model_path("dur")
        names = onnxrun.input_names(dpath)
        dfeeds = {"encoder_out": enc, "x_masks": xm, "ph_midi": ph_midi}
        if dur.cfg.get("dur_type") == "rel" or (not dur.cfg.get("dur_type") and "word_div" in names):
            dfeeds["word_div"] = word_div
            dfeeds["word_dur"] = word_dur
        if dur.speakers():
            dfeeds["spk_embed"] = dur.spk_embed([mix or {dur.speakers()[0]: 1.0} for _, mix in flat])
        out = onnxrun.run(dpath, dfeeds, "dur", seed=seed)
        return [float(x) for x in next(iter(out.values())).reshape(-1)]

    def _rule_frames(self, groups, pos, frame_ms):
        """no duration model: consonants get a fixed length, vowels fill the rest of their span."""
        cons = RULE_CONSONANT_MS / frame_ms
        frames = [cons]  # head SP (unused)
        for gi, g in enumerate(groups[:-1]):
            phs = g[2] if gi else g[2][1:]
            span = max(1.0, (pos[gi + 1] - pos[gi]) / frame_ms) if gi else 0
            nv = sum(1 for ph, _ in phs if self.is_vowel(ph)) or 1
            nc = len(phs) - sum(1 for ph, _ in phs if self.is_vowel(ph))
            c = min(cons, 0.4 * span / max(1, nc)) if gi else cons
            v = max(1.0, (span - c * nc) / nv)
            frames += [v if self.is_vowel(ph) else c for ph, _ in phs]
        return frames


def _stretch(source, ratio, end_pos):
    """positions (ms) of a run of durations scaled by ratio so the run ends at end_pos."""
    start = end_pos - sum(source) * ratio
    out, acc = [], start
    for d in source:
        out.append(acc)
        acc += d * ratio
    return out
