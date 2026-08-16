# Transfer notes

Everything in this directory is self-contained. It imports nothing from the surrounding
monorepo, so copying this folder anywhere is enough — no path fixing, no vendored deps.

## Getting it

Three routes, best first:

1. **Git.** It is already pushed to `philipplukas/evidara`, branch
   `claude/synthetic-speech-dynamics-0fq4w8`, under `spikes/synthetic_speech/`.
   `git clone`, `git checkout` that branch, and the folder is there with full history.
2. **The tarball**, `synthetic_speech.tar.gz`, sent alongside these notes. It excludes
   `.venv/`, `__pycache__/`, `*.egg-info/` and the ruff cache — nothing else.
3. Copy the directory verbatim.

## Running it on the research machine

```bash
cd synthetic_speech
uv venv --python 3.12 && uv pip install -e ".[dev]"
uv pip install torch --index-url https://download.pytorch.org/whl/cpu   # optional: the GRU baseline
uv run pytest -q          # 93 tests, ~4 s — run this first, it pins the generator's exactness
bash run_all.sh --quick   # smoke run, minutes
bash run_all.sh           # full corpora, roughly an hour on 4 cores
```

Without torch the GRU baseline is skipped and experiment 08 falls back to the
frame-independent model as its "generic" comparison; everything else is unaffected and the
report records `gru_available: false`.

## Provenance of the checked-in results — read this before quoting a number

`results/` currently holds a **mixed run**. The session was interrupted partway through the
full sweep, so:

| Experiment | Corpus | Status |
|---|---|---|
| 01 temporal effect | 2000 sequences | **full** |
| 02 temporal rank | 3000 sequences | **full** |
| 03 kernel recovery | 4000 sequences | **full** |
| 04 Jacobian / articulation | 3000 sequences | **full** |
| 05 dynamics identification | 4000 sequences | **full** |
| 06 identifiability | 400 sequences | quick — rerun before quoting |
| 07 group vs groupoid | 900 sequences | quick — rerun before quoting |
| 08 recognition | N up to 1000 | quick — rerun before quoting |
| 09 assumption stress test | 500 sequences | quick — rerun before quoting |

The qualitative conclusions in `README.md` hold in both regimes, but the quick-run numbers
for 06–09 are noisier, and one of them is materially different: experiment 03's two-mode
pole recovery goes from 59% error at quick size to **2%** at full size, because the second
articulatory mode carries ~0.03% of the contrast energy and needs the sample size to clear
the noise floor. Treat any 06–09 figure as provisional until `bash run_all.sh` has been run
end to end.

`bash run_all.sh` regenerates everything deterministically from `--seed`, and
`experiments/build_report.py` rebuilds `results/SYNTHETIC_SPEECH_REPORT.md` from whatever
JSON is present — it marks missing experiments rather than quietly dropping them.

## What is where

| Path | What it is |
|---|---|
| `config.py` | every ground-truth parameter and the named experimental conditions |
| `dynamics.py` `acoustics.py` `noise.py` `generator.py` | the generative mechanism |
| `analysis/` | the inference side; may not import any generator module (enforced by a test) |
| `experiments/01..09` | one script per experiment, each writing a figure and a JSON |
| `experiments/build_report.py` | aggregates the JSON into the markdown report |
| `experiments/build_artifact.py` | aggregates the same JSON into a standalone HTML page |
| `tests/` | 93 tests, including the two that enforce the oracle discipline |
| `results/` | figures (PDF + PNG), per-experiment JSON, the report |

## The one rule to keep if you extend this

`tests/test_oracle_discipline.py` enforces two things mechanically, and they are the reason
any of these numbers mean anything:

1. nothing under `analysis/` may import `config`, `dynamics`, `acoustics`, `noise` or
   `generator`;
2. every line under `experiments/` that reads a ground-truth attribute must be annotated
   `# GT` (used for scoring or reporting) or `# ORACLE` (fed into an estimator).

A third test deliberately feeds the checker an unmarked line and asserts it fires, so the
rule cannot silently stop working.
