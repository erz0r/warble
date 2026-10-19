# a tuning session using only warble's tools

milestone 5 asks for a short song tuned by an agent with nothing but the tools, plus before/after
`compare` reports. this is that session: さくら さくら (traditional, public domain), 14 notes,
on adachi rei ds v111.1, seed 7 throughout so takes differ only by the edits. files are under
`out/session/` (not committed: renders are reproducible from the project file and its history).

| take | what changed | median cents off intent | frames within 20c | vibrato notes | robotic-flat notes | artifacts | syllables recognized |
|---|---|---|---|---|---|---|---|
| 0 raw | nothing (pitch model only) | 2.2 | 98.4% | 1 | 9 | 1 spectral jump | 69.2% |
| 1 | `tune preset-apply ballad` | 1.8 | 96.9% | 12 | 0 | 0 | 76.9% |
| 2 | vibrato off on notes ≤ 1.5 beats; on notes 3, 6 (onset 40%, ±30c) and 14 (onset 45%, ±38c); `cons=1.5` on や, よ, last note | 2.4 | 99.9% | 3 | 8 | 1 spectral jump | 76.9% |
| 3 | lyric fix (ど → は, spotted from the recognizer's transcript "桜 桜 夜の空を"); drift 7c at 1.3 Hz on short notes | 2.4 | 99.2% | 3 | 6 | 0 | 76.9% |

how each step was decided, from the tools' own output:

1. `inspect` on the raw take: "9 long note(s) hold dead-flat pitch; consider drift or vibrato",
   and the recognizer misheard や, よ, の, ど.
2. the ballad preset fixed the flatness but its `min_beats 1` put vibrato on every quarter note
   (`inspect` listed 12 vibrato notes at ~5.4 Hz). a human tuner keeps vibrato for the long notes,
   so step 2 removed it from the short ones and shaped it on the three long ones.
3. `inspect`'s intelligibility check printed what it heard. the last syllable was never "ど":
   the line is やよいのそら**は**. dead-flat warnings came back because 0.5 Hz drift barely moves
   inside an 833 ms note, so drift on short notes went to 1.3 Hz.

`compare out/session/take0_raw.wav out/session/take3_final.wav`: no notes further from intent,
artifacts 1 → 0, robotic-flat notes 9 → 6, vibrato on exactly the three long notes. the pitch
comparison image is `out/session/cmp_raw_final/compare_pitch.png`.

what this shows about the tools: the numbers caught a preset that was too eager, and the
recognizer's transcript caught a lyric typo that no pitch metric could. what it doesn't show:
whether take 3 *sounds* better to a person. that still needs ears; the metrics only rule out the
measurable failures.

the project file's history (`warble tune history out/session/sakura.txt`) has every step, and
`warble tune diff out/session/sakura.txt raw current` shows the full set of edits.
