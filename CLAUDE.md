@AGENTS.md

## Claude Code quick reference

Repo-wide conventions live in `AGENTS.md` (imported above). This file only adds Claude-Code-specific pointers not covered there.

### Planning anchor

**#628 (M13) closed 2026-07-19** and has no successor planning issue. Do not scope work against
it — read its closing comments for what iterations 1 and 2 measured, then work the live issues
below. (This file pointed at #628 as "the current anchor" until 2026-07-22, three days after it
closed; if you were briefed from a stale pointer, that is why.)

The programme is unchanged and still executes
[ADR-0033](docs/adr/0033-agentic-legal-reasoning.md) (Accepted): the bet is that a thorough data
platform for law makes AI use cases easy, so the deliverable is the **loop** — blueprint → source
version → acceptance run → evidence → `enabled: true` → approval — not the corpus, which is its
output. The vertical slice is iteration 1; breadth is iterations 2..N.

Acceptance test: ADR-0033's dog question, answered over a corpus **assembled through the platform**
— or refused correctly because the ordinance is not in it.

ADR-0033 §4 is a standing guardrail: **do not build the MCP server first.** Its build order is
dependency-forced; #628's closing comments track which steps were done.

**Current lead: #731 — the LexFind provider** (26 cantons + Bund behind one unauthenticated JSON
API). It carries the cantonal rung of the dog question — `tol/22871` is the ZH Hundegesetz, md5-identical
to the canton's own PDF — and its `version_inactive_since` field models repeal separately from
consolidation date, which is what the #661 trap needed.

It was prioritised above the municipal rung (#736, #584) on measured evidence, not preference: the
2026-07-22 full survey of all 2,110 Swiss communes found platform clustering covers only ~5% of the
registry, and that share did not improve as coverage went from 61% to 100%. #736's premise — that
clustering turns ~2,110 units into ~15 — is not currently supported. #731 is the same scaling
question an order of magnitude cheaper, against a homogeneous source.

The predecessor M1–M6 roadmap (#279) closed 2026-04-20. When opening new work, prefer
`/issue-execute <number>` if a ticket exists; otherwise scope inline against ADR-0033's build order.

### Per-surface quality gates

Run the narrowest gate for the surface you touched before pushing:

| Surface | Gate |
|---|---|
| `platform-control/` | `bash scripts/check-platform-control.sh` — ruff check + ruff format --check + pytest **and** the OpenAPI contract-drift gate **and** the full admin gate. A bare `uv run pytest` is narrower than CI. |
| `platform-control/admin/` | `cd platform-control/admin && npm run check && npm run build` |
| `document-intelligence/` | `cd document-intelligence && uv run --extra dev --extra service --extra test --extra llm pytest && uv run ruff check . && uv run ruff format --check .` |
| `legal-search/api/` | `cd legal-search/api && npm run check` |
| `legal-search/frontend/` | `cd legal-search/frontend && npm run check && npm run build` — build is a separate CI step; it catches SSR issues `tsc` misses |
| `legal-search/` (both surfaces) | `bash scripts/check-legal-search.sh` |
| `legal-search/frontend/e2e/` | `bash scripts/check-e2e-spec-coverage.sh` — asserts every spec is selected by some CI command (#686) |
| `marketing/` | `cd marketing && npm run check` (then `npm run build` — the static export is the deploy artifact) |
| `tools/evidara-cli/` | `bash scripts/check-evidara-cli.sh` |
| `eval/` | see `.github/workflows/eval-ris.yml` — two `-k`-filtered pytest selections |
| `scripts/` | `uv run --with pyyaml python -m unittest discover -s scripts/tests -p "test_*.py"` — see note below; without pyyaml only 144 of 201 tests run |
| `country-overlays/` or `platform-control/src/platform_control/seeds/` | `for c in AT CH DE FR IT EU; do python scripts/check_country_overlay_files.py --country $c; done` — `--country` is required; the bare command exits 2 on argparse |
| Any scraping-touching PR | `bash scripts/check-scraping-qa.sh` |

Rows here must not be narrower than what CI runs: a clean local run against a
narrower gate means nothing, and the gap surfaces as a surprise red (#664, #688).

For `scripts/`, `--with pyyaml` is not optional either. CI installs it via
`requirements-docs.txt`; a workstation `python3` may or may not have it, and that is the
point — the gate must not depend on ambient state. Without it eleven test modules fail to
import and the runner reports `Ran 144 tests ... FAILED (errors=11)` — which reads as eleven
broken tests and is really **fifty-seven that never ran**. `uv` is already required by this
repo, so the command above needs no venv and no system package.

For `document-intelligence/`, the extras are not optional: a bare `uv run pytest` cannot collect
`test_instructor_extractor` or `test_eval_docling_extractor` and reports green over a smaller suite
than CI runs. `--extra llm` is on that list as of #685 — without it `test_dspy_modules.py` (11 tests)
is dropped at collection and `test_eval_dspy_extraction.py::test_eval_harness_runs_mock` skips,
covering the production LLM metadata extractor with nothing. `ruff format --check` is likewise part
of the CI job, not just `ruff check`. The full
CI gate is `scripts/check-document-intelligence.sh`, but it installs into the ambient `python3`
rather than a uv environment, so prefer the command above locally.

**Which dependency set each gate runs, and why they differ (#848).** There are two, deliberately:

| Runs | Dependency set | Python |
|---|---|---|
| The command above (`uv run`) | `uv.lock` | `document-intelligence/.python-version` (3.12) |
| `document-intelligence-locked` CI job | `uv.lock` (`uv sync --frozen`) | 3.12 |
| `document-intelligence/Dockerfile*` | `uv.lock` (`uv sync --frozen`) | 3.12 (base image) |
| `document-intelligence-check` CI job + `scripts/check-document-intelligence.sh` | `pyproject.toml` **floors**, resolved against PyPI on the day | 3.12 |

The locked row is what ships; the floating row is the early warning that a new
`deltalake`/`pyarrow` broke us. Until #848 the image also floated and the local gate was the
only locked runner, so the two silently disagreed — measured 2026-09-03, the image built
`deltalake` 1.6.3 / `pyarrow` 25.0.1 while `uv run` gave 1.5.0 / 23.0.1 on Python **3.13**.
Bumping a floor without re-locking now fails `uv sync --frozen` in CI and in the image build
rather than shipping something no gate ran.

### ID contract (see #264)

Canonical seeds: `platform-control/src/platform_control/seeds/reference/{authorities,jurisdictions,compliance_policies,extractor_profiles}.yaml`.
Legacy (being retired): `platform-control/src/platform_control/hierarchies/{authorities,jurisdictions}.yaml`.
Any PR that renames or adds an `authority_id` / `jurisdiction_id` must keep the canary script `scripts/ch-fedlex-fast-loop.sh` functional — it hardcodes `auth_fedlex` and `jur_ch_federal`.

### Alembic

Migrations under `platform-control/`. Current head at time of M0: `20260417_0010` (see #253 for staging/prod rollout).

### ADRs

`docs/adr/` — numbered. Add one for any architecture-level decision (see AGENTS.md rule on `architecture-change`).
