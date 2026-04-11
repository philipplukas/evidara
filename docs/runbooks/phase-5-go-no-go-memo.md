# Phase 5 go / no-go memo (draft)

Owner: Platform lead  
Last reviewed: 2026-04-11  
Last verified: 2026-04-11  
Applies to: release readiness / promotion (Linear **TAR-69**); **dev-first teams** use dev for TAR-85 — see [Environment strategy](../setup/environment-strategy.md#operator-posture-dev-first-no-staging-gcp-project)  
Canonical template history: this file is the **working draft**; publish final recommendation in Linear **TAR-69** when all gates are green.

**Operator entry point:** [Phase 5 evidence checklist](phase-5-evidence-checklist.md) (TAR-64 / TAR-77 / TAR-85 in one place).

## 1. Summary recommendation

- **Recommendation:** **PENDING** — operator evidence still required for full dev smoke (TAR-64 ×2), branch protection proof (TAR-77), and fresh **remote** MVP acceptance (**TAR-85** — use **dev** Cloud Run when no staging GCP project exists). Repo implementation for search/metadata/relevance is merged.
- **Date:** 2026-04-09 (draft)  
- **Environment(s) covered:** **dev** (primary remote integration + TAR-85 target for dev-first posture); staging only if your org provisions it — **re-verify** MVP acceptance tables after each promotion batch on `main`

## 2. Gate outcomes

| Gate | Source | Result | Evidence link |
|------|--------|--------|----------------|
| A–C vertical slice | `docs/runbooks/first-vertical-slice-exit-gates.md` | **PENDING** (dev smoke ×2) | See **TAR-64: dev smoke evidence** in that runbook |
| Local pre-flight | `scripts/vertical-slice-exit-gates-local.sh` (2×) | pass | Rows 2026-04-09 in verification log |
| MVP acceptance (remote) | `docs/runbooks/mvp-acceptance-scenario-pack.md` | pass (last table **2026-04-08**) | [mvp-acceptance-scenario-pack.md](mvp-acceptance-scenario-pack.md#latest-verification-evidence-2026-04-08) — **refresh** with `evidara workflow mvp-acceptance` against **dev** (or staging if operated); payload includes `evidence_pack_version` |
| Release Readiness (strict) | `Release Readiness` workflow | GO (historical) | Re-run on current `main`; download artifact **`release-readiness-<run_id>`** (JSON gate snapshots) and keep the run URL + GCS report path together in Linear (see section 2.1) |
| Interaction flow | `docs/runbooks/interaction-flow-validation.md` | pass (historical) | Latest staging workflow run + GCS bundle; generated manifest now includes a **TAR-67 / TAR-69** drill block (see section 2.1) |

## 2.1 Evidence capture improvements (repo, 2026-04-11)

These changes **lower friction** for operators filing **TAR-64**, **TAR-67**, and **TAR-69** evidence. They **do not** replace missing dev smokes, branch-protection proof (TAR-77), or a fresh **TAR-85** MVP acceptance pass (run against **dev** when you have no staging GCP project).

**CI note:** **Release Readiness** uses GitHub Environment **`RELEASE_READINESS_GITHUB_ENVIRONMENT`** (default **`staging`**) for OIDC; set to **`dev`** so GCP project, DI surfaces, GCS evidence root, DLQ regex, and WIF service account follow the **dev** path (see [Environment strategy](../setup/environment-strategy.md#operator-posture-dev-first-no-staging-gcp-project)). It gates on the latest successful **E2E smoke** workflow named **`RELEASE_READINESS_E2E_SMOKE_WORKFLOW`** (default **`E2E Smoke Staging`**; dev-first: **`E2E Smoke Dev`**). Interaction-flow rows still expect **`Interaction Flow Staging Evidence`** until a dev-native workflow exists. Details: [Runtime stack — §7](runtime-stack.md#7-release-readiness-go-no-go-operation).

| Area | What landed | Operator action when updating this memo |
|------|-------------|----------------------------------------|
| Runbook drill pattern | Shared “Operational drill evidence (TAR-67)” sections + cross-links: [first vertical slice exit gates](first-vertical-slice-exit-gates.md#drill-evidence-capture-tar-67), [DLQ triage](dlq-triage-and-replay.md#operational-drill-evidence-tar-67), [release / rollback](release-rollback.md#operational-drill-evidence-tar-67), [alert response](alert-response-playbook.md#operational-drill-evidence-tar-67) ([PR #191](https://github.com/philipplukas/evidara/pull/191)) | Paste the same discipline into Linear issues; prefer run URLs + downloaded artifacts over screenshots in git |
| Release Readiness | Report ends with **Drill evidence**; workflow uploads artifact **`release-readiness-<run_id>`** | Attach strict-run URL **and** artifact zip (or file list) when claiming “latest GO” |
| E2E smoke (staging or dev) | **Staging:** JSON drill artifact **`e2e-smoke-staging-drill-<run_id>`** (`platform_control_run_id`, `legal_search_document_id`, …). **Dev:** log artifact **`e2e-smoke-dev-log-<run_id>`**; workflow summary parses the same-style IDs from stdout (no separate drill JSON upload yet). Both link exit gates + [TAR-64 / TAR-85 evidence capture](tar64-tar85-evidence-capture.md). | Use staging JSON or dev log + summary for Gate D style copy/paste into Linear; align **Release Readiness** with the smoke you run via **`RELEASE_READINESS_E2E_SMOKE_WORKFLOW`** |
| Interaction Flow Staging | `interaction-flow-staging-evidence.md` includes drill filing bullets | Attach workflow run URL + `STAGING_EVIDENCE_GCS_PREFIX` from logs when filing browser evidence |
| Platform-control replay | `GET /v1/runs/{run_id}` exposes `replay_checkpoint` ([PR #190](https://github.com/philipplukas/evidara/pull/190)) | Cite checkpoint JSON when discussing acquisition partial reruns in risk reviews |

## 3. Search and metadata quality

| Topic | Status | Notes |
|-------|--------|--------|
| Projection fields (title, type, dates, structural path) | **Shipped** | `ProjectionsService` maps canonical DI lean rows; see `search-relevance-baseline.md` |
| Relevance eval pack | **PENDING** | Run query pack in `search-relevance-baseline.md` against **dev** (or staging) legal-search API; attach top-N table to TAR-82 / TAR-68 |
| Open issues | | TAR-64, TAR-77, TAR-85 until evidence attached |

## 4. Risk register

| Risk | Severity | Mitigation | Owner |
|------|----------|------------|-------|
| Branch protection not enforced | High | Complete TAR-77; block merge until required check appears on PRs | Repo admin |
| Stale remote acceptance (dev/staging) | Medium | Re-run MVP acceptance after each release candidate | Platform |
| Dev smoke drift | Medium | Two smoke passes on current `main` for TAR-64 | Platform |
| Acquisition replay resume gaps | Medium | Use `GET /v1/runs/{run_id}` `replay_checkpoint` plus provider reruns; treat Temporal `resume_token` as experimental until activities persist full frontiers | Platform |

## 5. Follow-ups (must be tracked issues)

- [ ] TAR-64 — two dev smokes with Gate D IDs  
- [ ] TAR-77 — ruleset screenshot + green `Release Readiness`  
- [ ] TAR-85 — `evidara workflow mvp-acceptance` output (dev Cloud Run when no staging project)  
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
2. **[TAR-62](https://linear.app/tart-baozi/issue/TAR-62)** — Automate DI + infra promotion (canonical **dev → staging → prod**; dev-first teams may scope to **dev → prod** until staging exists).  
3. **[TAR-63](https://linear.app/tart-baozi/issue/TAR-63)** — Resumable replay / checkpoint orchestration (platform-control).  
4. **[TAR-67](https://linear.app/tart-baozi/issue/TAR-67)** — Operational drills + runbook verification (withdrawal, DLQ, alias rollback). **Repo surfaces for drill evidence are on `main` (2026-04-11);** operators must still **run** drills and attach URLs + artifacts per section 2.1.

Optional parallel: [TAR-139](https://linear.app/tart-baozi/issue/TAR-139) (agent workflow surface) — **`agent-discovery` OpenAPI tags** landed ([#196](https://github.com/philipplukas/evidara/pull/196)); journal / mutating workflow APIs remain future if needed. Wizard epic [TAR-106](https://linear.app/tart-baozi/issue/TAR-106) is post-M5.

## Related docs

- [Phase 5 evidence checklist](phase-5-evidence-checklist.md) — single-page index for TAR-64, TAR-77, TAR-85
- [M5 evidence checklist](m5-evidence-checklist.md) — step-by-step operator actions for TAR-64, TAR-77, TAR-85  
- [Search relevance baseline](search-relevance-baseline.md) — eval pack for TAR-82 / TAR-68 (dev or staging API)  
- [First vertical slice exit gates](first-vertical-slice-exit-gates.md)  
- [MVP demo package and release recommendation](mvp-demo-release-recommendation.md) — operator evidence packet template (updated with section 2.1 artifact names)
