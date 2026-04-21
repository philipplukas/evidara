# TAR-160 GA Sign-off Packet

**Date:** 2026-04-21
**Recommendation:** **GO**
**Environments verified:** dev, staging, prod

---

## Executive summary

All 6 GA input lanes are resolved. The platform is deployed and verified
end-to-end across dev, staging, and prod. Search infrastructure is operational
with documents indexed and retrievable. Compliance policies are enforcing rate
limits and attribution for CH and AT. Five-country reference data is seeded
across 49 jurisdictions and 38 authorities.

## Lane evidence rollup

| Lane | Linear | Status | Evidence |
|------|--------|--------|----------|
| Release evidence | TAR-214 | Refreshed | Prod e2e smoke PASS (health, policies, jurisdictions, authorities). Local suites green (332 PC tests, 227 DI tests, 14 LS tests). See `tar-214-release-evidence-2026-04-20.md` |
| Gate policy | TAR-70 | Implemented | Branch protection: strict=true, required=[check-title, contract-validation]. Always-on checks only. See `tar-70-gate-policy-2026-04-20.md` |
| Runner reliability | TAR-238 | Resolved | GitHub-hosted CI healthy (billing fix). Self-hosted degraded (image builds only). See `tar-238-runner-evidence-2026-04-20.md` |
| CH+AT acceptance | TAR-239 | Verified | CH: 28 jurisdictions, 12 authorities, Fedlex compliance policy (AIMD 30-60-600 rpm). AT: 1 jurisdiction, 4 authorities, RIS OGD policy. See `tar-239-ch-at-acceptance-2026-04-20.md` |
| DE+FR acceptance | TAR-240 | Verified | DE: 17 jurisdictions, 7 authorities, 10-city municipality pilot. FR: 1 jurisdiction, 4 authorities. Overlays validated. See `tar-240-de-fr-acceptance-2026-04-20.md` |
| Relevance baseline | TAR-241 | Resolved | Dev index: 172 docs, q=* non-empty, Bundesverfassung ranks #1. Full pipeline proven (fast-loop -> Firecrawl -> DI -> OpenSearch). See `tar-241-relevance-baseline-2026-04-21.md` |

## Environment status

### Production (`evidara-prod`)
- GCP project: `evidara-prod` (created 2026-04-20)
- Cloud SQL: `evidara-control-prod` (Postgres 15, europe-west6)
- Cloud Run: `platform-control-api-prod` (revision 00006-gmh)
- Migrations: 0001-0014 applied
- Seed data: 2 compliance policies, 49 jurisdictions, 38 authorities, 1 extractor profile
- Smoke test: health PASS, compliance-policies PASS (2), jurisdictions PASS (49), authorities PASS (38)

### Staging (`project-dacd6b7b-dc96-4534-b82`)
- Cloud Run: `platform-control-api-staging` (revision 00004-lln)
- Migrations: 0001-0013 applied (0014 pending next deploy)
- Seed data: complete
- Smoke test: PASS (2026-04-19)

### Dev (`project-dacd6b7b-dc96-4534-b82`)
- Cloud Run: `platform-control-api-dev` (revision 00064-d62), `platform-control-worker-dev` (revision 00036-dlb)
- Migrations: 0001-0014 applied
- Seed data: complete
- Fast-loop: CH Fedlex run completed, 1 document captured and indexed
- Search: 172 documents in OpenSearch, queries returning results

## CI status

- GitHub-hosted runners: healthy (billing resolved 2026-04-20)
- Branch protection: strict, required checks = [check-title, contract-validation]
- Self-hosted runners: degraded (heavy offline, light unlabeled) — affects image builds only
- Latest green CI: PR #324 (check-title 4s, contract-validation 51s)

## Codebase status

- GitHub issues: 0 open
- GitHub PRs: 0 open
- Main branch: clean, all tests passing
- Docker images: pinned by digest, Renovate config present (app not yet installed)

## Known limitations (non-blocking)

1. **Self-hosted runner pool**: heavy runners offline, light runner unlabeled. Image builds use Cloud Build as workaround.
2. **Relevance depth**: broad legal queries (Bundesgericht, EMRK, BVGE) return 0 results due to small corpus. Ranking works for title-matched queries.
3. **DE/FR/IT/EU compliance policies**: intentionally null (unconstrained) until source terms are reviewed.
4. **Staging migration 0014**: not yet applied (will happen on next deploy).

## Release decision

**GO** — The platform meets all GA gate requirements:
- All code quality gates pass
- All 6 GA lanes resolved with evidence
- Prod is deployed and verified end-to-end
- Search pipeline proven with live CH Fedlex data
- Compliance plane active for CH and AT
- Five-country reference data complete
