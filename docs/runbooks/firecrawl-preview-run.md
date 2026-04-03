# Firecrawl Preview Run

Owner: Platform team
Last reviewed: 2026-04-03
Last verified: Not yet verified
Applies to: dev, staging

## Purpose

Run and troubleshoot a Firecrawl-backed preview for a source version. The primary operator path is
the code-managed admin app in `platform-control/admin`, with direct API calls as the fallback for
debugging or automation.

## Prerequisites

- [ ] Access to `platform-control/admin` or the platform-control API
- [ ] Firecrawl API key configured for the target environment
- [ ] GCS bucket configured for raw artifact storage
- [ ] Firecrawl webhook secret configured in platform-control
- [ ] `PLATFORM_CONTROL_ARTIFACT_STORE_BACKEND` and `PLATFORM_CONTROL_EVENT_PUBLISHER_BACKEND` configured for the target environment
- [ ] A source version exists and is approved for preview or production use

## Steps

### 1. Confirm the source version is ready

Use `platform-control/admin` or the API to confirm:

- the source exists
- the source version exists
- acquisition spec is populated
- version status is approved if the environment requires it

**Expected output:** The source version can be selected for a preview run without validation errors.

### 2. Trigger the preview run

Trigger a preview run from the `Source Versions` section in `platform-control/admin` or with
`POST /v1/runs` using the selected source version.

**Expected output:** A `run_id` is created and enters a non-terminal state. In `inline` dispatch mode, a provider job record is attached immediately; in `worker` mode, run `platform-control-connector-worker` and confirm the provider job appears after dispatch.

### 3. Confirm Firecrawl callbacks are being accepted

Watch the run status and webhook logs for:

- verified Firecrawl callbacks
- persisted webhook receipt
- no duplicate artifact creation from repeated deliveries

**Expected output:** The run receives provider callbacks and progresses toward `completed` or `failed`.

### 4. Verify artifact persistence

Inspect the run in `platform-control/admin`, or query the API/database directly, and confirm:

- at least one raw artifact was recorded
- captured resources were created
- artifact storage paths were written
- content types look plausible for the source family

**Expected output:** The preview run shows raw artifact and captured-resource counts greater than zero unless the source is truly empty.

### 5. Review preview output

Review the preview summary for:

- URL count
- PDFs discovered
- likely decision pages
- obvious boilerplate
- include or exclude path changes needed

**Expected output:** The operator can either accept the preview output or edit the acquisition spec and rerun.

## Verification

How to confirm the procedure succeeded:

- [ ] Run status reaches `completed`
- [ ] Raw artifacts exist for the run
- [ ] Captured resources exist for the run
- [ ] Duplicate webhook delivery does not create duplicate artifacts
- [ ] Preview summary is visible to the operator in `platform-control/admin`

## Rollback

If something goes wrong:

1. Mark the run as `failed` or `cancelled` through the platform-control action path.
2. Preserve webhook receipts for debugging instead of deleting them.
3. Delete only draft artifacts created by the failed preview if cleanup is required.
4. Update the acquisition spec and rerun with tighter limits or path filters.

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Run stays `pending` | Firecrawl job was never submitted | Check provider job creation and API credentials |
| Run stays `running` too long | Webhook not reaching platform-control | Check webhook URL, secret, and request logs |
| Zero artifacts recorded | Filters too strict or source layout changed | Loosen include/exclude rules and rerun preview |
| Duplicate artifacts | Webhook dedupe missing or broken | Inspect `webhook_receipts` handling and idempotency logic |
| Content types look wrong | Source returned unexpected documents or HTML wrappers | Inspect captured resources and tighten acquisition spec |

## Related

- [Platform-Control Local Demo Setup](../setup/platform-control-local-demo.md)
- [Platform Control](../components/platform-control.md)
- [Platform-Control Firecrawl V0 Plan](../architecture/platform-control-firecrawl-v0-plan.md)
- [Platform Control Testing](../components/testing/platform-control-testing.md)
