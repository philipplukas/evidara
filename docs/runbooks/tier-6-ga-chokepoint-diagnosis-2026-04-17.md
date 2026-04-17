# Tier 6 GA chokepoint diagnosis — 2026-04-17

Owner: Platform / GA
Applies to: GA operator board lanes TAR-70 (gate policy), TAR-238 (runner
reliability), TAR-241 (relevance baseline), TAR-214 (release evidence
refresh) — snapshot taken from PR #241 (`claude/plan-next-steps-OANlO`,
9 commits on top of `main`).

## Purpose

Snapshot of what this session could diagnose about the four GA-board
lanes from a non-operator perspective (no GCP auth, no Hetzner runner
access, no branch-protection admin). The goal is to hand the operator
a clean "what's actually failing vs what's noise" starting point.

## What I could verify vs not

Verifiable from this session:

- Which CI jobs pass/fail against a specific head SHA.
- Whether a failure is **code-owned** (my commits made CI go red) or
  **infrastructure-owned** (runner availability, external-network 403,
  Hetzner rotation, GitHub-Actions queue).
- Static workflow-file inspection (TAR-70 emitted-check surface vs
  required-check surface).

Not verifiable from this session:

- Live runner pool status (Hetzner / Tailscale / kubeconfig).
- Branch-protection configuration on GitHub.
- `staging-relevance-query-pack.sh` execution against dev/staging.
- Operator-captured evidence files.

## PR #241 CI snapshot (after commit `558f137` landed)

Sampled via `mcp__github__pull_request_read(method: get_check_runs)`
earlier this session. **Real CI signal this time** — no more mass
fast-fail pattern like the one that marked the first push. Interpretation
per check:

| Check | Status | Interpretation |
|---|---|---|
| `api` | ✅ | BFF tests pass on ubuntu-latest |
| `frontend` | ✅ | legal-search frontend tests pass |
| `Detect changed paths` | ✅ | dorny/paths-filter is healthy |
| `scraping-qa` | ✅ | contract guard is healthy |
| `document-intelligence-runtime-check` | ✅ | runtime-image build green |
| `Build platform-control image` | ✅ | heavy Nix image build green (not a runner issue) |
| `Build platform-control worker image` | ✅ | same |
| `check` (platform-control) | ❌ | real lint failure — `ruff format` + `ruff check` tripped on new code (fixed in this commit) |
| `contract-validation` | ❌ | real validator rejection — `scripts/check_country_overlay.py` hard-coded provider allow-list (fixed in this commit) |
| `document-intelligence-check` | ❌ | real lint failure — `ruff format` tripped on citation_extractor (fixed in this commit) |
| `Build platform-control admin image` | ❌ | 1-min duration; could be genuine admin build issue. Retry once this commit lands. |
| `interaction-flow-evidence` | ❌ | 3-min duration; Playwright e2e. Could be pre-existing flake or environment — not obviously code-owned. |
| `rocky-agents / QA` | ❌ | instant failure; external integration, not evidara-owned |

## TAR-70 — gate policy hardening

Status: **drift visible in workflow files** — the static analysis is doable.

Observations from reading `.github/workflows/*.yml`:

- `docs-and-contracts.yml` runs on every PR (no path filter). It's the
  real "always-on aggregator" for contract validation.
  **Friction:** 14 sequential steps, any one can redden the whole PR.
  A single failure (e.g., the overlay validator tripping this session)
  taints the whole `contract-validation` check. Consider splitting
  into a matrix of independent checks so failures name the right lane.
- `legal-search.yml` / `platform-control.yml` / `document-intelligence.yml`
  each have path filters. That's sensible per-component scoping.
- `interaction-flow-evidence` in `legal-search.yml` runs on every
  legal-search PR. It does full Playwright suites. **This is the most
  likely source of "always-red" PRs** on feature branches that don't
  touch UX — the 3-minute job with screenshot-pack retries is heavy
  for most PRs.
- `runner-bootstrap-preflight.yml` and `runner-pool-smoke.yml` exist.
  They appear to be periodic/manual, not PR-gating. Good.

Concrete TAR-70 recommendations (not yet actioned in this PR):

1. **Decide what is actually required vs emitted.** Most PRs here do
   not modify UX and don't need `interaction-flow-evidence` green.
   Either add a path filter (`src/components/**`, `src/app/**`) or
   mark it `needs.check.result == 'success'` optional.
2. **Split `contract-validation` into scoped jobs**: one per class
   of check (OpenAPI vs JSON schemas vs country overlays vs markdown
   vs doc links). A typo in one doesn't mask another's failure.
3. **Publish the emitted/required diff.** Run
   `python scripts/check_gate_policy_emitted_vs_required.py` (exists
   per the backlog) and attach to TAR-70 with the current delta.

## TAR-238 — runner reliability

Status: **visibly improved since the first session push**. The first
PR #241 push (commit `8cc8f96`) showed mass fast-fail on <3-second
runs across many jobs — classic runner-unavailable pattern. The most
recent push (`558f137`) shows real signal (successes, targeted
failures, no mass sub-3-second fails).

Not verifiable from this session: whether this stability will hold
through a recycle / scale-set change. TAR-238's `runner-pool-smoke.yml`
should continue on schedule.

## TAR-241 — relevance baseline

Status: **not touched this session**. My work added citation
extractors for DE/FR/IT (T5.3) and ELI URI emission (T5.1) which may
influence relevance once projected, but the baseline run itself is
operator work. Still open per the backlog.

Recommendation: run `scripts/run-staging-relevance-query-pack.sh` after
T4.1's EurLex acceptance run lands — the combined "new CH/IT ELI
metadata on canonical docs + richer citation coverage" is the right
moment to capture a fresh baseline.

## TAR-214 — release evidence refresh

Status: **not touched this session**. Depends on TAR-77 / TAR-64 /
TAR-85 lanes owned by the operator board. This PR adds to the body
of changes in flight; the refresh cycle should follow.

## Fixes landed in this commit (code-owned)

1. `scripts/check_country_overlay.py`:
   - Accept `eur_lex_sparql`, `bundesland_http`, `regione_http`
     providers (previously hard-coded to 4 providers).
   - Added EU to `--country` allowed set.
   - Refactored into `_SUPPORTED_PROVIDERS` constant to catch the
     parity-with-enum concern.
2. `.github/workflows/docs-and-contracts.yml`:
   - Added EU to the blueprint-validation matrix.
   - Added `check_country_overlay_files.py` as a separate step so its
     failure is distinguishable from blueprint-validator failures.
   - Added `test_check_country_overlay_files.py` to the contract-guard
     unit-test discovery list.
3. `platform-control/src/acquisition_core/providers.py`:
   - Renamed `ProviderNotLiveReady` → `ProviderNotLiveReadyError`
     (N818 pep8-naming).
4. `platform-control/src/platform_control/services/*.py`:
   - Ran `ruff format` on all touched files (lint-clean per project's
     `line-length = 100`).
5. `document-intelligence/src/document_intelligence/nlp/citation_extractor.py`
   + tests: same formatting pass.

## Known remaining (not code-owned)

- `Build platform-control admin image` — 1-min build failure.
  Possibly related to recent admin changes; retry once this commit
  rebuilds.
- `interaction-flow-evidence` — 3-min Playwright failure.
  Possibly pre-existing flake; operator should correlate with
  other recent PRs on the same branch.
- `rocky-agents / QA` / `rocky-agents / Release` — external integration
  status, not evidara-owned.

## Next operator actions (by priority)

1. **Retrigger CI on this branch once committed** — verify
   `contract-validation` + `check` + `document-intelligence-check`
   flip to ✅ with the fixes above.
2. **Triage `Build platform-control admin image`** — fetch the log;
   if it's a dep-install transient, retry fixes it; if it's a real
   build issue, needs a follow-up commit.
3. **Decide TAR-70 split** — split `contract-validation` into scoped
   jobs, or add path filter to `interaction-flow-evidence`, or both.
4. **When ready, kick TAR-241** — relevance baseline captured against
   current state.
