# Release & Rollback Runbook

Owner: Platform team
Last reviewed: 2026-04-03
Last verified: Not yet verified
Applies to: dev, prod

## Release Flow

```text
┌─────────┐     ┌─────────┐     ┌──────────────┐     ┌─────────┐
│  main   │────>│  Build  │────>│  Deploy Dev  │────>│  Smoke  │
│  merge  │     │  Images │     │  (SHA tag)   │     │  Tests  │
└─────────┘     └─────────┘     └──────────────┘     └────┬────┘
                                                          │ pass
                                                    ┌─────▼──────┐     ┌─────────┐
                                                    │ Deploy Prod │────>│  Smoke  │
                                                    │ (same SHA)  │     │  Tests  │
                                                    └─────────────┘     └─────────┘
```

### Key Design Decisions

- **SHA-pinned images**: Both dev and prod deploy the exact same image SHA (not `:latest`), ensuring what passed dev smoke tests is what runs in prod
- **Sequential promotion**: Prod can only deploy after dev succeeds (via `needs: deploy-dev`)
- **Environment protection**: GitHub environment protection rules on `prod` can require manual approval reviewers
- **Smoke tests**: Health and readiness checks run automatically after each deployment

## Pre-Deploy Checklist

Before merging to `main`:

- [ ] All CI checks pass (api, check, contract-validation, frontend, image builds)
- [ ] PR reviewed and approved
- [ ] No known breaking changes in platform-control or legal-search
- [ ] If schema change: migration tested locally and in dev first

## Rollback Procedures

### Method 1: Revert to Previous Revision (Fastest)

Use Cloud Run's built-in revision traffic management:

```bash
# List available revisions
gcloud run revisions list \
  --service platform-control-api-dev \
  --project evidara-dev \
  --region europe-west6

# Route 100% traffic to previous revision
gcloud run services update-traffic platform-control-api-dev \
  --project evidara-dev \
  --region europe-west6 \
  --to-revisions PREVIOUS_REVISION_NAME=100
```

### Method 2: Redeploy Previous Image SHA

If you know the previous working SHA:

```bash
# Find the previous image digest
gcloud run services describe platform-control-api-dev \
  --project evidara-dev \
  --region europe-west6 \
  --format='value(spec.template.spec.containers[0].image)'

# Redeploy with known-good SHA
gcloud run services update platform-control-api-dev \
  --project evidara-dev \
  --region europe-west6 \
  --image europe-west6-docker.pkg.dev/evidara-dev/evidara/platform-control:KNOWN_GOOD_SHA
```

### Method 3: Git Revert + Redeploy

For code-level rollback:

```bash
git revert HEAD
git push origin main
# CD pipeline will automatically build and deploy the revert
```

## Smoke Test Details

The CD pipeline runs these checks automatically:

| Service | Endpoint | Expected | Failure Action |
|---------|----------|----------|----------------|
| platform-control | `GET /health` | HTTP 200 | ❌ Pipeline fails |
| legal-search | `GET /health` | HTTP 200 | ❌ Pipeline fails |
| platform-control | `GET /ready` | `{"status":"ok"}` | ⚠️ Warning only |

### Manual Smoke Tests

After deployment, optionally verify deeper:

```bash
# Platform-control readiness (includes DB check)
curl -s ${PC_URL}/ready | jq .

# Legal-search readiness (includes OpenSearch check)
curl -s ${LS_URL}/health/ready | jq .

# Platform-control API: list sources
curl -s ${PC_URL}/v1/sources | jq '.data | length'

# Legal-search API: search
curl -s "${LS_URL}/v1/search?q=test&limit=1" | jq '.total'
```

## Image Traceability

| Property | How to Find |
|----------|-------------|
| Deployed SHA | GitHub Actions run summary |
| Image tag | `gcloud run services describe ... --format='value(spec.template.spec.containers[0].image)'` |
| Build log | GitHub Actions → Runtime Images workflow → matching SHA |
| Source commit | `git log --oneline <SHA>` |

## Related Resources

- [CD Workflow](../../.github/workflows/platform-control-cd.yml)
- [Alert Response Playbook](./alert-response-playbook.md)
- [Connector Worker Operations](./connector-worker-operations.md)
