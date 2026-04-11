# Phase 5 go / no-go memo (draft)

Owner: Platform lead  
Last reviewed: 2026-04-09  
Last verified: 2026-04-09  
Applies to: dev → staging transition (Linear **TAR-69**)  
Canonical template history: this file is the **working draft**; publish final recommendation in Linear **TAR-69** when all gates are green.

## 1. Summary recommendation

- **Recommendation:** **PENDING** — operator evidence still required for full dev smoke (TAR-64 ×2), branch protection proof (TAR-77), and fresh staging MVP acceptance (TAR-85). Repo implementation for search/metadata/relevance is merged.
- **Date:** 2026-04-09 (draft)  
- **Environment(s) covered:** dev (partial — local + historical CI), staging (last verified 2026-04-08 per MVP acceptance tables)

## 2. Gate outcomes

| Gate | Source | Result | Evidence link |
|------|--------|--------|----------------|
| A–C vertical slice | `docs/runbooks/first-vertical-slice-exit-gates.md` | **PENDING** (dev smoke ×2) | See **TAR-64: dev smoke evidence** in that runbook |
| Local pre-flight | `scripts/vertical-slice-exit-gates-local.sh` (2×) | pass | Rows 2026-04-09 in verification log |
| MVP acceptance (staging) | `docs/runbooks/mvp-acceptance-scenario-pack.md` | pass (last table **2026-04-08**) | [mvp-acceptance-scenario-pack.md](mvp-acceptance-scenario-pack.md#latest-verification-evidence-2026-04-08) — **refresh** with `evidara workflow mvp-acceptance` |
| Release Readiness (strict) | `Release Readiness` workflow | GO (historical) | e.g. [24049226588](https://github.com/philipplukas/evidara/actions/runs/24049226588) — re-confirm before sign-off |
| Interaction flow | `docs/runbooks/interaction-flow-validation.md` | pass (historical) | Linked from release-readiness / interaction-flow runs |

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
- [ ] Phase 5 workstreams: TAR-66 → TAR-62 → TAR-63 → TAR-67 (see §7)

### Repo gates to run before merge (automatable)

From repo root: `bash scripts/check_docs.sh`, `bash scripts/check-legal-search.sh`, `bash scripts/check-evidara-cli.sh`, `bash scripts/check-platform-control.sh` (needs Docker for one Postgres integration test), `cd document-intelligence && uv run ruff check . && uv run pytest tests/`.

## 6. Operator demo

- **Script:** `docs/runbooks/mvp-demo-release-recommendation.md` / `mvp-website-walkthrough.md`  
- **Demo date / participants:** _TBD after GO recommendation_

## 7. Phase 5 workstream schedule (recommended)

Execute after MVP path is credible (TAR-64 green):

1. **[TAR-66](https://linear.app/tart-baozi/issue/TAR-66)** — Harden HTML parsing + corpus fixtures (ingest stability).  
2. **[TAR-62](https://linear.app/tart-baozi/issue/TAR-62)** — Automate DI + infra promotion (dev → staging → prod).  
3. **[TAR-63](https://linear.app/tart-baozi/issue/TAR-63)** — Resumable replay / checkpoint orchestration (platform-control).  
4. **[TAR-67](https://linear.app/tart-baozi/issue/TAR-67)** — Operational drills + runbook verification (withdrawal, DLQ, alias rollback).

Optional parallel: [TAR-139](https://linear.app/tart-baozi/issue/TAR-139) (agent workflow surface) after CLI stabilizes; wizard epic [TAR-106](https://linear.app/tart-baozi/issue/TAR-106) is post-M5.

## Related docs

- [M5 evidence checklist](m5-evidence-checklist.md) — step-by-step operator actions for TAR-64, TAR-77, TAR-85  
- [Search relevance baseline](search-relevance-baseline.md) — staging eval pack for TAR-82 / TAR-68  
- [First vertical slice exit gates](first-vertical-slice-exit-gates.md)
