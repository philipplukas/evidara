# The rest of the speech research — where it actually is

Assembled 2026-08-16 by searching every source reachable from this container. Read this
before assuming anything is missing or that anything here is complete.

## The short version

**The code for the empirical speech work is not in this container and is not in any Claude
Code session.** It lives on your own machine. `EMA_LIE_FINDINGS.md` names the path
outright:

> "TORGO ships real 3-D EMA and it was already in this repo at
> `~/Projects/SpeechRecognition/data/raw/torgo`"

So `~/Projects/SpeechRecognition/` **is** the research repo you are trying to assemble, and
it is already on the machine you want to copy *to*. Nothing in this container needs to be
merged into it except the synthetic laboratory in the parent directory.

## What was searched, and what each search returned

| Source | How | Result |
|---|---|---|
| This container's filesystem | `find` for `*hat*`, `*speech*`, `*phon*`, `*articul*`, `*acoustic*`, `*asr*`, `*audio*`; `grep` for `articulat`, `coarticul`, `formant`, `phoneme`, `groupoid` across `.py/.md/.ipynb/.txt/.json` | Only `spikes/synthetic_speech/` — i.e. this session's own work. No "anthropic hats" folder; the only `*hat*` hits were the `hatchling` build backend in the uv cache. |
| `/mnt/attach`, `/mnt/user-data/working` | direct listing | Both empty |
| Claude Code sessions (46, all owned by you) | `list_sessions` | **None speech-related.** Every session targets `philipplukas/evidara`, `philipplukas/MacConfig` or `philipplukas/rocky-agents`, except this one. |
| Published artifacts | `Artifact list`, scope `all` | **8 speech artifacts** — listed below. None is attached to a Claude Code session, so all were published from claude.ai chats. |
| claude.ai chat transcripts | — | **Not reachable.** No tool exposes chat conversations. This is a hard boundary, not an oversight. |

## The 8 speech artifacts

All are private and owned by you; they persist on claude.ai independently of any container.
Mirrored copies of the first two are in this folder.

| Date | Artifact | URL | Mirrored here |
|---|---|---|---|
| 2026-08-15 | The Timescale Race | https://claude.ai/code/artifact/897aee85-01d2-40f1-8e55-5aff397535f6 | no |
| 2026-08-15 | Which Gestures Commute | https://claude.ai/code/artifact/66277857-902e-4c2d-8c2a-53d5d192a61c | no |
| 2026-08-13 | EMA_LIE_FINDINGS.md | https://claude.ai/code/artifact/2eb718ee-c765-455c-a487-f9396b7c2545 | **yes** |
| 2026-08-12 | Sign to Signal Curriculum | https://claude.ai/code/artifact/619e81e0-8a82-4552-9c14-3a3b689ca705 | no |
| 2026-08-12 | Whisper's Speaker Groupoid | https://claude.ai/code/artifact/a39c1365-cda5-4824-b0a9-d51c4a8e2730 | **yes** |
| 2026-08-12 | The Physical Function Space | https://claude.ai/code/artifact/3e92a6fa-af99-4051-89f1-2b40b504918a | no |
| 2026-08-11 | Whisper builds invariance by destroying physical structure | https://claude.ai/code/artifact/19b211f5-7265-44b3-8ffb-58237d6837e5 | no |
| 2026-08-09 | Atlas — a breadth-first pass over the curriculum | https://claude.ai/code/artifact/78b9a47b-2e9f-4aec-9ab2-e2378da9bf8a | no |

(A ninth artifact, "Evidara — A Categorical Model", 2026-07-28, is legal-tech and unrelated.)

## Code the artifacts reference — none of it is in this container

Collect these from `~/Projects/SpeechRecognition/` on the research machine. The artifacts are
the *write-ups*; these are the programs that produced them.

**Whisper speaker-groupoid pipeline** (TIMIT, whisper-small, 8 seeds, 187,737 phone-aligned tokens):

```
algebra_extract.py   algebra_cells.py    algebra_interaction.py
algebra_rank.py      algebra_composition.py   algebra_report.py
```
outputs: `algebra_interaction.json`, `rank_sweep_{SXSI,SXSI11,SA}.json`,
`algebra_composition.json`, written up in `FINDINGS.md §J`

**EMA Lie-bracket test** (TORGO, Carstens AG500, 200 Hz, 18,186 boundary trajectories, 6 speakers):

```
ema_lie_extract.py   ema_lie_test.py   ema_lie_selftest.py
```
outputs: `ema_lie_summary.json`, `ema_lie_test.log`
data: `~/Projects/SpeechRecognition/data/raw/torgo`

## How this connects to the synthetic laboratory next door

The spike in the parent directory is the controlled counterpart to the two empirical results
above, and it was specified partly from them:

- **Groupoid speaker structure.** The Whisper work measures phone-dependent speaker structure
  in a real encoder and finds ~50% of the speaker-related signal in early layers is
  interaction, invisible to any `u ↦ u + d_s` embedding. Experiment 07 in the spike is the
  synthetic version, where the answer is known: a global-group model's held-out error is 2.60×
  the phone-local model's on groupoid data against 1.00× on group data.
- **Its most important caveat transfers directly.** The Whisper work's Experiment 5 shows a
  pure microphone channel reproduces the *entire* qualitative signature — composing arrows,
  mismatched composition worth nothing, free beating tied — and composes *better* than real
  speakers. Composition therefore measures the generator's dimension, not its anatomy. The
  synthetic laboratory can and should be used to calibrate that fingerprint (interaction ÷
  additive, composition score, saturation rank) against generators whose dimension is known
  exactly, which is precisely what it is built to do.
- **The EMA result contradicts a Lie-bracket account** — the interaction is real (ν = 0.456
  outside the first-order span) but *time-symmetric*, not antisymmetric (C = −0.26 for typical
  speakers, where a bracket predicts +1, and the estimator returns +0.95 on planted bracket
  data so it is not a power failure). The spike's second-order dynamics are a blending model,
  which is the alternative the EMA findings recommend fitting on its own terms.

## What I could not do

- **Read your claude.ai chats.** There is no tool for it. If the reasoning behind these
  artifacts matters, the chats themselves have to be exported from claude.ai by you.
- **Recover the `algebra_*.py` / `ema_lie_*.py` sources.** They are not in this container, not
  in any Claude Code session, and not embedded in the artifacts. Only their names, their
  outputs and their conclusions survive in the write-ups.
