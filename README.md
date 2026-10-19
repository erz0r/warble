# warble

a singing engine for **diffsinger** and **classic utau** voicebanks, built to be driven by an llm
agent from a terminal or over mcp: text in, json out, and images plus numbers instead of ears.

everything warble knows about a bank comes from the bank's own files at load time. when a bank
does something warble doesn't support, it says what and why instead of guessing.

## setup

```sh
uv venv -p 3.12 .venv
uv pip install -p .venv -e ".[dev,mcp,plugins]"     # add ,asr for the speech-recognition check
.venv/bin/warble banks                               # what is installed, what is missing
```

- **banks** go under `banks/<character>/<bank>/` (any depth; `$WARBLE_BANKS` adds folders).
  a score can name a bank by path or by words from its folder or display name (`bank rei ds`).
- **diffsinger vocoders**: bundled `dsvocoder/` is used first; otherwise `vocoders/<name>/`
  (or `$WARBLE_VOCODERS`) with `vocoder.yaml` + onnx, named by the bank's dsconfig.
- **utau resamplers and wavtools**: executables in `resamplers/` (or `$WARBLE_RESAMPLERS`).
  native builds run directly, `.exe` through wine, `.py` through python. tested with
  straycat-rs and wavtool-yawu.
- **vst3 / audio unit effects**: found in the standard plugin folders (`$WARBLE_PLUGINS` adds
  more) and hosted through pedalboard.
- caches: `~/.cache/warble/` (tensors per model stage, phrases, resampler outputs). they return
  the earlier take for identical inputs, so pass `--seed` for reproducible a/b work and
  `--no-cache` to force a fresh take.

read each bank's readme and terms before publishing anything (`probe` lists the files). many
diffsinger banks require crediting the author and "DiffSinger" in titles; never redistribute banks.

## first steps for an agent

1. `warble banks` → what is installed and what is missing (a vocoder, a phonemizer).
2. `warble probe --check <bank>` before blaming tuning: broken oto entries, missing wavs,
   dictionary gaps, model/flag mismatches, sample-rate problems.
3. `warble new song.txt --bank "<name>"` or import: `.mid` (+ `--lyrics "..." --lang ja`),
   `.musicxml`, `.ust`, `.ustx`.
4. `warble check song.txt` → unknown lyrics, notes outside the bank's range, missing files.
5. `warble sing song.txt -o out/take1.wav --seed 1`, then `warble inspect out/take1.wav` and
   read `listening_notes` first, then the numbers, then the images.
6. tune with `warble tune ...` (every edit is versioned), re-render (only changed phrases
   re-render), and `warble compare take1.wav take2.wav` to check the edit helped.

## score format

plain text, one note per line, `#` starts a comment (a `#` inside `C#4` is fine).

```
bpm 120                       # also: bpm 140 @ bar 17 | @ beat 32 | @ tick 7680
time 3/4                      # time signature (optionally @ bar N)
key Am                        # used by harmony and the key guess
master preset=pop lufs=-14 ceiling=-1 room=1.6 chain=OTT(depth=15)
backing ./instrumental.wav @ bar 1 gain=-6        # or @ 2.5s
track lead                    # named tracks; each has its own bank/lang/voice/fx
bank ./banks/adachi_rei/足立レイ_DS_v111.1         # or: bank rei ds
lang ja                       # diffsinger: picks openutau's phonemizer for the language (en en-plus de de-marzipan fr
                              # it es pt ru fil fil-rule ko ko-dict zh yue ja); others read dsdict-<lang>.yaml
voice default                 # voice mode, or a mix like soft:0.7,power:0.3
phonemizer ja_vcv             # utau: override the phonemizer; diffsinger: an openutau class, e.g. DiffSingerARPAPlusEnglishPhonemizer
resampler straycat-rs         # utau: per track (or per note: resampler=...)
volume -3                     # dB
pan 0.2                       # -1..1
fx eq=low:-1,high:2 comp=-20:3 delay=320:0.3:0.15 reverb=0.25 chain=OTT(depth=30)
curve pitd 0:0,480:-20,960:0  # openutau track curves: pitd dyn genc brec tenc voic ene velc pexp
ら C4 1                        # lyric pitch length (beats: 1, 1/2, 1.5 | ms: 350ms)
+ E4 1/2                      # continuation (melisma); +~ / +* are vowel extensions
r 1                           # rest
[ja/k ja/a] G4 1              # explicit phonemes (diffsinger) or [alias] (utau)
か A4 1 @ 5:1                  # explicit position: bar 5 beat 1
さ B4 1 vel=120 vib=pop        # per-note controls (below)
track harmony
pan 0.3
harmonize lead 3              # notes generated from another track: 3, 6, 3below, +4st, oct ...
```

pitches: `C4`, `F#3`, `Bb4`, `A4+20c`, or midi numbers. 480 ticks per beat.

**per-note controls** (`key=value`):

| group | controls |
|---|---|
| pitch | `pts=x:y:shape,...` bend points (x ms from note start, y cents from the note; shapes io l i o sp h), `snap=0`, `vbr=length,period,depth,in,out,shift,drift` (openutau/ust vibrato), `vib=subtle\|pop\|ballad\|opera\|wide` or `rate:depth[:onset]`, `drift=depth:rate:seed`, `cents=`, `raw=start:step:c;c;...` (per-frame layer, ust mode1) |
| diffsinger | `gender` (openutau GENC units, + deeper), `vel` (consonant speed, 100 normal), `expr` (0..1), `ene` `brec` `voic` `tenc` (variance offsets, openutau units), `voice`, `cons` (scale consonant lengths), `phdur=ms,ms,...` |
| utau | `vol`, `atk`, `dec`, `mod`, `flags`, `vel`, `pre`/`ovl` (deltas ms), `preutter`/`overlap` (absolute), `shift`, `alt`, `color`, `env`, `resampler`, `wavtool` |

other inputs: `-e "ら:C4:1 ら:D4:1/2:vib=pop r:1"` inline (controls after colons), `.json`.

## commands

every command prints one json document on stdout; logs go to stderr. errors are json too:
`{"error": code, "message", "hint", "details"}` (exit 2; internal errors exit 3).

| command | what it does |
|---|---|
| `banks [dirs]` | detected banks: type, languages, voice modes, reclist style, missing dependencies |
| `probe <bank> [--check]` | everything about a bank from its files; `--check` adds qa |
| `new <path>` | a commented starter project |
| `check <score>` | validate without rendering |
| `phonemize <score>` | phonemes (ds) or aliases (utau) per note with ms/frame timings |
| `sing <score> -o out.wav` | render. `--seed --steps --depth --engine ds\|utau --phrase 3 --range 10-20 --allow-unknown --resampler --wavtool --stems DIR --mix dry\|pop\|ballad\|choir --lufs -14 --no-master --sample-rate --provider cpu\|coreml\|cuda --no-cache` |
| `inspect <wav>` | images + report: per-note pitch vs intent, transitions, vibrato, onset, voicing, loudness, breathiness, hnr, formants; artifacts with timestamps; listening notes; intelligibility. `--notes 12-20 --ref other.wav --score` |
| `analyze <wav>` | the same for any audio (notes segmented from pitch when there's no score) |
| `compare a.wav b.wav` | a/b images, dtw-aligned diff (mel distance, pitch, timing, loudness, dynamics), per-note deltas, verdict |
| `pitch extract <wav>` | f0 from every extractor available, where they disagree, a curves file |
| `tune <action> <project> ...` | `show`, `op <name> -p k=v --notes 3-7`, `apply '<json ops>'`, `auto <tuner>`, `undo`, `redo`, `snapshot <name>`, `restore <name>`, `diff [a] [b]`, `history`, `ops`, `presets`, `preset-save`, `preset-apply`, `import-pitch <wav>` |
| `harmony <project> --interval 3` | add a harmony track (diatonic in the key, semitones, octaves) |
| `lyrics "<text>" --lang ja [--score s -o out]` | split text into mora/syllables (kanji readings reported) and assign to notes |
| `export <score> -o out.{txt,json,mid,ust,ustx,musicxml}` | convert |
| `resamplers`, `plugins [info <name>]`, `phonemizers` | what tools are installed |
| `serve [--socket path]` | json lines `{"command", "args"}` in, `{"id", "result"}` out; models stay loaded |
| `mcp` | mcp server on stdio: every command is a tool, inspect/analyze/compare return images |

**tuning ops** (`warble tune ops` lists parameters): `transition` (dur, start offset, shape,
preparation, overshoot, settle), `scoop`, `fall`, `fry`, `flat`, `unbend`, `offset`, `drift`,
`vibrato` (presets none/subtle/pop/ballad/opera/wide_late plus fields), `copy_vibrato`, `set`
(any expression), `ramp`, `nudge`, `copy_tuning`. selections: `--notes 3-7,12 --lyric ら
--phrase 2 --min-beats 1 --interval ">=3"` (or `abs>=4`). auto-tuners: `flat`, `utau_mode1`,
`utau_mode2`, `openutau`, `rule`, `dspitch` (`-p ds_bank=<name>`: a diffsinger pitch model
drafts the curve for any bank). presets: `gentle`, `pop`, `ballad`, `robot`, plus your own.

## how it works

- **diffsinger** (ported from openutau): lyric → romanization (hanzi → pinyin / jyutping, kana → romaji,
  hangul batchim) → the bank's `dsdict-<lang>.yaml`, then openutau's builtin g2p for the language remapped
  onto the bank's symbols (`warble/ds/g2p_phonemizers.py`, parity-tested with `ref/harness_ds`), then
  warble's language front-end fallbacks → `dsdur` durations aligned so leading consonants end on the note and each
  note's phonemes fill it → `dspitch` (or a rule curve) → `dsvariance` when the acoustic model
  needs it → acoustic → vocoder. every model is fed from its real onnx signature, so dsconfig flags
  that disagree with the graph are reported instead of crashing.
- **utau**: openutau's phonemizers (ported and checked against openutau itself, see below) pick
  aliases; preutterance and overlap are auto-fitted like openutau; the built-in world resampler
  (pyworld) or an external resampler renders each note; the built-in or an external wavtool joins
  them with utau envelopes.
- **pitch**: the engine's curve (pitch model, or a rule curve), then per-note bend points,
  vibrato, drift, raw layers and offsets (openutau's note pitch model), then track `pitd`.
- **mix**: per-track eq / compressor / delay / plugin chain / pan → shared reverb → backing →
  master chain → loudness target → limiter. stems and their sidecars on request.
- **perception**: harvest + dio (+ crepe/rmvpe when installed) with harmonic-salience arbitration,
  world aperiodicity, stft/mel, loudness, lpc formants; `sing` writes `<out>.render.json` with
  notes, phones and the intended curve so `inspect` knows what was meant. score time `t` is at
  `t + score_offset_ms` in the file.

## phonemizer parity

openutau's phonemizers are ported one c# file per python module in `warble/utau/pz/`. a port only
counts once it reproduces openutau's own output: `ref/harness` (a small .net console app built
against openutau's sources, not committed) runs the real phonemizers on the cases in
`tests/parity/cases/` and writes `tests/parity/goldens/`; `tests/test_parity.py` replays them.
status for every phonemizer is in `docs/phonemizers.md` (regenerate with
`python tools/phonemizer_inventory.py`). to add or regenerate goldens you need the openutau
checkout in `ref/OpenUtau` and a .net 10 sdk; see `docs/PORTING.md`.

## tests

`.venv/bin/python -m pytest -q tests` builds mock diffsinger banks (tiny onnx graphs with the real
signatures) and mock utau banks (synthesized samples in cv/vcv/cvvc/multi-pitch/shift-jis
variants), renders through every path, plants faults that `inspect` must find, round-trips
ust/ustx/musicxml/text, checks tuning ops numerically, keeps the mcp server identical to the cli,
and replays the phonemizer goldens. real banks under `./banks` get probed too when present;
`python tools/real_bank_report.py` renders a standard set of phrases on each and writes
`docs/real_banks.md`.

## other notes

- `--provider coreml` works on apple silicon but was about 2× slower than cpu on rei ds in our
  test (compilation per session); cpu is the default.
- known limits: no gui, no enunu/vogen/voicevox renderers, no learned tuner yet (see `SPEC.md`
  section 7; per-note stats from `inspect` and the tuning representation are meant to feed it),
  no realtime playback.

## credits

ported logic follows [OpenUtau](https://github.com/stakira/OpenUtau) (MIT, © StAkira and
contributors) and implements the inference interface of [DiffSinger](https://github.com/openvpi/DiffSinger)
(Apache-2.0, © openvpi) models; openutau's g2p models and test banks are included under its MIT
license. see `NOTICE`. every file with ported logic says so at the top.
