# Scraping Nightly Canary

Owner: Platform team
Last reviewed: 2026-04-05
Last verified: 2026-04-12
Applies to: dev, staging

## Purpose

Run and triage the scheduled scraping/acquisition canary that validates end-to-end ingestion health overnight.

## Workflow

- GitHub Actions workflow: `.github/workflows/scraping-nightly-canary.yml`
- Schedule: daily at 02:15 UTC
- Manual trigger supported via `workflow_dispatch`

The workflow mints audience-scoped Cloud Run ID tokens via `gcloud`, runs `scripts/e2e-smoke-test.sh`, uploads the evidence log as an artifact, and posts a Slack notification when configured.

## Canary Configuration

The current canary uses a deterministic synthetic source path from the smoke script.

Target expansion (tracked in Linear) is 3-5 stable source versions in each environment:

1. clean structured HTML source
2. noisy/chrome-heavy HTML source
3. discovery-heavy source
4. rendered/snapshot path source
5. non-HTML handoff source

## Prerequisites

- [ ] GitHub environment variables are configured:
  - `GCP_REGION`
  - `GCP_PROJECT_ID_DEV`
  - `GCP_PROJECT_ID_STAGING` (optional for manual staging runs)
- [ ] GitHub environment secrets are configured:
  - `GCP_WORKLOAD_IDENTITY_PROVIDER`
  - `GCP_SERVICE_ACCOUNT_DEV`
  - `GCP_SERVICE_ACCOUNT_STAGING` (optional for manual staging runs)
  - `SCRAPING_CANARY_SLACK_WEBHOOK` (optional)
- [ ] Runtime services are reachable in the target environment.

## Verification

- [ ] Workflow run finishes with `passed` status
- [ ] Evidence artifact is uploaded (`scraping-canary-evidence-<run_id>`)
- [ ] Evidence includes a completed run ID, projection events, and search result count
- [ ] Failure alert is delivered (when webhook secret is configured)

## Failure Triage

1. Open the failed workflow run.
2. Download the evidence artifact and inspect:
   - `failure.step`
   - `failure.message`
   - `entities.run_id`
3. If `run_id` exists, inspect platform-control and legal-search logs around the run.
4. Re-run manually once to rule out transient provider/network issues.
5. If persistent, file or update an incident issue and attach evidence JSON.

## Related

- [Scraping QA Standard](../testing/scraping-qa-standard.md)
- [First Vertical Slice Exit Gates](first-vertical-slice-exit-gates.md)
