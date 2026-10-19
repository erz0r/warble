"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Plugin.Builtin/PolishCVCPhonemizer.cs

polish cvc (reclist by haku): a syllable based phonemizer without a dictionary (lyrics are space separated
symbols).

note: the c# class never overrides GetConsonants, and SyllableBasedPhonemizer.SetSinger calls it for
phonemizers without a yaml file, so in openutau SetSinger throws NotImplementedException and every note
fails. the port keeps that behaviour, with one difference forced by warble's runner: set_singer remembers
the exception and set_up/process raise it, so the failure shows up per run (like openutau's per-note errors)
instead of escaping from set_singer.
"""

from .api import phonemizer
from .syllable_based import SyllableBasedPhonemizer, last


@phonemizer("Polish CVC Phonemizer", "PL CVC", language="PL", openutau_class="OpenUtau.Plugin.Builtin.PolishCVCPhonemizer", author="Heiden.BZR")
class PolishCVCPhonemizer(SyllableBasedPhonemizer):
    """And example of realization of AdvancedPhonemizer without a dictionary. Reclist by haku"""

    no_gap = True  # Endings has 50 ticks gap

    def __init__(self):
        super().__init__()
        self._pl_vowels = "a A e E i o u y".split(" ")
        self._singer_error = None

    def get_vowels(self):
        return self._pl_vowels

    # ---- the SetSinger failure (see the module docstring) ----------------------------------------------
    def set_singer(self, singer):
        self._singer_error = None
        try:
            super().set_singer(singer)
        except NotImplementedError as e:
            self._singer_error = e

    def set_up(self, groups):
        if self._singer_error is not None:
            raise self._singer_error
        super().set_up(groups)

    def process(self, notes, prev, next, prev_neighbour, next_neighbour, prev_neighbours):
        if self._singer_error is not None:
            raise self._singer_error
        return super().process(notes, prev, next, prev_neighbour, next_neighbour, prev_neighbours)

    # ---- the phonemizer -----------------------------------------------------------------------------------
    def process_syllable(self, syllable):
        prev_v = syllable.prev_v
        cc = syllable.cc
        v = syllable.v

        phonemes = []
        if syllable.is_starting_v:
            base_phoneme = f"- {v}"
        elif syllable.is_starting_cv:
            base_phoneme = f"- {last(cc)}{v}"
            for i in range(len(cc) - 1):
                phonemes.append(f"- {cc[i]}")
        elif syllable.is_vv:
            if not self.can_make_alias_extension(syllable):
                base_phoneme = v
            else:
                # the previous alias will be extended
                base_phoneme = None
        else:  # VCV
            base_phoneme = f"{last(cc)}{v}"
            phonemes.append(f"{prev_v} {cc[0]}")
            for i in range(len(cc) - 1):
                phonemes.append(cc[i])
        phonemes.append(base_phoneme)
        return phonemes

    def process_ending(self, ending):
        cc = ending.cc
        v = ending.prev_v

        phonemes = []
        if ending.is_ending_v:
            phonemes.append(f"{v} -")
        else:
            phonemes.append(f"{v} {cc[0]}-")
            for i in range(1, len(cc)):
                cr = f"{cc[i]} -"
                phonemes.append(cr if self.has_oto(cr, ending.tone) else cc[i])
        return phonemes

    def get_transition_basic_length_ms_with_attr(self, alias, tone, attr):
        oto_length = self.get_transition_basic_length_ms_by_oto(alias, tone, attr)
        return oto_length
