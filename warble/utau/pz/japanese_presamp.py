"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Plugin.Builtin/JapanesePresampPhonemizer.cs

the presamp.ini file watcher (PresampWatcher / globalPresampGeneration) is an editor feature for
reloading a changed presamp.ini and is not ported; presamp.ini is read once per set_singer.
"""

import re
import unicodedata

from .api import Phoneme, Phonemizer, alt_str, phonemizer
from .presamp import Presamp, singer_text_file_encoding

# in case voicebank is missing certain symbols
SUBSTITUTION = ["ty,ch,ts=t", "j,dy=d", "gy=g", "ky=k", "py=p", "ny=n", "ry=r", "my=m", "hy,f=h", "by,v=b", "dz=z", "l=r", "ly=l"]


def _substitute_lookup():
    out = {}
    for line in SUBSTITUTION:
        parts = line.split("=")
        for orig in parts[0].split(","):
            if orig in out:
                raise ValueError(f"duplicate key {orig}")  # ToDictionary throws on duplicates
            out[orig] = parts[1]
    return out


SUBSTITUTE_LOOKUP = _substitute_lookup()


def _match_value(pattern, s):
    """Regex.Match(s, pattern).Value: '' when nothing matches."""
    m = re.search(pattern, s)
    return m.group(0) if m else ""


def _nfc(s):
    return unicodedata.normalize("NFC", s)


@phonemizer("Japanese presamp Phonemizer", "JA VCV & CVVC", language="JA", openutau_class="OpenUtau.Plugin.Builtin.JapanesePresampPhonemizer",
            author="Maiko")
class JapanesePresampPhonemizer(Phonemizer):
    # CV, VCV, CVVCを含むすべての日本語VBをサポートする予定です。Will support all Japanese VBs including CV, VCV, CVVC
    # 基本的な仕様はpresampに準拠します。Basic behavior conforms to presamp
    # 歌詞に書かれた"強"などの表情は非対応。VoiceColorでやってもらいます。Append suffixes such as "強" written in the lyrics are not supported
    # 喉切り"・"はpresamp.iniに書いてなくても動くようなんとかします。I'll try to make it work even if "・" are not written in presamp.ini
    # Supporting: [VOWEL][CONSONANT][PRIORITY][REPLACE][ALIAS(VCPAD,VCVPAD)]
    # Partial supporting: [NUM][APPEND][PITCH] -> Using to exclude useless characters in lyrics

    def __init__(self):
        super().__init__()
        self.presamp = None

    def set_singer(self, singer):
        if self.singer is singer:
            return
        self.singer = singer
        if self.singer is None:
            return
        if self.presamp is None:
            self.presamp = Presamp()
            self.presamp.read_presamp_ini(singer.location, singer_text_file_encoding(singer))

    def process(self, notes, prev, next, prev_neighbour, next_neighbour, prev_neighbours):
        result = []
        pre_c_flag = False

        note = notes[0]
        current_lyric = self._parse_lyric_from_note(note)
        current_alias = self._parse_alias_from_lyric(current_lyric)  # exclude useless characters
        vcvpad = self.presamp.alias_rules.VCVPAD
        vcpad = self.presamp.alias_rules.VCPAD
        initial = f"-{vcvpad}{current_lyric}"
        cf_lyric = f"*{vcpad}{current_lyric}"

        vowel_upper = _match_value("[あいうえおんン]", current_lyric)
        glottal_cv_tests = [f"・{vcpad}{vowel_upper}", f"・{vowel_upper}", f"{vowel_upper}・", f"-{vcvpad}{vowel_upper}・", f"-{vcvpad}{vowel_upper}", initial,
                            current_lyric, vowel_upper]

        # Convert 1st phoneme
        if note.phonetic_hint:  # not convert
            oto = self._check_oto_until_hit([current_lyric], note)
            if oto is not None:
                current_lyric = oto.alias
        elif prev_neighbour is None:  # beginning of phrase
            pre_c_flag = True
            if "・" in current_lyric:
                tests = [f"-{vcvpad}{vowel_upper}・", f"・{vcpad}{vowel_upper}", f"{vowel_upper}・", f"・{vowel_upper}", f"-{vcvpad}{vowel_upper}", initial, current_lyric]
                oto1 = self._check_oto_until_hit(tests, note)
                if oto1 is not None:
                    current_lyric = oto1.alias
            else:
                oto = self._check_oto_until_hit([initial, current_lyric], note)
                if oto is not None:
                    current_lyric = oto.alias
        else:  # middle of phrase
            prev_lyric = self._parse_lyric_from_note(prev_neighbour)
            prev_alias = self._parse_alias_from_lyric(prev_lyric)  # exclude useless characters

            vc_glottal_stop = "[aiueonN]" + vcpad + "・$"  # [a ・]
            if prev_lyric == "・" or re.search(vc_glottal_stop, prev_lyric):
                # 喉切り(Glottal stop) prev is VC -> current is Glottal stop CV[・ あ][・あ][あ・][- あ][あ]
                oto = self._check_oto_until_hit(glottal_cv_tests, note)
                if oto is not None:
                    current_lyric = oto.alias
            elif "っ" in prev_lyric:
                # try CV
                oto = self._check_oto_until_hit([current_lyric, initial], note)
                if oto is not None:
                    current_lyric = oto.alias
            elif (prev_phoneme := self._try_get_presamp_phoneme(prev_alias)) is not None:
                current_phoneme = None
                if "・" in current_lyric:
                    # Glottal stop
                    tests = []
                    if re.search(vc_glottal_stop, current_lyric):  # current is VC = 2nd phoneme is not needed
                        tests = [current_lyric]
                        oto = self._check_oto_until_hit(tests, note)
                        if oto is not None:
                            return self.make_simple_result(oto.alias)
                    elif current_lyric == "・" and prev_phoneme.has_vowel:  # current is VC = 2nd phoneme is not needed
                        vc = f"{prev_phoneme.vowel}{vcpad}{current_lyric}"
                        tests = [vc, current_lyric]
                        oto = self._check_oto_until_hit(tests, note)
                        if oto is not None:
                            return self.make_simple_result(oto.alias)
                    elif prev_phoneme.has_vowel:  # current is VCV
                        tests.append(f"{prev_phoneme.vowel}{vcvpad}{current_lyric}")
                        tests.append(f"{prev_phoneme.vowel}{vcvpad}{vowel_upper}・")
                        tests.append(f"{prev_phoneme.vowel}{vcvpad}・{vowel_upper}")
                    tests.extend(glottal_cv_tests)  # current is CV
                    oto = self._check_oto_until_hit(tests, note)
                    if oto is not None:  # check VCV and CV
                        current_lyric = oto.alias
                elif (current_phoneme := self._try_get_presamp_phoneme(current_lyric)) is not None and current_phoneme.is_priority:
                    # Priority: not VCV, VC (almost C)
                    oto = self._check_oto_until_hit([current_lyric, initial], note)
                    if oto is not None:
                        current_lyric = oto.alias
                elif prev_phoneme.has_vowel:
                    prev_vow = prev_phoneme.vowel

                    if current_lyric == "っ" and next_neighbour is not None:  # っ = current is VC
                        next_lyric = self._parse_lyric_from_note(next_neighbour)
                        next_alias = self._parse_alias_from_lyric(next_lyric)

                        axtu1 = f"{prev_vow}{vcvpad}{current_lyric}"  # a っ
                        axtu2 = f"{prev_vow}{vcpad}{current_lyric}"  # a っ
                        tests2 = [axtu1, axtu2, current_lyric]
                        next_phoneme = self._try_get_presamp_phoneme(next_alias)
                        if next_phoneme is not None and next_phoneme.has_consonant:
                            tests2.insert(2, f"{prev_vow}{vcpad}{next_phoneme.consonant}")  # VC
                        oto2 = self._check_oto_until_hit(tests2, note)
                        if oto2 is not None:
                            return self.make_simple_result(oto2.alias)
                    else:  # try VCV, VC
                        vcv = f"{prev_vow}{vcvpad}{current_lyric}"
                        vc = f"{prev_vow}{vcpad}{current_lyric}"
                        oto = self._check_oto_until_hit([vcv, vc, cf_lyric, current_lyric], note)
                        if oto is not None:
                            current_lyric = oto.alias
                else:
                    # try CV
                    oto = self._check_oto_until_hit([current_lyric, initial], note)
                    if oto is not None:
                        current_lyric = oto.alias
            else:
                # try "- CV" (prev is R, breath, etc.)
                pre_c_flag = True
                oto = self._check_oto_until_hit([initial, current_lyric], note)
                if oto is not None:
                    current_lyric = oto.alias
        result.append(Phoneme(current_lyric, index=0))

        # Insert "- C"
        if (not note.phonetic_hint
                and pre_c_flag
                and vcvpad not in current_lyric
                and (phoneme := self._try_get_presamp_phoneme(current_alias)) is not None
                and phoneme.has_consonant
                and (self.presamp.priorities is None or phoneme.consonant not in self.presamp.priorities)):
            c_oto = self._check_oto_until_hit_index([f"-{vcvpad}{phoneme.consonant}"], note, 2)
            oto = self._check_oto_until_hit([current_lyric], note) if c_oto is not None else None
            if c_oto is not None and oto is not None:
                end_tick = notes[-1].position + notes[-1].duration
                attr = note.attr(0)
                ratio = attr.consonant_stretch_ratio if attr.consonant_stretch_ratio is not None else self.get_parent_consonant_stretch_ratio()
                c_length = max(30, -self.time_axis.ms_to_tick_at(-oto.preutter, end_tick) * ratio)

                if prev_neighbour is not None:
                    c_length = min(_div(prev_neighbour.duration, 2), c_length)
                elif prev is not None:
                    c_length = min(note.position - prev.position - prev.duration, c_length)

                # Convert.ToInt32 rounds half to even, like python's round
                result.insert(0, Phoneme(c_oto.alias, position=int(round(-c_length)), index=2))

        # Insert 2nd phoneme (when next doesn't have hint)
        if next_neighbour is not None and not next_neighbour.phonetic_hint:
            total_duration = sum(n.duration for n in notes)
            if self.tick_to_ms(total_duration) < 100 and not self.presamp.must_vc:
                return result

            next_lyric = self._parse_lyric_from_note(next_neighbour)
            next_alias = self._parse_alias_from_lyric(next_lyric)  # exclude useless characters

            # Without current vowel, VC cannot be created
            current_phoneme = self._try_get_presamp_phoneme(current_alias)
            if current_phoneme is None or not current_phoneme.has_vowel:
                return result
            vowel = current_phoneme.vowel

            if re.search("[aiueonN]" + vcvpad, next_lyric) or re.search("[aiueonN]" + vcpad, next_lyric):
                # next is VCV or VC (VC is not needed)
                return result
            else:
                if "・" in next_lyric:  # Glottal stop
                    if next_lyric == "・":  # next is VC (VC is not needed)
                        return result
                    else:
                        vowel_upper = _match_value("[あいうえおんン]", next_lyric)
                        # (Regex Match Value is never null, so the c# null check never returns)

                        # next is VCV (VC is not needed)
                        tests = [f"{vowel}{vcvpad}{next_lyric}", f"{vowel}{vcvpad}{vowel_upper}・", f"{vowel}{vcvpad}・{vowel_upper}"]
                        glottal_cv_tests = [f"・{vcpad}{vowel_upper}", f"・{vowel_upper}", f"{vowel_upper}・", f"-{vcvpad}{vowel_upper}・", f"-{vcvpad}{vowel_upper}",
                                            initial, next_lyric, vowel_upper]
                        tests.extend(glottal_cv_tests)
                        oto1 = self._check_oto_until_hit(tests, next_neighbour)
                        if oto1 is not None and f"{vowel}{vcvpad}" in oto1.alias:
                            return result

                        # next is CV (VC is needed)
                        oto1 = self._check_oto_until_hit_index([f"{vowel}{vcpad}・"], note, 1)
                        if oto1 is not None:
                            vc_phoneme = oto1.alias
                        else:
                            return result
                else:
                    # Without next consonant, VC cannot be created
                    next_phoneme = self._try_get_presamp_phoneme(next_alias)
                    if next_phoneme is None or not next_phoneme.has_consonant:
                        return result
                    consonant = next_phoneme.consonant

                    # If next is not priority and is convertable VC, VC is not needed
                    # If next is VCV, VC is not needed
                    if not next_phoneme.is_priority:
                        next_vcv = f"{vowel}{vcvpad}{next_alias}"
                        next_vc = f"{vowel}{vcpad}{next_alias}"
                        oto1 = self._check_oto_until_hit([next_vcv, next_vc, next_alias], next_neighbour)
                        if oto1 is not None and (re.search("[aiueonN]" + vcvpad, oto1.alias) or re.search("[aiueonN]" + vcpad, oto1.alias)):
                            return result

                    # Insert VC
                    vc_phoneme = f"{vowel}{vcpad}{consonant}"
                    vc_phonemes = [vc_phoneme]
                    # find potential substitute symbol
                    con = SUBSTITUTE_LOOKUP.get(consonant if consonant is not None else "")
                    if con is not None:
                        vc_phonemes.append(f"{vowel}{vcpad}{con}")
                    oto = self._check_oto_until_hit_index(vc_phonemes, note, 1)
                    if oto is not None:
                        vc_phoneme = oto.alias
                    else:
                        return result
            if vc_phoneme:
                vc_length = 120
                end_tick = notes[-1].position + notes[-1].duration
                next_attr = next_neighbour.attr(0)
                shift = next_attr.tone_shift if next_attr.tone_shift is not None else self.get_parent_tone_shift()
                color = next_attr.voice_color if next_attr.voice_color is not None else self.get_parent_voice_color()
                next_oto = self.singer.try_get_mapped_oto(next_lyric, next_neighbour.tone + shift, color)
                if next_oto is not None:
                    # If overlap is a negative value, vcLength is longer than Preutter
                    if next_oto.overlap < 0:
                        vc_length = -self.time_axis.ms_to_tick_at(-(next_oto.preutter - next_oto.overlap), end_tick)
                    else:
                        vc_length = -self.time_axis.ms_to_tick_at(-next_oto.preutter, end_tick)
                # Minimam is 30 tick, maximum is half of note
                ratio = next_attr.consonant_stretch_ratio if next_attr.consonant_stretch_ratio is not None else self.get_parent_consonant_stretch_ratio()
                vc_length = int(round(min(_div(total_duration, 2), max(30, vc_length * ratio))))

                result.append(Phoneme(vc_phoneme, position=total_duration - vc_length, index=1))

        return result

    def _check_oto_until_hit(self, inputs, note):
        attr = note.attr(0)
        color = attr.voice_color if attr.voice_color is not None else self.get_parent_voice_color()
        shift = attr.tone_shift if attr.tone_shift is not None else self.get_parent_tone_shift()
        alt = attr.alternate if attr.alternate is not None else self.get_parent_alternate()

        otos = []
        for test in inputs:
            oto_alt = self.singer.try_get_mapped_oto(test + alt_str(alt), note.tone + shift, color)
            if oto_alt is not None:
                otos.append(oto_alt)
            else:
                oto_candidacy = self.singer.try_get_mapped_oto(test, note.tone + shift, color)
                if oto_candidacy is not None:
                    otos.append(oto_candidacy)

        if otos:
            oto = next((o for o in otos if o.is_color_match(color)), None)
            if oto is None:
                oto = otos[0]
            return oto
        return None

    def _check_oto_until_hit_index(self, inputs, note, index):
        """the c# overload with an index (and a colorIndex out param that only feeds expressions)."""
        attr = note.attr(index)
        attr0 = note.attr(0)
        color = attr.voice_color if attr.voice_color is not None else (attr0.voice_color if attr0.voice_color is not None else self.get_parent_voice_color())
        shift = attr.tone_shift if attr.tone_shift is not None else (attr0.tone_shift if attr0.tone_shift is not None else self.get_parent_tone_shift())
        alt = attr.alternate if attr.alternate is not None else self.get_parent_alternate()

        otos = []
        for test in inputs:
            oto_alt = self.singer.try_get_mapped_oto(test + alt_str(alt), note.tone + shift, color)
            if oto_alt is not None:
                otos.append(oto_alt)
            else:
                oto_candidacy = self.singer.try_get_mapped_oto(test, note.tone + shift, color)
                if oto_candidacy is not None:
                    otos.append(oto_candidacy)

        if otos:
            oto = next((o for o in otos if o.is_color_match(color)), None)
            if oto is not None:
                return oto
            elif index != 1 and index != 2:  # Main phoneme is required, preC and VC are not required
                return otos[0]
        return None

    def _parse_lyric_from_note(self, note):
        lyric = _nfc(note.lyric)  # Normalize(): measures for Unicode
        if note.phonetic_hint:
            lyric = _nfc(note.phonetic_hint)
        else:
            # replace (exact match)
            if self.presamp.replace is not None:
                for key, value in self.presamp.replace.items():
                    if key == lyric:
                        lyric = value
        return lyric

    def _parse_alias_from_lyric(self, lyric):
        alias = self.presamp.parse_alias(lyric)[1]  # 0:preVowel, 1:phoneme, 2:suffix
        if alias != "・" and "・" in alias:
            alias = alias.replace("・", "")
        return alias

    def _try_get_presamp_phoneme(self, alias):
        p = self.presamp.phoneme_list.get(alias)
        if p is not None:
            return p
        match = re.search(r".+([ぁぃぅぇぉゃゅょ])", alias)
        if match:
            return self.presamp.phoneme_list.get(match.group(1))
        return None


def _div(a, b):
    """c# integer division truncates toward zero."""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q
