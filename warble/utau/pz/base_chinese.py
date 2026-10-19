"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Core/BaseChinesePhonemizer.cs"""

from .api import Note, Phonemizer
from ._pinyin import ManTone, Pinyin, cs_len, to_str_list


def change_lyric(group, lyric):
    old = group[0]
    group[0] = Note(lyric=lyric, tone=old.tone, position=old.position, duration=old.duration,
                    phonetic_hint=old.phonetic_hint, phoneme_attributes=old.phoneme_attributes)
    return group


def romanize(lyrics):
    lyrics_array = list(lyrics)
    inst = Pinyin.instance()
    hanzi_lyrics = [l for l in lyrics_array if inst.is_hanzi(l)]
    pinyin_result = to_str_list(inst.hanzi_to_pinyin(hanzi_lyrics, ManTone.NORMAL, 0, False, False, False))
    pinyin_index = 0
    for i in range(len(lyrics_array)):
        if cs_len(lyrics_array[i]) == 1 and inst.is_hanzi(lyrics_array[i]):
            lyrics_array[i] = pinyin_result[pinyin_index]
            pinyin_index += 1
    return lyrics_array


def zip_change(groups, result_lyrics, change=change_lyric):
    """Enumerable.Zip(groups, lyrics, ChangeLyric).Last(): every pair is visited (Last forces the
    lazy zip); Last() throws on an empty sequence."""
    n = min(len(groups), len(result_lyrics))
    if n == 0:
        raise ValueError("Sequence contains no elements")
    for g, l in zip(groups, result_lyrics):
        change(g, l)


def romanize_notes(groups):
    result_lyrics = romanize(g[0].lyric for g in groups)
    zip_change(groups, result_lyrics)


class BaseChinesePhonemizer(Phonemizer):
    """abstract (not registered): romanizes hanzi lyrics to toneless pinyin in set_up."""

    def set_up(self, groups):
        super().set_up(groups)
        romanize_notes(groups)
