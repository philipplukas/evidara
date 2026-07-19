@AGENTS.md

## Claude Code quick reference

Repo-wide conventions live in `AGENTS.md` (imported above). This file only adds Claude-Code-specific pointers not covered there.

### Planning anchor

The current anchor is **issue #628 — M13: prove the coverage loop**. It executes
[ADR-0033](docs/adr/0033-agentic-legal-reasoning.md) (Accepted): the bet is that a thorough data
platform for law makes AI use cases easy, so the deliverable is the **loop** — blueprint → source
version → acceptance run → evidence → `enabled: true` → approval — not the corpus, which is its
output. The vertical slice is iteration 1; breadth is iterations 2..N.

Acceptance test: ADR-0033's dog question, answered over a corpus **assembled through the platform**
— or refused correctly because the ordinance is not in it.

ADR-0033 §4 is a standing guardrail: **do not build the MCP server first.** Its build order is
dependency-forced, and #628 tracks which steps are done.

The predecessor M1–M6 roadmap (#279) closed 2026-04-20. When opening new work, prefer
`/issue-execute <number>` if a ticket exists; otherwise scope inline against #628.

### Per-surface quality gates

Run the narrowest gate for the surface you touched before pushing:

| Surface | Gate |
|---|---|
| `platform-control/` | `cd platform-control && uv run ruff check . && uv run ruff format --check . && uv run pytest` |
| `platform-control/admin/` | `cd platform-control/admin && npm run check` |
| `document-intelligence/` | `cd document-intelligence && uv run --extra dev --extra service --extra test pytest && uv run ruff check . && uv run ruff format --check .` |
| `legal-search/api/` | `cd legal-search/api && npm run check` |
| `legal-search/frontend/` | `cd legal-search/frontend && npm run check` |
| `country-overlays/` or `platform-control/src/platform_control/seeds/` | `python scripts/check_country_overlay_files.py` |
| Any scraping-touching PR | `bash scripts/check-scraping-qa.sh` |

For `document-intelligence/`, the extras are not optional: a bare `uv run pytest` cannot collect
`test_instructor_extractor` or `test_eval_docling_extractor` and reports green over a smaller suite
than CI runs. `ruff format --check` is likewise part of the CI job, not just `ruff check`. The full
CI gate is `scripts/check-document-intelligence.sh`, but it installs into the ambient `python3`
rather than a uv environment, so prefer the command above locally.

### ID contract (see #264)

Canonical seeds: `platform-control/src/platform_control/seeds/reference/{authorities,jurisdictions,compliance_policies,extractor_profiles}.yaml`.
Legacy (being retired): `platform-control/src/platform_control/hierarchies/{authorities,jurisdictions}.yaml`.
Any PR that renames or adds an `authority_id` / `jurisdiction_id` must keep the canary script `scripts/ch-fedlex-fast-loop.sh` functional — it hardcodes `auth_fedlex` and `jur_ch_federal`.

### Alembic

Migrations under `platform-control/`. Current head at time of M0: `20260417_0010` (see #253 for staging/prod rollout).

### ADRs

`docs/adr/` — numbered. Add one for any architecture-level decision (see AGENTS.md rule on `architecture-change`).
