"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Core/G2p/JapaneseMonophoneG2p.cs

the c# LoadPack here merges hiragana.txt, katakana.txt, romaji.txt and special.txt into one dictionary and
returns the (still null) static session: the pack has no g2p.onnx, so words outside the dictionaries get no
prediction and query() returns None for them."""

from ._cs import split_ws, trim
from .g2p_dictionary import G2pDictionary
from .g2p_pack import G2pPack, extract_text


class JapaneseMonophoneG2p(G2pPack):
    graphemes = [
        "", "", "", "", "a", "b", "c", "d", "e", "f", "g",
        "h", "i", "j", "k", "m", "n", "o", "p", "r", "s",
        "t", "u", "v", "w", "y", "z", "あ", "い", "う", "え",
        "お", "ぁ", "ぃ", "ぅ", "ぇ", "ぉ", "か", "き", "く",
        "け", "こ", "さ", "し", "す", "せ", "そ", "ざ", "じ", "ず",
        "ぜ", "ぞ", "た", "ち", "つ", "て", "と", "だ", "ぢ", "づ", "で",
        "ど", "な", "に", "ぬ", "ね", "の", "は", "ひ", "ふ", "へ", "ほ",
        "ば", "び", "ぶ", "べ", "ぼ", "ぱ", "ぴ", "ぷ", "ぺ", "ぽ", "ま",
        "み", "む", "め", "も", "や", "ゆ", "よ", "ゃ", "ゅ", "ょ", "ら",
        "り", "る", "れ", "ろ", "わ", "を", "ん", "っ", "ヴ", "ゔ", "゜",
        "ゐ", "ゑ", "ア", "イ", "ウ", "エ", "オ", "ァ", "ィ", "ゥ", "ェ",
        "ォ", "カ", "キ", "ク", "ケ", "コ", "サ", "シ", "ス", "セ", "ソ",
        "ザ", "ジ", "ズ", "ゼ", "ゾ", "タ", "チ", "ツ", "テ", "ト", "ダ",
        "ヂ", "ヅ", "デ", "ド", "ナ", "ニ", "ヌ", "ネ", "ノ", "ハ", "ヒ",
        "フ", "ヘ", "ホ", "バ", "ビ", "ブ", "ベ", "ボ", "パ", "ピ", "プ",
        "ペ", "ポ", "マ", "ミ", "ム", "メ", "モ", "ヤ", "ユ", "ヨ", "ャ",
        "ュ", "ョ", "ラ", "リ", "ル", "レ", "ロ", "ワ", "ヲ", "ン", "ッ",
        "ヰ", "ヱ", "息", "吸", "-", "R",
    ]

    phonemes = [
        "", "", "", "", "A", "AP", "E", "I", "N", "O", "U",
        "SP", "a", "b", "by", "ch", "cl", "d", "dy", "e", "f", "g", "gw",
        "gy", "h", "hy", "i", "j", "k", "kw", "ky", "m", "my", "n",
        "ng", "ngy", "ny", "o", "p", "py", "r", "ry", "s", "sh", "t", "ts",
        "ty", "u", "v", "w", "y", "z",
    ]

    pack = "g2p-ja-mono.zip"

    @staticmethod
    def load_pack(path, prep_grapheme=None, prep_phoneme=None):
        prep_grapheme = prep_grapheme or (lambda s: s)
        prep_phoneme = prep_phoneme or (lambda s: s)
        texts = [extract_text(path, n) for n in ("hiragana.txt", "katakana.txt", "romaji.txt", "special.txt")]
        phones_txt = extract_text(path, "phones.txt")
        builder = G2pDictionary.new_builder()
        for line in phones_txt:
            parts = split_ws(trim(line))
            if len(parts) == 2:
                builder.add_symbol(prep_phoneme(parts[0]), parts[1])
        for txt in texts:
            for line in txt:
                if line.startswith(";;;"):
                    continue
                parts = trim(line).split("  ")
                if len(parts) == 2:
                    builder.add_entry(prep_grapheme(parts[0]), [prep_phoneme(s) for s in split_ws(parts[1])])
        return builder.build(), None  # the static session is still null when LoadPack returns it

    def _load_static(self):
        return self.load_pack(self.pack_path())
