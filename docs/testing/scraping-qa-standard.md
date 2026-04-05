# Scraping QA Standard

## Purpose

Define the smallest credible QA strategy for Evidara scraping and acquisition in a 1–3 person team, aligned with the testing pyramid and current component boundaries.

## Scope

This standard applies to scraping/acquisition behavior owned by `platform-control`:

- provider dispatch (`firecrawl`, deterministic HTTP, and future providers)
- webhook ingestion and idempotency
- artifact and bundle-manifest publication
- `artifact_bundle.available` boundary quality

It does not cover downstream parsing/indexing behavior owned by `document-intelligence` and `legal-search`.

## Team-Realistic Testing Pyramid

Use this minimum pyramid for all scraping changes:

| Level | Required Now | Why it is necessary |
|------|--------------|---------------------|
| Contract tests | Yes | Prevent silent boundary breakage (`ArtifactBundleManifest`, event shape, provenance fields) |
| Unit tests | Yes | Keep provider mapping, retries, dedupe, and state transitions deterministic |
| Golden fixtures | Yes | Catch crawl-output regressions on representative source families |
| Integration tests | Yes (small set) | Prove one run can produce immutable handoff artifacts correctly |
| Staging smoke tests | Yes (scheduled) | Catch environment/runtime drift and external source breakage |
| Large E2E suite | Later | Too expensive/flaky for a small team as a first gate |

## Must-Have Gate (MVP+)

Every scraping change should satisfy all of the following:

1. Contract validation passes for:
   - bundle manifest payload
   - `artifact_bundle.available` event
   - required lineage/provenance fields
2. Golden fixture suite passes for representative source families (target: 8-12 fixtures).
3. Provider canary integration passes (at least one per active provider path).
4. Idempotency behavior is validated:
   - duplicate webhook/event delivery does not duplicate artifacts/manifests.
5. Staging smoke job remains healthy for a small canary source set (target: 3-5 sources).

## Source Family Coverage (Practical Baseline)

Maintain at least one fixture for each:

- clean structured HTML source
- noisy HTML source (nav/footer/chrome heavy)
- sitemap/discovery-heavy source
- JS-rendered capture path (provider snapshot output)
- non-HTML content path that still reaches immutable handoff

For each fixture, assert:

- selected primary artifact role is correct
- expected content type and checksum are present
- bundle provenance is complete
- publication event references immutable bundle manifest refs

## Failure-Mode Tests (High Leverage)

Keep a small deterministic set for:

- upstream 429/5xx and retry policy behavior
- timeout handling and run failure surfacing
- partial callback/replay behavior
- malformed/empty payload handling
- unsupported or unexpected content-type behavior

These tests prevent the most expensive production incidents for acquisition systems.

## Visualization and Operational Confidence

Run a simple scraping/acquisition dashboard per environment with:

- run success/failure rate
- stage latency (`pending -> running -> completed/failed`) p50/p95
- artifact and captured-resource count distribution
- top error categories (timeout, blocked, parse mismatch, empty output)
- last successful run by source version
- duplicate webhook/idempotency counter

Also maintain one run drill-down view (or query playbook) showing:

- source/source-version/run IDs
- provider job ID
- artifact URIs and content types
- published bundle-manifest ref
- emitted event IDs

See [Scraping Run Health Dashboard & Drill-Down](../runbooks/scraping-run-health-dashboard.md) for the baseline panel set and triage workflow.

## CI and Cadence Recommendation

For a 1-3 person team:

- On PR: contract + unit + golden + minimal provider canary integration.
- On merge to main: same checks plus runtime image build checks.
- Nightly: staging smoke pack and drift checks.
- Recommended CI gate command: `bash scripts/check-scraping-qa.sh`.
- Nightly canary operational runbook: `docs/runbooks/scraping-nightly-canary.md`.

Target PR check duration for scraping-focused changes: keep under 10 minutes.

## Temporary Merge Enforcement (Until Branch Protection Is Available)

Because this repository currently cannot enforce required status checks via GitHub branch protection/rulesets on the active plan, use this manual policy:

1. Any PR that changes scraping/acquisition behavior must have a successful `scraping-qa` workflow run.
2. The PR author links the green `scraping-qa` run in the PR body under Reviewer Notes.
3. Reviewer must explicitly confirm the green run before approving/merging.
4. Do not merge scraping-impacting PRs with a missing, failed, or stale `scraping-qa` run.

When branch protection/rulesets become available, replace this manual policy with required-check enforcement on `main`.

## Change Policy

A PR that changes scraping behavior should include at least one of:

- updated or added golden fixture
- updated failure-mode test
- explicit note that behavior is refactor-only with unchanged fixture output

This keeps test maintenance proportional while preserving high confidence.

## 30-Day Adoption Plan (1-3 Engineers)

Use this phased rollout to adopt the standard without overloading a small team.

### Week 1: Enforce PR hygiene

- Enable the scraping/acquisition checklist in the PR template.
- Require explicit "not applicable" or completed items for scraping-affecting PRs.
- Define one owner for fixture quality and one owner for smoke/runtime checks (can be the same person in a 1-person setup).

### Week 2: Stabilize test gates

- Lock a baseline fixture set (target: 8-12 fixtures).
- Ensure at least one provider canary test exists for each active provider path.
- Add/verify idempotency and one failure-mode test per critical boundary.

### Week 3-4: Operational confidence

- Add environment dashboard metrics listed in this document.
- Add a run drill-down query/playbook and include it in runbooks.
- Start nightly staging smoke runs (3-5 canary sources) and alert on failures.

### Definition of Done for adoption

The standard is considered adopted when:

- PR template checklist is actively used on scraping PRs.
- Fixture and canary gates run in CI for scraping changes.
- Nightly smoke exists and has an owner.
- Dashboard + drill-down are available in the target environment.
