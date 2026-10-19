"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Plugin.Builtin/EnglishCpVPhonemizer.cs

english c+v (cadlaxa): arpabet+ sung on c+v banks (separate consonant and vowel samples, [- C] [C] [V] [V C]
[C -]), with vowel fallbacks for 5-vowel romaji banks and transition lengths scaled by consonant class
(fricatives long, taps short) unless the yaml `timings` say otherwise."""

from ...g2p import ArpabetPlusG2p
from ...g2p._cs import trim
from .api import phonemizer
from .syllable_based import SKIP_ITERATOR_STR, SyllableBasedPhonemizer, cs_regex_word_boundary_match, cs_replace, cs_str, distinct

VOWELS = [
    "aa", "ax", "ae", "ah", "ao", "aw", "ay", "eh", "er", "ey", "ih", "iy", "ow", "oy", "uh", "uw", "a", "e", "i", "o", "u", "ai", "ei", "oi", "au", "ou", "ix", "ux",
    "aar", "ar", "axr", "aer", "ahr", "aor", "or", "awr", "aur", "ayr", "air", "ehr", "eyr", "eir", "ihr", "iyr", "ir", "owr", "our", "oyr", "oir", "uhr", "uwr", "ur",
    "aal", "al", "axl", "ael", "ahl", "aol", "ol", "awl", "aul", "ayl", "ail", "ehl", "el", "eyl", "eil", "ihl", "iyl", "il", "owl", "oul", "oyl", "oil", "uhl", "uwl", "ul",
    "aan", "an", "axn", "aen", "ahn", "aon", "on", "awn", "aun", "ayn", "ain", "ehn", "en", "eyn", "ein", "ihn", "iyn", "in", "own", "oun", "oyn", "oin", "uhn", "uwn", "un",
    "aang", "ang", "axng", "aeng", "ahng", "aong", "ong", "awng", "aung", "ayng", "aing", "ehng", "eng", "eyng", "eing", "ihng", "iyng", "ing", "owng", "oung", "oyng", "oing", "uhng", "uwng", "ung",
    "aam", "am", "axm", "aem", "ahm", "aom", "om", "awm", "aum", "aym", "aim", "ehm", "em", "eym", "eim", "ihm", "iym", "im", "owm", "oum", "oym", "oim", "uhm", "uwm", "um", "oh",
    "eu", "oe", "yw", "yx", "wx", "ox", "ex", "ea", "ia", "oa", "ua", "ean", "eam", "eang", "N", "nn", "mm", "ll",
]

CCV_EXCEPTION = ["ch", "dh", "dx", "fh", "gh", "hh", "jh", "kh", "ph", "ng", "sh", "th", "vh", "wh", "zh"]
ROMAJI_EXCEPTION = ["a", "e", "i", "o", "u"]
DEFAULT_CONTINUOUS = ["l", "r", "w", "y", "f", "v", "th", "dh", "s", "z", "sh", "zh", "m", "n", "ng", "hh", "ll", "mm", "nn"]

# fallbacks for vowel phonemes (especially for banks with only 5 romaji vowels)
VOWEL_FALLBACKS = {
    "aa": ["a", "ah"], "ae": ["a", "eh"], "ah": ["a", "aa"], "ao": ["o", "ow"], "aw": ["ae", "a"], "ax": ["ah", "a"], "ay": ["ai", "a"],
    "eh": ["e", "ae"], "er": ["r", "e"], "ey": ["eh", "e"], "ih": ["i", "iy"], "iy": ["i", "ih"], "ow": ["ao", "o"], "oy": ["ow", "ao", "o"],
    "uh": ["u", "uw"], "uw": ["u", "uh"],
    # romaji cross-fallbacks
    "a": ["aa", "ah"], "e": ["eh"], "i": ["iy", "ih"], "o": ["ao", "ow"], "u": ["uw", "uh"],
    # diphthong splits
    "ay-": ["iy-", "y", "iy", "i"], "ey-": ["iy-", "y", "iy", "i"], "oy-": ["iy-", "y", "iy", "i"],
    "aw-": ["uw-", "w", "uw", "uh", "u"], "ow-": ["uw-", "w", "uw", "uh", "u"],
}


def _to_dict(spec):
    out = {}
    for entry in spec.split(","):
        parts = entry.split("=")
        if len(parts) != 2 or parts[0] == parts[1]:
            continue
        if parts[0] in out:
            raise ValueError(f"An item with the same key has already been added. Key: {parts[0]}")
        out[parts[0]] = parts[1]
    return out


@phonemizer("English C+V Phonemizer", "EN C+V", language="EN", openutau_class="OpenUtau.Plugin.Builtin.EnglishCpVPhonemizer", author="Cadlaxa")
class EnglishCpVPhonemizer(SyllableBasedPhonemizer):
    yaml_file_name = "en-cPv.yaml"
    yaml_template = "en_cPv.template.yaml"
    yaml_version = "1.1.1"
    no_gap = True

    def __init__(self):
        super().__init__()
        self.vowels = list(VOWELS)
        self.consonants = "b,ch,d,dh,dr,dx,f,g,hh,jh,k,l,m,n,ng,p,q,r,s,sh,t,th,tr,v,w,y,z".split(",")
        self.diphthong_tails = {"ay": "ay-", "ey": "ey-", "oy": "oy-", "aw": "aw-", "ow": "ow-"}
        # for banks with missing custom consonants
        self.missing_c_phonemes = _to_dict("nx=n,tx=t,dx=d,zh=sh,z=s,ng=n,cl=q,vf=q,dd=d,lx=l")
        self.is_missing_c_phonemes = False

    def get_vowels(self):
        return self.vowels

    def get_consonants(self):
        return self.consonants

    def get_dictionary_name(self):
        return ""

    def get_symbols(self, note):
        original = super().get_symbols(note)
        if original is None:
            return None
        final = []
        # SPLITS UP DR AND TR
        for s in original:
            if s == "dr" and not self.has_oto(f"{s} {cs_str(self.vowels)}", note.tone) and not self.has_oto(f"ay {s}", note.tone):
                final.extend(["d", s[1]])
            elif s == "tr" and not self.has_oto(f"{s} {cs_str(self.vowels)}", note.tone) and not self.has_oto(f"ay {s}", note.tone):
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

        # check for missing consonant phonemes
        for key, value in self.missing_c_phonemes.items():
            if not H(key, tone) and not H(value, tone):
                self.is_missing_c_phonemes = True
                break

        if syllable.is_starting_v:
            # tries - V then -V and so on
            base_phoneme = AF(v, "startingV", vtone, "")
        elif syllable.is_vv:
            if not self.can_make_alias_extension(syllable):
                if H(f"{prev_v} {v}", vtone) or H(V(f"{prev_v} {v}"), vtone):
                    base_phoneme = f"{prev_v} {v}"
                elif prev_v in self.diphthong_splits or prev_v in self.diphthong_tails:
                    if prev_v in self.diphthong_splits:
                        split_override = self.diphthong_splits[prev_v]
                        vc = AF(split_override[0].replace("{v}", v), "vcEx", tone, prev_v)
                        cv = AF(split_override[1].replace("{v}", v), "vv", vtone, "")
                        add(phonemes, tone, vc, V(vc))
                    else:
                        tail = self.diphthong_tails[prev_v]  # e.g. "ay-"
                        vc_space = f"{prev_v} {tail}"
                        vc_no_space = f"{prev_v}{tail}"
                        vc_mix = AF(tail, "diph_mix", vtone, "")
                        if H(vc_space, vtone) or H(V(vc_space), vtone):
                            add(phonemes, tone, vc_space, V(vc_space))
                        elif H(vc_no_space, vtone) or H(V(vc_no_space), vtone):
                            add(phonemes, tone, vc_no_space, V(vc_no_space))
                        else:
                            add(phonemes, tone, vc_mix, V(vc_mix))
                        cv = AF(v, "vv", vtone, "")
                    if H(cv, vtone) or H(V(cv), vtone):
                        base_phoneme = cv
                    elif H(v, vtone) or H(V(v), vtone):
                        base_phoneme = v
                    else:
                        base_phoneme = AF(v, "vv", vtone, "")
                else:
                    if H(v, vtone) or H(V(v), vtone):
                        base_phoneme = v
                    else:
                        base_phoneme = AF(v, "vv", vtone, "")
            else:
                base_phoneme = None
        elif syllable.is_starting_cv_with_one_consonant:
            # [- C/-C/C]
            base_phoneme = AF(v, "cv", vtone, "")
            add(phonemes, tone, AF(cc[0], "cc_start", tone, ""))
        elif syllable.is_starting_cv_with_more_than_one_consonant:
            # CCV with multiple starting consonants with cc's support
            base_phoneme = AF(v, "cv", vtone, "")
            # TRY RCC [- CC] [-CC] [CC]
            for i in range(len(cc), 1, -1):
                if add(phonemes, tone, AF("".join(cc[:i]), "cc_start", tone, "")):
                    first_c = i - 1
                break
            # [- C] [-C] [C]
            if len(phonemes) == 0:
                add(phonemes, tone, AF(cc[0], "cc_start", tone, ""))
        else:
            # VCV part (not starting but in the middle of a phrase): [V] to [-V] to [- V]
            base_phoneme = AF(v, "cv", vtone, "")
            # try [V C], [V CC], [VC C], [V -][- C]
            for i in range(last_c + 1, -1, -1):
                vr = f"_{prev_v}"
                vr1 = f"{prev_v}-"
                vc = f"{prev_v} {cc[0]}"
                ccv_ok = False
                if len(syllable.current_word_cc) >= 2 and cc[0] not in CCV_EXCEPTION:
                    jcc = "".join(cc)
                    if H(jcc, vtone) or H(f"- {jcc}", vtone) or H(f"-{jcc}", vtone):
                        ccv_ok = True
                has_vr = H(vr, tone) or H(V(vr), tone) or (H(vr1, tone) or H(V(vr1), tone)) and not H(vc, tone)
                if i == 0 and not H(vc, tone):
                    add(phonemes, tone, AF(cc[0], "cc", tone, ""))
                    break
                elif H(vc, tone) or H(V(vc), tone):
                    # prioritize vc aliases
                    add(phonemes, tone, vc, V(vc))
                    break
                elif prev_v in self.diphthong_tails and has_vr:
                    # use vowel ending
                    add(phonemes, vtone, AF(self.diphthong_tails[prev_v], "diph_mix", vtone, ""))
                    add(phonemes, tone, AF(cc[0], "cc", tone, ""))
                    break
                elif prev_v in self.diphthong_tails and not has_vr:
                    # use consonants for diphthongs if the vb doesn't have vowel endings
                    add(phonemes, vtone, AF(self.diphthong_tails[prev_v], "diph_mix", vtone, ""))
                    add(phonemes, tone, AF(cc[0], "cc", tone, ""))
                    break
                elif ccv_ok:
                    add(phonemes, tone, vc, V(vc))
                    add(phonemes, tone, AF("".join(cc), "cc", tone, ""))
                    first_c = 1
                    break
                else:
                    continue

        i = first_c
        while i < last_c:
            cc1 = SKIP_ITERATOR_STR  # $"{cc.Skip(i)}" prints the iterator's type name
            if not H(cc1, tone):
                cc1 = V(cc1)
            # [C1][C2]
            if not H(cc1, tone) or not H(V(cc1), tone):
                cc1 = AF(cc[i + 1], "cc", tone, "")
            if not H(cc1, tone):
                cc1 = V(cc1)
            rest = "".join(cc[i + 1:])
            # CCV
            if len(syllable.current_word_cc) >= 2:
                if (H(f"{v}", vtone) or H(f"- {v}", vtone) or H(f"-{v}", vtone)) and H(AF(rest, "cc", tone, ""), vtone):
                    base_phoneme = AF(v, "cv", vtone, "")
                    last_c = i
                elif H(AF(v, "cv", tone, ""), vtone) and H(cc1, vtone):
                    base_phoneme = AF(v, "cv", vtone, "")
                # [C2C3]
                if H(AF(rest, "cc", tone, ""), vtone):
                    cc1 = AF(rest, "cc", tone, "")
                if cc[i + 1] in self.liquid or cc[i + 1] in self.semivowel or V(cc[i + 1]) in self.liquid or V(cc[i + 1]) in self.semivowel:
                    self.glides(cc1)
            elif len(syllable.current_word_cc) == 1 and len(syllable.previous_word_cc) == 1:
                # CV
                base_phoneme = AF(v, "cv", vtone, "")
                # [C1] [C2]
                if not H(cc1, tone):
                    cc1 = AF(cc[i + 1], "cc", tone, "")
            if i + 1 < last_c:
                if not H(cc1, tone):
                    cc1 = V(cc1)
                # [C1][C2]
                if not H(cc1, tone):
                    cc1 = AF(cc[i + 1], "cc", tone, "")
                if not H(cc1, tone):
                    cc1 = V(cc1)
                # CCV
                if len(syllable.current_word_cc) >= 2:
                    if (H(f"{v}", vtone) or H(f"- {v}", vtone) or H(f"-{v}", vtone)) and H(AF(rest, "cc", tone, ""), vtone):
                        base_phoneme = AF(v, "cv", vtone, "")
                        last_c = i
                    elif H(AF(v, "cv", tone, ""), vtone) and H(cc1, vtone):
                        base_phoneme = AF(v, "cv", vtone, "")
                    # [C2C3]
                    if H(AF(rest, "cc", tone, ""), vtone):
                        cc1 = AF(rest, "cc", tone, "")
                    if cc[i + 1] in self.liquid or cc[i + 1] in self.semivowel or V(cc[i + 1]) in self.liquid or V(cc[i + 1]) in self.semivowel:
                        self.glides(cc1)
                elif len(syllable.current_word_cc) == 1 and len(syllable.previous_word_cc) == 1:
                    # CV
                    base_phoneme = AF(v, "cv", vtone, "")
                    # [C1] [C2]
                    if not H(cc1, tone):
                        cc1 = AF(cc[i + 1], "cc", tone, "")
                if add(phonemes, tone, f"{cc[i]}{cc[i + 1]}{cc[i + 2]} -"):
                    # if it exists, use [C1][C2][C3] -
                    i += 2
                elif H(cc1, tone) and H(cc1, tone):
                    # like [V C1] [C1 C2] [C2 C3] [C3 ..]
                    phonemes.append(cc1)
                elif add(phonemes, tone, cc1):
                    # like [V C1] [C1 C2] [C2 ..]
                    pass
            else:
                add(phonemes, tone, cc1)
            i += 1

        phonemes.append(base_phoneme)
        return phonemes

    def _is_continuous_consonant(self, c):
        if not c:
            return False
        valid_c = self.validate_alias(c)

        def in_array(arr):
            return arr is not None and len(arr) > 0 and (c in arr or valid_c in arr)

        if in_array(self.liquid) or in_array(self.semivowel) or in_array(self.fricative) or in_array(self.nasal) or in_array(self.aspirate):
            return True
        return c in DEFAULT_CONTINUOUS or valid_c in DEFAULT_CONTINUOUS

    def _has_ending_c(self, c, tone, t):
        """-> the ending alias or None"""
        for cand in [f"{c} {t}", f"{c}{t}", f"{c} -", f"{c}-"]:
            if self.has_oto(cand, tone):
                return cand
            valid = self.validate_alias(cand, tone)
            if self.has_oto(valid, tone):
                return valid
        return None

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
        t = self.replace_phoneme(ending.tail, tone) if ending.has_tail else "-"

        if ending.is_ending_v:
            # 1. ending vowel
            v_r = f"{v} {t}"
            v_r2 = f"{v}{t}"
            if H(v_r, tone) or H(V(v_r), tone) or H(v_r2, tone) or H(V(v_r2), tone):
                add(phonemes, tone, AF(v, "ending", tone, "", t))
            elif prev_v in self.diphthong_tails:
                add(phonemes, tone, AF(self.diphthong_tails[prev_v], "cv", tone, "", t))
        elif ending.is_ending_vc_with_one_consonant:
            # 2. single consonant ending
            vc = f"{v} {cc[0]}"
            vcr = f"{v} {cc[0]}{t}"
            vcr2 = f"{v}{cc[0]} {t}"
            if cc[0] not in ROMAJI_EXCEPTION:
                if H(vcr, tone) or H(V(vcr), tone):
                    add(phonemes, tone, vcr, V(vcr))
                elif H(vcr2, tone) or H(V(vcr2), tone):
                    add(phonemes, tone, vcr2, V(vcr2))
                else:
                    vc_added = False
                    if H(vc, tone) or H(V(vc), tone):
                        vc_added = add(phonemes, tone, vc, V(vc))
                    elif prev_v in self.diphthong_tails:
                        add(phonemes, tone, AF(self.diphthong_tails[prev_v], "diph_mix", tone, "", t))
                    c = cc[0]
                    end_c = self._has_ending_c(c, tone, t)
                    if end_c is not None:
                        if self._is_continuous_consonant(c) and not vc_added:
                            add(phonemes, tone, c, V(c))
                        add(phonemes, tone, end_c)
                    elif not vc_added:
                        add(phonemes, tone, c, V(c))
        else:
            first_c = 0
            if cc[0] not in ROMAJI_EXCEPTION:
                vcc = f"{v} {''.join(cc[:2])}{t}"
                vcc2 = f"{v}{' '.join(cc[:2])} {t}"
                vcc3 = f"{v}{' '.join(cc[:2])}"
                vcc4 = f"{v} {''.join(cc[:2])}"
                vc = f"{v} {cc[0]}"
                if (H(vcc, tone) or H(V(vcc), tone)) and cc[0] not in CCV_EXCEPTION:
                    add(phonemes, tone, vcc, V(vcc))
                    first_c = 2
                elif (H(vcc2, tone) or H(V(vcc2), tone)) and cc[0] not in CCV_EXCEPTION:
                    add(phonemes, tone, vcc2, V(vcc2))
                    first_c = 2
                elif (H(vcc3, tone) or H(V(vcc3), tone)) and cc[0] not in CCV_EXCEPTION:
                    add(phonemes, tone, vcc3, V(vcc3))
                    first_c = 2
                elif (H(vcc4, tone) or H(V(vcc4), tone)) and cc[0] not in CCV_EXCEPTION:
                    add(phonemes, tone, vcc4, V(vcc4))
                    first_c = 2
                elif H(vc, tone) or H(V(vc), tone):
                    add(phonemes, tone, vc, V(vc))
                    first_c = 1
                elif prev_v in self.diphthong_tails:
                    add(phonemes, tone, AF(self.diphthong_tails[prev_v], "diph_mix", tone, "", t))

            # sequential walk through all unconsumed consonants
            for i in range(first_c, len(cc)):
                is_last = i == len(cc) - 1
                if not is_last:
                    # the final two consonants may have a combined ending release (e.g. [s t-])
                    if i == len(cc) - 2:
                        end_pair = f"{cc[i]} {cc[i + 1]}{t}"
                        end_pair2 = f"{cc[i]}{cc[i + 1]}{t}"
                        if H(end_pair, tone) or H(V(end_pair), tone):
                            add(phonemes, tone, end_pair, V(end_pair))
                            break
                        if H(end_pair2, tone) or H(V(end_pair2), tone):
                            add(phonemes, tone, end_pair2, V(end_pair2))
                            break
                    add(phonemes, tone, cc[i], V(cc[i]))
                else:
                    last_cons = cc[i]
                    end_last = self._has_ending_c(last_cons, tone, t)
                    if end_last is not None:
                        if self._is_continuous_consonant(last_cons):
                            add(phonemes, tone, last_cons, V(last_cons))
                        add(phonemes, tone, end_last)
                    else:
                        add(phonemes, tone, last_cons, V(last_cons))
        return phonemes

    def alias_format(self, alias, type_, tone, prev_v, t="-"):
        H = self.has_oto
        V = self.validate_alias
        alias_formats = {
            "startingV": ["-", "- ", "_", ""],
            "vv": ["-", "", "_", "- "],
            "vvExtend": ["", "_", "-", "- "],
            "cv": ["-", "", "*", "_"],
            "ending": [f" {t}", f"{t}"],
            "ending_mix": [f"{t}", f" {t}", "_", "--"],
            "cc": ["", "-", "- ", "_"],
            "cc_start": ["- ", "-", "", "_"],
            "cc_end": [f" {t}", f"{t}", ""],
            "cc_mix": [f" {t}", f" {t}", f"{t}", "", "_", "- ", "-"],
            "cc1_mix": ["", " -", "-", " R", "_", "- ", "-"],
            "diph_mix": [f"{t}", "_", "", f" {t}", "", "_", "- ", "-"],
        }
        if type_ not in alias_formats and "dynamic" not in type_:
            return alias

        if "dynStart" in type_:
            consonant, vowel = (alias.split(" ")[0], alias.split(" ")[1]) if " " in alias else (alias, "")
            for variation in [f"- {consonant}{vowel}", f"- {consonant} {vowel}", f"-{consonant} {vowel}", f"-{consonant}{vowel}",
                              f"-{consonant}_{vowel}", f"- {consonant}_{vowel}"]:
                if H(variation, tone):
                    return variation
                elif H(V(variation), tone):
                    return V(variation)
        if "dynMid" in type_:
            consonant, vowel = (alias.split(" ")[0], alias.split(" ")[1]) if " " in alias else (alias, "")
            for variation in [f"{consonant}{vowel}", f"{consonant} {vowel}", f"{consonant}_{vowel}"]:
                if H(variation, tone):
                    return variation
                elif H(V(variation), tone):
                    return V(variation)
        if "dynEnd" in type_:
            consonant, vowel = (alias.split(" ")[1], alias.split(" ")[0]) if " " in alias else (alias, "")
            for variation in [f"{vowel}{consonant} -", f"{vowel} {consonant}-", f"{vowel}{consonant}-", f"{vowel} {consonant} -"]:
                if H(variation, tone):
                    return variation
                elif H(V(variation), tone):
                    return V(variation)

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
            elif H(V(alias_format), tone):
                return V(alias_format)
        return alias

    def _apply_contextual_fallbacks(self, alias, tone):
        if not alias:
            return alias
        if self.has_oto(alias, tone):
            return alias
        for fb in VOWEL_FALLBACKS.get(alias, []):
            if self.has_oto(fb, tone):
                return fb
        return alias

    def get_hardcoded_fallback(self, alias, tone, suppressed_tokens):
        if not alias:
            return alias
        current = alias
        contextual = self._apply_contextual_fallbacks(alias, tone)
        if contextual != alias and self.has_oto(contextual, tone):
            return contextual
        if self.is_missing_c_phonemes and self.missing_c_phonemes is not None:
            for key, value in sorted(self.missing_c_phonemes.items(), key=lambda kv: len(kv[0]), reverse=True):
                if suppressed_tokens is not None and key in suppressed_tokens:
                    continue
                current = cs_replace(current, key, value)
            if current != alias and self.has_oto(current, tone):
                return current
        return current if current != alias else None

    @staticmethod
    def _phoneme_is_present(alias, phoneme):
        if not alias or not phoneme:
            return False
        if alias == phoneme:
            return True
        return alias.endswith(phoneme)

    def _is_ending_alias(self, alias):
        if not alias:
            return False
        trimmed = trim(alias)
        if trimmed.endswith("-") or trimmed.endswith("R"):
            return True
        if self.tails is not None and any(t and (trimmed.endswith(t) or trimmed.endswith(f" {t}")) for t in self.tails):
            return True
        return False

    def get_transition_multiplier(self, alias):
        base_multiplier = super().get_transition_multiplier(alias)
        if self._is_ending_alias(alias):
            return 1.0
        if base_multiplier != 1.0:
            return base_multiplier
        fricative_def = 1.8
        aspirate_def = 1.2
        semivowel_def = 1.2
        liquid_def = 1.2
        nasal_def = 1.3
        stop_def = 1.3
        tap_def = 0.5
        affricate_def = 1.3
        for symbol, value in sorted(self.phoneme_overrides.items(), key=lambda kv: len(kv[0]), reverse=True):
            if self._is_ending_alias(alias) and symbol != alias:
                continue
            if cs_regex_word_boundary_match(alias, symbol):
                return base_multiplier * value
        for c in self.fricative:
            if self._phoneme_is_present(alias, c):
                return fricative_def
        for c in self.aspirate:
            if self._phoneme_is_present(alias, c):
                return aspirate_def
        for c in self.semivowel:
            if self._phoneme_is_present(alias, c):
                return semivowel_def
        for c in self.liquid:
            if self._phoneme_is_present(alias, c):
                return liquid_def
        for c in self.nasal:
            if self._phoneme_is_present(alias, c):
                return nasal_def
        for c in self.stop:
            if self._phoneme_is_present(alias, c):
                return stop_def
        for c in self.tap:
            if self._phoneme_is_present(alias, c):
                return tap_def
        for c in self.affricate:
            if self._phoneme_is_present(alias, c):
                return affricate_def
        return 1.0
