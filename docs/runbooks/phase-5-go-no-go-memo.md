# Phase 5 go / no-go memo (draft)

Owner: Platform lead  
Last reviewed: 2026-04-11  
Last verified: 2026-04-11  
Applies to: dev → staging transition (Linear **TAR-69**)  
Canonical template history: this file is the **working draft**; publish final recommendation in Linear **TAR-69** when all gates are green.

**Operator entry point:** [Phase 5 evidence checklist](phase-5-evidence-checklist.md) (TAR-64 / TAR-77 / TAR-85 in one place).

## 1. Summary recommendation

- **Recommendation:** **PENDING** — operator evidence still required for full dev smoke (TAR-64 ×2), branch protection proof (TAR-77), and fresh staging MVP acceptance (TAR-85). Repo implementation for search/metadata/relevance is merged.
- **Date:** 2026-04-09 (draft)  
- **Environment(s) covered:** dev (partial — local + historical CI), staging (last verified 2026-04-08 per MVP acceptance tables; **re-verify** after each promotion batch on `main`)

## 2. Gate outcomes

| Gate | Source | Result | Evidence link |
|------|--------|--------|----------------|
| A–C vertical slice | `docs/runbooks/first-vertical-slice-exit-gates.md` | **PENDING** (dev smoke ×2) | See **TAR-64: dev smoke evidence** in that runbook |
| Local pre-flight | `scripts/vertical-slice-exit-gates-local.sh` (2×) | pass | Rows 2026-04-09 in verification log |
| MVP acceptance (staging) | `docs/runbooks/mvp-acceptance-scenario-pack.md` | pass (last table **2026-04-08**) | [mvp-acceptance-scenario-pack.md](mvp-acceptance-scenario-pack.md#latest-verification-evidence-2026-04-08) — **refresh** with `evidara workflow mvp-acceptance` (payload includes `evidence_pack_version`) |
| Release Readiness (strict) | `Release Readiness` workflow | GO (historical) | Re-run on current `main`; download artifact **`release-readiness-<run_id>`** (JSON gate snapshots) and keep the run URL + GCS report path together in Linear (see section 2.1) |
| Interaction flow | `docs/runbooks/interaction-flow-validation.md` | pass (historical) | Latest staging workflow run + GCS bundle; generated manifest now includes a **TAR-67 / TAR-69** drill block (see section 2.1) |

## 2.1 Evidence capture improvements (repo, 2026-04-11)

These changes **lower friction** for operators filing **TAR-64**, **TAR-67**, and **TAR-69** evidence. They **do not** replace missing dev smokes, branch-protection proof (TAR-77), or a fresh staging MVP acceptance pass.

| Area | What landed | Operator action when updating this memo |
|------|-------------|----------------------------------------|
| Runbook drill pattern | Shared “Operational drill evidence (TAR-67)” sections + cross-links: [first vertical slice exit gates](first-vertical-slice-exit-gates.md#drill-evidence-capture-tar-67), [DLQ triage](dlq-triage-and-replay.md#operational-drill-evidence-tar-67), [release / rollback](release-rollback.md#operational-drill-evidence-tar-67), [alert response](alert-response-playbook.md#operational-drill-evidence-tar-67) ([PR #191](https://github.com/philipplukas/evidara/pull/191)) | Paste the same discipline into Linear issues; prefer run URLs + downloaded artifacts over screenshots in git |
| Release Readiness | Report ends with **Drill evidence**; workflow uploads artifact **`release-readiness-<run_id>`** | Attach strict-run URL **and** artifact zip (or file list) when claiming “latest GO” |
| E2E Smoke Staging | Step summary links exit gates + [TAR-64 / TAR-85 evidence capture](tar64-tar85-evidence-capture.md); artifact **`e2e-smoke-staging-drill-<run_id>`** (JSON with `platform_control_run_id`, `legal_search_document_id`, …) | Use JSON for Gate D style copy/paste into Linear |
| Interaction Flow Staging | `interaction-flow-staging-evidence.md` includes drill filing bullets | Attach workflow run URL + `STAGING_EVIDENCE_GCS_PREFIX` from logs when filing browser evidence |
| Platform-control replay | `GET /v1/runs/{run_id}` exposes `replay_checkpoint` ([PR #190](https://github.com/philipplukas/evidara/pull/190)) | Cite checkpoint JSON when discussing acquisition partial reruns in risk reviews |

## 3. Search and metadata quality

| Topic | Status | Notes |
|-------|--------|--------|
| Projection fields (title, type, dates, structural path) | **Shipped** | `ProjectionsService` maps canonical DI lean rows; see `search-relevance-baseline.md` |
| Relevance eval pack | **PENDING** | Run staging query pack in `search-relevance-baseline.md`; attach top-N table to TAR-82 / TAR-68 |
| Open issues | | TAR-64, TAR-77, TAR-85 until evidence attached |

## 4. Risk register

| Risk | Severity | Mitigation | Owner |
|------|----------|------------|-------|
| Branch protection not enforced | High | Complete TAR-77; block merge until required check appears on PRs | Repo admin |
| Stale staging acceptance | Medium | Re-run MVP acceptance after each release candidate | Platform |
| Dev smoke drift | Medium | Two smoke passes on current `main` for TAR-64 | Platform |
| Acquisition replay resume gaps | Medium | Use `GET /v1/runs/{run_id}` `replay_checkpoint` plus provider reruns; treat Temporal `resume_token` as experimental until activities persist full frontiers | Platform |

## 5. Follow-ups (must be tracked issues)

- [ ] TAR-64 — two dev smokes with Gate D IDs  
- [ ] TAR-77 — ruleset screenshot + green `Release Readiness`  
- [ ] TAR-85 — staging `evidara workflow mvp-acceptance` output  
- [ ] Phase 5 workstreams: TAR-66 → **TAR-62 (merged)** → **TAR-63 (merged)** → **TAR-67 (runbook + CI drill surfaces merged; execute drills + attach evidence)** (see section 7)

### Repo gates to run before merge (automatable)

From repo root: `bash scripts/check_docs.sh`, `bash scripts/check-legal-search.sh`, `bash scripts/check-evidara-cli.sh`, `bash scripts/check-platform-control.sh` (needs Docker for one Postgres integration test), `cd document-intelligence && uv run ruff check . && uv run pytest tests/`.

## 6. Operator demo

- **Script:** `docs/runbooks/mvp-demo-release-recommendation.md` / `mvp-website-walkthrough.md`  
- **Demo date / participants:** _TBD after GO recommendation_

## 7. Phase 5 workstream schedule (recommended)

Narrative + evidence pointers: [post-MVP engineering workstreams](post-mvp-engineering-workstreams.md).

Execute after MVP path is credible (TAR-64 green):

1. **[TAR-66](https://linear.app/tart-baozi/issue/TAR-66)** — Harden HTML parsing + corpus fixtures (ingest stability). **Repo:** header chrome skip + regression tests merged ([#195](https://github.com/philipplukas/evidara/pull/195)); extend or close in Linear if remaining scope is fixture-only.  
2. **[TAR-62](https://linear.app/tart-baozi/issue/TAR-62)** — Automate DI + infra promotion (dev → staging → prod).  
3. **[TAR-63](https://linear.app/tart-baozi/issue/TAR-63)** — Resumable replay / checkpoint orchestration (platform-control).  
4. **[TAR-67](https://linear.app/tart-baozi/issue/TAR-67)** — Operational drills + runbook verification (withdrawal, DLQ, alias rollback). **Repo surfaces for drill evidence are on `main` (2026-04-11);** operators must still **run** drills and attach URLs + artifacts per section 2.1.

Optional parallel: [TAR-139](https://linear.app/tart-baozi/issue/TAR-139) (agent workflow surface) — **`agent-discovery` OpenAPI tags** landed ([#196](https://github.com/philipplukas/evidara/pull/196)); journal / mutating workflow APIs remain future if needed. Wizard epic [TAR-106](https://linear.app/tart-baozi/issue/TAR-106) is post-M5.

## Related docs

- [Phase 5 evidence checklist](phase-5-evidence-checklist.md) — single-page index for TAR-64, TAR-77, TAR-85
- [M5 evidence checklist](m5-evidence-checklist.md) — step-by-step operator actions for TAR-64, TAR-77, TAR-85  
- [Search relevance baseline](search-relevance-baseline.md) — staging eval pack for TAR-82 / TAR-68  
- [First vertical slice exit gates](first-vertical-slice-exit-gates.md)  
- [MVP demo package and release recommendation](mvp-demo-release-recommendation.md) — operator evidence packet template (updated with section 2.1 artifact names)
