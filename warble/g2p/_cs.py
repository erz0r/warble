"""small c# string semantics the g2p ports rely on (string.Split(), ToLowerInvariant, StreamReader.ReadLine,
char.IsDigit). kept separate so the ported modules stay line-by-line close to the c#."""

import re
import unicodedata

# char.IsWhiteSpace: Zs/Zl/Zp plus \t \n \v \f \r, U+0085 and U+00A0 (python's isspace also counts \x1c-\x1f)
_CTRL_WS = {"\t", "\n", "\v", "\f", "\r", "\x85", "\xa0"}


def is_white_space(c):
    return c in _CTRL_WS or unicodedata.category(c) in ("Zs", "Zl", "Zp")


def split_ws(s):
    """string.Split() with no arguments: splits on every whitespace char, keeping empty entries."""
    out, cur = [], []
    for c in s:
        if is_white_space(c):
            out.append("".join(cur))
            cur = []
        else:
            cur.append(c)
    out.append("".join(cur))
    return out


def trim(s):
    """string.Trim(): strips char.IsWhiteSpace chars from both ends."""
    i, j = 0, len(s)
    while i < j and is_white_space(s[i]):
        i += 1
    while j > i and is_white_space(s[j - 1]):
        j -= 1
    return s[i:j]


def to_lower_invariant(s):
    """string.ToLowerInvariant(): simple (1:1) case mapping, unlike python's full mapping (U+0130 -> 'i')."""
    out = []
    for c in s:
        lo = c.lower()
        out.append(lo if len(lo) == 1 else lo[0])
    return "".join(out)


def is_digit(c):
    """char.IsDigit: unicode category Nd."""
    return unicodedata.category(c) == "Nd"


_NEWLINE = re.compile(r"\r\n|\r|\n")


def read_lines(data):
    """StreamReader(stream, Encoding.UTF8) + ReadLine until EndOfStream: bom stripped, \\r\\n, \\r and \\n end
    a line, a trailing newline does not make an extra empty line."""
    text = data.decode("utf-8-sig", errors="replace") if isinstance(data, (bytes, bytearray)) else data
    if text == "":
        return []
    lines = _NEWLINE.split(text)
    if _NEWLINE.search(text[-1:]) or text.endswith("\r\n"):
        lines.pop()
    return lines


def is_all_punct(s):
    """Regex(@"^[\\p{P}]$").IsMatch: one utf-16 punctuation char, optionally followed by a final newline."""
    if s.endswith("\n"):
        s = s[:-1]
    return len(s) == 1 and ord(s) < 0x10000 and unicodedata.category(s).startswith("P")
