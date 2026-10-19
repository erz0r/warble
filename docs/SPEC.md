# project: a small singing engine built from the guts of openutau, diffsinger and classic utau

build a python singing engine that can render any diffsinger voicebank and any classic utau voicebank from a simple score. the main user of this engine is you, claude, driving it from a terminal. optimize every interface for an llm agent that can't hear audio: text in, json out, visual and numeric self-checks.

the rule for the whole project: nothing is hardcoded to one voicebank, one language or one reclist style. everything the engine needs to know about a bank comes from the bank's own files, read at load time. if a bank does something the engine doesn't support, it says exactly what and why instead of guessing.

## 0. voicebanks and the first test bank

- banks live in a folder i point the engine at (`--bank <path>` or a `banks/` directory it scans). the engine auto-detects the bank type: diffsinger (`dsconfig.yaml` at root or `character.yaml` with `singer_type: diffsinger`), classic utau (`oto.ini` anywhere under the root, `character.txt`), and reports anything else as unsupported with what it found.
- the first real test bank is adachi rei ds by tigermeat (a diffsinger port of missile39's utau rei). the download is a google drive link on https://tigermeat.xyz/cast/rei/ , which is javascript-rendered, so plain fetchers only see empty headings. if you don't have a browser tool, ask me to download it and give you the path. rei's original utau bank (missile39, mechanicalgirl.jp) is a good first utau test too. after that, test with at least one bank of a different language and, for utau, at least one vcv or cvvc bank, so the generic paths actually get exercised.
- read each bank's readme/terms. many diffsinger banks require crediting the author and putting "DiffSinger" in upload titles, and some require a paid license for commercial use. the engine should surface the bank's readme/license file path in `probe` output. never redistribute banks.
- vocoders: a diffsinger bank either bundles `dsvocoder/vocoder.yaml` or names a vocoder in `dsconfig.yaml`'s `vocoder:` field (an openutau "dependency" folder, often a pc-nsf-hifigan variant). support a `vocoders/` directory of installed vocoders, each a folder with `vocoder.yaml` + onnx, resolved by name, with a clear error naming what's missing and where to get it (openvpi's pc_nsf_hifigan from github.com/openvpi/vocoders releases is the common fallback; some authors ship their own). the vocoder's sample_rate, hop_size, win_size, fft_size, num_mel_bins, mel_fmin/fmax and mel_scale must match the acoustic dsconfig; mel_base may differ (10 vs e) and is fixed by scaling the mel by 2.30259 or 0.434294.
- before writing pipeline code, write `probe <bank>`: dump the folder tree, every dsconfig.yaml, phoneme file format (txt = line index, json = name→id), languages json, speakers (.emb files, `hiddenSize` float32 each), character.yaml subbanks/voice modes, dictionaries present, and the input/output names, dtypes and shapes of every onnx model. for utau banks: oto sets per subfolder, alias count, detected reclist style, prefix.map, encoding. design against what's actually there, not against my notes.
- `probe --check <bank>` is bank qa: missing or unreadable wavs, oto entries whose offset/consonant/cutoff fall outside the file or overlap wrongly, duplicate or shadowed aliases, aliases a phonemizer will ask for that the bank lacks, sample-rate and bit-depth mismatches, and suspicious preutterance/overlap values. a lot of what sounds like bad tuning in utau is really a bad oto, so agents should run this before blaming the tuning.

## 1. reference implementation

clone https://github.com/stakira/OpenUtau. for diffsinger read `OpenUtau.Core/DiffSinger/` (Renderer, Utils, Variance, Pitch, BasePhonemizer, Singer, Vocoder, SpeakerEmbedManager, and the language phonemizers in `Phonemizers/`) and `OpenUtau.Core/Api/G2pDictionary*.cs`. for utau read `OpenUtau.Core/Classic/` (voicebank/oto loading, the built-in resampler and wavtool) and the classic phonemizers under `OpenUtau.Plugin.Builtin/` (cv, vcv, cvvc, en arpasing etc.) for how lyrics map to aliases. port behavior faithfully. key diffsinger facts i already pulled out, verify against the source:

**bank layout.** root `dsconfig.yaml` + acoustic model + phonemes. optional subfolders, each with its own dsconfig/phonemes/dicts: `dsdur/` (linguistic encoder + duration model), `dspitch/` (linguistic + pitch), `dsvariance/` (linguistic + variance), `dsvocoder/`. any of them may be missing; degrade gracefully (no dsdur → durations from a simple rule like consonants fixed-length, vowels fill the note; no dspitch → f0 from the note grid with smooth transitions and optional vibrato; no dsvariance → skip variance inputs only if the acoustic model doesn't require them, otherwise error). dictionaries: `dsdict-<lang>.yaml` for the chosen language, else `dsdict.yaml`. format: `symbols: [{symbol, type}]` (vowel/consonant/semivowel/liquid; semivowel and liquid are "glides") and `entries: [{grapheme, phonemes: [...]}]`. SP and AP are always vowels. multilingual banks prefix phonemes like `ja/a`; the language id is the part before `/`, looked up in the languages json. some banks use one combined phoneme set, some per-language prefixes: handle both.

**padding.** every phrase is padded with 8 frames of SP at the head and 8 at the tail. gaps between phonemes become SP segments. phrases split at rests. ms→frame conversion uses cumulative rounding: `frame = round(cum_ms / frame_ms + 0.5)` (banker's rounding), durations are frame deltas. frame_ms = 1000 * hop_size / sample_rate. each sub-model has its own frame_ms; resample curves between them per padded segment.

**phonemizer (dsdur).** lyric lookup priority: explicit phonetic hint, then dict lookup of the lyric (and lowercased), then treat the lyric as space-separated phonemes (trying with and without the language prefix). language front-ends normalize lyrics before dict lookup; make these small pluggable modules keyed by language code, and only add ones the dicts actually need: japanese kana → romaji (ん → `N`; check the dict for っ and long vowels), and for languages where dicts don't cover arbitrary words (english especially), an optional g2p fallback (cmudict / g2p_en) mapped onto the bank's symbol set. a word = a note plus following continuation notes (lyric starting with `+`; `+~`/`+*` are vowel extensions). phonemes are split across notes at vowels (a glide before a vowel moves to the note start when preceded by a consonant). leading consonants before the first vowel belong to the previous note group. the phrase starts with an SP and 500 ms of lead padding.
- linguistic encoder inputs: `tokens` [1,N] int64, `word_div` [1,W] int64, `word_dur` [1,W] int64 (frames), optional `languages` [1,N] int64. outputs `encoder_out`, `x_masks`.
- duration model inputs: `encoder_out`, `x_masks`, `ph_midi` [1,N] int64 (note tone per phoneme), plus `word_div`/`word_dur` if dur_type is "rel" or the graph has those inputs, plus `spk_embed` [1,N,hidden] if speakers. output: predicted durations in frames (float).
- alignment: the leading consonants keep predicted length and end exactly at the first note onset; every later group is stretched by a ratio so it exactly fills its note span.

**pitch (dspitch).** linguistic encoder in word mode (if predict_dur) or phoneme mode (`ph_dur`). pitch model inputs: `encoder_out`, `note_midi` [1,M] float, `note_dur` [1,M] int64, `ph_dur` [1,N] int64, `pitch` [1,T] float (init 60), `retake` [1,T] bool (all true), sampling inputs, optional `expr` [1,T] float (0..1), `note_rest` [1,M] bool, `spk_embed` [1,T,hidden]. notes get a head rest, inserted rests for gaps, and a tail rest. rest notes take the midi of the nearest non-rest neighbor (split at the middle of a rest group). note_dur must be fit to sum exactly to T. output is midi pitch per frame.

**variance (dsvariance).** linguistic encoder as above. variance inputs: `encoder_out`, `ph_dur`, `pitch` [1,T] in midi, zero curves `energy`/`breathiness`/`voicing`/`tension` for whichever `predict_*` flags are true, `retake` [1,T,num_variances] bool, sampling inputs, optional `spk_embed`. outputs `energy_pred`, `breathiness_pred`, `voicing_pred`, `tension_pred`. user offsets are added afterwards (energy/breathiness/voicing clamped to [-96, 0], tension clamped to [-10, 10]).

**acoustic.** inputs `tokens`, `durations` (frames, padded), `f0` [1,T] in hz, sampling inputs, and as flagged by dsconfig: `languages`, `spk_embed` [1,T,hidden], `gender` (key shift, scaled by augmentationArgs.randomPitchShifting.range), `velocity`, `energy`, `breathiness`, `voicing`, `tension`. output: mel [1,T,bins].

**sampling inputs.** if `use_continuous_acceleration`: `steps` int64 and (if variable depth) `depth` float in 0..1. otherwise `speedup` int64 = largest divisor of 1000 that's ≤ 1000/steps, and (if variable depth) `depth` int64 = round(depth*1000) rounded down to a multiple of speedup. max_depth caps depth. older banks use the `use_shallow_diffusion` key for variable depth.

**vocoder.** inputs `mel`, `f0` (hz) → `waveform` [1,samples]. resample to the output rate if needed.

**speakers / voice modes.** each speaker is a `.emb` file. subbanks in character.yaml map voice colors to speaker suffixes and pitch ranges. mixing is per-frame weights over speakers, normalized so weights sum to 1, then a dot product with the embedding matrix. expose voice modes by name and allow per-note or ranged mixes.

don't trust dsconfig flags alone: read each onnx session's actual input names, decide what to feed from both, and raise a clear error naming any missing/extra inputs. this is what keeps odd or old banks working.

## 2. the engine, designed for an agent

- python package with a short cli name (pick one, not tied to any singer). targets macos arm64 and linux. cpu onnxruntime by default, no gpu assumed, with the coreml (mac) and cuda (linux) execution providers as options. keep openutau's mit and diffsinger's apache-2.0 license notices on any ported code, and credit both in the readme. load sessions lazily and cache them in-process; also add a persistent `serve` mode (stdin json-lines or a unix socket) so repeated renders don't pay model load time each call. multiple banks can be loaded at once.
- **mcp server.** expose every command as a tool on an mcp server (stdio transport), on top of the same core as the cli. typed parameters, structured json results, and `inspect`/`analyze`/`compare` return their images as actual image content, not just file paths, so an agent sees them in context. keep sessions warm between calls. the cli and the mcp server must stay feature-identical; generate one from the other's command definitions if that's easy.
- **score format** (plain text), terse and diff-friendly, one note per line:
  ```
  bank ./banks/some_singer
  bpm 120
  lang ja
  voice default
  ら C4 1
  ら D4 1/2
  + E4 1/2        # continuation (melisma) of previous syllable
  r 1             # rest, length in beats
  [k a] G4 1      # explicit phonemes (ds) or [alias] (utau)
  ```
  `bank`, `lang` and `voice` can change mid-score. the format also needs tempo changes (`bpm 140 @ bar 17`), time signatures, key, bar/beat positions as an alternative to sequential lengths, and multiple named tracks (`track lead` / `track harmony`), each with its own bank, phonemizer, voice and volume/pan. also accept json, inline via `-e "ら:C4:1 ら:D4:1/2"`, and `.ust` (utau) and `.ustx` (openutau) import, keeping their pitch bends, flags and expressions where they map. lengths in beats or ms. per-note or ranged controls: pitch offset curve, vibrato, expr, energy/breathiness/voicing/tension offsets, voice mode mix, gender/key shift, velocity.
- **getting songs in.** agents will mostly start from midi, musicxml, or a melody plus lyrics as plain text, not hand-typed notes. support midi import (pick tracks, quantize, read embedded lyric events), musicxml import (lyrics, ties, slurs, tempo and time signature marks), and export of the score back to midi and musicxml. a `lyrics` command assigns text to notes: it splits text into syllables or mora per language (japanese via pykakasi or fugashi for kanji → kana, with small kana, っ and ー handled; english via a hyphenation/syllable dictionary; chinese one character per note), assigns one per note with `+` continuations when there are more notes than syllables, and reports mismatches instead of silently dropping text. it also shows the reading it chose for every kanji so an agent can correct misreadings.
- **finishing a song.** mixing of all tracks with volume/pan, an optional instrumental/backing track placed at an offset (in seconds or bars), loudness normalization to a target lufs, stem export per track, and wav/flac output at a chosen sample rate. `inspect` can take the mix or a single stem.
- **commands**
  - `banks`: list detected banks with type, languages, voice modes and missing dependencies (like a vocoder), as json.
  - `probe <bank>`: the inspection above, as json.
  - `phonemize <score>`: phonemes or aliases per note with timings in ms and frames, unknown lyrics listed with the closest valid symbols. no audio.
  - `sing <score> -o out.wav [--steps N --depth D --seed S]`: full render. stdout is a json report (paths, duration, phrase count, per-stage timing, warnings). nothing chatty on stdout; logs to stderr.
  - tuning commands are in section 5, and `inspect` / `analyze` / `compare` / `pitch extract` are in section 6.
- deterministic when `--seed` is set (diffusion noise), so a/b comparisons are fair.
- cache tensors per stage keyed by a hash of inputs, so changing only the vocoder or only variance offsets doesn't recompute everything.
- errors are specific and actionable: which lyric, which phoneme, which model, which input, which file.

## 3. the utau path

- read classic banks: `oto.ini` in the root and in subfolders (alias, offset, consonant, cutoff, preutterance, overlap; negative cutoff is measured from offset, positive from the file end), `prefix.map` (per-pitch prefix/suffix, used for multi-pitch banks), `character.txt`, `readme.txt`, and openutau's `character.yaml` subbanks when present. detect encodings (shift-jis, utf-8, gbk, others) and say which was used.
- lyric → alias resolution goes through phonemizers (section 4). apply prefix.map by note pitch, and support per-note append suffixes for multi-expression banks.
- **external resamplers and wavtools.** the utau sound people actually know comes from resamplers like moresampler, tips, straycat, hifisampler and worldline, so the engine must be able to call any resampler or wavtool executable through the standard utau command-line interface. that means the full resampler argument list (input, output, tone, velocity, flags, offset, length, consonant, cutoff, volume, modulation, tempo, and the base64-encoded pitchbend string with its run-length `#n#` compression) and the wavtool argument list (output, input, stp, length, envelope points, overlap). read openutau's classic resampler code for the exact encoding and match it. support native builds where they exist (straycat-rs and others are cross-platform), and running windows-only exes through wine when it's installed. resamplers live in a `resamplers/` folder, chosen per bank, per track or per note, with each tool's supported flags listed by a `resamplers` command. cache resampler outputs by argument hash, run them in parallel, and report a resampler's crash or empty output as a clear per-note error.
- built-in resampler (the fallback, and the default when no external one is installed): pyworld (harvest or dio + cheaptrick + d4c) to pitch-shift and time-stretch each sample to the note, keeping the consonant region unstretched (fixed), stretching or looping the vowel region, applying the pitch curve. support the common flags g (gender/formant shift), b (breathiness), and velocity (consonant speed); ignore unknown flags with a warning.
- wavtool: place each note at its position minus preutterance, crossfade with the previous note over the overlap, apply volume and envelopes like classic utau.
- `sing --engine ds|utau` picks the path when a bank could go either way, so the same score can be compared across a classic and a diffsinger version of the same singer.

## 4. phonemizers: as many as possible, with parity

the goal is coverage close to openutau's whole phonemizer catalog, not a handful of hand-written ones.

- read `OpenUtau.Core/Api/Phonemizer.cs` and the base classes in `OpenUtau.Plugin.Builtin/` (`SyllableBasedPhonemizer`, `LatinDiphonePhonemizer`, `BaseChinesePhonemizer`, the presamp-based japanese phonemizer, and whatever else the repo has now). mirror that api in python: a phonemizer gets the current note group plus previous and next neighbors and returns phonemes with position offsets and per-phoneme attributes (alternate, shift, color, expressions). port the base classes first, because most phonemizers are thin subclasses of them; then port the subclasses in bulk.
- inventory every phonemizer in the repo (classic utau and diffsinger) into a table: name, language, base class, required bank files (presamp.ini, dictionaries, g2p models), and port status. aim to port all of them. the ones that depend on .net-only libraries or bundled g2p models get a python equivalent or a clear "not ported, here's why" entry.
- support the shared building blocks they rely on: presamp.ini (vowel/consonant tables, endings, priorities, replacements), dictionary formats (cmudict-style, yaml g2p dicts, openutau's g2p onnx models where they're plain onnx), kana/hangul/pinyin conversion, and the `[phonetic hint]` and `+`/`-` lyric conventions.
- **parity testing against openutau itself.** write a tiny .net console tool that references `OpenUtau.Core` and `OpenUtau.Plugin.Builtin`, loads a bank, runs a named phonemizer on a list of notes, and prints the result as json. use it to generate golden outputs for every ported phonemizer across a test set of lyrics, then diff the python port against them. a phonemizer counts as ported when it matches the goldens. if dotnet isn't available, install it; if that's impossible, say so and fall back to hand-written goldens.
- `phonemizers` command lists every available phonemizer with language and which loaded banks it's compatible with. auto-pick a default per bank (character.yaml `default_phonemizer`, reclist detection) and let the score override it per track or per note.

## 5. tuning toolkit for agents

the priority for now is giving an agent everything it needs to tune by hand, the way a human tuner works in openutau, and to judge the result itself. learned tuners come later (section 7).

**pitch representation.** every note's pitch is the note grid plus a deviation curve in cents. store deviations as editable control points with per-segment interpolation (linear, ease in/out, s-curve, hold), plus an optional raw per-frame layer on top. vibrato is a separate object per note (rate hz, depth cents, onset delay, fade in/out, phase, drift), rendered into the curve at the end. this keeps edits small and readable instead of a wall of numbers.

**tuning ops**, each a small command and also a json op so an agent can batch them:
- transitions: shape the bend between two notes with duration, start offset relative to the boundary, curve type, preparation dip, overshoot amount and settle time.
- note-level: scoop in, fall off, flat hold, pitch offset, drift (slow random wander with a seed), fry/creak dips at note ends.
- vibrato: add, edit, remove, copy; preset styles (none, subtle, pop, ballad, opera, wide and late).
- dynamics and timbre where the engine supports them: volume/intensity, envelopes, breathiness, gender/formant, tension, voicing, velocity (consonant speed), per-note utau flags, diffsinger variance offsets and voice-mode mixes.
- timing: nudge note starts, consonant length, preutterance/overlap overrides per note (utau), phoneme duration overrides (diffsinger).
- bulk and reuse: apply an op to a selection (by index range, lyric, interval size, note length), copy tuning from one phrase to another, save and load named presets, and run any built-in auto-tuner as a starting draft to edit.
- built-in auto-tuners as starting points: flat, utau mode1 (raw PitchBend), utau mode2 (PBS/PBW/PBY/PBM plus VBR), openutau's default portamento and vibrato, a rule-based tuner (interval-aware preparation, overshoot, drift, vibrato onset and depth ramp by note length), and the diffsinger pitch model as a tuner, so a utau bank can borrow a neural pitch curve.

**tuning state.** a project file holds the score, phonemizer choices, and all tuning, as diff-friendly text. every edit is versioned (undo, redo, named snapshots, diff between two states). `tune show <project> [--notes 12-20]` prints a compact table of each note's lyric, pitch, transitions, vibrato and expressions, so an agent can read the current state without an image.

**fast loop.** editing one phrase re-renders only that phrase (cached everything else), so an agent can make an edit, render, look, and repeat in seconds. `sing --phrase 3` and `sing --range 10-20` render just a slice.

**import and export.** ust (mode1 and mode2, flags, envelopes, tempo changes) and ustx (curves, vibrato, expressions) both import into this representation and export back out without losing tuning, so work moves freely between the engine and the openutau gui. also import pitch from a reference vocal recording: extract f0 and align it to the score, so an agent can match a real performance.

## 6. perception: making the agent understand what it sounds like

this is the most important part of the engine for an agent. it has no ears, so every render has to come with images and numbers that describe it as fully as a listener would. one command, `inspect <wav> [--score project] [--notes 12-20] [--ref other.wav]`, writes a folder of images plus a json report. images must be readable when an agent views them: big labels, the lyric and note name on everything, consistent colors, and zoomed crops rather than one huge plot.

**images**
- piano roll: the target note grid with lyrics and phoneme boundaries, the intended pitch curve, and the measured f0 of the render, on a semitone axis with octave and note-name gridlines.
- spectrograms: linear and mel, log-frequency, with harmonics visible, phoneme boundaries and lyric labels on the time axis, and f0 overlaid. a zoomed version per phrase and per note on request.
- cents-error strip: per-frame deviation of measured from intended pitch, colored by size, so tuning mistakes and resampler errors jump out.
- vibrato close-ups: measured vs intended vibrato with fitted rate and depth.
- loudness and timbre lanes: rms/lufs, breathiness or aperiodicity (from d4c), spectral centroid, harmonic-to-noise ratio, and formant tracks f1–f3 per vowel.
- join view (utau): every concatenation point with a small waveform and spectrogram crop before and after, so clicks and timbre jumps between samples are visible.
- a/b views: two renders side by side and a difference spectrogram, aligned by dtw when timings differ.

**numeric report (json)**
- per note: intended vs measured pitch (median cents error, worst, % of frames within 20 cents), onset offset, voiced ratio, transition shape stats, vibrato rate/depth/regularity, loudness, breathiness.
- artifacts, each with timestamps and a severity: clicks and discontinuities at joins, sudden spectral or pitch jumps, octave errors, unvoiced frames inside vowels, noise or bleed in rests, clipping, dc offset, aliasing above the original sample's bandwidth, robotic flatness (pitch variance near zero on long notes), and phase/buzz artifacts from the resampler or vocoder.
- intelligibility: if a speech recognizer can run locally (whisper or similar, cpu is fine for short clips), transcribe each phrase and compare it to the lyrics, reporting which syllables came out wrong. this is the closest thing to the agent hearing whether the words are understandable. say plainly when it's unavailable.
- a short plain-text "listening notes" summary generated from the numbers, like "phrase 2: note 5 (か, a4) lands 40 cents flat for 120 ms after a slow transition; click at the join into note 6; vibrato on note 9 is 7.8 hz, faster than the rest", so an agent gets the gist before opening images.

**other perception tools**
- `analyze <any wav>` runs the same pipeline on any audio, including a real singer's recording, so agents can study references and match them.
- `pitch extract <wav>` gets f0 with a choice of extractor (harvest, dio, crepe or rmvpe if installable) and reports where extractors disagree, since extractor errors would otherwise look like tuning errors.
- `compare a.wav b.wav` gives the a/b images and a numeric diff, for checking whether an edit actually helped.
- `play`-free sanity checks: duration, sample rate, peak and rms, and a warning when a render is silent or all noise.

## 7. later: learned tuners

once the toolkit and perception are solid, the next phase is a learned tuner. pretrain on sung f0 extracted from public singing databases with aligned scores, fine-tune on community usts collected only where the terms allow it (or donated with consent), with style tags for sung vs ust. evaluate by regenerating held-out songs from bare notes and scoring against the reference curves. don't build this now, but keep the tuning representation and the per-note stats in `inspect` usable as training features and eval metrics, so this phase plugs straight in.

## 8. testing

- don't wait for real banks to start. generate mock banks:
  - a mock diffsinger bank of tiny onnx models built with the onnx python api, whose input/output names, dtypes and rank match the real signatures above (outputs can be simple deterministic functions of inputs, like a mel derived from f0, so `inspect` has something to measure). make variants that toggle the optional pieces: no dspitch, no dsvariance, multi-speaker, use_lang_id with prefixed phonemes, continuous acceleration vs speedup, txt vs json phonemes, abs vs rel duration models, bundled vs named vocoder.
  - mock utau banks generated from sine/formant samples with matching oto.ini files in cv, vcv and cvvc styles, one with prefix.map and pitch subfolders, one in shift-jis.
- run every command on every mock. unit tests for the timing math (frame rounding, padding, alignment/stretch, note_dur fitting, rest midi filling, word_div construction), dict lookup and language front-ends, oto.ini parsing and alias resolution, and the speaker mix.
- phonemizer parity goldens from the .net harness, run as part of the test suite.
- ust/ustx round-trip tests: parse then re-export without losing tuning, and the mode2 → curve conversion matches openutau's.
- tuning ops: each op changes exactly what it claims (check the curve numerically), and undo/redo/snapshots round-trip.
- perception: plant known faults in mock renders (a click, a 50-cent flat note, an octave jump, noise in a rest, a clipped peak) and check `inspect` finds each one at the right timestamp. also check that a clean render reports no artifacts.
- external resampler bridge: the pitchbend encoding and argument strings match openutau's for the same notes (golden tests), and a mock resampler script records the arguments it receives.
- importers: midi and musicxml fixtures with tempo changes, ties and lyrics; the `lyrics` command on japanese (with kanji, small kana, っ, ー), english and chinese text.
- with real banks: probe each, then render a few phrases (a scale on one vowel, a short line exercising tricky phonemes for that language, a melisma, a phrase with rests), run `inspect` on each, and report the numbers.

## 9. scope

**non-goals for now:** no gui; no enunu/nnsvs, vogen, voicevox or other renderers beyond diffsinger and classic utau (but keep the renderer interface clean enough to add them later); no learned tuners (section 7); no realtime playback.

**done means**, per milestone. don't move on until the current one is met:
1. probe: every test bank (real and mock) probes and `--check`s with no crashes, and the output is accurate when compared by hand.
2. first sound: a japanese cv utau bank and the first diffsinger bank each sing an 8-note phrase from the text format, from midi + lyrics, and from a ust, end to end.
3. perception: `inspect` produces every image and metric in section 6, and the planted-fault tests pass.
4. utau depth: vcv and cvvc banks, prefix.map, at least one external resampler and wavtool via the cli interface, and a ust round-trip that preserves tuning.
5. tuning: every op in section 5, undo and snapshots, phrase-only re-render, and a short song tuned by an agent using only the tools, with before/after `compare` reports.
6. finishing: multi-track mix over an instrumental, loudness normalization, stems.
7. mcp server feature-identical to the cli.
8. phonemizers: the parity harness runs in the test suite, and the inventory table shows status for every phonemizer in openutau.

## 10. working style

- start with `probe` on whatever real banks i give you, and show me the summary before building on assumptions.
- follow the milestone order in section 9, and get one thing rendering end to end early.
- keep the core small: bank loading, score and importers, lyrics, phonemizers, ds pipeline, utau path and resampler bridge, tuning, perception, mixing, cli/mcp. no framework. adding a bank quirk, a phonemizer or a tuner should mean adding or touching one file.
- write a short readme with the score format and every command, written for a future agent session that has never seen this project.
