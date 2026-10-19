"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Core/Classic/Presamp.cs

the presamp.ini model. openutau's built-in default presamp (used when a bank has no presamp.ini,
and as the starting point that a presamp.ini's blocks override) is not a resource file: it is the
defVowels / defConsonants / defReplace / defNums / defAppends / defPitches tables at the bottom of
Presamp.cs (themselves taken from https://delta-kimigatame.hatenablog.jp/entry/ar483589), so it is
ported here as the same tables.
"""

import codecs
import os
import re

# ---- c# helpers -----------------------------------------------------------------------------------

# .NET encoding names (character.yaml text_file_encoding, Encoding.GetEncoding) -> python codecs.
# .NET's "shift_jis" is code page 932, i.e. python's cp932; 936 is gbk; 949 cp949; 950 cp950.
_NET_CODEC = {
    "shift_jis": "cp932", "shift-jis": "cp932", "sjis": "cp932", "x-sjis": "cp932", "ms_kanji": "cp932", "csshiftjis": "cp932",
    "windows-31j": "cp932", "cp932": "cp932", "932": "cp932",
    "gb2312": "gbk", "gbk": "gbk", "cp936": "gbk", "936": "gbk", "x-cp20936": "gbk",
    "ks_c_5601-1987": "cp949", "cp949": "cp949", "949": "cp949", "euc-kr": "euc_kr",
    "big5": "cp950", "cp950": "cp950", "950": "cp950",
    "utf-8": "utf-8", "utf8": "utf-8", "utf-16": "utf-16-le", "utf-16le": "utf-16-le", "unicode": "utf-16-le", "utf-16be": "utf-16-be",
}


def net_codec(name):
    """the python codec for a .NET encoding name (defaults to shift_jis like VoicebankLoader)."""
    if not name:
        return "cp932"
    n = str(name).strip().lower()
    if n in _NET_CODEC:
        return _NET_CODEC[n]
    try:
        return codecs.lookup(n).name
    except LookupError:
        return "cp932"


def singer_text_file_encoding(singer):
    """USinger.TextFileEncoding: character.yaml's text_file_encoding, else shift_jis."""
    bank = getattr(singer, "bank", None)
    return net_codec(getattr(bank, "declared_encoding", None))


def _strict_ok(data, codec):
    try:
        data.decode(codec, errors="strict")
        return True
    except (UnicodeDecodeError, LookupError):
        return False


def read_all_lines(path, codec):
    """File.ReadAllLines(path, encoding): a byte order mark wins over the given encoding, invalid
    bytes become replacement characters, and lines end only at \\r\\n, \\r or \\n."""
    with open(path, "rb") as f:
        data = f.read()
    return split_lines(decode_with_bom(data, codec))


def decode_with_bom(data, codec):
    if data.startswith(codecs.BOM_UTF8):
        return data[3:].decode("utf-8", errors="replace")
    if data.startswith(codecs.BOM_UTF32_LE):
        return data[4:].decode("utf-32-le", errors="replace")
    if data.startswith(codecs.BOM_UTF16_LE):
        return data[2:].decode("utf-16-le", errors="replace")
    if data.startswith(codecs.BOM_UTF16_BE):
        return data[2:].decode("utf-16-be", errors="replace")
    return data.decode(codec, errors="replace")


def split_lines(text):
    """TextReader.ReadLine semantics (str.splitlines would also split on \\x85, \\u2028 etc)."""
    lines = re.split(r"\r\n|\r|\n", text)
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def cs_split(s, sep):
    """string.Split(new string[] { sep }, StringSplitOptions.None): an empty separator is ignored."""
    if sep == "":
        return [s]
    return s.split(sep)


def _try_parse_int(s):
    """int.TryParse with NumberStyles.Integer."""
    m = re.fullmatch(r"[ \t\n\v\f\r]*([+-]?[0-9]+)[ \t\n\v\f\r]*", s)
    if not m:
        return None
    v = int(m.group(1))
    if v < -2147483648 or v > 2147483647:
        return None
    return v


# ---- the model --------------------------------------------------------------------------------------


class PresampPhoneme:
    def __init__(self):
        self.phoneme = ""
        self.vowel = ""
        self.vowel_vol = 100
        self.consonant = ""
        self.not_clossfade = False
        self.is_priority = False

    @property
    def has_vowel(self):
        return self.vowel != ""

    @property
    def has_consonant(self):
        return self.consonant != ""


class PresampVowel:
    def __init__(self):
        self.vowel_lower = ""
        self.vowel_upper = ""
        self.phonemes = []
        self.vol = 100


class PresampConsonant:
    def __init__(self):
        self.consonant = ""
        self.phonemes = []
        self.not_clossfade = False


class PresampAliasRules:
    def __init__(self):
        self.VCPAD = " "
        self.VCVPAD = " "
        self._vcv = "%v%%VCVPAD%%CV%"
        # write eventually
        self.BEGINING_CV = "-%VCVPAD%%CV%"
        self.CROSS_CV = "*%VCVPAD%%CV%"
        self.VC = "%v%%vcpad%%c%,%c%%vcpad%%c%"
        self.CV = "%CV%,%c%%V%"
        self.C = "%c%"
        self.LONG_V = "%V%ー"
        self.ENDING1 = "%v%%VCPAD%R"
        self.ENDING2 = "-"

    @property
    def VCV(self):
        return self._replacer(self._vcv)

    @VCV.setter
    def VCV(self, value):
        self._vcv = value

    def _replacer(self, s):
        return s.replace("%CVPAD%", self.VCPAD).replace("%VCVPAD%", self.VCVPAD)


class Presamp:
    # presamp.ini specification https://delta-kimigatame.hatenablog.jp/entry/ar483589

    def __init__(self):
        self.file_exists = False
        self.vowels = {}
        self.consonants = {}
        self.priorities = []
        self.replace = {}
        self.alias_rules = PresampAliasRules()
        self.prefixs = []
        self.suffix_order = []
        self.nums = []
        self.appends = []
        self.pitches = []
        self.alias_priority_default = []
        self.alias_priority_dif_append = []
        self.alias_priority_dif_pitch = []
        self.split = True
        self.must_vc = False
        self.cflags = "p0"
        self.vc_length_from_cv = True
        # 0: not 1: add ending note 2: convert last note
        self.add_ending = 1
        self.phoneme_list = {}
        self.reset()
        self._make_phoneme_list()

    def reset(self):
        self.set_vowels(DEF_VOWELS)
        self.set_consonants(DEF_CONSONANTS)
        self.priorities = ["k", "ky", "g", "gy", "t", "ty", "d", "dy", "ch", "ts", "b", "by", "p", "py", "r", "ry"]
        self.replace = dict(DEF_REPLACE)
        self.alias_rules = PresampAliasRules()
        self.prefixs = []  # def: empty
        self.suffix_order = ["%num%", "%append%", "%pitch%"]
        self.nums = list(DEF_NUMS)
        self.appends = list(DEF_APPENDS)
        self.pitches = list(DEF_PITCHES)
        self.alias_priority_default = ["VCV", "CVVC", "CROSS_CV", "CV", "BEGINING_CV"]
        self.alias_priority_dif_append = ["CVVC", "VCV", "CROSS_CV", "CV", "BEGINING_CV"]
        self.alias_priority_dif_pitch = ["CVVC", "VCV", "CROSS_CV", "CV", "BEGINING_CV"]
        self.split = True
        self.must_vc = False
        self.cflags = "p0"
        self.vc_length_from_cv = True
        self.add_ending = 1

    def read_presamp_ini(self, dir_path, text_file_encoding="cp932"):
        """text_file_encoding is a python codec name (see singer_text_file_encoding)."""
        self.reset()
        try:
            ini_path = os.path.join(dir_path, "presamp.ini")
            if not os.path.isfile(ini_path):
                self.file_exists = False
                self._make_phoneme_list()
                return
            self.file_exists = True

            # Smart Encoding Auto-Detection (UTF-8 -> Strict ANSI -> Fallbacks)
            with open(ini_path, "rb") as f:
                data = f.read()
            encoding = text_file_encoding
            if _strict_ok(data, "utf-8"):
                encoding = "utf-8"
            else:
                parsed = False
                # singer's default text encoding
                if _strict_ok(data, text_file_encoding):
                    encoding = text_file_encoding
                    parsed = True
                # cycle through common ANSI encodings (Japanese, Chinese, Korean, Traditional Chinese)
                if not parsed:
                    for cp in ("cp932", "gbk", "cp949", "cp950"):  # Shift-JIS, GBK, EUC-KR, Big5
                        if _strict_ok(data, cp):
                            encoding = cp
                            break

            # Manual Parsing to preserve exact Case Sensitivity
            lines = split_lines(decode_with_bom(data, encoding))
            current_block = ""
            acc = {"v": None, "c": None}  # vowelLines, consonantLines

            for line in lines:
                if line.startswith(";"):
                    continue
                if line.startswith("[") and line.endswith("]"):
                    current_block = line.upper()
                    # Clear lists upon entering block to prepare for custom data overriding defaults
                    if current_block == "[VOWEL]":
                        self.vowels.clear()
                    elif current_block == "[CONSONANT]":
                        self.consonants.clear()
                    elif current_block == "[PRIORITY]":
                        self.priorities.clear()
                    elif current_block == "[REPLACE]":
                        self.replace.clear()
                    elif current_block == "[PRE]":
                        self.prefixs.clear()
                    elif current_block == "[NUM]":
                        self.nums.clear()
                    elif current_block == "[APPEND]":
                        self.appends.clear()
                    elif current_block == "[PITCH]":
                        self.pitches.clear()
                    elif current_block == "[ALIAS_PRIORITY]":
                        self.alias_priority_default.clear()
                    elif current_block == "[ALIAS_PRIORITY_DIFAPPEND]":
                        self.alias_priority_dif_append.clear()
                    elif current_block == "[ALIAS_PRIORITY_DIFPITCH]":
                        self.alias_priority_dif_pitch.clear()
                    elif current_block == "[CFLAGS]":
                        self.cflags = ""
                    continue

                try:
                    self._read_line(current_block, line, acc)
                except Exception:  # noqa: BLE001 - Log.Error(e, "failed to load presamp.ini block")
                    continue

            if acc["v"] is not None:
                self.set_vowels(acc["v"])
            if acc["c"] is not None:
                self.set_consonants(acc["c"])
        except Exception:  # noqa: BLE001 - Log.Error(e, "failed to load presamp.ini")
            pass

        self._make_phoneme_list()

    def _read_line(self, current_block, line, acc):
        if current_block == "[VOWEL]":
            if acc["v"] is None:
                acc["v"] = []
            acc["v"].append(line)
        elif current_block == "[CONSONANT]":
            if acc["c"] is None:
                acc["c"] = []
            acc["c"].append(line)
        elif current_block == "[PRIORITY]":
            self.priorities.extend(line.split(","))
        elif current_block == "[REPLACE]":
            s = line.split("=", 1)
            if len(s) >= 2:
                self.replace[s[0]] = s[1]
        elif current_block == "[ALIAS]":
            parts = line.split("=", 1)
            if len(parts) < 2:
                return
            key = parts[0].upper()
            r = self.alias_rules
            if key == "VCV":
                r.VCV = parts[1]
            elif key == "BEGINING_CV":
                r.BEGINING_CV = parts[1]
            elif key == "CROSS_CV":
                r.CROSS_CV = parts[1]
            elif key == "VC":
                r.VC = parts[1]
            elif key == "CV":
                r.CV = parts[1]
            elif key == "C":
                r.C = parts[1]
            elif key == "LONG_V":
                r.LONG_V = parts[1]
            elif key == "VCPAD":
                if parts[1]:
                    r.VCPAD = parts[1]
            elif key == "VCVPAD":
                if parts[1]:
                    r.VCVPAD = parts[1]
            elif key == "ENDING1":
                r.ENDING1 = parts[1]
            elif key == "ENDING2":
                r.ENDING2 = parts[1]
        elif current_block in ("[ENDTYPE]", "[ENDTYPE1]"):
            self.alias_rules.ENDING1 = line
        elif current_block == "[ENDTYPE2]":
            self.alias_rules.ENDING2 = line
        elif current_block == "[VCPAD]":
            if line:
                self.alias_rules.VCPAD = line
        elif current_block == "[PRE]":
            if line not in self.prefixs:
                self.prefixs.append(line)
        elif current_block == "[SU]":
            if "%num%" not in line or "%append%" not in line or "%pitch%" not in line:
                return
            if not re.fullmatch(r"(?:%num%|%append%|%pitch%)+", line):
                return
            self.suffix_order.clear()
            for m in re.finditer(r"%num%|%append%|%pitch%", line):
                self.suffix_order.append(m.group(0))
        elif current_block == "[NUM]":
            if not re.search(r"^@.+@$", line):
                self.nums.append(line)
        elif current_block == "[APPEND]":
            if not re.search(r"^@.+@$", line):
                self.appends.append(line)
        elif current_block == "[PITCH]":
            if not re.search(r"^@.+@$", line):
                self.pitches.append(line)
        elif current_block == "[ALIAS_PRIORITY]":
            if len(self.alias_priority_default) >= 5:  # default count is 5
                self.alias_priority_default.clear()
                self.alias_priority_default.append(line)
        elif current_block == "[ALIAS_PRIORITY_DIFAPPEND]":
            if len(self.alias_priority_dif_append) >= 5:
                self.alias_priority_dif_append.clear()
                self.alias_priority_dif_append.append(line)
        elif current_block == "[ALIAS_PRIORITY_DIFPITCH]":
            if len(self.alias_priority_dif_pitch) >= 5:
                self.alias_priority_dif_pitch.clear()
                self.alias_priority_dif_pitch.append(line)
        elif current_block == "[SPLIT]":
            if line == "0":
                self.split = False
            elif line == "1":
                self.split = True
        elif current_block == "[MUSTVC]":
            if line == "0":
                self.must_vc = False
            elif line == "1":
                self.must_vc = True
        elif current_block == "[CFLAGS]":
            self.cflags = line
        elif current_block == "[VCLENGTH]":
            if line == "0":
                self.vc_length_from_cv = True
            elif line == "1":
                self.vc_length_from_cv = False
        elif current_block == "[ENDFLAG]":
            result = _try_parse_int(line)
            if result is not None:
                self.add_ending = result
        # [VERSION] [LOCALE] [RESAMP] [TOOL] [BATNUM]: Not for voicebanks

    def _make_phoneme_list(self):
        self.phoneme_list.clear()
        for pc in self.consonants.values():
            if pc.consonant not in self.phoneme_list:
                pp = PresampPhoneme()
                pp.phoneme = pc.consonant
                pp.consonant = pc.consonant
                pp.not_clossfade = pc.not_clossfade
                self.phoneme_list[pc.consonant] = pp
            for phoneme in pc.phonemes:
                if phoneme not in self.phoneme_list:
                    pp = PresampPhoneme()
                    pp.phoneme = phoneme
                    pp.consonant = pc.consonant
                    pp.not_clossfade = pc.not_clossfade
                    self.phoneme_list[phoneme] = pp
        for pv in self.vowels.values():
            for phoneme in pv.phonemes:
                pp = self.phoneme_list.get(phoneme)
                if pp is not None:
                    pp.vowel = pv.vowel_lower
                    pp.vowel_vol = pv.vol
                else:
                    pp = PresampPhoneme()
                    pp.phoneme = phoneme
                    pp.vowel = pv.vowel_lower
                    pp.vowel_vol = pv.vol
                    self.phoneme_list[phoneme] = pp
        for pp in self.phoneme_list.values():  # 拗音の母音情報をゃゅょから取得する Vowel completion
            if not pp.has_vowel:
                # Substring(Length - 1) throws on an empty phoneme, like c#
                if len(pp.phoneme) < 1:
                    raise ValueError("startIndex cannot be larger than length of string.")
                vowel = self.phoneme_list.get(pp.phoneme[-1:])
                if vowel is not None:
                    pp.vowel = vowel.vowel
                    pp.vowel_vol = vowel.vowel_vol
        for p in self.priorities:
            phoneme = self.phoneme_list.get(p)
            if phoneme is not None:
                phoneme.is_priority = True

    def parse_alias(self, lyric):
        """Break down lyric. -> [preVowel, phoneme, suffix]"""
        pre_vowel = ""
        phoneme = lyric
        suffix = ""

        r = self.alias_rules
        if r.VCPAD and r.VCPAD in phoneme:
            split = cs_split(phoneme, r.VCPAD)
            if len(split) > 1:
                pre_vowel = split[0]
                phoneme = split[1]
        elif r.VCVPAD and r.VCVPAD in phoneme:
            split = cs_split(phoneme, r.VCVPAD)
            if len(split) > 1:
                pre_vowel = split[0]
                phoneme = split[1]

        if phoneme == "":
            return [pre_vowel, phoneme, suffix]

        saving = phoneme[:1]
        phoneme = phoneme[1:]

        for group in (self.nums, self.appends, self.pitches):
            for n in group:
                if n in phoneme:
                    split = cs_split(phoneme, n)
                    suffix = re.sub(split[0], "", phoneme, count=1) + suffix
                    phoneme = split[0]
        if "_" in phoneme:
            split = phoneme.split("_")
            suffix = re.sub(split[0], "", phoneme, count=1) + suffix
            phoneme = split[0]

        return [pre_vowel, saving + phoneme, suffix]

    def set_vowels(self, lst):
        if isinstance(lst, dict):
            self.vowels = lst
            return
        d = {}
        for line in lst:
            parts = line.split("=")
            if len(parts) >= 3:
                vowel = PresampVowel()
                vowel.vowel_lower = parts[0]
                vowel.vowel_upper = parts[1]
                for sound in parts[2].split(","):
                    vowel.phonemes.append(sound)
                if len(parts) >= 4:
                    vol = _try_parse_int(parts[3])
                    if vol is not None:
                        vowel.vol = vol
                # Assign via indexer to bypass Duplicate Key crashes
                d[vowel.vowel_lower] = vowel
        self.vowels = d

    def set_consonants(self, lst):
        if isinstance(lst, dict):
            self.consonants = lst
            return
        d = {}
        for line in lst:
            parts = line.split("=")
            if len(parts) >= 2:
                consonant = PresampConsonant()
                consonant.consonant = parts[0]
                for sound in parts[1].split(","):
                    consonant.phonemes.append(sound)
                if len(parts) >= 3 and parts[2] == "1":
                    consonant.not_clossfade = True
                # Assign via indexer to bypass Duplicate Key crashes
                d[consonant.consonant] = consonant
        self.consonants = d


# ---- default value of presamp.ini (from https://delta-kimigatame.hatenablog.jp/entry/ar483589 ) ----

DEF_VOWELS = [
    "a=あ=ぁ,あ,か,が,さ,ざ,た,だ,な,は,ば,ぱ,ま,ゃ,や,ら,わ,ァ,ア,カ,ガ,サ,ザ,タ,ダ,ナ,ハ,バ,パ,マ,ャ,ヤ,ラ,ワ=100",
    "i=い=ぃ,い,き,ぎ,し,じ,ち,ぢ,に,ひ,び,ぴ,み,り,ゐ,ィ,イ,キ,ギ,シ,ジ,チ,ヂ,ニ,ヒ,ビ,ピ,ミ,リ,ヰ=100",
    "u=う=ぅ,う,く,ぐ,す,ず,つ,づ,ぬ,ふ,ぶ,ぷ,む,ゅ,ゆ,る,ゥ,ウ,ク,グ,ス,ズ,ツ,ヅ,ヌ,フ,ブ,プ,ム,ュ,ユ,ル,ヴ=100",
    "e=え=ぇ,え,け,げ,せ,ぜ,て,で,ね,へ,べ,ぺ,め,れ,ゑ,ェ,エ,ケ,ゲ,セ,ゼ,テ,デ,ネ,ヘ,ベ,ペ,メ,レ,ヱ=100",
    "o=お=ぉ,お,こ,ご,そ,ぞ,と,ど,の,ほ,ぼ,ぽ,も,ょ,よ,ろ,を,ォ,オ,コ,ゴ,ソ,ゾ,ト,ド,ノ,ホ,ボ,ポ,モ,ョ,ヨ,ロ,ヲ=100",
    "n=ん=ん=100",
    "N=ン=ン=100",
]
DEF_CONSONANTS = [
    "ch=ch,ち,ちぇ,ちゃ,ちゅ,ちょ=1",
    "gy=gy,ぎ,ぎぇ,ぎゃ,ぎゅ,ぎょ=1",
    "ts=ts,つ,つぁ,つぃ,つぇ,つぉ=1",
    "ty=ty,てぃ,てぇ,てゃ,てゅ,てょ=1",
    "py=py,ぴ,ぴぇ,ぴゃ,ぴゅ,ぴょ=1",
    "ry=ry,り,りぇ,りゃ,りゅ,りょ=1",
    "ny=ny,に,にぇ,にゃ,にゅ,にょ=0",
    "r=r,ら,る,れ,ろ=1",
    "hy=hy,ひ,ひぇ,ひゃ,ひゅ,ひょ=0",
    "dy=dy,でぃ,でぇ,でゃ,でゅ,でょ=1",
    "by=by,び,びぇ,びゃ,びゅ,びょ=1",
    "b=b,ば,ぶ,べ,ぼ=1",
    "d=d,だ,で,ど,どぅ=1",
    "g=g,が,ぐ,げ,ご=1",
    "f=f,ふ,ふぁ,ふぃ,ふぇ,ふぉ=0",
    "h=h,は,へ,ほ=0",
    "k=k,か,く,け,こ=1",
    "j=j,じ,じぇ,じゃ,じゅ,じょ=0",
    "m=m,ま,む,め,も=0",
    "n=n,な,ぬ,ね,の=0",
    "p=p,ぱ,ぷ,ぺ,ぽ=1",
    "s=s,さ,す,すぃ,せ,そ=0",
    "sh=sh,し,しぇ,しゃ,しゅ,しょ=0",
    "t=t,た,て,と,とぅ=1",
    "w=w,うぃ,うぅ,うぇ,うぉ,わ,を=0",
    "v=v,ヴ,ヴぁ,ヴぃ,ヴぅ,ヴぇ,ヴぉ=0",
    "y=y,いぃ,いぇ,や,ゆ,よ,ゐ,ゑ=0",
    "ky=ky,き,きぇ,きゃ,きゅ,きょ=1",
    "z=z,ざ,ず,ずぃ,ぜ,ぞ=0",
    "my=my,み,みぇ,みゃ,みゅ,みょ=0",
]

DEF_REPLACE = {
    "N": "ン", "a": "あ", "ba": "ば", "be": "べ", "bi": "び", "bo": "ぼ", "bu": "ぶ", "bya": "びゃ", "bye": "びぇ", "byi": "び",
    "byo": "びょ", "byu": "びゅ", "cha": "ちゃ", "che": "ちぇ", "chi": "ち", "cho": "ちょ", "chu": "ちゅ", "da": "だ", "de": "で",
    "dha": "でゃ", "dhe": "でぇ", "dhi": "でぃ", "dho": "でょ", "dhu": "でゅ", "di": "でぃ", "do": "ど", "du": "どぅ", "e": "え",
    "fa": "ふぁ", "fe": "ふぇ", "fi": "ふぃ", "fo": "ふぉ", "fu": "ふ", "fyu": "ふゅ", "ga": "が", "ge": "げ", "gi": "ぎ", "go": "ご",
    "gu": "ぐ", "gya": "ぎゃ", "gye": "ぎぇ", "gyi": "ぎ", "gyo": "ぎょ", "gyu": "ぎゅ", "ha": "は", "he": "へ", "hi": "ひ", "ho": "ほ",
    "hu": "ふ", "hya": "ひゃ", "hye": "ひぇ", "hyi": "ひ", "hyo": "ひょ", "hyu": "ひゅ", "i": "い", "ja": "じゃ", "je": "じぇ",
    "ji": "じ", "jo": "じょ", "ju": "じゅ", "ka": "か", "ke": "け", "ki": "き", "ko": "こ", "ku": "く", "kya": "きゃ", "kye": "きぇ",
    "kyi": "き", "kyo": "きょ", "kyu": "きゅ", "ma": "ま", "me": "め", "mi": "み", "mo": "も", "mu": "む", "mya": "みゃ", "mye": "みぇ",
    "myi": "み", "myo": "みょ", "myu": "みゅ", "n": "ん", "na": "な", "ne": "ね", "ni": "に", "no": "の", "nu": "ぬ", "nya": "にゃ",
    "nye": "にぇ", "nyi": "に", "nyo": "にょ", "nyu": "にゅ", "o": "お", "pa": "ぱ", "pe": "ぺ", "pi": "ぴ", "po": "ぽ", "pu": "ぷ",
    "pya": "ぴゃ", "pye": "ぴぇ", "pyi": "ぴ", "pyo": "ぴょ", "pyu": "ぴゅ", "ra": "ら", "re": "れ", "ri": "り", "ro": "ろ", "ru": "る",
    "rya": "りゃ", "rye": "りぇ", "ryi": "り", "ryo": "りょ", "ryu": "りゅ", "sa": "さ", "se": "せ", "sha": "しゃ", "she": "しぇ",
    "shi": "し", "sho": "しょ", "shu": "しゅ", "si": "すぃ", "so": "そ", "su": "す", "ta": "た", "te": "て", "ti": "てぃ", "to": "と",
    "tsa": "つぁ", "tse": "つぇ", "tsi": "つぃ", "tso": "つぉ", "tsu": "つ", "tu": "とぅ", "tya": "てゃ", "tye": "てぇ", "tyi": "てぃ",
    "tyo": "てょ", "tyu": "てゅ", "u": "う", "va": "ヴぁ", "ve": "ヴぇ", "vi": "ヴぃ", "vo": "ヴぉ", "vu": "ヴ", "vyu": "ヴゅ",
    "wa": "わ", "we": "うぇ", "wi": "うぃ", "wo": "うぉ", "wu": "うぅ", "ya": "や", "ye": "いぇ", "yi": "い", "yo": "よ", "yu": "ゆ",
    "za": "ざ", "ze": "ぜ", "zi": "ずぃ", "zo": "ぞ", "zu": "ず", "zya": "じゃ", "zye": "じぇ", "zyi": "じ", "zyo": "じょ", "zyu": "じゅ",
    "を": "お", "ぢ": "じ", "づ": "ず",
}

DEF_NUMS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"]
DEF_APPENDS = ["強", "弱", "暗", "明", "囁", "叫", "超", "幼", "甘", "笑", "瞭", "憂", "優", "感", "張", "抗", "泣叫", "癖", "元気", "艶"]
DEF_PITCHES = [
    "C1", "C#1", "Db1", "D1", "D#1", "Eb1", "E1", "F1", "F#1", "Gb1", "G1", "G#1", "Ab1", "A1", "A#1", "Bb1", "B1",
    "C2", "C#2", "Db2", "D2", "D#2", "EB2", "E2", "F2", "F#2", "Gb2", "G2", "G#2", "Ab2", "A2", "A#2", "Bb2", "B2",
    "C3", "C#3", "Db3", "D3", "D#3", "EB3", "E3", "F3", "F#3", "Gb3", "G3", "G#3", "Ab3", "A3", "A#3", "Bb3", "B3",
    "C4", "C#4", "Db4", "D4", "D#4", "EB4", "E4", "F4", "F#4", "Gb4", "G4", "G#4", "Ab4", "A4", "A#4", "Bb4", "B4",
    "C5", "C#5", "Db5", "D5", "D#5", "EB5", "E5", "F5", "F#5", "Gb5", "G5", "G#5", "Ab5", "A5", "A#5", "Bb5", "B5",
    "C6", "C#6", "Db6", "D6", "D#6", "EB6", "E6", "F6", "F#6", "Gb6", "G6", "G#6", "Ab6", "A6", "A#6", "Bb6", "B6",
    "C7", "C#7", "Db7", "D7", "D#7", "EB7", "E7", "F7", "F#7", "Gb7", "G7", "G#7", "Ab7", "A7", "A#7", "Bb7", "B7",
    "↑", "↓", "→", "←", "high", "low", "mid",
]
