# MVP Website Walkthrough (Dev -> Staging)

Owner: Platform team
Last reviewed: 2026-04-06
Last verified: 2026-04-06
Applies to: dev, staging

## Purpose

Run a repeatable, evidence-first walkthrough of user-facing MVP flow surfaces:

1. Platform control entry points (source/version/run controls)
2. Legal search query/detail experience
3. Operator/demo pages used in release walkthroughs

This runbook captures both the checklist and the latest verification evidence.

## Surface Inventory

Discovered runtime services in `europe-west6`:

- `platform-control-api-dev`, `platform-control-api-staging`
- `legal-search-api-dev`, `legal-search-api-staging`
- `platform-control-admin-dev`, `platform-control-admin-staging`
- `legal-search-frontend-dev`, `legal-search-frontend-staging`
- `document-intelligence-consumer-*` (runtime service, not user UI)
- `platform-control-worker-*` (runtime worker, not user UI)

Published website surfaces:

- Dev legal search UI: `https://legal-search-frontend-dev-kxc5agexna-oa.a.run.app`
- Dev admin UI: `https://platform-control-admin-dev-kxc5agexna-oa.a.run.app`
- Staging legal search UI: `https://legal-search-frontend-staging-kxc5agexna-oa.a.run.app`
- Staging admin UI: `https://platform-control-admin-staging-kxc5agexna-oa.a.run.app`

## Checklist

### A. Platform Control Surface

- [x] `GET /health` returns 200 in dev and staging
- [x] `GET /docs` returns 200 in dev and staging
- [x] `GET /v1/sources` returns 200 in dev and staging

### B. Legal Search Surface

- [x] `GET /health` returns 200 in dev and staging
- [x] `GET /v1/search?q=<term>` returns 200 in dev and staging
- [x] `GET /v1/documents/{id}` returns 200 in dev and staging
- [x] Deployed browser UI (`legal-search/frontend`) is accessible in dev and staging
- [x] Frontend proxied search path (`/v1/search`) returns 200 in dev and staging

### C. Platform Control Admin Surface

- [x] Deployed React-admin UI is accessible in dev and staging
- [x] Frontend proxied source list path (`/api/platform-control/v1/sources`) returns 200 in dev and staging
- [ ] Operator flow walkthrough captured with screenshots

## Verification Evidence (2026-04-06)

Authenticated endpoint probes (gcloud identity token) succeeded:

- Platform control:
  - dev: `/health` 200, `/docs` 200, `/openapi.json` 200, `/v1/sources` 200
  - staging: `/health` 200, `/docs` 200, `/openapi.json` 200, `/v1/sources` 200
- Legal search:
  - dev: `/health` 200, `/v1/search?q=art%20754` 200, `/v1/documents/{id}` 200
  - staging: `/health` 200, `/v1/search?q=art%20754` 200, `/v1/documents/{id}` 200

Observed UX-quality findings from API payloads:

1. Result/detail metadata is minimal and generic (`type: "unknown"`, generic
   titles like `Document <id>`), limiting user trust and explainability.
2. Legal-search docs endpoints (`/docs`) are not exposed (404) while platform
   control docs are available; this reduces operator/debug discoverability.
3. Browser surfaces are reachable, but operator screenshot evidence still needs
   a canonical capture pack for demo workflows.

## Triage Mapping

Use these labels when filing/triaging issues:

- `severity:blocker`: prevents real website walkthrough in target env
- `severity:high`: flow works but user confidence/credibility is low
- `severity:medium`: operational discoverability or quality gap

Suggested mapping for this run:

- Generic document metadata/titles in result/detail payloads -> `severity:high`
- Missing legal-search docs surface -> `severity:medium`
- Missing screenshot evidence pack for operator walkthrough -> `severity:medium`
