# warble

a small singing engine for **diffsinger** and **classic utau** voicebanks, built to be driven by an
llm agent from a terminal: text in, json out, numbers and images instead of ears.

everything warble knows about a bank comes from the bank's own files at load time. when a bank
does something warble doesn't support, it says what and why instead of guessing.

## setup

```sh
uv venv -p 3.12 .venv && uv pip install -p .venv -e ".[dev]" mido pykakasi pyphen "setuptools<81"
.venv/bin/warble banks            # lists banks under ./banks
```

banks live under `banks/<character>/<bank>/` (any depth works). diffsinger vocoders go in
`vocoders/<name>/vocoder.yaml` (or `$WARBLE_VOCODERS`); external utau resamplers in `resamplers/`.
never redistribute banks: read each bank's readme/terms (probe lists them).

## first steps for an agent

1. `warble banks` to see what is installed and what is missing (e.g. a vocoder).
2. `warble probe --check <bank>` before blaming tuning: it finds broken oto entries, missing
   wavs, model/flag mismatches, dictionary symbols the model can't sing.
3. `warble phonemize score.txt` to see what each note will sing, with timings. no audio.
4. `warble sing score.txt -o out/take1.wav --seed 1`, then read the json report.

## score format

plain text, one note per line, `#` comments (a `#` inside `C#4` is fine).

```
bank ./banks/adachi_rei/足立レイ_DS_v111.1   # directives apply to following notes
bpm 120                       # tempo; also: bpm 140 @ bar 17 / bpm 90 @ beat 32
time 3/4                      # time signature (optionally @ bar N)
key C
lang ja                       # picks dsdict-<lang>.yaml and the lyric front-end
voice default                 # voice mode: a name, or a mix like soft:0.7,power:0.3
track lead                    # named tracks; each has its own bank/lang/voice/volume/pan
volume -3                     # track gain in dB
pan 0.2                       # -1..1
ら C4 1                        # lyric pitch length(beats: 1, 1/2, 1.5 | ms: 350ms)
ら D4 1/2
+ E4 1/2                      # continuation (melisma); +~ / +* are vowel extensions
r 1                           # rest
[ja/k ja/a] G4 1              # explicit phonemes (diffsinger) or [alias] (utau)
か A4 1 @ 5:1                  # explicit position: bar 5 beat 1 (or @ bar 5, @ beat 16, @ tick 960)
さ B4 1 vel=120 vib=pop        # per-note controls
```

pitches: `C4`, `F#3`, `Bb4`, `A4+20c`, or midi numbers. ticks are 480 per beat.

per-note controls (key=value): `cents` (pitch offset), `vib` (none/subtle/pop/ballad/opera/wide or
rate:depth[:delay]), `vibrate`, `vibdepth`, `vibdelay`, `voice`, `gender` (openutau GENC units,
+ = deeper), `vel` (100 = normal consonant speed), `expr` (0..1, ds pitch expressiveness),
`ene`/`brec`/`voic`/`tenc` (ds variance offsets in openutau curve units), `vol`, `mod`, `atk`,
`dec`, `flags` (utau resampler flags), `pre`/`ovl` (utau preutterance/overlap deltas in ms),
`preutter`/`overlap` (absolute overrides), `shift` (utau tone shift for alias lookup), `color`.

other inputs: `-e "ら:C4:1 ら:D4:1/2 r:1"` inline, `.json`, `.ust` (notes, tempo, flags,
intensity, velocity, modulation, preutterance/overlap, mode1 pitchbends), `.mid` (`--midi-track`,
`--quantize`, lyric meta events, or `--lyrics "text" --lang ja`).

## commands

every command prints one json document on stdout; logs go to stderr. errors are json too:
`{"error": code, "message", "hint", "details"}` with exit code 2.

| command | what it does |
|---|---|
| `banks [dirs]` | detected banks: type, languages, voice modes, reclist style, missing dependencies |
| `probe <bank> [--check]` | everything about a bank from its files; `--check` adds qa (oto, wavs, models, dicts) |
| `phonemize <score>` | phonemes (ds) or aliases (utau) per note with ms/frame timings; unknown lyrics with closest symbols |
| `sing <score> -o out.wav` | render. `--seed`, `--steps`, `--depth`, `--engine ds\|utau`, `--phrase 3`, `--range 10-20`, `--allow-unknown`, `--resampler`, `--provider cpu\|coreml\|cuda` |
| `lyrics "<text>" --lang ja [--score s -o out]` | split text into mora/syllables (kanji readings reported) and assign to notes |
| `export <score> -o out.{txt,json,mid}` | convert between formats |

`sing` also writes `<out>.render.json`: per phrase, the notes, the timed phones and the intended
pitch curve. time `t` in the score is at `t + score_offset_ms` in the audio (non-zero when a
consonant starts before the first note).

## how rendering works

- **diffsinger**: lyrics → dictionary (`dsdict-<lang>.yaml`) → `dsdur` predicts phoneme lengths,
  aligned so leading consonants end on the note and each note's phonemes fill it exactly →
  `dspitch` (or a rule curve) → `dsvariance` if the acoustic model needs it → acoustic → vocoder.
  each model is fed from its real onnx signature; tensors are cached per stage in
  `~/.cache/warble/tensors` (the cache returns the earlier take for identical inputs).
- **utau**: phonemizer picks aliases (default/cv, japanese vcv, japanese cvvc; chosen from
  character.yaml or the reclist style), preutterance/overlap are auto-fitted like openutau, the
  built-in world resampler (pyworld) stretches and pitch-shifts each sample, and the wavtool
  crossfades with utau envelopes. external resamplers get the standard utau argument list.

## status

milestones 1 (probe) and 2 (first sound) are done; see `SPEC.md` for the rest.
not yet: `inspect`/`analyze`/`compare`, tuning ops, mode2 ust pitch, ustx/musicxml, mixing with
backing tracks, mcp server, the phonemizer catalog (presamp, arpasing, vccv...).

## credits

ported code follows [OpenUtau](https://github.com/stakira/OpenUtau) (MIT, © StAkira and
contributors) and [DiffSinger](https://github.com/openvpi/DiffSinger) (Apache-2.0, © openvpi);
see `NOTICE`. files containing ported logic say so at the top.
