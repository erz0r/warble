"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Plugin.Builtin/EnglishVCCVPhonemizer.cs

english vccv (cubialpha & mim, cadlaxa): cmudict arpabet mapped onto the cz vccv symbols, sung as [-CV] [VC]
[CC] [CV] with many reclist-specific exceptions, plus automatic consonant velocity ("convel"): every alias gets
a consonant stretch from its note's length and the tempo.

convel needs the part's notes. openutau takes them from the project, and when a group isn't in a voice part (the
parity harness, and warble, which has no project) it builds them from the note groups it is given, which is what
this port does. its float math is single precision, emulated with f32()."""

import builtins
import math
import os
import re
import struct

from ...g2p import ArpabetG2p
from .api import phonemizer
from .syllable_based import PhonemeExpression, SyllableBasedPhonemizer, cs_regex_word_boundary_match, last


def f32(x):
    """round a python float to c# float (single precision)."""
    return struct.unpack("f", struct.pack("f", x))[0]


def dotnet_regex_escape(s):
    """Regex.Escape: \\ * + ? | { [ ( ) ^ $ . # and white space."""
    out = []
    for c in s:
        if c in "\\*+?|{[()^$.#":
            out.append("\\" + c)
        elif c == " ":
            out.append("\\ ")
        elif c == "\t":
            out.append("\\t")
        elif c == "\n":
            out.append("\\n")
        elif c == "\r":
            out.append("\\r")
        elif c == "\f":
            out.append("\\f")
        elif c == "\v":
            out.append("\\v")
        else:
            out.append(c)
    return "".join(out)


class UNote:
    def __init__(self, position, duration, tone, lyric):
        self.position = position
        self.duration = duration
        self.tone = tone
        self.lyric = lyric
        self.phoneme_expressions = []


VC_EXCEPTIONS = {
    "i ng": "1 ng", "ing": "1ng", "0 r": "0r-", "9r": "0r", "9r-": "0r-", "er-": "Ar-", "er": "Ar", "@m": "&m", "@n": "&n",
    "@m-": "&m-", "@n-": "&n-", "@ ng": "Ang-", "@ng": "Ang", "ang": "9ng", "a ng": "9ng-", "al": "9l", "al-": "9l-",
    "0 l": "0l-", "Ol": "0l", "ir": "Er", "ir-": "Er-", "6r-": "or-", "6r": "or",
}
VV_EXCEPTIONS = {"o": "w", "O": "w", "8": "w", "W": "w", "A": "y", "I": "y", "Y": "y", "E": "y", "Q": "y", "i": "y", "3": "r"}
CC_FALLBACK = {"z": "s", "g": "k", "zh": "sh", "j": "ch", "b": "p", "v": "f", "d": "t", "dh": "th"}
CC_EXCEPTIONS = ["th", "ch", "dh", "zh", "sh", "ng"]
CCC_EXCEPTIONS = ["spr", "spl", "skr", "str", "skw", "sky", "spy", "skt"]
VCCC_EXCEPTIONS = {"spr": "sp", "spl": "sp", "skr": "sk", "str": "st", "skw": "sk", "sky": "sk", "spy": "sp", "skt": "sk"}
CC_NO_PARSING = ["sk", "sm", "sn", "sp", "st", "hy"]
STOP_CS = ["b", "d", "g", "k", "p", "t"]
UCV_CS = ["r", "l", "w", "y", "f"]
STARLIGHT_CCS = ["rl", "ll", "nn", "mm"]


def _dict_replacements(spec):
    out = {}
    for entry in spec.split(";"):
        parts = entry.split("=")
        if len(parts) != 2 or parts[0] == parts[1]:
            continue
        if parts[0] in out:
            raise ValueError(f"An item with the same key has already been added. Key: {parts[0]}")
        out[parts[0]] = parts[1]
    return out


@phonemizer("English VCCV Phonemizer", "EN VCCV", language="EN", openutau_class="OpenUtau.Plugin.Builtin.EnglishVCCVPhonemizer", author="cubialpha & Mim")
class EnglishVCCVPhonemizer(SyllableBasedPhonemizer):
    yaml_file_name = "envccv.yaml"
    yaml_template = "envccv.template.yaml"
    yaml_version = "1.2"

    def __init__(self):
        super().__init__()
        self.vowels = "a,@,u,0,8,I,e,3,A,i,E,O,Q,6,o,1ng,9,&,x,1,Y,L,W,8n,Ang,9l".split(",")
        self.consonants = "b,ch,d,dh,f,g,h,j,k,l,m,n,ng,p,r,s,sh,t,th,v,w,y,z,zh,dd,hh,sp,st".split(",")
        self.dictionary_replacements = _dict_replacements(
            "ax=x;aa=a;ae=@;ah=u;ao=9;aw=8;ay=I;"
            "b=b;ch=ch;d=d;dh=dh;eh=e;er=3;ey=A;f=f;g=g;hh=h;hhy=hh;ih=i;iy=E;jh=j;k=k;l=l;m=m;n=n;ng=ng;ow=O;oy=Q;"
            "p=p;r=r;s=s;sh=sh;t=t;th=th;uh=6;uw=o;v=v;w=w;y=y;z=z;zh=zh;dx=dd;")
        self.use_convel = True
        self.base_bpm = 120
        self.vc_vowels = {}
        self.unotes = []
        self.part_pos = 0
        self._patterns = None
        self._classify_cache = {}
        self._syll_of_index = []

    def get_vowels(self):
        return self.vowels

    def get_consonants(self):
        return self.consonants

    def get_dictionary_name(self):
        return ""

    def get_base_g2ps(self):
        return [ArpabetG2p()]

    def get_symbols(self, note):
        original = super().get_symbols(note)
        if note.lyric in self.tails:
            return [note.lyric]
        if original is None:
            return None
        for i in range(len(original)):
            if original[i] in self.dictionary_replacements:
                original[i] = self.dictionary_replacements[original[i]]
        final = []
        for s in original:
            if s in ("tr", "dr") and not self.has_oto(s, note.tone) and not self.has_oto(f"A {s}", note.tone):
                final.extend([s[0], s[1]])
            else:
                final.append(s)
        return final

    # we have a custom property in the yaml, so we have to load it twice
    def set_singer(self, singer):
        super().set_singer(singer)
        if self.singer is None:
            return
        file = None
        if getattr(singer, "location", None):
            file = self._singer_yaml_path()
        else:
            file = self.plugin_yaml_path()
        if not file or not os.path.isfile(file):
            return
        try:
            raw = self.load_yaml_raw(file)
            if not isinstance(raw, dict):
                return
            vcvowels = raw.get("vcvowels")
            if isinstance(vcvowels, dict):
                self.vc_vowels.clear()
                for k, v in vcvowels.items():
                    if isinstance(v, (list, dict)):
                        raise ValueError("vcvowels value is not a scalar")
                    if k and v and v not in ("~", "null", "Null", "NULL"):
                        self.vc_vowels[k] = v
            elif vcvowels is not None and vcvowels not in ("", "~", "null"):
                raise ValueError("vcvowels is not a mapping")
            useconvel = raw.get("useconvel")
            if useconvel not in (None, "", "~", "null"):
                if useconvel.lower() not in ("true", "false"):
                    raise ValueError("useconvel is not a bool")
                self.use_convel = useconvel.lower() == "true"
            basebpm = raw.get("basebpm")
            if basebpm not in (None, "", "~", "null"):
                bb = int(basebpm)
                if bb < 0 or bb > 2 ** 32 - 1:
                    raise ValueError("basebpm out of range")
                self.base_bpm = bb
        except Exception:  # noqa: BLE001 - Log.Error("Failed to load vccv specific features")
            pass

    # this lets us get the unotes for convel
    def set_up(self, groups):
        super().set_up(groups)
        # no voice part in a project: openutau's test fixture fallback builds the notes from the groups
        self.part_pos = 0
        notes = [UNote(n.position, n.duration, n.tone, n.lyric) for g in groups for n in g]
        self.unotes = sorted(notes, key=lambda n: n.position)

    def _init_patterns(self):
        if self._patterns is not None:
            return

        def alt(symbols):
            esc = sorted([dotnet_regex_escape(s) for s in symbols], key=len, reverse=True)
            return "(" + "|".join(esc) + ")"

        V = alt(self.vowels)
        C = alt(self.consonants)
        C2 = alt(UCV_CS)
        self._patterns = [
            (re.compile(rf"^-{V}$"), "-V"),
            (re.compile(rf"^_{V}$"), "_V"),
            (re.compile(rf"^{V}-$"), "V-"),
            (re.compile(rf"^-{C}{V}$"), "-CV"),
            (re.compile(rf"^-{C}{C2}$"), "-CC"),
            (re.compile(rf"^_{C}{V}$"), "_CV"),
            (re.compile(rf"^{V}{C}{C}-$"), "VCC-"),
            (re.compile(rf"^{V}{C}{C}$"), "VCC"),
            (re.compile(rf"^{V}{C}-$"), "VC-"),
            (re.compile(rf"^{C}{C}-$"), "CC-"),
            (re.compile(rf"^{V} {C}$"), "V C"),
            (re.compile(rf"^{C} {C}$"), "C C"),
            (re.compile(rf"^{V}{C} {C}$"), "VC C"),
            (re.compile(rf"^{V}{C}$"), "VC"),
            (re.compile(rf"^{C}{C2}$"), "onsetCC"),
            (re.compile(rf"^{C}{C}$"), "codaCC"),
            (re.compile(rf"^{C}{V}$"), "CV"),
            (re.compile(rf"^{V}$"), "V"),
        ]

    def _classify(self, alias):
        hit = self._classify_cache.get(alias)
        if hit is not None:
            return hit
        if alias in STARLIGHT_CCS:
            result = "codaCC"
        else:
            self._init_patterns()
            result = "Unknown"
            for pattern, type_ in self._patterns:
                if pattern.search(alias):
                    result = type_
                    break
        self._classify_cache[alias] = result
        return result

    def _calc_convel(self, note):
        if note is None:
            return f32(100.0)
        abs_tick = self.part_pos + note.position
        bpm = f32(self.time_axis.get_bpm_at_tick(abs_tick)) if self.time_axis is not None else f32(120.0)
        base_convel = f32(100 * f32(bpm / f32(self.base_bpm)))
        vel_min = f32(0.0)
        vel_max = f32(200.0)
        if note.duration >= 480:
            final = f32(base_convel + f32(50 - f32(100 * f32(f32(note.duration) / 960))))
        else:
            final = f32(base_convel + f32(100 - f32(100 * f32(f32(note.duration) / 480))))
        return min(max(final, vel_min), vel_max)

    def _unote_at(self, abs_pos):
        if not self.unotes:
            return None, None
        rel = abs_pos - self.part_pos
        un = next((n for n in reversed(self.unotes) if n.position <= rel), None) or self.unotes[0]
        idx = self.unotes.index(un)
        return un, (self.unotes[idx + 1] if idx + 1 < len(self.unotes) else None)

    # automatic convel
    def process(self, notes, prev, next, prev_neighbour, next_neighbour, prev_neighbours):
        result = super().process(notes, prev, next, prev_neighbour, next_neighbour, prev_neighbours)
        if not self.unotes or not self.use_convel or result is None:
            return result

        def note_for_phoneme(phoneme, current_notes):
            abs_pos = current_notes[0].position + phoneme.position
            return builtins.next((n for n in current_notes if n.position <= abs_pos < n.position + n.duration), current_notes[0])

        cur_un, next_un = self._unote_at(notes[0].position)
        cur_idx = self.unotes.index(cur_un)
        prev_un = self.unotes[cur_idx - 1] if cur_idx > 0 else None
        prev_vel = self._calc_convel(prev_un) if prev_un is not None else None
        next_vel = self._calc_convel(next_un) if next_un is not None else None

        for i in range(len(result)):
            phoneme = result[i]
            if phoneme.phoneme is None:
                continue
            abs_pos = notes[0].position + phoneme.position
            phoneme_un, _ = self._unote_at(abs_pos)
            note_vel = self._calc_convel(phoneme_un)
            if i < len(result) - 1 and result[i + 1].phoneme is not None:
                next_abs = notes[0].position + result[i + 1].position
                next_phoneme_un, _ = self._unote_at(next_abs)
                if next_phoneme_un is not None:
                    next_vel = self._calc_convel(next_phoneme_un)

            is_manual = False
            vel = note_vel
            if cur_un is not None and cur_un.phoneme_expressions:
                user_exp = builtins.next((e for e in cur_un.phoneme_expressions if e.abbr == "vel" and e.index == i), None)
                if user_exp is not None:
                    vel = user_exp.value
                    is_manual = True
            if not is_manual:
                type_ = self._classify(phoneme.phoneme)
                if type_ in ("V C", "VC", "VC-", "VCC", "VCC-", "codaCC", "C C", "VC C", "V-", "CC-"):
                    n = note_for_phoneme(phoneme, notes)
                    if n.lyric == "+" or n.lyric == "+~" or n.lyric.startswith("+"):
                        vel = note_vel
                    else:
                        vel = prev_vel if prev_vel is not None else note_vel
                elif type_ in ("onsetCC", "-CC"):
                    vel = next_vel if next_vel is not None else note_vel
                else:
                    vel = note_vel
            phoneme.expressions = [PhonemeExpression("vel", vel)]
            result[i] = phoneme
            # transitions inherit this phoneme's velocity as their preceding anchor
            prev_vel = vel
        return result

    def process_syllable(self, syllable):
        H = self.has_oto
        V = self.validate_alias
        tone = syllable.tone
        vtone = syllable.vowel_tone
        syllable.prev_v = "" if syllable.prev_v in self.tails else syllable.prev_v
        replaced_prev_v = self.replace_phoneme(syllable.prev_v, tone)
        prev_v = "" if not replaced_prev_v else replaced_prev_v
        cc = [self.replace_phoneme(c, tone) for c in syllable.cc]
        v = self.replace_phoneme(syllable.v, vtone)
        last_c = len(cc) - 1
        current_word_cc = [self.replace_phoneme(c, tone) for c in syllable.current_word_cc]
        previous_word_cc = [self.replace_phoneme(c, tone) for c in syllable.previous_word_cc]
        last_c_prev_word = syllable.prev_word_consonants_count
        vc_vowels = self.vc_vowels

        def is_glide_c(c):
            return c in self.liquid or c in self.semivowel or V(c) in self.liquid or V(c) in self.semivowel

        base_phoneme = None
        phonemes = []
        if syllable.is_starting_v:
            # if starting V -> -V
            base_phoneme = f"-{v}"
        elif syllable.is_vv:
            # VV first, then Vc + cV depending on certain rules, then V
            base_phoneme = f"{prev_v}{v}"
            if not H(base_phoneme, vtone):
                base_phoneme = f"{prev_v} {v}"
                if prev_v in VV_EXCEPTIONS and prev_v != v:
                    vc = f"{prev_v} {VV_EXCEPTIONS[prev_v]}"
                    if not H(vc, vtone):
                        vc = f"{prev_v}{VV_EXCEPTIONS[prev_v]}"
                    phonemes.append(vc)
                    base_phoneme = f"{VV_EXCEPTIONS[prev_v]}{v}"
                if prev_v in vc_vowels and not H(base_phoneme, vtone):
                    phonemes.append(f"{prev_v}")
                    base_phoneme = f"_{v}"
                if not H(base_phoneme, vtone):
                    base_phoneme = f"{v}"
        elif syllable.is_starting_cv_with_one_consonant:
            # [-CV], fallback to [CV]
            base_phoneme = f"-{cc[0]}{v}"
            if not H(base_phoneme, tone):
                if cc[0] == "h" and v == "E":
                    base_phoneme = "-hhE"
                else:
                    base_phoneme = f"{cc[0]}{v}"
        elif syllable.is_starting_cv_with_more_than_one_consonant:
            base_phoneme = f"_{last(cc)}{v}"
            if not H(base_phoneme, tone):
                base_phoneme = f"{last(cc)}{v}"
            # try CCVs
            ccv = ""
            if len(cc) == 2:
                ccv = f"-{cc[0]}{cc[1]}{v}"
                if H(ccv, tone):
                    base_phoneme = ccv
                elif cc[0] == "h":
                    ccv = f"-hh{cc[1]}{v}"
                    if H(ccv, tone):
                        base_phoneme = ccv
            if len(cc) == 3:
                ccv = f"-{cc[0]}{cc[1]}{cc[2]}"
                if H(ccv, tone):
                    phonemes.append(ccv)
                elif cc[0] == "h":
                    ccv = f"-hh{cc[1]}{v}"
                    if H(ccv, tone):
                        base_phoneme = ccv
                if is_glide_c(cc[2]):
                    self.glides(ccv)
            # if there still is no match, add [-CC] + [CC] etc.
            if not H(ccv, tone):
                for i in range(0, last_c):
                    current_cc = f"{cc[i]}{cc[i + 1]}"
                    if i == 0 and H(f"-{cc[i]}{cc[i + 1]}", tone):
                        current_cc = f"-{cc[i]}{cc[i + 1]}"
                    if H(current_cc, tone):
                        phonemes.append(current_cc)
                    if is_glide_c(cc[i + 1]):
                        self.glides(current_cc)
        else:
            # VCV
            parsing_vcc = f"{prev_v}{cc[0]}-"
            parsing_cc = ""
            if syllable.is_vcv_with_one_consonant:
                # [V C] + [CV], [VC-][CV], or [VC][_V]
                base_phoneme = f"{last(cc)}{v}"
                vc = f"{prev_v} {last(cc)}"
                if H(vc, vtone):
                    vc = f"{prev_v} {last(cc)}"
                else:
                    vc = f"{prev_v}{last(cc)}"
                if not H(base_phoneme, vtone):
                    if last(cc) == "ng":
                        base_phoneme = f"_{v}"
                    if cc[0] == "h" and v == "E":
                        base_phoneme = "hhE"
                if last_c_prev_word == 1 and len(current_word_cc) == 0:
                    if last(previous_word_cc) == "r" or last(previous_word_cc) == "l":
                        if H(f"{prev_v}{last(previous_word_cc)}-", vtone) and H(f"{last(previous_word_cc)} {v}", vtone):
                            base_phoneme = f"{last(previous_word_cc)} {v}"
                            vc = f"{prev_v}{last(previous_word_cc)}-"
                        else:
                            vc = f"{prev_v}{last(previous_word_cc)}-"
                if not H(vc, vtone):
                    if prev_v in vc_vowels:
                        vc = f"{prev_v}-"
                        parsing_cc = f"{vc_vowels[prev_v]} {cc[0]}"
                vc = self._check_vc_exceptions(vc)
                phonemes.append(vc)
                if parsing_cc != "":
                    phonemes.append(parsing_cc)
            elif syllable.is_vcv_with_more_than_one_consonant:
                ex_ing = prev_v == "i" and cc[0] == "ng"
                ex_1ng = prev_v == "1" and cc[0] == "ng"
                ex_1nk = prev_v == "1" and cc[0] == "n"
                # defaults to [CV]
                base_phoneme = f"{last(cc)}{v}"

                # clusters of 2, defaults to [VC] + [CV]
                if len(cc) == 2:
                    # sk, sm, sn, sp & st exceptions
                    cc_no_parse = f"{cc[0]}{cc[1]}"
                    dont_parse = False
                    if len(cc) - last_c_prev_word > 1:
                        for _ in range(len(CC_NO_PARSING)):
                            if cc_no_parse in CC_NO_PARSING:
                                dont_parse = True
                                break
                    if dont_parse:
                        base_phoneme = f"{cc_no_parse}{v}"
                        if cc_no_parse == "hy":
                            base_phoneme = f"hhy{v}"
                        if not H(base_phoneme, vtone):
                            base_phoneme = f"_{v}"
                        vc = f"{prev_v} {cc_no_parse}"
                        if cc_no_parse == "hy":
                            vc = f"{prev_v} hh"
                        phonemes.append(vc)

                    # also [VC C] exceptions
                    vcc_exceptions = f"{prev_v}{cc[0]} {cc[1]}"
                    # i to 1 conversion
                    if ex_ing or ex_1ng or ex_1nk:
                        vcc_exceptions = f"1ng {cc[1]}"
                        # 1nk exception
                        if cc[1] == "k" and last_c_prev_word != 1:
                            vcc_exceptions = "1nk-"
                    if H(vcc_exceptions, vtone):
                        phonemes.append(vcc_exceptions)

                    if len(phonemes) == 0:
                        # opera [9 p] + [pr] + [_ru]
                        parsing_cc = f"{cc[0]}{cc[1]}"
                        if H(parsing_cc, vtone) and last_c_prev_word != 1 and cc[1] in UCV_CS and f"{cc[0]}{cc[1]}" not in STARLIGHT_CCS:
                            parsing_vcc = f"{prev_v} {cc[0]}"
                            base_phoneme = f"_{last(cc)}{v}"
                            if last_c_prev_word == len(cc):
                                parsing_vcc = f"{prev_v}{cc[0]}-"
                                if last(cc) in STOP_CS:
                                    base_phoneme = f"-{v}"
                            # sp fix
                            if cc[0] == "s" and cc[1] == "p":
                                parsing_vcc = f"{prev_v} sp"
                            phonemes.append(parsing_vcc)
                            phonemes.append(parsing_cc)
                            if is_glide_c(cc[1]):
                                self.glides(parsing_cc)
                        else:
                            # bonehead [On-] + [n h] + [he]
                            parsing_cc = f"{cc[0]} {cc[1]}"
                            if not H(parsing_cc, vtone):
                                if cc[1] in CC_FALLBACK:
                                    parsing_cc = f"{cc[0]} {CC_FALLBACK[cc[1]]}"
                            if H(parsing_cc, vtone):
                                if not H(parsing_vcc, vtone):
                                    parsing_vcc = self._check_vc_exceptions(parsing_vcc)
                                if not H(parsing_vcc, vtone):
                                    parsing_vcc = f"{prev_v} {cc[0]}"
                                # sp fix
                                if cc[0] == "s" and cc[1] == "p":
                                    parsing_vcc = f"{prev_v} sp"
                                phonemes.append(parsing_vcc)
                                phonemes.append(parsing_cc)
                            else:
                                # backpack [@k] + [p@]
                                if cc[0] == "s" and cc[1] == "p":
                                    parsing_vcc = f"{prev_v} sp"
                                else:
                                    parsing_vcc = f"{prev_v}{cc[0]}"
                                if not H(parsing_vcc, vtone):
                                    if prev_v in vc_vowels:
                                        parsing_vcc = f"{prev_v}-"
                                        parsing_cc = f"{vc_vowels[prev_v]}{cc[0]}"
                                        if not H(parsing_cc, vtone) and "ng" in parsing_cc and cc[0] == "k":
                                            parsing_cc = "nk"
                                phonemes.append(parsing_vcc)
                                if parsing_cc != "" and H(parsing_cc, vtone):
                                    phonemes.append(parsing_cc)

                # LOGIC FOR MORE THAN 2 CONSONANTS
                if len(cc) > 2 and len(phonemes) == 0:
                    # also [VC CC] exceptions
                    vcc_exceptions = f"{prev_v}{cc[0]}{cc[1]} {cc[2]}"
                    starting_c = 2
                    # 1nks exception
                    ing = False
                    if ex_ing or ex_1ng or ex_1nk:
                        vcc_exceptions = f"1ng {cc[1]}"
                        ing = True
                        starting_c = 1
                        if last_c_prev_word == 2:
                            vcc_exceptions = f"1ng{cc[1]}"
                        if cc[1] == "k" and last_c_prev_word >= 2:
                            vcc_exceptions = "1nk"
                            starting_c = 2
                            if cc[2] == "s" and last_c_prev_word == 3:
                                vcc_exceptions = "1nks"
                                starting_c = 3

                    cc_no_parse = f"{cc[len(cc) - 3]}{cc[len(cc) - 2]}{cc[len(cc) - 1]}"
                    dont_parse = False
                    last_c_for_loop = len(cc) - 1
                    leading_c_before_cluster = False

                    # str exceptions
                    if cc_no_parse in CCC_EXCEPTIONS and len(cc) - 3 >= last_c_prev_word:
                        vc = f"{prev_v}{cc[0]}-"
                        if prev_v in vc_vowels:
                            vc = f"{prev_v}-"
                        if len(cc) == 3:
                            vcc_e = VCCC_EXCEPTIONS[cc_no_parse]
                            vc = f"{prev_v} {vcc_e}"
                        if len(cc) == 4:
                            if H(f"{cc[0]} {cc[1]}", vtone):
                                vc = f"{prev_v}{cc[0]}-"
                                leading_c_before_cluster = True
                            else:
                                vc = f"{prev_v}{cc[0]}"
                                last_c_for_loop = 0
                        if vc == "ing":
                            vc = "1ng"
                        phonemes.append(vc)
                        starting_c = 0
                        last_c_for_loop -= 2
                        if is_glide_c(last(cc)):
                            self.glides(cc_no_parse)
                    else:
                        cc_no_parse = f"{cc[len(cc) - 2]}{cc[len(cc) - 1]}"
                        cc_sp = f"{cc[0]}{cc[1]}"
                        # sk, sm, sn, sp & st exceptions
                        if len(cc) - last_c_prev_word > 1:
                            for _ in range(len(CC_NO_PARSING)):
                                if cc_no_parse in CC_NO_PARSING:
                                    dont_parse = True
                                    break
                            if is_glide_c(cc[1]):
                                self.glides(cc_no_parse)
                        if dont_parse:
                            base_phoneme = f"{cc[len(cc) - 2]}{cc[len(cc) - 1]}{v}"
                            if cc_no_parse == "hy":
                                base_phoneme = f"hhy{v}"
                            vcc_exceptions = f"1ng {cc[1]}{cc[2]}"
                            if cc_no_parse == "hy":
                                vcc_exceptions = "1ng hhy"
                            if ing and H(vcc_exceptions, vtone):
                                vcc_exceptions = f"1ng {cc[1]}{cc[2]}"
                                if cc_no_parse == "hy":
                                    vcc_exceptions = "1ng hhy"
                                phonemes.append(vcc_exceptions)
                                starting_c = 2
                            else:
                                vcc_exceptions = f"{prev_v}{cc[0]}-"
                                if vcc_exceptions == "ing-":
                                    vcc_exceptions = "1ng-"
                                phonemes.append(vcc_exceptions)
                                if H(f"{cc[0]} {cc[1]}{cc[2]}", vtone):
                                    phonemes.append(f"{cc[0]} {cc[1]}{cc[2]}")
                                    starting_c = 2
                                else:
                                    base_phoneme = f"-{cc[len(cc) - 2]}{cc[len(cc) - 1]}{v}"
                                    if cc_no_parse == "hy":
                                        base_phoneme = f"-hhy{v}"
                                    starting_c = 0

                        if len(phonemes) == 0:
                            if H(vcc_exceptions, vtone):
                                phonemes.append(vcc_exceptions)
                            else:
                                starting_c = 0
                            if len(phonemes) == 0:
                                parsing_vcc = f"{prev_v}{cc[0]}-"
                                if len(cc) - last_c_prev_word - 1 > 0 and not dont_parse and not H(f"{cc[0]} {cc[1]}", vtone) and last_c_prev_word == 0:
                                    parsing_vcc = f"{prev_v}{cc[0]}"
                                if not H(parsing_vcc, vtone):
                                    parsing_vcc = self._check_vc_exceptions(f"{prev_v}{cc[0]}") + "-"
                                    if not H(parsing_vcc, vtone):
                                        parsing_vcc = f"{prev_v} {cc[0]}"
                                    if prev_v in vc_vowels:
                                        parsing_vcc = f"{prev_v}-"
                                if last_c_prev_word == 1 and cc[0] in STOP_CS and (not H(f"{cc[0]} {cc[1]}", vtone) and prev_v not in vc_vowels):
                                    parsing_vcc = f"{prev_v}{cc[0]}"
                                    if prev_v in vc_vowels:
                                        parsing_vcc = f"{prev_v}-"
                                if cc_sp == "sp":
                                    parsing_vcc = f"{prev_v} sp"
                                phonemes.append(parsing_vcc)

                    for i in range(starting_c, last_c_for_loop):
                        parsing_cc = f"{cc[i]}{cc[i + 1]}-"
                        if prev_v in vc_vowels and len(phonemes) == 1:
                            vc_vowels_cc = f"{vc_vowels[prev_v]}{cc[i]}-"
                            if i == last_c_prev_word - 1 and not H(f"{cc[i]} {cc[i + 1]}", vtone):
                                vc_vowels_cc = f"{vc_vowels[prev_v]}{cc[i]}"
                            vc_vowels_cc = vc_vowels_cc.replace("ngk", "nk")
                            phonemes.append(vc_vowels_cc)
                        if dont_parse and i == len(cc) - 3:
                            parsing_cc = f"{cc[i]} {cc[i + 1]}{cc[i + 2]}"
                            if prev_v in vc_vowels:
                                parsing_cc = f"{vc_vowels[prev_v]} {cc[i]}{cc[i + 1]}"
                        if i == last_c_prev_word - 1 or (leading_c_before_cluster and i == 0):
                            parsing_cc = f"{cc[i]} {cc[i + 1]}"
                            if prev_v in vc_vowels and i > 0 and f"{cc[i - 1]}{cc[i]}" not in phonemes:
                                parsing_cc = f"{cc[i - 1]}{cc[i]}"
                        if i == last_c_prev_word - 2:
                            parsing_cc = f"{cc[i]}{cc[i + 1]}"
                            if prev_v in vc_vowels and len(phonemes) < i + 1:
                                parsing_cc = f"{vc_vowels[prev_v]}{cc[i]}"
                            if i + 2 < len(cc):
                                if H(f"{cc[i + 1]} {cc[i + 2]}", vtone):
                                    parsing_cc = f"{cc[i]}{cc[i + 1]}-"
                            if base_phoneme == f"{cc[i + 1]}{v}":
                                parsing_cc = f"{cc[i]}{cc[i + 1]}-"
                            if not H(parsing_cc, vtone):
                                parsing_cc = f"{cc[i]}{cc[i + 1]}-"
                                if prev_v in vc_vowels:
                                    parsing_cc = f"{vc_vowels[prev_v]}{cc[i]}-"
                                if not H(parsing_cc, vtone):
                                    parsing_cc = f"{cc[i]} {cc[i + 1]}"
                        if not H(parsing_cc, vtone) and i != last_c_prev_word - 1:
                            parsing_cc = f"{cc[i]}{cc[i + 1]}"
                            if not H(parsing_cc, vtone) and H(f"{cc[i]} {cc[i + 1]}", vtone):
                                parsing_cc = f"{cc[i]} {cc[i + 1]}"
                            if is_glide_c(cc[i + 1]):
                                self.glides(parsing_cc)
                        if dont_parse and i == len(cc) - 2:
                            parsing_cc = ""
                        # ng to nk exception
                        parsing_cc = parsing_cc.replace("ngk", "nk")
                        if parsing_cc != "" and H(parsing_cc, vtone):
                            phonemes.append(parsing_cc)

                    if len(cc) - last_c_prev_word - 1 > 0 and not dont_parse:
                        base_phoneme = f"_{last(cc)}{v}"
                    if cc_no_parse in CCC_EXCEPTIONS:
                        phonemes.append(cc_no_parse)

        if base_phoneme is not None and not H(base_phoneme, vtone):
            base_phoneme = f"{last(cc)}{v}" if len(cc) > 0 else v
        if base_phoneme is not None:
            phonemes.append(base_phoneme)
        return phonemes

    def process_ending(self, ending):
        H = self.has_oto
        tone = ending.tone
        cc = [self.replace_phoneme(c, tone) for c in ending.cc]
        v = self.replace_phoneme(ending.prev_v, tone)
        phonemes = []
        if ending.is_ending_v:
            # try V- else no ending
            self.try_add_phoneme(phonemes, tone, f"{v}-")
        else:
            vc = f"{v}{cc[0]}"
            current_cc = ""
            has_vc_vowel = v in self.vc_vowels
            vc_vowel_sub = self.vc_vowels.get(v)
            has_ending_vc_vowel = ending.prev_v in self.vc_vowels
            if ending.is_ending_vc_with_one_consonant:
                vc = self._check_vc_exceptions(vc) + "-"
                if not H(vc, tone):
                    if has_ending_vc_vowel:
                        vc = f"{v}-"
                    if has_vc_vowel:
                        current_cc = f"{vc_vowel_sub}{cc[0]}-"
                        if current_cc == "ngk-":
                            current_cc = "nk-"
                phonemes.append(vc)
                if current_cc != "":
                    phonemes.append(current_cc)
            else:
                vc = f"{v}{cc[0]}"
                vc = self._check_vc_exceptions(vc) + "-"
                # "1nks" exception
                starting_c = 0
                vcc = ""
                new_v = v
                if v == "i" and cc[0] == "ng":
                    new_v = "1"
                if len(cc) > 2:
                    vcc = f"{new_v}{cc[0]}{cc[1]}{cc[2]}-"
                    vc = vcc
                    starting_c = 2
                    if vcc == "1ngks-":
                        vcc = "1nks-"
                    if not H(vcc, tone):
                        vcc = f"{cc[0]}{cc[1]}{cc[2]}-"
                        vc = f"{new_v}{cc[0]}-"
                        starting_c = 2
                if not H(vcc, tone) or vcc == "":
                    vcc = f"{new_v}{cc[0]}{cc[1]}-"
                    vc = vcc
                    starting_c = 1
                    if vcc == "1ngk-":
                        vcc = "1nk-"
                if not H(vcc, tone):
                    vcc = f"{new_v}{cc[0]}-"
                    vc = vcc
                    starting_c = 0
                # sp fix
                if f"{cc[0]}{cc[1]}" == "sp":
                    vcc = f"{new_v} {cc[0]}{cc[1]}"
                    vc = vcc
                    starting_c = 1
                if has_vc_vowel:
                    vc = f"{v}-"
                    vcc = vc
                    starting_c = 0
                if H(vcc, tone):
                    if H(vc, tone):
                        phonemes.append(vc)
                    if vc != vcc and vcc != "":
                        phonemes.append(vcc)

                # ENDING VCC
                for i in range(starting_c, len(cc) - 1):
                    current_cc = f"{cc[i]}{cc[i + 1]}-"
                    if has_vc_vowel and len(phonemes) == 1:
                        vc_vowels_cc = f"{vc_vowel_sub}{cc[i]}-"
                        vc_vowels_cc = vc_vowels_cc.replace("ngk", "nk")
                        phonemes.append(vc_vowels_cc)
                    if not H(current_cc, tone):
                        current_cc = f"{cc[i]}{cc[i + 1]}"
                        if has_vc_vowel and len(phonemes) == 1:
                            phonemes.append(f"{vc_vowel_sub}{cc[i]}")
                    if not H(current_cc, tone):
                        current_cc = f"{cc[i]} {cc[i + 1]}"
                        if has_vc_vowel and len(phonemes) == 1:
                            phonemes.append(f"{vc_vowel_sub} {cc[i]}")
                    if not H(current_cc, tone):
                        current_cc = f"{cc[i]}x"
                        if has_vc_vowel and len(phonemes) == 1:
                            phonemes.append(f"{vc_vowel_sub}x")
                        if i == len(cc) - 2:
                            phonemes.append(current_cc)
                            current_cc = f"{cc[i + 1]}x"
                            if has_vc_vowel and len(phonemes) == 1:
                                phonemes.append(f"{cc[i]}x")
                    # ng to nk exception
                    current_cc = current_cc.replace("ngk", "nk")
                    if H(current_cc, tone):
                        phonemes.append(current_cc)
        return phonemes

    @staticmethod
    def _check_vc_exceptions(vc):
        return VC_EXCEPTIONS.get(vc, vc)

    def validate_alias(self, alias, tone=0):
        if self.has_oto(alias, tone):
            return alias
        base_resolved = super().validate_alias(alias, tone)
        if base_resolved and base_resolved != alias:
            if self.has_oto(base_resolved, tone):
                return base_resolved
            alias = base_resolved
        for consonant in ["6r"]:
            alias = alias.replace(consonant, "3")
        return alias

    @staticmethod
    def _is_transition(type_):
        return type_ in ("VC", "V C", "VC-", "VCC", "VCC-", "codaCC", "C C", "VC C", "V-", "CC-")

    def _is_base_alias(self, alias):
        if not alias:
            return False
        t = self._classify(alias)
        if t in ("-V", "_V", "V", "-CV", "_CV", "CV"):
            return True
        if t == "Unknown":
            # CCV / VV bases end in a vowel symbol; 1nks, 1nks- etc. don't
            return any(alias.endswith(v) for v in self.vowels)
        return False

    def sync_attributes(self, notes, phoneme_symbols, start_index, attr_list):
        self._syll_of_index = [0] * len(phoneme_symbols)
        bases = 0
        for i in range(len(phoneme_symbols)):
            self._syll_of_index[i] = bases  # base phonemes seen before this one
            if self._is_base_alias(phoneme_symbols[i]):
                bases += 1
        super().sync_attributes(notes, phoneme_symbols, start_index, attr_list)

    def get_dynamic_phoneme_attributes(self, alias, index, current_attr, notes):
        if not self.unotes or not self.use_convel:
            return current_attr
        # manual VEL edits already arrive through current_attr
        if current_attr.consonant_stretch_ratio is not None and abs(current_attr.consonant_stretch_ratio - 1.0) > 0.0001:
            return current_attr
        j = self._syll_of_index[index] if 0 <= index < len(self._syll_of_index) else 0
        if self._is_transition(self._classify(alias)):
            j -= 1  # VC / CC / endings take the previous note
        j = min(j, len(notes) - 1)
        if j >= 0:
            target_un, _ = self._unote_at(notes[j].position)
        else:
            # before the first note of the group: use the note preceding the group
            own_un, _ = self._unote_at(notes[0].position)
            idx = self.unotes.index(own_un)
            target_un = self.unotes[idx - 1] if idx > 0 else own_un
        vel = self._calc_convel(target_un)
        current_attr.consonant_stretch_ratio = math.pow(2.0, (100.0 - vel) / 100.0)
        return current_attr

    def get_transition_basic_length_ms_with_attr(self, alias, tone, attr):
        oto_length = self.get_transition_basic_length_ms_by_oto(alias, tone, attr)
        for symbol, value in sorted(self.phoneme_overrides.items(), key=lambda kv: len(kv[0]), reverse=True):
            if cs_regex_word_boundary_match(alias, symbol):
                return self.get_transition_basic_length_ms_by_constant() * value
        return oto_length
