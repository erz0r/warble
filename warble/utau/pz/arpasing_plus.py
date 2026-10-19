"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Plugin.Builtin/ArpasingPlusPhonemizer.cs

arpasing+ (cadlaxa): an arpasing phonemizer on SyllableBasedPhonemizer whose focus is falling back to whatever
aliases an arpasing bank has (vowel/consonant substitution tables, cv/vc/cc/vv contextual fallbacks, dynamic
alias formats like "- CV" / "-C V" / "C_V"), plus automatic alternates picked by recording-name continuity.

the auto-alt scoring (SyncAttributes) looks at the project's notes around the group; openutau finds none when a
group isn't in a voice part (the parity harness case) and warble has no project, so it scores each group as a
whole phrase (phrase start and end), exactly as openutau does there."""

import os
import re

from ...g2p import ArpabetPlusG2p
from .api import PhonemeAttributes, phonemizer
from .syllable_based import (SyllableBasedPhonemizer, copy_attr, cs_regex_word_boundary_match, cs_replace, cs_str, distinct, find_attr,
                             last)


def _to_dict(spec):
    """"a=b,c=d".Split(',').Select(e => e.Split('=')).Where(len 2).Where(p0 != p1).ToDictionary(...)"""
    out = {}
    for entry in spec.split(","):
        parts = entry.split("=")
        if len(parts) != 2 or parts[0] == parts[1]:
            continue
        if parts[0] in out:
            raise ValueError(f"An item with the same key has already been added. Key: {parts[0]}")
        out[parts[0]] = parts[1]
    return out


def _norm_wav(path):
    """Path.GetFileNameWithoutExtension(wav).ToLower().Replace("-", "").Trim().Replace(" ", "_"), "__" collapsed."""
    norm = os.path.splitext(os.path.basename(path or ""))[0].lower().replace("-", "").strip().replace(" ", "_")
    while "__" in norm:
        norm = norm.replace("__", "_")
    return norm


class AltCandidate:
    def __init__(self, alt=0, oto=None, wav_norm="", padded_wav="", is_phonetic=False):
        self.alt = alt
        self.oto = oto
        self.wav_norm = wav_norm
        self.padded_wav = padded_wav
        self.is_phonetic = is_phonetic


def _candidate(alt, oto):
    norm = _norm_wav(oto.file if oto is not None else "")
    return AltCandidate(alt, oto, norm, f"_{norm}_", any(c.isalpha() for c in norm))


VOWELS = [
    "aa", "ax", "ae", "ah", "ao", "aw", "ay", "eh", "er", "ey", "ih", "iy", "ow", "oy", "uh", "uw", "a", "e", "i", "o", "u", "ai", "ei", "oi", "au", "ou", "ix", "ux",
    "aar", "ar", "axr", "aer", "ahr", "aor", "or", "awr", "aur", "ayr", "air", "ehr", "eyr", "eir", "ihr", "iyr", "ir", "owr", "our", "oyr", "oir", "uhr", "uwr", "ur",
    "aal", "al", "axl", "ael", "ahl", "aol", "ol", "awl", "aul", "ayl", "ail", "ehl", "el", "eyl", "eil", "ihl", "iyl", "il", "owl", "oul", "oyl", "oil", "uhl", "uwl", "ul",
    "aan", "an", "axn", "aen", "ahn", "aon", "on", "awn", "aun", "ayn", "ain", "ehn", "en", "eyn", "ein", "ihn", "iyn", "in", "own", "oun", "oyn", "oin", "uhn", "uwn", "un",
    "aang", "ang", "axng", "aeng", "ahng", "aong", "ong", "awng", "aung", "ayng", "aing", "ehng", "eng", "eyng", "eing", "ihng", "iyng", "ing", "owng", "oung", "oyng", "oing", "uhng", "uwng", "ung",
    "aam", "am", "axm", "aem", "ahm", "aom", "om", "awm", "aum", "aym", "aim", "ehm", "em", "eym", "eim", "ihm", "iym", "im", "owm", "oum", "oym", "oim", "uhm", "uwm", "um", "oh",
    "eu", "oe", "yw", "yx", "wx", "ox", "ex", "ea", "ia", "oa", "ua", "ean", "eam", "eang",
]

VC_FALLBACKS = {"aw": "uw", "ow": "uw", "uh": "uw", "ay": "iy", "ey": "iy", "oy": "iy", "aa": "ah", "ae": "ah", "ao": "ah"}
ROMAJI_EXCEPTION = ["a", "e", "i", "o", "u"]

# VV FALLBACKS, START and END
VV_VOWEL1_FALLBACKS = {
    "aa": ["ah", "ay", "aw", "ae", "ao"], "ae": ["eh", "aw", "ay", "ah", "aa"], "ah": ["aa", "aw", "ay", "ae", "ao"],
    "ao": ["aa", "ow", "ah", "ay", "ae"], "ax": ["ah", "uh", "aa"], "eh": ["ey", "ax"], "er": ["r", "ah", "ax"], "ih": ["iy", "eh"],
    "iy": ["ih"], "uh": ["uw"], "uw": ["uh"], "aw": ["ae", "aa", "ah", "ay"], "ay": ["ah", "ae", "aw", "aa"], "ey": ["eh", "ae"],
    "oy": ["ow", "ao"], "ow": ["oy", "ao"],
}
VV_VOWEL2_FALLBACKS = {
    "aa": ["ah", "ay", "aw", "ae", "ao"], "ae": ["eh", "aw", "ay", "ah", "aa"], "ah": ["aa", "aw", "ay", "ae", "ao"],
    "ao": ["aa", "ow", "ah", "ay", "ae"], "ax": ["ah", "uh", "aa"], "eh": ["ey", "ax"], "er": ["r", "ah", "ax"], "ih": ["iy", "eh"],
    "uh": ["uw"],
}
# CV FALLBACKS
CV_CONSONANT_FALLBACKS = {
    "b": ["p", "d", "v"], "ch": ["sh", "jh"], "d": ["p", "d", "v"], "dh": ["d", "v"], "dx": ["d"], "f": ["hh", "p", "th"], "g": ["k"],
    "hh": ["f"], "jh": ["ch"], "k": ["g"], "l": ["r"], "m": ["n"], "n": ["m"], "ng": ["n"], "p": ["b", "d"], "q": ["-"],
    "r": ["er", "w", "l"], "s": ["z", "f"], "sh": ["s", "zh"], "t": ["d", "k"], "th": ["s", "th"], "v": ["b", "f", "zh"],
    "w": ["uw", "uh"], "y": ["iy"], "z": ["s"], "zh": ["sh", "jh", "ch"],
}
CV_VOWEL_FALLBACKS = {
    "aa": ["ah", "ay", "aw", "ae", "ao"], "ae": ["eh", "aw", "ay", "ah", "aa"], "ah": ["aa", "aw", "ay", "ae", "ao"],
    "ao": ["aa", "ow", "ah", "ay", "ae"], "ax": ["ah", "uh", "aa"], "eh": ["ey", "ax"], "ih": ["iy", "eh"], "iy": ["ih"],
    "uh": ["uw"], "uw": ["uh"], "aw": ["ae", "aa", "ah", "ay"], "ay": ["ah", "ae", "aw", "aa"], "ey": ["eh", "ae"],
    "oy": ["ow", "ao"], "ow": ["oy", "ao"],
}
# VC FALLBACKS
VC_VOWEL_FALLBACKS = {
    "aa": ["ah", "ae", "ao"], "ae": ["eh", "ah", "aa"], "ah": ["aa", "ae", "ao"], "ao": ["aa", "ow", "ah", "ae"], "ax": ["ah", "aa", "uh"],
    "eh": ["ah", "ey"], "er": ["r", "ah", "ax"], "ih": ["iy", "eh"], "iy": ["ih"], "uh": ["uw"], "uw": ["uh"], "aw": ["uw", "uh"],
    "ay": ["iy", "ih", "y"], "ey": ["iy", "ih", "y"], "oy": ["iy", "ih", "y"], "ow": ["uw", "uh"],
}
VC_CONSONANT_FALLBACKS = {
    "b": ["p", "d"], "ch": ["t", "k", "q", "p", "g"], "d": ["p", "b", "g"], "dh": ["d", "v"], "dx": ["d", "t", "r"], "f": ["s", "th"],
    "g": ["k", "p", "b"], "hh": ["f", "th"], "jh": ["d", "b", "g"], "k": ["t", "d", "g"], "l": ["r"], "m": ["n"], "n": ["m"],
    "ng": ["n", "m"], "p": ["b", "d", "g"], "q": ["t", "-"], "r": ["l", "w"], "s": ["z", "f"], "sh": ["s", "zh"], "t": ["d", "k"],
    "th": ["s", "th"], "v": ["f", "b", "zh"], "w": ["uw", "uh"], "y": ["iy"], "z": ["s"], "zh": ["sh", "jh", "ch"],
}
# CC FALLBACKS
CC_CONSONANT1_FALLBACKS = {
    "b": ["p", "d"], "d": ["p", "b", "g"], "dh": ["d", "v"], "dx": ["d", "t", "r"], "f": ["s", "th"], "g": ["k", "p", "b"],
    "hh": ["f", "th"], "k": ["g", "d", "t"], "l": ["r"], "m": ["n"], "n": ["m"], "ng": ["n", "m"], "p": ["b", "d", "g"],
    "q": ["t", "-"], "r": ["w", "l"], "s": ["z", "f"], "sh": ["s", "zh"], "t": ["d", "k"], "th": ["s", "th"], "v": ["f", "b", "zh"],
    "w": ["uw", "uh"], "y": ["iy", "ih"], "z": ["s"], "zh": ["sh", "jh", "ch"],
}
CC_CONSONANT2_FALLBACKS = {
    "b": ["p", "d"], "ch": ["sh", "jh"], "d": ["p", "d", "v"], "dh": ["d", "v"], "dx": ["d"], "f": ["hh", "p", "th"], "g": ["k"],
    "hh": ["f"], "jh": ["ch"], "k": ["g"], "l": ["r"], "m": ["n"], "n": ["m"], "ng": ["n"], "p": ["b", "d"], "q": ["-"],
    "r": ["w", "l"], "s": ["z", "f"], "sh": ["s", "zh"], "t": ["d", "k"], "th": ["s", "th"], "v": ["b", "f", "zh"],
    "w": ["uw", "uh"], "y": ["iy"], "z": ["s"], "zh": ["jh", "ch"],
}


@phonemizer("Arpasing+ Phonemizer", "EN ARPA+", language="EN", openutau_class="OpenUtau.Plugin.Builtin.ArpasingPlusPhonemizer", author="Cadlaxa")
class ArpasingPlusPhonemizer(SyllableBasedPhonemizer):
    yaml_file_name = "arpasing.yaml"
    yaml_template = "arpasing.template.yaml"
    enable_phoneme_tokenization = True
    no_gap = True  # endings have a 50 ticks gap

    def __init__(self):
        super().__init__()
        self.vowels = list(VOWELS)
        self.consonants = "b,ch,d,dh,dr,dx,f,g,hh,jh,k,l,m,n,ng,p,q,r,s,sh,t,th,tr,v,w,y,z".split(",")
        self.diphthong_tails = {"ay": "y", "ey": "y", "oy": "y", "aw": "w", "ow": "w", "er": "r", "iy": "y"}
        # for banks with missing vowels / custom consonants
        self.missing_v_phonemes = _to_dict("ax=ah,aa=ah,ae=ah,iy=ih,uh=uw,ix=ih,ux=uh,oh=ao,eu=uh,oe=ax,uy=uw,yw=uw,yx=iy,wx=uw,ea=eh,ia=iy,oa=ao,ua=uw,R=-,N=n,mm=m,ll=l")
        self.missing_c_phonemes = _to_dict("nx=n,tx=t,dx=d,zh=sh,z=s,ng=n,cl=q,vf=q,dd=d,lx=l")
        self.vc_fall_back = False
        self.phonetic_hint = False
        self.vc_fall_backs = dict(VC_FALLBACKS)
        # AUTO ALTS
        self.unotes = []
        self.running_oto = None

    def get_vowels(self):
        return self.vowels

    def get_consonants(self):
        return self.consonants

    def get_dictionary_name(self):
        return ""

    def get_symbols(self, note):
        original = super().get_symbols(note)
        self.phonetic_hint = bool(note.phonetic_hint)
        if original is None:
            return None
        final = []
        # SPLITS UP DR AND TR
        for s in original:
            if s in ("dr",) and not self.has_oto(f"{s} {cs_str(self.vowels)}", note.tone) and not self.has_oto(f"ay {s}", note.tone):
                final.extend(["d", s[1]])
            elif s in ("tr",) and not self.has_oto(f"{s} {cs_str(self.vowels)}", note.tone) and not self.has_oto(f"ay {s}", note.tone):
                final.extend(["t", s[1]])
            else:
                final.append(s)
        return final

    def get_base_g2ps(self):
        return [ArpabetPlusG2p()]

    def set_singer(self, singer):
        super().set_singer(singer)
        if self.singer is not None:
            self.cons_exceptions.clear()
            if self.stop is not None:
                self.cons_exceptions.extend(self.stop)
            if self.tap is not None:
                self.cons_exceptions.extend(self.tap)
            self.cons_exceptions = distinct(self.cons_exceptions)

    # ---- AUTO ALTS ---------------------------------------------------------------------------------------
    def set_up(self, groups):
        super().set_up(groups)
        # the voice part's notes; none outside a project (openutau finds none either when the group isn't in a part)
        self.unotes = []

    def _unote_at(self, abs_pos):
        if not self.unotes:
            return None, None
        un = next((n for n in reversed(self.unotes) if n.position <= abs_pos), None) or self.unotes[0]
        idx = self.unotes.index(un)
        return un, (self.unotes[idx + 1] if idx + 1 < len(self.unotes) else None)

    def _get_pure_alias(self, raw_alias):
        if raw_alias is None or not raw_alias.strip() or self.singer is None:
            return raw_alias if raw_alias is not None else ""
        clean = raw_alias
        subbanks = self.singer.subbanks
        if subbanks is not None:
            suffixes = sorted(distinct([s["suffix"] for s in subbanks if s["suffix"]]), key=len, reverse=True)
            for suffix in suffixes:
                if clean.endswith(suffix):
                    clean = clean[:len(clean) - len(suffix)]
                    break
            prefixes = sorted(distinct([s["prefix"] for s in subbanks if s["prefix"]]), key=len, reverse=True)
            for prefix in prefixes:
                if clean.startswith(prefix):
                    clean = clean[len(prefix):]
                    break
        clean = re.sub(r"\s*\d+$", "", clean)
        return clean.strip()

    def _try_get_mapped_oto_any_format(self, base_alias, alt, tone, color):
        formats = [base_alias] if alt == 0 else [f"{base_alias}{alt}"]
        for fmt in formats:
            oto = self.singer.try_get_mapped_oto(fmt, tone, color)
            if oto is not None:
                return oto
        return None

    @staticmethod
    def _format_for_chunking(clean_alias):
        if not clean_alias:
            return ""
        pure = clean_alias.lower()
        pure = pure.replace("-", "").strip()
        pure = pure.replace(" ", "_")
        while "__" in pure:
            pure = pure.replace("__", "_")
        return pure

    @staticmethod
    def _merge_chunks(left, right):
        if not left:
            return right
        if not right:
            return left
        l_parts = left.split("_")
        r_parts = right.split("_")
        if l_parts and r_parts and l_parts[-1] == r_parts[0]:
            return left + "_" + "_".join(r_parts[1:])
        return left + "_" + right

    def _get_candidates(self, clean_alias, tone, color):
        out = []
        base_alias = clean_alias.lower()
        for alt in range(25):
            oto = self._try_get_mapped_oto_any_format(base_alias, alt, tone, color)
            if oto is not None:
                if not oto.file:
                    continue
                out.append(_candidate(alt, oto))
        if not out:
            default_oto = self._try_get_mapped_oto_any_format(base_alias, 0, tone, color)
            if default_oto is not None:
                out.append(AltCandidate(0, default_oto, "", "", False))
        if not out:
            out.append(AltCandidate(0, None, "", "", False))
        return out

    def _score_transition(self, curr, prev, curr_chunk, prev_chunk):
        if curr is None:
            return 0
        score = 0
        # single emission match
        if curr.padded_wav and curr_chunk:
            if f"_{curr_chunk}_" in curr.padded_wav:
                score += 30
        # direct same-wav connection
        if prev is not None and prev.oto is not None and prev.oto.file and curr.oto is not None and curr.oto.file:
            if curr.oto.file.lower() == prev.oto.file.lower():
                score += 150 if curr.is_phonetic else 250
        # multi-phoneme chunk overlaps in recording filename
        if prev_chunk and curr_chunk:
            backward = self._merge_chunks(prev_chunk, curr_chunk)
            if backward:
                if curr.padded_wav is not None and f"_{backward}_" in curr.padded_wav:
                    score += 180
                if prev is not None and prev.padded_wav is not None and f"_{backward}_" in prev.padded_wav:
                    score += 180
        # cross-chunk presence
        if prev_chunk and curr.padded_wav is not None and f"_{prev_chunk}_" in curr.padded_wav:
            score += 40
        if curr_chunk and prev is not None and prev.padded_wav is not None and f"_{curr_chunk}_" in prev.padded_wav:
            score += 40
        return score

    def sync_attributes(self, notes, phoneme_symbols, start_index, attr_list):
        if self.singer is None or len(phoneme_symbols) == 0 or notes is None or len(notes) == 0:
            return
        tone = notes[0].tone
        n = len(phoneme_symbols)

        cur_un, next_un = self._unote_at(notes[0].position)
        cur_idx = self.unotes.index(cur_un) if cur_un is not None else -1
        prev_un = self.unotes[cur_idx - 1] if cur_idx > 0 else None
        note_start = notes[0].position
        note_end = notes[-1].position + notes[-1].duration
        is_phrase_start = prev_un is None or note_start > prev_un.position + prev_un.duration + 10
        is_phrase_end = next_un is None or next_un.position > note_end + 10
        if is_phrase_start:
            self.running_oto = None

        clean_aliases = [None] * n
        chunks = [None] * n
        candidates_per = [None] * n
        for i in range(n):
            attr = find_attr(attr_list, start_index + i)
            clean_aliases[i] = self._get_pure_alias(phoneme_symbols[i])
            chunks[i] = self._format_for_chunking(clean_aliases[i])
            color = attr.voice_color if attr.voice_color is not None else ""
            shift_tone = tone + (attr.tone_shift if attr.tone_shift is not None else 0)
            if attr.alternate is not None:
                # manual selection
                manual = self._try_get_mapped_oto_any_format(clean_aliases[i].lower(), attr.alternate, shift_tone, color)
                if manual is not None:
                    candidates_per[i] = [_candidate(attr.alternate, manual)]
                else:
                    candidates_per[i] = self._get_candidates(clean_aliases[i], shift_tone, color)
            else:
                candidates_per[i] = self._get_candidates(clean_aliases[i], shift_tone, color)

        initial_prev = None
        initial_prev_chunk = ""
        if not is_phrase_start and self.running_oto is not None:
            initial_prev = _candidate(0, self.running_oto)
            initial_prev_chunk = self._format_for_chunking(self._get_pure_alias(self.running_oto.alias))

        next_candidates = None
        next_chunk = ""
        if not is_phrase_end and next_un is not None:
            from .api import Note
            next_symbols = super().get_symbols(Note(lyric=next_un.lyric, tone=next_un.tone, position=0, duration=0))
            if next_symbols is not None and len(next_symbols) > 0:
                next_first_clean = self._get_pure_alias(next_symbols[0])
                next_chunk = self._format_for_chunking(next_first_clean)
                next_candidates = self._get_candidates(next_first_clean, next_un.tone, "")

        dp = [[0] * len(candidates_per[i]) for i in range(n)]
        parent = [[0] * len(candidates_per[i]) for i in range(n)]
        for c, curr in enumerate(candidates_per[0]):
            dp[0][c] = self._score_transition(curr, initial_prev, chunks[0], initial_prev_chunk)
            parent[0][c] = -1
        for i in range(1, n):
            prev_chunk = chunks[i - 1]
            curr_chunk = chunks[i]
            for curr_idx, curr in enumerate(candidates_per[i]):
                max_score = -(2 ** 31)
                best_parent = 0
                for prev_idx, prev in enumerate(candidates_per[i - 1]):
                    total = dp[i - 1][prev_idx] + self._score_transition(curr, prev, curr_chunk, prev_chunk)
                    if total > max_score:
                        max_score = total
                        best_parent = prev_idx
                dp[i][curr_idx] = max_score
                parent[i][curr_idx] = best_parent

        if next_candidates:
            for c, curr in enumerate(candidates_per[n - 1]):
                best_next = 0
                for nc in next_candidates:
                    fwd = self._score_transition(nc, curr, next_chunk, chunks[n - 1])
                    if fwd > best_next:
                        best_next = fwd
                dp[n - 1][c] += best_next

        # backtrack optimal path
        best_end = 0
        highest = -(2 ** 31)
        for c in range(len(candidates_per[n - 1])):
            if dp[n - 1][c] > highest:
                highest = dp[n - 1][c]
                best_end = c
        optimal = [0] * n
        cur = best_end
        for i in range(n - 1, -1, -1):
            optimal[i] = cur
            cur = parent[i][cur]

        # apply selected alternates and update continuity
        for i in range(n):
            global_idx = start_index + i
            existing = next((k for k, a in enumerate(attr_list) if a.index == global_idx), -1)
            attr = copy_attr(attr_list[existing]) if existing >= 0 else PhonemeAttributes(index=global_idx)
            candidates = candidates_per[i]
            pick = optimal[i]
            if pick < 0 or pick >= len(candidates):
                pick = 0
            if candidates:
                chosen = candidates[pick]
                if attr.alternate is None and chosen.alt > 0:
                    attr.alternate = chosen.alt
                if chosen.oto is not None:
                    self.running_oto = chosen.oto
            if existing >= 0:
                attr_list[existing] = attr
            else:
                attr_list.append(attr)

        if is_phrase_end:
            self.running_oto = None

    # ---- syllables ---------------------------------------------------------------------------------------
    def process_syllable(self, syllable):
        H = self.has_oto
        V = self.validate_alias
        AF = self.alias_format
        add = self.try_add_phoneme
        tone = syllable.tone
        vtone = syllable.vowel_tone

        syllable.prev_v = "" if syllable.prev_v in self.tails else syllable.prev_v
        replaced_prev_v = self.replace_phoneme(syllable.prev_v, tone)
        prev_v = "" if not replaced_prev_v else replaced_prev_v
        cc = [self.replace_phoneme(c, tone) for c in syllable.cc]
        v = self.replace_phoneme(syllable.v, vtone)
        phonemes = []
        last_c = len(cc) - 1
        first_c = 0
        current_word_cc = [self.replace_phoneme(c, tone) for c in syllable.current_word_cc]
        previous_word_cc = [self.replace_phoneme(c, tone) for c in syllable.previous_word_cc]
        prev_word_consonants_count = syllable.prev_word_consonants_count

        # For VC Fallback phonemes
        for key in self.vc_fall_backs:
            if not H(f"{key} {cs_str(cc)}", tone) or not H(f"ao {cs_str(cc)}", tone):
                self.vc_fall_back = True

        def find_start(c0):
            for ln in range(len(c0), 0, -1):
                c = c0[:ln]  # shr -> sh -> s
                target = AF(c, "cc_start", vtone, "")
                valid = V(target, vtone)
                if H(target, vtone) or H(valid, vtone):
                    add(phonemes, tone, target, valid)
                    return True
            return False

        if syllable.is_starting_v:
            base_phoneme = AF(v, "startingV", vtone, "")
        elif syllable.is_vv:
            if not self.can_make_alias_extension(syllable):
                vv_space = f"{prev_v} {v}"
                vv_no_space = f"{prev_v}{v}"
                valid_vv_space = V(vv_space, vtone)
                valid_vv_no_space = V(vv_no_space, vtone)
                if H(vv_space, vtone):
                    base_phoneme = vv_space
                elif H(valid_vv_space, vtone):
                    base_phoneme = valid_vv_space
                elif H(vv_no_space, vtone):
                    base_phoneme = vv_no_space
                elif H(valid_vv_no_space, vtone):
                    base_phoneme = valid_vv_no_space
                elif prev_v in self.diphthong_splits or prev_v in self.diphthong_tails:
                    if prev_v in self.diphthong_splits:
                        split_override = self.diphthong_splits[prev_v]
                        vc = AF(split_override[0].replace("{v}", v), "vcEx", tone, prev_v)
                        cv = AF(split_override[1].replace("{v}", v), "dynMid", vtone, "")
                        add(phonemes, tone, vc, V(vc, tone))
                    else:
                        tail = self.diphthong_tails[prev_v]
                        vc_space = AF(f"{prev_v} {tail}", "vcEx", tone, prev_v)
                        vc_no_space = AF(f"{prev_v}{tail}", "vcEx", tone, prev_v)
                        cv = AF(f"{tail} {v}", "dynMid", vtone, "")
                        add(phonemes, tone, vc_space, V(vc_space, tone), vc_no_space, V(vc_no_space, tone))
                    valid_cv = V(cv, vtone)
                    valid_v = V(v, vtone)
                    if H(cv, vtone):
                        base_phoneme = cv
                    elif H(valid_cv, vtone):
                        base_phoneme = valid_cv
                    elif H(v, vtone):
                        base_phoneme = v
                    elif H(valid_v, vtone):
                        base_phoneme = valid_v
                    else:
                        base_phoneme = V(AF(f"- {v}", "dynMid", vtone, ""), vtone)
                        phonemes.append(V(AF(f"{prev_v} -", "dynMid", tone, ""), tone))
                else:
                    valid_v = V(v, vtone)
                    if H(v, vtone):
                        base_phoneme = v
                    elif H(valid_v, vtone):
                        base_phoneme = valid_v
                    else:
                        base_phoneme = V(AF(f"- {v}", "dynMid", vtone, ""), vtone)
                        phonemes.append(V(AF(f"{prev_v} -", "dynMid", tone, ""), tone))
            else:
                base_phoneme = None
        elif syllable.is_starting_cv_with_one_consonant:
            rcv = f"- {cc[0]} {v}"
            rcv1 = f"- {cc[0]}{v}"
            crv = f"{cc[0]} {v}"
            if H(rcv, vtone) or H(V(rcv, vtone), vtone) or (H(rcv1, vtone) or H(V(rcv1, vtone), vtone)):
                # - CV
                base_phoneme = AF(f"{cc[0]} {v}", "dynStart", vtone, "")
            elif H(crv, vtone) or H(V(crv, vtone), vtone):
                # CV
                base_phoneme = AF(f"{cc[0]} {v}", "dynMid", vtone, "")
                if not find_start(cc[0]):
                    add(phonemes, tone, AF(cc[0], "cc_start", vtone, ""), V(AF(cc[0], "cc_start", vtone, ""), vtone))
            else:
                base_phoneme = AF(f"{cc[0]} {v}", "dynMid", vtone, "")
                if not find_start(cc[0]):
                    add(phonemes, tone, AF(cc[0], "cc_start", vtone, ""), V(AF(cc[0], "cc_start", vtone, ""), vtone))
        elif syllable.is_starting_cv_with_more_than_one_consonant:
            jcc = "".join(cc)
            rccv = f"- {jcc} {v}"
            rccv1 = f"- {jcc}{v}"
            crv = f"{last(cc)} {v}"
            crv1 = f"{last(cc)}{v}"
            ccv = f"{jcc} {v}"
            ccv1 = f"{jcc}{v}"
            if H(rccv, vtone) or H(V(rccv, vtone), vtone) or H(rccv1, vtone) or H(V(rccv1, vtone), vtone):
                # - CCV
                base_phoneme = AF(f"{jcc} {v}", "dynStart", vtone, "")
                last_c = 0
            else:
                # CCV and CV
                if not self.phonetic_hint and (H(ccv, vtone) or H(V(ccv, vtone), vtone) or H(ccv1, vtone) or H(V(ccv1, vtone), vtone)):
                    base_phoneme = AF(f"{jcc} {v}", "dynMid", vtone, "")
                    last_c = 0
                elif H(crv, vtone) or H(V(crv, vtone), vtone) or H(crv1, vtone) or H(V(crv1, vtone), vtone):
                    base_phoneme = AF(f"{last(cc)} {v}", "dynMid", vtone, "")
                else:
                    base_phoneme = AF(f"{last(cc)} {v}", "dynMid", vtone, "")
                # TRY RCC [- CC]
                if not self.phonetic_hint:
                    for i in range(len(cc), 1, -1):
                        a = AF("".join(cc[:i]), "cc_start", vtone, "")
                        if add(phonemes, tone, a, V(a, vtone)):
                            first_c = i - 1
                            break
                # [- C]
                if len(phonemes) == 0:
                    add(phonemes, tone, AF(cc[0], "cc_start", vtone, ""), V(AF(cc[0], "cc_start", vtone, ""), vtone))
        else:  # VCV
            jcc = "".join(cc)
            vcv = f"{prev_v} {cc[0]}{v}"
            vcv2 = f"{prev_v}{cc[0]}{v}"
            vcv_end = f"{prev_v}{cc[0]} {v}"
            vccv = f"{prev_v} {jcc}{v}"
            vccv3 = f"{prev_v}{jcc}"
            crv = f"{last(cc)} {v}"
            cv = f"{last(cc)}{v}"
            same = self.are_tones_from_the_same_subbank(tone, vtone)
            one = syllable.is_vcv_with_one_consonant
            more = syllable.is_vcv_with_more_than_one_consonant
            if same and one and (H(vcv, vtone) and H(V(vcv), vtone)) and prev_word_consonants_count == 0 and len(current_word_cc) == 1:
                base_phoneme = vcv
            elif same and one and (H(vcv2, vtone) and H(V(vcv2), vtone)) and prev_word_consonants_count == 0 and len(current_word_cc) == 1:
                base_phoneme = vcv2
            elif same and one and prev_word_consonants_count == 1 and len(current_word_cc) == 0 and (H(vcv_end, vtone) and H(V(vcv_end), vtone)):
                base_phoneme = vcv_end
            elif same and one and (not H(vcv_end, vtone) and not H(V(vcv_end), vtone)) and (H(vcv, vtone) and H(V(vcv), vtone)):
                base_phoneme = vcv
            elif same and more and (H(vccv, vtone) and H(V(vccv), vtone)) and prev_word_consonants_count == 0:
                base_phoneme = vccv
                last_c = 0
            elif same and more and (H(vccv3, vtone) and H(V(vccv3), vtone)):
                base_phoneme = AF(f"{prev_v} {jcc}{v}", "dynMid", vtone, "")
                last_c = 0
            else:
                # CV
                if H(crv, vtone) or H(V(crv, vtone), vtone) or H(cv, vtone) or H(V(cv, vtone), vtone):
                    base_phoneme = AF(f"{last(cc)} {v}", "dynMid", vtone, "")
                else:
                    base_phoneme = AF(f"{last(cc)} {v}", "dynMid", vtone, "")
                # try [CC V] or [CCV]
                for i in range(first_c, len(cc) - 1):
                    ccv = f"{jcc} {v}"
                    ccv1 = f"{jcc}{v}"
                    if len(current_word_cc) >= 2:
                        # CCV
                        if not self.phonetic_hint and (H(ccv, vtone) or H(V(ccv), vtone) or H(ccv1, vtone) or H(V(ccv1), vtone)):
                            base_phoneme = AF(f"{jcc} {v}", "dynMid", vtone, "")
                            last_c = i
                            break
                        elif H(crv, vtone) or H(V(crv, vtone), vtone) or H(cv, vtone) or H(V(cv, vtone), vtone):
                            base_phoneme = AF(f"{last(cc)} {v}", "dynMid", vtone, "")
                        else:
                            base_phoneme = AF(f"{last(cc)} {v}", "dynMid", vtone, "")
                    elif len(current_word_cc) == 1 and len(previous_word_cc) == 1:
                        # C-Last
                        if H(crv, vtone) or H(V(crv), vtone) or H(cv, vtone) or H(V(cv), vtone):
                            base_phoneme = AF(f"{last(cc)} {v}", "dynMid", vtone, "")
                        else:
                            base_phoneme = AF(f"{last(cc)} {v}", "dynMid", vtone, "")

                # try [V C], [V CC], [VC C], [V -][- C]
                for i in range(last_c + 1, -1, -1):
                    vcc = f"{prev_v} {''.join(cc[:2])}"
                    vc = f"{prev_v} {cc[0]}"
                    vr = AF(f"{v} -", "ending", tone, "")
                    CCV = False
                    if not self.phonetic_hint and len(current_word_cc) >= 2:
                        if H(AF(f"{jcc} {v}", "dynMid", vtone, ""), vtone):
                            CCV = True
                    last_vc = False
                    for ln in range(len(cc[0]), 0, -1):
                        c = cc[0][:ln]  # shr -> sh -> s
                        vc_try = f"{prev_v} {c}"
                        has_vc = H(vc, tone) or H(V(vc, tone), tone)
                        if not has_vc and (H(vc_try, tone) or H(V(vc_try, tone), tone)):
                            add(phonemes, tone, vc_try, V(vc_try, tone))
                            last_vc = True
                            break
                    if last_vc:
                        break
                    if (H(vcc, tone) or H(V(vcc, tone), tone)) and CCV:
                        add(phonemes, tone, vcc, V(vcc, tone))
                        first_c = 1
                        break
                    elif H(vc, tone) or H(V(vc, tone), tone):
                        add(phonemes, tone, vc, V(vc, tone))
                        break
                    else:
                        continue

        i = first_c
        while i < last_c:
            ccv = f"{''.join(cc[i + 1:])} {v}"
            ccv1 = f"{''.join(cc[i + 1:])}{v}"
            cc1 = " ".join(cc[i:])
            lcv = f"{last(cc)} {v}"
            cv = f"{last(cc)}{v}"

            for ln in range(len(cc[i + 1]), 0, -1):
                c = cc[i + 1][:ln]  # shr -> sh -> s
                cc_try = f"{cc[i]} {c}"
                if H(cc_try, tone) and not (H(cc1, tone) or H(V(cc1, tone), tone)):
                    cc1 = cc_try
                    break

            if not H(cc1, tone):
                cc1 = V(cc1, tone)
            # [C1 C2]
            if not H(cc1, tone):
                cc1 = f"{cc[i]} {cc[i + 1]}"
            if not H(cc1, tone):
                cc1 = V(cc1, tone)
            # CC FALLBACKS
            if not H(cc1, tone) or (not H(V(cc1, tone), tone) and not H(f"{cc[i]} {cc[i + 1]}", tone)):
                cc1 = self._cc_fallback(cc[i], cc[i + 1], cc1, phonemes, tone, vtone)
            if not H(cc1, tone):
                cc1 = V(cc1, tone)
            # CCV
            if len(current_word_cc) >= 2:
                can_glide = True
                if not self.phonetic_hint and (H(ccv, vtone) or H(V(ccv, vtone), vtone) or H(ccv1, vtone) or H(V(ccv1, vtone), vtone)):
                    base_phoneme = AF(f"{''.join(cc[i + 1:])} {v}", "dynMid", vtone, "")
                    last_c = i
                elif H(cv, vtone) or H(V(cv, vtone), vtone) or H(lcv, vtone) or H(V(lcv, vtone), vtone) and H(cc1, vtone) and not H(ccv, vtone):
                    base_phoneme = AF(f"{last(cc)} {v}", "dynMid", vtone, "")
                # [C1 C2C3]
                if not self.phonetic_hint and H(f"{cc[i]} {''.join(cc[i + 1:])}", tone):
                    cc1 = f"{cc[i]} {''.join(cc[i + 1:])}"
                    last_c = i
                if can_glide:
                    if cc[i + 1] in self.liquid or cc[i + 1] in self.semivowel or V(cc[i + 1]) in self.liquid or V(cc[i + 1]) in self.semivowel:
                        self.glides(cc1)
            elif len(current_word_cc) == 1 and len(previous_word_cc) == 1:
                # CV
                base_phoneme = AF(f"{last(cc)} {v}", "dynMid", vtone, "")
                # [C1 C2]
                if not H(cc1, tone):
                    cc1 = f"{cc[i]} {cc[i + 1]}"

            if i + 1 < last_c:
                if not H(cc1, tone):
                    cc1 = V(cc1, tone)
                # [C1 C2]
                if not H(cc1, tone):
                    cc1 = f"{cc[i]} {cc[i + 1]}"
                if not H(cc1, tone):
                    cc1 = V(cc1, tone)
                # CC FALLBACKS
                if not H(cc1, tone) or (not H(V(cc1, tone), tone) and not H(f"{cc[i]} {cc[i + 1]}", tone)):
                    cc1 = self._cc_fallback(cc[i], cc[i + 1], cc1, phonemes, tone, vtone)
                if not H(cc1, tone):
                    cc1 = V(cc1, tone)
                # CCV
                if len(current_word_cc) >= 2:
                    can_glide = True
                    if not self.phonetic_hint and (H(ccv, vtone) or H(V(ccv, vtone), vtone) or H(ccv1, vtone) or H(V(ccv1, vtone), vtone)):
                        base_phoneme = AF(f"{''.join(cc[i + 1:])} {v}", "dynMid", vtone, "")
                        last_c = i
                    elif H(cv, vtone) or H(V(cv, vtone), vtone) or H(lcv, vtone) or H(V(lcv, vtone), vtone) and H(cc1, vtone) and not H(ccv, vtone):
                        base_phoneme = AF(f"{last(cc)} {v}", "dynMid", vtone, "")
                    # [C1 C2C3]
                    if not self.phonetic_hint and H(f"{cc[i]} {''.join(cc[i + 1:])}", tone):
                        cc1 = f"{cc[i]} {''.join(cc[i + 1:])}"
                    if can_glide:
                        if cc[i + 1] in self.liquid or cc[i + 1] in self.semivowel or V(cc[i + 1]) in self.liquid or V(cc[i + 1]) in self.semivowel:
                            self.glides(cc1)
                elif len(current_word_cc) == 1 and len(previous_word_cc) == 1:
                    # CV
                    base_phoneme = AF(f"{last(cc)} {v}", "dynMid", vtone, "")
                    # [C1 C2]
                    if not H(cc1, tone):
                        cc1 = f"{cc[i]} {cc[i + 1]}"
                        last_c = i
                if H(cc1, tone) and H(cc1, tone) and "".join(cc[i:]) not in cc1:
                    # like [V C1] [C1 C2] [C2 C3] [C3 ..]
                    phonemes.append(cc1)
                elif add(phonemes, tone, cc1, V(cc1, tone)):
                    # like [V C1] [C1 C2] [C2 ..]
                    if " ".join(cc[i + 1:]) in cc1:
                        i += 1
                else:
                    # singular cc
                    if (cc1 in previous_word_cc) == (cc1 in current_word_cc):
                        cc1 = V(cc1, tone)
                    else:
                        add(phonemes, tone, cc1, cc[i], V(cc[i], tone))
            else:
                add(phonemes, tone, cc1)
            i += 1

        phonemes.append(base_phoneme)
        return phonemes

    def _cc_fallback(self, c1, c2, cc1, phonemes, tone, vtone):
        c1_exc = c1 in self.cons_exceptions
        c2_exc = c2 in self.cons_exceptions
        if not c1_exc and not c2_exc:
            # [C1 -] [- C2]
            self.try_add_phoneme(phonemes, tone, self.validate_alias(self.alias_format(c1, "cc_endB", vtone, ""), vtone))
        elif c1_exc and not c2_exc:
            cc1 = self.alias_format(c2, "cc_inB", vtone, "")
        elif not c1_exc and c2_exc:
            cc1 = self.alias_format(c1, "cc_endB", vtone, "")
        elif c1_exc and c2_exc:
            cc1 = ""
        return cc1

    def process_ending(self, ending):
        H = self.has_oto
        V = self.validate_alias
        AF = self.alias_format
        add = self.try_add_phoneme
        tone = ending.tone
        prev_v = self.replace_phoneme(ending.prev_v, tone)
        cc = [self.replace_phoneme(c, tone) for c in ending.cc]
        v = self.replace_phoneme(ending.prev_v, tone)
        phonemes = []
        last_c = len(cc) - 1
        first_c = 0
        t = self.replace_phoneme(ending.tail, tone) if ending.has_tail else "-"

        if ending.is_ending_v:
            v_r = f"{prev_v} {t}"
            v_r2 = f"{prev_v}{t}"
            if H(v_r, tone) or H(V(v_r, tone), tone) or H(v_r2, tone) or H(V(v_r2, tone), tone):
                a = AF(prev_v, "ending", tone, "", t)
                add(phonemes, tone, a, V(a, tone))
        elif ending.is_ending_vc_with_one_consonant:
            vc = f"{prev_v} {cc[0]}"
            vcr = f"{prev_v} {cc[0]}{t}"
            vcr2 = f"{prev_v}{cc[0]} {t}"
            vcr3 = f"{prev_v} {cc[0]} {t}"
            vcr4 = f"{prev_v}{cc[0]}{t}"
            if cc[0] not in ROMAJI_EXCEPTION:
                if H(vcr, tone) or H(V(vcr, tone), tone) or (H(vcr2, tone) or H(V(vcr2, tone), tone)):
                    a = AF(f"{v} {cc[0]}", "dynEnd", tone, "", t)
                    add(phonemes, tone, a, V(a, tone))
                elif H(vcr3, tone) or H(V(vcr3, tone), tone):
                    add(phonemes, tone, vcr3, V(vcr3, tone))
                elif H(vcr4, tone) or H(V(vcr4, tone), tone):
                    add(phonemes, tone, vcr4, V(vcr4, tone))
                elif H(vc, tone) or H(V(vc, tone), tone):
                    add(phonemes, tone, vc, V(vc, tone))
                    if cc[0] in vc:
                        a = AF(cc[0], "ending", tone, "", t)
                        add(phonemes, tone, a, V(a, tone))
                else:
                    for ln in range(len(cc[0]), 0, -1):
                        c = cc[0][:ln]  # shr -> sh -> s
                        vc_try = f"{prev_v} {c}"
                        if H(vc_try, tone) or H(V(vc_try, tone), tone):
                            add(phonemes, tone, vc_try, V(vc_try, tone))
                            break
                    if cc[0] in vc:
                        a = AF(cc[0], "ending", tone, "", t)
                        add(phonemes, tone, a, V(a, tone))
        else:
            for i in range(last_c, -1, -1):
                vr = f"{v} {t}"
                vr1 = f"{v} R"
                vr2 = f"{v}{t}"
                vcc = f"{v} {''.join(cc[:2])}{t}"
                vcc2 = f"{v}{' '.join(cc[:2])} {t}"
                vcc3 = f"{v}{' '.join(cc[:2])}"
                vcc4 = f"{v} {''.join(cc[:2])}"
                vc = f"{v} {cc[0]}"
                if cc[0] not in ROMAJI_EXCEPTION:
                    if i == 0:
                        if H(vr, tone) or H(V(vr, tone), tone) or H(vr2, tone) or H(V(vr2, tone), tone) or H(vr1, tone) or H(V(vr1, tone), tone) and not H(vc, tone):
                            a = AF(v, "ending", tone, "", t)
                            add(phonemes, tone, a, V(a, tone))
                        break
                    elif H(vcc, tone) or H(V(vcc, tone), tone) and last_c == 1:
                        add(phonemes, tone, vcc, V(vcc, tone))
                        first_c = 1
                        break
                    elif H(vcc2, tone) or H(V(vcc2, tone), tone) and last_c == 1:
                        add(phonemes, tone, vcc2, V(vcc2, tone))
                        first_c = 1
                        break
                    elif not self.phonetic_hint and (H(vcc3, tone) or H(V(vcc3, tone), tone)):
                        add(phonemes, tone, vcc3, V(vcc3, tone))
                        if vcc3.endswith(last(cc)) and last_c == 1:
                            if last(cc) in self.consonants:
                                a = AF(last(cc), "ending", tone, "", t)
                                add(phonemes, tone, a, V(a, tone))
                        first_c = 1
                        break
                    elif not self.phonetic_hint and (H(vcc4, tone) or H(V(vcc4, tone), tone)):
                        add(phonemes, tone, vcc4, V(vcc4, tone))
                        if vcc4.endswith(last(cc)) and last_c == 1:
                            if last(cc) in self.consonants:
                                a = AF(last(cc), "ending", tone, "", t)
                                add(phonemes, tone, a, V(a, tone))
                        first_c = 1
                        break
                    elif (H(vcc, tone) and not H(V(vcc, tone), tone)
                          or not H(vcc2, tone) and H(V(vcc2, tone), tone)
                          or not H(vcc3, tone) and H(V(vcc3, tone), tone)
                          or not H(vcc4, tone) and H(V(vcc4, tone), tone)):
                        add(phonemes, tone, vc, V(vc, tone))
                        break
                    else:
                        for ln in range(len(cc[0]), 0, -1):
                            c = cc[0][:ln]  # shr -> sh -> s
                            vc_try = f"{prev_v} {c}"
                            if H(vc_try, tone) or H(V(vc_try, tone), tone):
                                add(phonemes, tone, vc_try, V(vc_try, tone))
                                break
                        break

            i = first_c
            while i < last_c:
                remaining = len(cc) - i
                matched_cluster = False
                # ([ccc-], [c cc-], [cc c-], [cc-], [c c-])
                if not self.phonetic_hint and remaining >= 2:
                    for cluster_length in range(min(3, remaining), 1, -1):
                        if i + cluster_length == len(cc):
                            cluster = cc[i:i + cluster_length]
                            patterns = ["".join(cluster)]
                            if cluster_length == 3:
                                patterns.append(f"{cluster[0]} {cluster[1]}{cluster[2]}")
                                patterns.append(f"{cluster[0]}{cluster[1]} {cluster[2]}")
                                patterns.append(f"{cluster[0]} {cluster[1]} {cluster[2]}")
                            elif cluster_length == 2:
                                patterns.append(f"{cluster[0]} {cluster[1]}")
                            hyphens = [f"{t}", f" {t}"]
                            for cons_pattern in patterns:
                                for hyphen in hyphens:
                                    candidate = f"{cons_pattern}{hyphen}"
                                    if add(phonemes, tone, candidate, V(candidate, tone)):
                                        matched_cluster = True
                                        i += cluster_length - 1
                                        break
                                if matched_cluster:
                                    break
                            if matched_cluster:
                                break
                if matched_cluster:
                    i += 1
                    continue

                # [c1 c2]
                cc1 = f"{cc[i]} {cc[i + 1]}"
                for ln in range(len(cc[i + 1]), 0, -1):
                    c = cc[i + 1][:ln]
                    cc_try = f"{cc[i]} {c}"
                    if H(cc_try, tone) and not (H(cc1, tone) or H(V(cc1, tone), tone)):
                        cc1 = cc_try
                        break
                pair = f"{cc[i]} {cc[i + 1]}"
                has_cc1 = H(cc1, tone) or H(V(cc1, tone), tone) or H(pair, tone) or H(V(pair, tone), tone)
                if i < len(cc) - 2:
                    if has_cc1:
                        add(phonemes, tone, cc1, V(cc1, tone), pair, V(pair, tone))
                    else:
                        # no [c c] available -> c1 fallback
                        add(phonemes, tone, V(AF(cc[i], "cc_endB", tone, ""), tone), AF(cc[i], "cc_endB", tone, ""), f"{cc[i]} {t}", cc[i])
                else:
                    # final consonant pair
                    if has_cc1:
                        add(phonemes, tone, cc1, V(cc1, tone), pair, V(pair, tone))
                        # resolve final tail closure for c2
                        add(phonemes, tone, V(AF(cc[i + 1], "ending", tone, "", t), tone), AF(cc[i + 1], "ending", tone, "", t),
                            f"{cc[i + 1]} {t}", V(f"{cc[i + 1]} {t}", tone), cc[i + 1])
                    else:
                        add(phonemes, tone, V(AF(cc[i], "cc_endB", tone, ""), tone), AF(cc[i], "cc_endB", tone, ""), f"{cc[i]} {t}", cc[i])
                        add(phonemes, tone, V(AF(cc[i + 1], "ending", tone, "", t), tone), AF(cc[i + 1], "ending", tone, "", t),
                            f"{cc[i + 1]} {t}", V(f"{cc[i + 1]} {t}", tone), cc[i + 1])
                i += 1
        return phonemes

    def alias_format(self, alias, type_, tone, prev_v, t="-"):
        H = self.has_oto
        V = self.validate_alias
        alias_formats = {
            "dynStart": [""],
            "dynMid": [""],
            "dynMid_vv": [""],
            "dynEnd": [""],
            "startingV": ["-", "- ", "_", ""],
            "vcEx": [f"{prev_v} ", f"{prev_v}"],
            "vvExtend": ["", "_", "-", "- "],
            "cv": ["-", "", "- ", "_"],
            "cvStart": ["-", "- ", "_"],
            "ending": [f" {t}", f"{t}"],
            "ending_mix": [f"{t}", f" {t}", "--"],
            "cc": ["", "-", "- ", "_"],
            "cc_start": ["- ", "-", "_"],
            "cc_end": [f" {t}", f"{t}", ""],
            "cc_inB": ["_", "-", "- "],
            "cc_endB": ["_", f"{t}", f" {t}"],
            "cc_mix": [f" {t}", " R", f"{t}", "", "_", f"{t} ", f"{t}"],
            "cc1_mix": ["", " -", "-", " R", "_", "- ", "-"],
        }
        if type_ not in alias_formats and "dynamic" not in type_:
            return alias

        if "dynStart" in type_:
            consonant, vowel = self._split_cv(alias)
            for variation in [f"- {consonant}{vowel}", f"- {consonant} {vowel}", f"-{consonant} {vowel}", f"-{consonant}{vowel}",
                              f"-{consonant}_{vowel}", f"- {consonant}_{vowel}"]:
                if H(variation, tone):
                    return variation
                elif H(V(variation, tone), tone):
                    return V(variation, tone)

        if "dynMid" in type_:
            consonant, vowel = self._split_cv(alias)
            for variation in [f"{consonant}{vowel}", f"{consonant} {vowel}", f"{consonant}_{vowel}"]:
                if H(variation, tone):
                    return variation
                elif H(V(variation, tone), tone):
                    return V(variation, tone)

        if "dynEnd" in type_:
            if " " in alias:
                parts = alias.split(" ")
                consonant, vowel = parts[1], parts[0]
            else:
                consonant, vowel = alias, ""
            for variation in [f"{vowel}{consonant} -", f"{vowel} {consonant}-", f"{vowel}{consonant}-", f"{vowel} {consonant} -"]:
                if H(variation, tone):
                    return variation
                elif H(V(variation, tone), tone):
                    return V(variation, tone)

        formats_to_try = alias_formats[type_]
        counter = 0
        for fmt in formats_to_try:
            if "mix" in type_ and counter < 4:
                alias_format = f"{alias}{fmt}" if counter % 2 == 0 else f"{fmt}{alias}"
                counter += 1
            elif "end" in type_ or ("End" in type_ and "dynEnd" not in type_):
                alias_format = f"{alias}{fmt}"
            else:
                alias_format = f"{fmt}{alias}"
            if H(alias_format, tone):
                return alias_format
            elif H(V(alias_format, tone), tone):
                return V(alias_format, tone)
        return alias

    @staticmethod
    def _split_cv(alias):
        if " " in alias:
            parts = alias.split(" ")
            return parts[0], parts[1]
        return alias, ""

    def get_hardcoded_fallback(self, alias, tone, suppressed_tokens):
        # vowel-only global fallbacks (skipping suppressed tokens)
        v_alias = alias
        if self.missing_v_phonemes is not None:
            for key, value in sorted(self.missing_v_phonemes.items(), key=lambda kv: len(kv[0]), reverse=True):
                if key in suppressed_tokens:
                    continue
                v_alias = cs_replace(v_alias, key, value)
        if v_alias != alias and self.has_oto(v_alias, tone):
            return v_alias
        # consonant-only global fallbacks
        c_alias = alias
        if self.missing_c_phonemes is not None:
            for key, value in sorted(self.missing_c_phonemes.items(), key=lambda kv: len(kv[0]), reverse=True):
                if key in suppressed_tokens:
                    continue
                c_alias = cs_replace(c_alias, key, value)
        if c_alias != alias and self.has_oto(c_alias, tone):
            return c_alias
        # contextual array fallbacks
        contextual = self._apply_contextual_fallbacks(alias, tone, suppressed_tokens)
        if contextual != alias:
            return contextual
        return None

    def _apply_contextual_fallbacks(self, alias, tone, suppressed_tokens=None):
        p1 = p2 = None
        has_space = " " in alias
        if has_space:
            parts = alias.split(" ")
            if len(parts) == 2:
                p1, p2 = parts[0], parts[1]
        else:
            all_phonemes = sorted(list(self.vowels) + list(self.consonants) + ["-", "R"], key=len, reverse=True)
            for ph1 in all_phonemes:
                if alias.startswith(ph1):
                    remainder = alias[len(ph1):]
                    if remainder in self.vowels or remainder in self.consonants or remainder == "-" or remainder == "R":
                        p1, p2 = ph1, remainder
                        break
        if p1 is None or p2 is None:
            return alias

        suppress_p1 = suppressed_tokens is not None and p1 in suppressed_tokens
        suppress_p2 = suppressed_tokens is not None and p2 in suppressed_tokens
        if suppress_p1 and suppress_p2:
            return alias

        def ph_type(ph):
            if ph in self.tails:
                return 0
            if ph in self.vowels:
                return 1
            if ph in self.consonants:
                return 2
            return -1

        type1, type2 = ph_type(p1), ph_type(p2)
        dict1, dict2 = {}, {}
        if type1 == 2 and type2 == 1:  # CV
            dict1, dict2 = CV_CONSONANT_FALLBACKS, CV_VOWEL_FALLBACKS
        elif type1 == 1 and type2 == 2:  # VC
            dict1, dict2 = VC_VOWEL_FALLBACKS, VC_CONSONANT_FALLBACKS
        elif type1 == 2 and type2 == 2:  # CC
            dict1, dict2 = CC_CONSONANT1_FALLBACKS, CC_CONSONANT2_FALLBACKS
        elif type1 == 1 and type2 == 1:  # VV
            dict1, dict2 = VV_VOWEL2_FALLBACKS, VV_VOWEL1_FALLBACKS
        elif type1 == 0 and type2 == 1:  # starting vowel (- V)
            dict2 = CV_VOWEL_FALLBACKS
        elif type1 == 1 and type2 == 0:  # ending vowel (V -)
            dict1 = VC_VOWEL_FALLBACKS
        elif type1 == 0 and type2 == 2:  # starting consonant (- C)
            dict2 = CV_CONSONANT_FALLBACKS
        elif type1 == 2 and type2 == 0:  # ending consonant (C -)
            dict1 = VC_CONSONANT_FALLBACKS
        found = self._find_valid_combination(p1, p2, dict1, dict2, tone, has_space)
        return found if found is not None else alias

    def _find_valid_combination(self, part1, part2, dict1, dict2, tone, has_space):
        p1_options = [part1] + list(dict1.get(part1, []))
        p2_options = [part2] + list(dict2.get(part2, []))
        if len(p1_options) > 1:
            for opt1 in p1_options[1:]:
                try_alias = f"{opt1} {part2}" if has_space else f"{opt1}{part2}"
                if self.has_oto(try_alias, tone):
                    return try_alias
        if len(p2_options) > 1:
            for opt2 in p2_options[1:]:
                try_alias = f"{part1} {opt2}" if has_space else f"{part1}{opt2}"
                if self.has_oto(try_alias, tone):
                    return try_alias
        if len(p1_options) > 1 and len(p2_options) > 1:
            for opt1 in p1_options[1:]:
                for opt2 in p2_options[1:]:
                    try_alias = f"{opt1} {opt2}" if has_space else f"{opt1}{opt2}"
                    if self.has_oto(try_alias, tone):
                        return try_alias
        return None

    def get_transition_basic_length_ms_with_attr(self, alias, tone, attr):
        oto_length = self.get_transition_basic_length_ms_by_oto(alias, tone, attr)
        for symbol, value in sorted(self.phoneme_overrides.items(), key=lambda kv: len(kv[0]), reverse=True):
            if cs_regex_word_boundary_match(alias, symbol):
                return self.get_transition_basic_length_ms_by_constant() * value
        return oto_length
