"""diffsinger phonemizer: lyrics -> phonemes -> timed phones.

ported from openutau (MIT, Copyright (c) 2014 StAkira):
OpenUtau.Core/DiffSinger/DiffSingerBasePhonemizer.cs, MachineLearningPhonemizer.cs.

the language-specific parts (which dictionary, the g2p behind it, lyric romanization, korean SetUp, the
english+ Process rewrites) come from a language phonemizer in g2p_phonemizers.py, picked from the
explicit phonemizer name, else the track language (and the bank's character.yaml default_phonemizer when
it names a class for that language), else openutau's generic DiffSingerPhonemizer.

lookup priority, as openutau: explicit [phonetic hint], then the g2p (the bank's dsdict, then the
language's builtin g2p remapped onto the bank's symbols; lyric, then lowercase), then the lyric read as
space-separated phonemes (with and without the language prefix). when that leaves a word unknown, warble
also tries its language front-ends (japanese kana spellings and romaji splits, see warble/lang) before
giving up. unlike openutau, unknown symbols are never dropped silently: they are reported with the
closest valid symbols.
"""

import difflib
import re

import numpy as np

from .. import lang as langs
from .. import onnxrun
from ..errors import WarbleError
from ..g2p._cs import to_lower_invariant
from . import g2p_phonemizers as gp
from . import voices
from .util import durations_ms_to_frames  # noqa: F401 - re-exported for tests

LEAD_PADDING_MS = 500.0
RULE_CONSONANT_MS = 70.0
_WS = re.compile(r"[\s]")


def choose(lang=None, phonemizer=None, default_phonemizer=None, dict_dir=None):
    """the language phonemizer class (and constructor args) for a track: an explicit openutau class name wins,
    then the bank's default_phonemizer when it names a diffsinger class for this language (or there is no
    language), then the language's class, then the generic DiffSingerPhonemizer (with the language code as a
    warble extension). -> (instance, how)"""
    if phonemizer:
        cls = gp.by_class(phonemizer)
        if cls is not None:
            return _make(cls, lang), f"phonemizer {phonemizer}"
        if "diffs" in str(phonemizer).lower():
            raise WarbleError("phonemizer_unknown", f"no diffsinger phonemizer named '{phonemizer}'",
                              hint=f"known: {[c.openutau_class.rsplit('.', 1)[-1] for c in gp.CLASSES]}")
    lkey = gp.norm_lang(lang)
    dcls = gp.BY_OPENUTAU_CLASS.get(default_phonemizer or "")
    if dcls is not None and (not lkey or dcls in gp.BY_LANG.get(lkey, [])):
        return _make(dcls, lang), f"character.yaml default_phonemizer {default_phonemizer}"
    cls = gp.for_lang(lkey, dict_dir)
    if cls is not None:
        return cls(), f"lang {lkey}"
    return gp.DiffSingerPhonemizer(lkey or None), ("generic" + (f" (lang {lkey})" if lkey else ""))


def _make(cls, lang):
    if cls is gp.DiffSingerPhonemizer:
        return cls(gp.norm_lang(lang) or None)
    return cls()


def _ms_to_tick(tm, ms):
    """TimeAxis.MsPosToTickPos: rounded half to even."""
    return int(round(tm.ms_to_tick(ms)))


class Phonemizer:
    def __init__(self, bank, models, lang=None, phonemizer=None, frontend_fallbacks=True):
        self.bank = bank
        self.models = models
        self.lang = lang or ""
        self.frontend_fallbacks = frontend_fallbacks
        self.dur = models.get("dsdur")
        # symbol types come from the duration model's folder when there is one
        src = self.dur or models.get("acoustic")
        self.tokens = src.tokens
        default = (getattr(bank, "character", None) or {}).get("default_phonemizer")
        self.lp, self.chosen_by = choose(lang, phonemizer, default, src.dir)
        self.g2p = None
        dirs = [src.dir] + ([models.get("acoustic").dir] if src is not models.get("acoustic") else [])
        for d in dirs:
            try:
                self.g2p = self.lp.load_g2p(d, bool(src.cfg["use_lang_id"]), self.tokens)
                break
            except FileNotFoundError:
                continue
        if self.g2p is None:
            raise WarbleError(
                "dictionary_missing",
                f"{bank.name} has no {self.lp.get_dictionary_name()} or dsdict.yaml in {src.dir}",
                hint="give lyrics as explicit phonemes in [brackets], or add a dictionary",
            )
        self.dict_path = getattr(self.lp, "dictionary_path", None)
        self.lang_code = self.lp.get_lang_code()
        cfg = (self.dur or models.get("acoustic")).cfg
        # DsConfig.frameMs() is a float
        self.frame_ms_f = float(np.float32(np.float32(1000.0 * cfg["hop_size"]) / np.float32(cfg["sample_rate"])))
        self._phrase_out = {}

    @property
    def phonemizer_class(self):
        return self.lp.openutau_class

    def describe(self):
        return {"class": self.lp.openutau_class, "name": self.lp.name, "chosen_by": self.chosen_by, "dictionary": self.dict_path,
                "lang_code": self.lang_code}

    # ---- symbols ---------------------------------------------------------------------

    def _valid(self, ph):
        """ValidatePhoneme: a known symbol that the model can tokenize, else try '<lang>/<ph>'."""
        if self.g2p.is_valid_symbol(ph) and ph in self.tokens:
            return ph
        if self.lang_code:
            pref = f"{self.lang_code}/{ph}"
            if self.g2p.is_valid_symbol(pref) and pref in self.tokens:
                return pref
        return None

    def _dict_symbols(self):
        out = set()
        for d in self.g2p.dictionaries:
            if hasattr(d, "symbols"):
                out |= set(d.symbols())
        return out

    def closest(self, ph, n=6):
        pool = [s for s in self._dict_symbols() if s in self.tokens]
        if self.lang_code:
            pool += [s.split("/", 1)[1] for s in pool if s.startswith(self.lang_code + "/")]
        return difflib.get_close_matches(ph, sorted(set(pool)), n=n, cutoff=0.4)

    def _query(self, lyric):
        """g2p.Query(lyric) ?? g2p.Query(lyric.ToLowerInvariant()), remembering which g2p answered."""
        for q in (lyric, to_lower_invariant(lyric)):
            for i, d in enumerate(self.g2p.dictionaries):
                r = d.query(q)
                if r is not None:
                    return r, ("dict" if i == 0 else "g2p") + f":{q}"
        return None, None

    def get_symbols(self, note):
        """GetSymbols -> (symbols, rejected, source)."""
        if note.phonetic_hint:
            raw = _WS.split(note.phonetic_hint)
            ok = [self._valid(s) for s in raw]
            return [s for s in ok if s], [r for r, s in zip(raw, ok) if not s], "hint"
        res, source = self._query(note.lyric)
        if res is not None:
            return res, [], source
        raw = _WS.split(note.lyric)
        ok = [self._valid(s) for s in raw]
        good = [s for s in ok if s]
        return good, [r for r, s in zip(raw, ok) if not s], ("as-phonemes" if good else "unknown")

    def _frontend(self, lyric):
        """warble's language front-ends, tried only when openutau's lookup leaves the word unknown."""
        d = self.g2p.dictionaries[0]
        for cand in langs.candidates(self.lang, lyric):
            r = d.query(cand)
            if r and all(p in self.tokens for p in r):
                return r, f"frontend-dict:{cand}"
        for guess in langs.phoneme_guesses(self.lang, lyric):
            ok = [self._valid(s) for s in guess]
            if ok and all(ok):
                return ok, "frontend-romaji"
        return None, None

    def symbols_for(self, note):
        """(symbols, rejected, source) of a score note, through romanization like a one-note part."""
        pn = gp.PartNote(note.lyric, note.hint, int(round(note.tone)), note.position, note.duration, note)
        g = [[pn]]
        rom = self.lp.romanize([pn.lyric])
        gp.change_lyric(g[0], rom[0])
        return self.get_symbols(g[0][0])

    def is_vowel(self, ph):
        return self.g2p.is_vowel(ph)

    def is_glide(self, ph):
        return self.g2p.is_glide(ph)

    # ---- words -----------------------------------------------------------------------

    def process_word(self, notes, symbols, mix):
        """ProcessWord: distribute a word's phonemes across its notes. returns a list of
        [tick position, tone, [(phoneme, mix)]]; the first entry (position None) holds the leading
        consonants that belong before the word's first vowel."""
        for s in symbols:
            if not self.g2p.is_valid_symbol(s):
                raise WarbleError("symbol_type_missing",
                                  f'Type definition of symbol "{s}" not found. Consider adding it to dsdict.yaml (or dsdict-<lang>.yaml) of the phonemizer.',
                                  file=self.dict_path)
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
                out.append([non_ext[ni].position, non_ext[ni].tone, []])
                ni += 1
            out[-1][2].append((s, mix))
        return out

    # ---- parts (openutau's SetUp + Process) ------------------------------------------

    def _part_groups(self, groups):
        return [[gp.PartNote(n.lyric, n.hint, int(round(n.tone)), n.position, n.duration, n) for n in g] for g in groups]

    def process_groups(self, groups, tm, voice_of=None, seed=None):
        """run like openutau's PhonemizerRunner over a whole part: SetUp on every group, then Process per group
        (reverse order, prev / next and touching neighbours). groups: score note groups. returns one entry per
        group: {"lyric": romanized lyric, "phonemes": [(phoneme, tick offset from the group's first note)],
        "error": message or None}."""
        voice_of = voice_of or (lambda n: None)
        pg = self._part_groups(groups)
        self._phrase_out = {}
        self.lp.set_up(pg, lambda phrase: self._process_part(phrase, tm, voice_of, seed))
        out = [None] * len(pg)
        for i in range(len(pg) - 1, -1, -1):
            prev = nxt = prev_nb = next_nb = None
            prevs = []
            if i > 0:
                prev = pg[i - 1][0]
                pl = pg[i - 1][-1]
                if pl.position + pl.duration >= pg[i][0].position:
                    prev_nb, prevs = prev, pg[i - 1]
            if i < len(pg) - 1:
                nxt = pg[i + 1][0]
                tl = pg[i][-1]
                if tl.position + tl.duration >= nxt.position:
                    next_nb = nxt
            try:
                r = self.lp.process(pg[i], prev, nxt, prev_nb, next_nb, prevs)
                out[i] = {"lyric": pg[i][0].lyric, "phonemes": [(p[0], p[1]) for p in r], "error": None}
            except gp.PhonemizerError as e:
                msg = str(e)
                if msg == "Phonemizer failed to process." and e.__cause__ is not None:
                    msg = str(e.__cause__)
                out[i] = {"lyric": pg[i][0].lyric, "phonemes": [("error", 0)], "error": msg}
        self.lp.clean_up()
        return out

    def phonemize_phrase(self, words, tm, voice_of, seed=None, context=None):
        """words: note groups of one phrase (no rests inside). context: every note group of the track, in order
        (romanization and neighbours look across the whole part like openutau; defaults to words). voice_of(note)
        -> voice spec. returns {"phones": [...], "words": [...], "unknown": [...], "durations": "model"|"rule"}."""
        ctx = list(context) if context else list(words)
        first = words[0][0].position
        if not any(g[0].position == first for g in ctx):
            ctx = list(words)
        pg = self._part_groups(ctx)
        index = {g[0].position: i for i, g in enumerate(pg)}
        self._phrase_out = {}

        def only_this(phrase):
            if phrase[0][0].position == first:
                self._process_part(phrase, tm, voice_of, seed)

        self.lp.set_up(pg, only_this)
        err = self.lp.last_process_part_exception
        out = self._phrase_out.get(first)
        if out is None:
            if isinstance(err, WarbleError):
                raise err
            raise WarbleError("phonemizer_failed", f"{self.lp.name}: {err or 'phrase not processed'}")
        # Process per word, with neighbours from the whole part
        unknown = out["unknown"]
        reported = {u["position"] for u in unknown}
        phones = []
        for wi, w in enumerate(words):
            i = index[w[0].position]
            g = pg[i]
            prev = nxt = prev_nb = next_nb = None
            prevs = []
            if i > 0:
                prev = pg[i - 1][0]
                pl = pg[i - 1][-1]
                if pl.position + pl.duration >= g[0].position:
                    prev_nb, prevs = prev, pg[i - 1]
            if i < len(pg) - 1:
                nxt = pg[i + 1][0]
                if g[-1].position + g[-1].duration >= nxt.position:
                    next_nb = nxt
            raw = out["raw"][wi]
            winfo = out["words"][wi]
            try:
                res = self.lp.process(g, prev, nxt, prev_nb, next_nb, prevs)
                winfo["result"] = [[p[0], p[1]] for p in res]
            except gp.PhonemizerError as e:
                res = None
                winfo["error"] = str(e)
                if w[0].position not in reported:
                    unknown.append(self._unknown_entry(w[0], winfo, [w[0].lyric]))
                    reported.add(w[0].position)
            if res is None or w[0].position in reported or not winfo["found"]:
                phones.extend(dict(p, word=wi) for p in raw)  # what was aligned (SP for a word nobody could read)
                continue
            note_ms = tm.tick_to_ms(w[0].position)
            mix = raw[0]["mix"] if raw else voices.resolve(self.bank, voice_of(w[0]), w[0].tone)
            for sym, tick, ms in res:
                phones.append({"phoneme": sym, "position_ms": float(note_ms if ms is None else ms), "mix": mix,
                               "tick": w[0].position + tick, "word": wi})
        end_ms = out["end_ms"]
        phones = self._finish(phones, words, tm, end_ms, out)
        return {"phones": phones, "words": out["words"], "unknown": unknown, "durations": out["durations"],
                "frame_ms": out["frame_ms"], "start_ms": out["start_ms"], "end_ms": end_ms, "phonemizer": self.describe()}

    def _finish(self, phones, words, tm, end_ms, out):
        for k, ph in enumerate(phones):
            nxt = phones[k + 1]["position_ms"] if k + 1 < len(phones) else end_ms
            ph["duration_ms"] = max(0.0, nxt - ph["position_ms"])
            ph["vowel"] = bool(self.is_vowel(ph["phoneme"])) and ph["phoneme"] not in ("SP", "AP")
        # tone per phone: the note sounding at the phone's start (leading consonants take the next note)
        notes = [n for w in words for n in w]
        for ph in phones:
            t = ph["position_ms"]
            tone = notes[0].tone
            for n in notes:
                if tm.tick_to_ms(n.position) <= t + 1e-6:
                    tone = n.tone
            ph["tone"] = tone
        return phones

    def _unknown_entry(self, head, winfo, rejected):
        src = head.src if isinstance(head, gp.PartNote) else head
        e = {"lyric": src.lyric, "position": src.position, "line": getattr(src, "line", None), "rejected": rejected,
             "closest": {r: self.closest(r) for r in rejected}}
        if winfo.get("lyric") not in (None, src.lyric):
            e["romanized"] = winfo["lyric"]
        if winfo.get("error"):
            e["error"] = winfo["error"]
        return e

    def _process_part(self, phrase, tm, voice_of, seed):
        """ProcessPart: run the duration model on one phrase (list of PartNote groups) and align. fills the
        language phonemizer's part_result / unrecognized_lyrics like openutau, and keeps warble's own view of the
        phrase (phones with ms positions and mixes, per-word info, unknown words) for rendering."""
        lp = self.lp
        frame_ms = self.frame_ms_f
        head0 = phrase[0][0]
        groups = [[None, head0.tone, [("SP", voices.resolve(self.bank, voice_of(head0.src), head0.tone))]]]
        note_ph_index = [1]
        found = []
        unknown = []
        word_info = []
        for w in phrase:
            head = w[0]
            raw_syms, rejected, source = self.get_symbols(head)
            syms = [s for s in raw_syms if s in self.tokens]
            rejected = rejected + [s for s in raw_syms if s not in self.tokens]
            if (rejected or not syms) and self.frontend_fallbacks and source != "hint":
                fb, fsrc = self._frontend(head.src.lyric if head.src is not None else head.lyric)
                if fb:
                    syms, rejected, source = list(fb), [], fsrc
            if rejected:
                lp.unrecognized_lyrics[head.position] = " ".join(rejected)
            elif not syms:
                lp.unrecognized_lyrics[head.position] = head.lyric or ""
            mix = voices.resolve(self.bank, voice_of(head.src), head.tone)
            info = {"lyric": head.lyric, "symbols": list(syms), "source": source}
            if rejected or not syms:
                unknown.append(self._unknown_entry(head, info, rejected or [head.lyric]))
            if not syms:
                syms = ["SP"]
                found.append(False)
            else:
                found.append(True)
            wp = self.process_word(w, syms, mix)
            groups[-1][2].extend(wp[0][2])
            groups.extend(wp[1:])
            note_ph_index.append(note_ph_index[-1] + sum(len(g[2]) for g in wp))
            word_info.append(info)
        last = phrase[-1][-1]
        end_tick = last.position + last.duration
        end_ms = tm.tick_to_ms(end_tick)
        groups.append([end_tick, last.tone, []])
        # phrasePhonemes[0].Position = MsPosToTickPos(TickPosToMsPos(phrasePhonemes[1].Position) - padding)
        groups[0][0] = _ms_to_tick(tm, tm.tick_to_ms(groups[1][0]) - LEAD_PADDING_MS)
        pos = [tm.tick_to_ms(g[0]) for g in groups]

        flat = [(ph, mix) for g in groups for ph, mix in g[2]]
        if self.dur is not None:
            frames = self._predict(groups, flat, pos, seed)
            how = "model"
        else:
            frames = self._rule_frames(groups, pos, frame_ms)
            how = "rule"

        # user timing overrides before alignment: cons scales a word's consonants, phdur sets
        # explicit lengths in ms (0 keeps the prediction)
        frames = list(frames)
        for wi, w in enumerate(phrase):
            c = w[0].src.controls if w[0].src is not None and hasattr(w[0].src, "controls") else {}
            lo, hi = note_ph_index[wi], note_ph_index[wi + 1]
            if c.get("cons") not in (None, ""):
                m = float(c["cons"])
                for k in range(lo, hi):
                    if not self.is_vowel(flat[k][0]):
                        frames[k] *= m
            if c.get("phdur"):
                vals = [float(v) for v in str(c["phdur"]).replace(";", ",").split(",") if v.strip() != ""]
                for k, ms in zip(range(lo, hi), vals):
                    if ms > 0:
                        frames[k] = ms / frame_ms

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

        # part result per word (ticks from the note), and warble's phones
        raw = []
        for wi, w in enumerate(phrase):
            head = w[0]
            note_ms = tm.tick_to_ms(head.position)
            entries = []
            ph_list = []
            for k in range(note_ph_index[wi], note_ph_index[wi + 1]):
                sym, mix = flat[k]
                ms = float(positions[k - 1])
                tick = _ms_to_tick(tm, ms) - _ms_to_tick(tm, note_ms)
                ph_list.append({"phoneme": sym, "position_ms": ms, "mix": mix, "tick": head.position + tick})
                if sym:
                    entries.append((sym, tick, ms))
            raw.append(ph_list)
            word_info[wi]["found"] = found[wi]
            if not found[wi]:
                lp.part_result[head.position] = []
                continue
            if head.lyric.startswith("+"):
                continue
            lp.part_result[head.position] = entries
        self._phrase_out[head0.position] = {
            "raw": raw, "words": word_info, "unknown": unknown, "durations": how, "frame_ms": frame_ms,
            "start_ms": pos[1], "end_ms": end_ms,
        }

    def _predict(self, groups, flat, pos, seed):
        dur = self.dur
        frame_ms = self.frame_ms_f
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

