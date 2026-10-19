"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Plugin.Builtin/PhonemeBasedPhonemizer.cs

the base of the phoneme based phonemizers (arpasing, the latin diphone ones, the monophone ones): a g2p turns
each lyric (or the phonetic hint) into symbols, the first vowel sits on the note start, leading consonants get
ConsonantLength ticks each before it, and "+n" extension notes align the n-th symbol by hand.

helpers this module adds (the api lacks them): cs_int_try_parse (c# int.TryParse), dotnet_sort (the
unstable introsort List<T>.Sort uses, so ties land where openutau puts them), cs_div (integer division that
truncates toward zero) and plugin_file (the yaml dictionaries openutau keeps in its Plugins folder; warble
ships the templates under data/phoneme_based/ and never writes there).
"""

import os
import re

from ...g2p._cs import split_ws, to_lower_invariant
from .api import Phoneme, PhonemeAttributes, Phonemizer

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "phoneme_based")


def plugin_file(name):
    """PluginDir/<name>. openutau writes arpasing.yaml / german.yaml from its templates on first use and reads
    french.yaml / zhcvv.yaml only if a user put them there; a fresh install has exactly the templates."""
    base = os.path.splitext(name)[0]
    path = os.path.join(DATA_DIR, f"{base}.template.yaml")
    return path if os.path.exists(path) else None


def read_all_text(path):
    """File.ReadAllText: utf-8 with the bom stripped."""
    with open(path, "rb") as f:
        return f.read().decode("utf-8-sig", errors="replace")


_INT = re.compile(r"^[ \t\n\v\f\r]*([+-]?[0-9]+)[ \t\n\v\f\r]*$")


def cs_int_try_parse(s):
    """int.TryParse(s, out v): -> v or None."""
    m = _INT.match(s)
    if not m:
        return None
    v = int(m.group(1))
    if v < -(2 ** 31) or v > 2 ** 31 - 1:
        return None
    return v


def cs_div(a, b):
    """c# integer division: truncates toward zero, throws on zero."""
    if b == 0:
        raise ZeroDivisionError("Attempted to divide by zero.")
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


def _at(arr, i):
    """c# array indexing: no wrap-around for negative indexes."""
    if i < 0:
        raise IndexError("Index was outside the bounds of the array.")
    return arr[i]


def dotnet_sort(keys, comparer):
    """List<T>.Sort(Comparison<T>): .NET's ArraySortHelper introsort, in place. not stable."""
    n = len(keys)
    if n > 1:
        _intro_sort(keys, 0, n, 2 * (n.bit_length() - 1 + 1), comparer)


def _swap_if_greater(keys, cmp, i, j):
    if cmp(keys[i], keys[j]) > 0:
        keys[i], keys[j] = keys[j], keys[i]


def _intro_sort(keys, lo, hi, depth_limit, cmp):
    partition_size = hi - lo
    while partition_size > 1:
        if partition_size <= 16:
            if partition_size == 2:
                _swap_if_greater(keys, cmp, lo, lo + 1)
                return
            if partition_size == 3:
                _swap_if_greater(keys, cmp, lo, lo + 1)
                _swap_if_greater(keys, cmp, lo, lo + 2)
                _swap_if_greater(keys, cmp, lo + 1, lo + 2)
                return
            _insertion_sort(keys, lo, lo + partition_size, cmp)
            return
        if depth_limit == 0:
            _heap_sort(keys, lo, lo + partition_size, cmp)
            return
        depth_limit -= 1
        p = _pick_pivot_and_partition(keys, lo, lo + partition_size, cmp)
        _intro_sort(keys, p + 1, lo + partition_size, depth_limit, cmp)
        partition_size = p - lo


def _insertion_sort(keys, lo, hi, cmp):
    for i in range(lo, hi - 1):
        t = keys[i + 1]
        j = i
        while j >= lo and cmp(t, keys[j]) < 0:
            keys[j + 1] = keys[j]
            j -= 1
        keys[j + 1] = t


def _pick_pivot_and_partition(keys, lo, hi_excl, cmp):
    hi = hi_excl - 1
    middle = lo + ((hi - lo) >> 1)
    _swap_if_greater(keys, cmp, lo, middle)
    _swap_if_greater(keys, cmp, lo, hi)
    _swap_if_greater(keys, cmp, middle, hi)
    pivot = keys[middle]
    keys[middle], keys[hi - 1] = keys[hi - 1], keys[middle]
    left, right = lo, hi - 1
    while left < right:
        left += 1
        while cmp(keys[left], pivot) < 0:
            left += 1
        right -= 1
        while cmp(pivot, keys[right]) < 0:
            right -= 1
        if left >= right:
            break
        keys[left], keys[right] = keys[right], keys[left]
    if left != hi - 1:
        keys[left], keys[hi - 1] = keys[hi - 1], keys[left]
    return left


def _heap_sort(keys, lo, hi, cmp):
    n = hi - lo
    for i in range(n >> 1, 0, -1):
        _down_heap(keys, lo, i, n, cmp)
    for i in range(n, 1, -1):
        keys[lo], keys[lo + i - 1] = keys[lo + i - 1], keys[lo]
        _down_heap(keys, lo, 1, i - 1, cmp)


def _down_heap(keys, lo, i, n, cmp):
    d = keys[lo + i - 1]
    while i <= n >> 1:
        child = 2 * i
        if child < n and cmp(keys[lo + child - 1], keys[lo + child]) < 0:
            child += 1
        if not cmp(d, keys[lo + child - 1]) < 0:
            break
        keys[lo + i - 1] = keys[lo + child - 1]
        i = child
    keys[lo + i - 1] = d


class PhonemeBasedPhonemizer(Phonemizer):
    # ConsonantLength { get; set; } = 60; addTail = true
    consonant_length = 60
    add_tail = True

    def __init__(self):
        super().__init__()
        self.vowel_fallback = None
        self.g2p = None
        self.is_dictionary_loading = False
        # [(index of phoneme, tick position from the lyrical note in notes[], is manual)]
        self.alignments = []
        try:
            self.initialize()
        except Exception:  # noqa: BLE001 - Log.Error(e, "Failed to initialize.")
            pass

    def load_g2p(self):
        raise NotImplementedError

    def load_vowel_fallbacks(self):
        raise NotImplementedError

    def initialize(self):
        self.g2p = self.load_g2p()
        self.vowel_fallback = self.load_vowel_fallbacks()

    def set_singer(self, singer):
        self.singer = singer
        self.g2p = self.load_g2p()

    def process(self, notes, prev, next, prev_neighbour, next_neighbour, prev_neighbours):
        if self.is_dictionary_loading:
            return self.make_simple_result("")
        note = notes[0]

        # Force alias using ? prefix
        if note.lyric and note.lyric[0] == "?":
            return self.make_simple_result(note.lyric[1:])

        # Get the symbols of previous note.
        prev_symbols = None if prev_neighbour is None else self.get_symbols(prev_neighbour)
        # The user is using a tail "-" note to produce a "<something> -" sound.
        if note.lyric == "-" and prev_symbols is not None:
            attr = note.phoneme_attributes[0] if note.phoneme_attributes else PhonemeAttributes()
            color = attr.voice_color if attr.voice_color is not None else self.get_parent_voice_color()
            alias = f"{_last(prev_symbols)} -"
            oto = self.singer.try_get_mapped_oto(alias, note.tone, color)
            if oto is not None:
                return self.make_simple_result(oto.alias)
            return self.make_simple_result(alias)
        # Get the symbols of current note.
        symbols = self.get_symbols(note)
        if self.add_tail and next_neighbour is None:
            # Auto add tail "-".
            if symbols is None:
                raise TypeError("Value cannot be null. (Parameter 'source')")  # Enumerable.Append on null
            symbols = symbols + ["-"]
        if symbols is None or len(symbols) == 0:
            # No symbol is found for current note.
            # Otherwise assumes the user put in an alias.
            return self.make_simple_result(note.lyric)
        # Find phone types of symbols.
        is_vowel = [self.g2p.is_vowel(s) for s in symbols]
        is_glide = [self.g2p.is_glide(s) for s in symbols]
        # Arpasing aligns the first vowel at 0 and shifts leading consonants to negative positions,
        # so we need to find the first vowel.
        phonemes = [Phoneme(None, 0) for _ in symbols]

        # Alignments
        # - Tries to align every note to one syllable.
        # - "+n" manually aligns to n-th phoneme.
        alignments = self.alignments
        alignments.clear()
        # notes except those whose lyrics start witn "+*" or "+~"
        non_extension_notes = [n for n in notes if not self.is_syllable_vowel_extension_note(n)]
        for i in range(len(symbols)):
            if is_vowel[i] and len(alignments) < len(non_extension_notes):
                # Handle glide phonemes
                # For "Consonant-Glide-Vowel" syllable, the glide phoneme is placed after the start position of the note.
                if i >= 2 and is_glide[i - 1] and not is_vowel[i - 2]:
                    alignments.append((i - 1, non_extension_notes[len(alignments)].position - notes[0].position, False))
                else:
                    alignments.append((i, non_extension_notes[len(alignments)].position - notes[0].position, False))
        position = notes[0].duration
        for i in range(1, len(notes)):
            idx = cs_int_try_parse(notes[i].lyric[1:])
            if idx is not None:
                alignments.append((idx - 1, position, True))
            position += notes[i].duration
        alignments.append((len(phonemes), position, True))
        dotnet_sort(alignments, lambda a, b: (a[0] > b[0]) - (a[0] < b[0]))
        i = 0
        while i < len(alignments):
            if alignments[i][2]:
                while i > 0 and (alignments[i - 1][1] >= alignments[i][1] or alignments[i - 1][0] == alignments[i][0]):
                    del alignments[i - 1]
                    i -= 1
                while i < len(alignments) - 1 and (alignments[i + 1][1] <= alignments[i][1] or alignments[i + 1][0] == alignments[i][0]):
                    del alignments[i + 1]
            i += 1

        start_index = 0
        first_vowel = is_vowel.index(True) if True in is_vowel else -1
        start_tick = -self.consonant_length * first_vowel
        for alignment in alignments:
            # Distributes phonemes between two aligment points.
            self.distribute_duration(is_vowel, phonemes, start_index, alignment[0], start_tick, alignment[1])
            start_index = alignment[0]
            start_tick = alignment[1]
        alignments.clear()

        # Select aliases.
        note_index = 0
        prev_symbol = "-" if prev_symbols is None else _last(prev_symbols)
        for i in range(len(symbols)):
            attr = note.attr(i)
            alt_v = attr.alternate if attr.alternate is not None else self.get_parent_alternate()
            alt = "" if alt_v is None else str(alt_v)
            color = attr.voice_color if attr.voice_color is not None else self.get_parent_voice_color()
            tone_shift = attr.tone_shift if attr.tone_shift is not None else self.get_parent_tone_shift()
            phoneme = phonemes[i]
            while note_index < len(notes) - 1 and notes[note_index].position - note.position < phoneme.position:
                note_index += 1
            tone = prev_neighbours[-1].tone if (i == 0 and prev_neighbours is not None and len(prev_neighbours) > 0) else notes[note_index].tone
            phoneme.phoneme = self.get_phoneme_or_fallback(prev_symbol, symbols[i], tone + tone_shift, color, alt)
            prev_symbol = symbols[i]

        return phonemes

    @staticmethod
    def is_syllable_vowel_extension_note(note):
        """does this note extend the previous syllable?"""
        return note.lyric.startswith("+~") or note.lyric.startswith("+*")

    def get_symbols(self, note):
        if not note.phonetic_hint:
            # User has not provided hint, query CMUdict.
            return self.g2p.query(to_lower_invariant(note.lyric))
        # Split space-separated symbols into an array.
        return [s for s in split_ws(note.phonetic_hint) if self.g2p.is_valid_symbol(s)]  # skip the invalid symbols.

    def get_phoneme_or_fallback(self, prev_symbol, symbol, tone, color, alt):
        raise NotImplementedError

    def distribute_duration(self, is_vowel, phonemes, start_index, end_index, start_tick, end_tick):
        if start_index == end_index:
            return
        # First count number of vowels and consonants.
        consonants = 0
        vowels = 0
        duration = end_tick - start_tick
        for i in range(start_index, end_index):
            if _at(is_vowel, i):
                vowels += 1
            else:
                consonants += 1
        # If vowels exist, consonants are given fixed length, but combined no more than half duration.
        # However, if no vowel exists, consonants are evenly distributed within the total duration.
        if vowels > 0:
            consonant_duration = min(self.consonant_length, cs_div(cs_div(duration, 2), consonants)) if consonants > 0 else 0
        else:
            consonant_duration = cs_div(duration, consonants)
        # Vowels are evenly distributed within (total duration - total consonant duration).
        vowel_duration = cs_div(duration - consonant_duration * consonants, vowels) if vowels > 0 else 0
        position = start_tick
        # Compute positions using previously computed durations.
        for i in range(start_index, end_index):
            if _at(is_vowel, i):
                _at(phonemes, i).position = position
                position += vowel_duration
            else:
                _at(phonemes, i).position = position
                position += consonant_duration


def _last(seq):
    """Enumerable.Last(): throws on an empty sequence."""
    if not seq:
        raise ValueError("Sequence contains no elements")
    return seq[-1]
