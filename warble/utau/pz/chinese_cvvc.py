"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Plugin.Builtin/ChineseCVVCPhonemizer.cs"""

import codecs
import os
import re

from .api import Phoneme, Phonemizer, phonemizer
from .base_chinese import change_lyric, romanize as base_romanize, zip_change

# .NET Encoding.GetEncoding names -> python codecs (.NET shift_jis is code page 932, etc.)
_DOTNET_CODECS = {"shift_jis": "cp932", "shift-jis": "cp932", "sjis": "cp932", "gb2312": "gbk", "gbk": "gbk", "big5": "cp950",
                  "euc-kr": "cp949", "ks_c_5601-1987": "cp949", "utf-8": "utf-8", "utf8": "utf-8"}


def text_file_encoding(singer):
    """USinger.TextFileEncoding: shift_jis unless character.yaml sets text_file_encoding."""
    name = getattr(getattr(singer, "bank", None), "declared_encoding", None) or "shift_jis"
    return _DOTNET_CODECS.get(name.lower(), name)


def read_lines(path, encoding):
    """StreamReader(path, encoding) with bom detection, then ReadLine until EOF: lines end at \\r\\n,
    \\r or \\n only (not str.splitlines). invalid bytes decode to replacement chars like .NET."""
    with open(path, "rb") as f:
        data = f.read()
    for bom, enc in ((codecs.BOM_UTF8, "utf-8"), (codecs.BOM_UTF32_LE, "utf-32-le"), (codecs.BOM_UTF32_BE, "utf-32-be"),
                     (codecs.BOM_UTF16_LE, "utf-16-le"), (codecs.BOM_UTF16_BE, "utf-16-be")):
        if data.startswith(bom):
            data = data[len(bom):]
            encoding = enc
            break
    text = data.decode(encoding, errors="replace")
    lines = re.split(r"\r\n|\r|\n", text)
    if lines and lines[-1] == "":
        lines.pop()  # ReadLine returns no extra line after a trailing newline
    return lines


class IniBlock:
    def __init__(self):
        self.header = None
        self.lines = []


def read_blocks(lines, header_pattern, trim=True):
    """OpenUtau.Classic.Ini.ReadBlocks"""
    header_regex = re.compile(header_pattern)
    blocks = []
    for line in lines:
        if trim:
            line = line.strip()
        if not line:
            continue
        if header_regex.search(line):
            blocks.append(IniBlock())
        if not blocks:
            raise ValueError("Unexpected beginning of ust file.")  # FileFormatException
        blocks[-1].lines.append(line)
    for block in blocks:
        block.header = block.lines[0]
        block.lines.pop(0)
    return blocks


def find_block(blocks, header):
    return next((b for b in blocks if b.header == header), None)


def block_lines(blocks, header):
    b = find_block(blocks, header)
    if b is None:
        raise AttributeError("Object reference not set to an instance of an object.")  # NullReferenceException
    return b.lines


def cs_round(x):
    """Convert.ToInt32(double): round half to even."""
    return int(round(x))


@phonemizer("Chinese CVVC Phonemizer", "ZH CVVC", language="ZH", openutau_class="OpenUtau.Plugin.Builtin.ChineseCVVCPhonemizer")
class ChineseCVVCPhonemizer(Phonemizer):
    def __init__(self):
        super().__init__()
        self.vowels = {}
        self.consonants = {}
        self.replace = {}

    def _mapped(self, phoneme, tone, attr):
        shift = attr.tone_shift if attr.tone_shift is not None else self.get_parent_tone_shift()
        color = attr.voice_color if attr.voice_color is not None else self.get_parent_voice_color()
        return self.singer.try_get_mapped_oto(phoneme, tone + shift, color)

    def process(self, notes, prev, next, prev_neighbour, next_neighbour, prev_neighbours):
        lyric = notes[0].lyric
        for k, v in self.replace.items():  # replace (exact match)
            if k == lyric:
                lyric = v
        consonant = self.consonants.get(lyric, lyric)
        prev_vowel = "-"
        if prev_neighbour is not None:
            prev_lyric = prev_neighbour.lyric
            if prev_lyric in self.vowels:
                prev_vowel = self.vowels[prev_lyric]
        attr0 = notes[0].attr(0)
        attr1 = notes[0].attr(1)
        attr2 = notes[0].attr(2)
        tone = notes[0].tone
        if lyric == "-" or lyric.lower() == "r":
            oto1 = self._mapped(f"{prev_vowel} R", tone, attr0)
            if oto1 is not None:
                return [Phoneme(oto1.alias)]
            return [Phoneme(f"{prev_vowel} R")]
        curr_vowel = self.vowels.get(lyric, lyric)
        total_duration = sum(n.duration for n in notes)

        oto = self._mapped(f"{prev_vowel} {lyric}", tone, attr0)
        if oto is not None:
            if next_neighbour is None:
                oto1 = self._mapped(f"{curr_vowel} R", tone, attr1)
                if oto1 is not None:
                    # automatically add ending if present
                    return [Phoneme(oto.alias), Phoneme(oto1.alias, position=total_duration - min(total_duration // 6, 60))]
            return [Phoneme(oto.alias)]
        vc_len = 120
        end_tick = notes[-1].position + notes[-1].duration
        cv_oto = self._mapped(lyric, tone, attr1)
        if cv_oto is not None:
            vc_len = -self.time_axis.ms_to_tick_at(-cv_oto.preutter, end_tick)
            if cv_oto.overlap == 0 and vc_len < 120:
                vc_len = min(120, vc_len * 2)  # explosive consonant with short preutter.
            if cv_oto.overlap < 0:
                vc_len = -self.time_axis.ms_to_tick_at(-(cv_oto.preutter - cv_oto.overlap), end_tick)

        cv_oto_simple = self._mapped(lyric, tone, attr0)
        if cv_oto_simple is not None:
            lyric = cv_oto_simple.alias

        ratio = attr1.consonant_stretch_ratio if attr1.consonant_stretch_ratio is not None else self.get_parent_consonant_stretch_ratio()
        vc_phoneme = f"{prev_vowel} {consonant}"
        if prev_neighbour is not None:
            oto = self._mapped(vc_phoneme, prev_neighbour.tone, attr0)
            if oto is not None:
                vc_phoneme = oto.alias
            # prevDuration calculated on basis of previous note length
            prev_duration = notes[0].position - prev_neighbour.position
            vc_len = cs_round(min(prev_duration / 1.5, max(30, vc_len * ratio)))
        else:
            oto = self._mapped(vc_phoneme, tone, attr0)
            if oto is not None:
                vc_phoneme = oto.alias
            # no previous note, so length can be minimum velocity regardless of oto
            vc_len = cs_round(min(vc_len * 2, max(30, vc_len * ratio)))

        cv_alias = cv_oto.alias if cv_oto is not None else lyric
        if next_neighbour is None:  # automatically add ending if present
            oto0 = self._mapped(f"{prev_vowel} {lyric}", tone, attr0)
            if oto0 is not None:
                oto_end = self._mapped(f"{curr_vowel} R", tone, attr1)
                if oto_end is not None:
                    return [Phoneme(oto0.alias), Phoneme(oto_end.alias, position=total_duration - min(total_duration // 6, 60))]
            else:
                # use vc if present
                vc_oto1 = self._mapped(vc_phoneme, tone, attr0) if prev_neighbour is None else None
                vc_oto2 = None
                if prev_neighbour is None and vc_oto1 is not None:
                    vc_phoneme = vc_oto1.alias
                    oto_end = self._mapped(f"{curr_vowel} R", tone, attr2)
                    if oto_end is not None:
                        return [Phoneme(vc_phoneme, position=-vc_len), Phoneme(cv_alias),
                                Phoneme(oto_end.alias, position=total_duration - min(total_duration // 6, 60))]
                elif prev_neighbour is not None:
                    vc_oto2 = self._mapped(vc_phoneme, prev_neighbour.tone, attr0)
                    if vc_oto2 is not None:
                        vc_phoneme = vc_oto2.alias
                        oto_end = self._mapped(f"{curr_vowel} R", tone, attr2)
                        if oto_end is not None:
                            return [Phoneme(vc_phoneme, position=-vc_len), Phoneme(cv_alias),
                                    Phoneme(oto_end.alias, position=total_duration - min(total_duration // 6, 60))]
                # just base note and ending
                oto_end1 = self._mapped(f"{curr_vowel} R", tone, attr1)
                if oto_end1 is not None:
                    return [Phoneme(cv_oto_simple.alias if cv_oto_simple is not None else lyric),
                            Phoneme(oto_end1.alias, position=total_duration - min(total_duration // 6, 60))]

        oto = self._mapped(vc_phoneme, tone, attr0)
        if oto is not None:
            return [Phoneme(vc_phoneme, position=-vc_len), Phoneme(cv_alias)]
        return [Phoneme(cv_oto_simple.alias if cv_oto_simple is not None else lyric)]

    def set_singer(self, singer):
        if self.singer is singer:
            return
        self.singer = singer
        self.vowels.clear()
        self.consonants.clear()
        self.replace.clear()
        if self.singer is None:
            return
        try:
            file = os.path.join(singer.location, "presamp.ini")
            lines = read_lines(file, text_file_encoding(singer))
            blocks = read_blocks(lines, r"\[\w+\]")
            for line in block_lines(blocks, "[VOWEL]"):
                parts = line.split("=")
                if len(parts) >= 3:
                    vowel_lower = parts[0]
                    for sound in parts[2].split(","):
                        self.vowels[sound] = vowel_lower
            for line in block_lines(blocks, "[CONSONANT]"):
                parts = line.split("=")
                if len(parts) >= 3:
                    for sound in parts[1].split(","):
                        self.consonants[sound] = parts[0]
            for line in block_lines(blocks, "[REPLACE]"):
                parts = line.split("=")
                if len(parts) < 2:
                    raise IndexError("Index was outside the bounds of the array.")
                self.replace[parts[0]] = parts[1]
        except Exception:  # noqa: BLE001 - openutau logs "failed to load presamp.ini" and keeps what it read
            pass

    def romanize(self, lyrics):
        return base_romanize(lyrics)

    def romanize_notes(self, groups):
        result_lyrics = self.romanize([g[0].lyric for g in groups])
        zip_change(groups, result_lyrics, change_lyric)

    def set_up(self, groups):
        super().set_up(groups)
        self.romanize_notes(groups)
