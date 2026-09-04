# Compliance Policy Staging Rollout Runbook

Owner: Platform team
Last reviewed: 2026-04-17
Last verified: Not yet verified
Applies to: staging, prod

## Scope

This runbook applies the scraping-compliance plane (PRs #243, #262) to an
environment where it has been merged to `main` but not yet activated. The
feature code ships inert — rate-limiter, robots.txt enforcement, retention
and attribution only engage after the DB has the new tables and rows.

Covers three sequenced steps:

1. Alembic migrations `0009` (`source_versions.execution_mode`) + `0010`
   (`compliance_policies` + `jurisdictions.compliance_policy_id` FK).
2. Reference-data seed run to populate `cp_ch_fedlex_open_data` and
   `cp_at_ris_ogd` and attach them to `jur_ch` / `jur_at`.
3. Smoke verification that limiter + robots context reaches `start_run`.

Related issues: [#253](https://github.com/philipplukas/evidara/issues/253),
[#254](https://github.com/philipplukas/evidara/issues/254).

## Ownership

- **Primary owner**: Platform on-call.
- **Escalation owner**: Service owner for platform-control.

## Pre-flight

Confirm before starting:

- [ ] Latest `main` is deployed to the target environment. Check Cloud Run
      revision is built from a SHA at or after `957b137` (merge of #262).
- [ ] You have `platform_control_dsn` secret access in the target GCP project
      (or a bastion/Cloud SQL Auth Proxy shell with it).
- [ ] You have a 15-minute window where no crawl runs will start (schedules
      fire on cron; check `Schedule.last_triggered_at` offsets).

## Step 1 — Apply migrations 0009 + 0010

The migrations add:

- `source_versions.execution_mode` (varchar, default `live`) — operator kill
  switch per source version.
- `compliance_policies` table — per-jurisdiction politeness posture.
- `jurisdictions.compliance_policy_id` FK — the attachment column.

Both use `batch_alter_table` so they run cleanly on SQLite (tests) and
Postgres (staging/prod).

### Commands

```bash
# 1. Point at the target DB.
export PLATFORM_CONTROL_DATABASE_URL="postgresql+asyncpg://<user>:<pass>@<host>:5432/<db>"

# 2. From the repo root, on the platform-control package:
cd platform-control

# 3. Dry-check: confirm current head and that 0008 is applied.
uv run alembic current
# Expected: 20260411_0008 (head before this rollout)

# 4. Preview what will run.
uv run alembic upgrade head --sql > /tmp/upgrade.sql
less /tmp/upgrade.sql
# Expect DDL for compliance_policies + jurisdictions + source_versions only.

# 5. Apply.
uv run alembic upgrade head

# 6. Verify.
uv run alembic current
# Expected: 20260417_0010
```

### Postgres-side verification

Connect with `psql` (or your preferred client) and confirm shape:

```sql
\d compliance_policies
-- Columns: compliance_policy_id (pk), name (unique), description, robots_mode,
-- max_requests_per_minute_per_host, max_concurrent_per_host, retention_days,
-- attribution_required, attribution_text, contact_url, created_at, updated_at.

\d source_versions
-- execution_mode column present, server_default = 'live'.

\d jurisdictions
-- compliance_policy_id column present, FK fk_jurisdictions_compliance_policy.
```

### Rollback

Migration is reversible. If the deploy pipeline needs to be rolled back:

```bash
uv run alembic downgrade 20260411_0008
```

Downgrade removes the FK column and drops `compliance_policies`. This is
safe only if no rows have been written to the new table yet — if the seed
has already run, downgrade will fail the drop because of FK dependencies.
Nullify the column first (`UPDATE jurisdictions SET compliance_policy_id =
NULL;`) before downgrade in that case.

## Step 2 — Seed `CompliancePolicy` rows

Merged in #262. Populates `cp_ch_fedlex_open_data` and `cp_at_ris_ogd`, plus
sets `jurisdictions.compliance_policy_id` for CH and AT.

Other jurisdictions (DE/FR/IT/EU) stay unattached.

> **Amended 2026-09-03.** This step used to read "absence means unconstrained by
> design". That is no longer true, and it was never a decision anyone made — it
> was the fallthrough. A source whose jurisdiction (and authority) resolves to no
> policy is now **refused** at dispatch with the slug
> `compliance_policy_missing`, and the attempt is recorded as a terminal FAILED
> run with `refused: true`. There is deliberately no parent fallback: inheriting
> would hand `jur_ch`'s open-data posture (`robots_mode: ignore`, 600 rpm) to
> every canton and commune beneath it, none of which is in that programme. An
> unattached jurisdiction is therefore inert, not unconstrained — declare a
> policy before onboarding a source under it.

### Commands

```bash
# Same env var as Step 1.
cd platform-control

# Preview.
uv run platform-control-seed-reference-data --dry-run

# Expected summary line (on a fresh environment):
# compliance_policies: created=2 updated=0 unchanged=0
# jurisdictions: created=6 updated=0 unchanged=0
# authorities: created=N updated=0 unchanged=0
# extractor_profiles: created=N updated=0 unchanged=0

# If the jurisdictions already exist (typical staging), expect:
# compliance_policies: created=2 updated=0 unchanged=0
# jurisdictions: created=0 updated=2 unchanged=4

# Apply for real.
uv run platform-control-seed-reference-data
```

### Postgres-side verification

```sql
SELECT compliance_policy_id, name, robots_mode,
       max_requests_per_minute_per_host, max_concurrent_per_host,
       attribution_required
FROM compliance_policies
ORDER BY compliance_policy_id;
-- cp_at_ris_ogd           | at-ris-ogd           | ignore | 60 | 4 | true
-- cp_ch_fedlex_open_data  | ch-fedlex-open-data  | ignore | 60 | 4 | true

SELECT jurisdiction_id, compliance_policy_id FROM jurisdictions ORDER BY 1;
-- jur_at     | cp_at_ris_ogd
-- jur_ch     | cp_ch_fedlex_open_data
-- jur_de     | NULL
-- jur_eu     | NULL
-- jur_fr     | NULL
-- jur_it     | NULL
```

## Step 3 — Smoke verification

Confirm the runtime paths actually consume the policy.

### Via API

```bash
OPERATOR_TOKEN=<staging operator api key>
curl -H "X-API-Key: $OPERATOR_TOKEN" \
     https://platform-control-staging.<project>.run.app/v1/compliance-policies
# Expect both policies in the response list.

curl -H "X-API-Key: $OPERATOR_TOKEN" \
     https://platform-control-staging.<project>.run.app/v1/compliance-policies/cp_ch_fedlex_open_data
# Expect 200 with the shaped policy.
```

### Via a test run

Trigger a Fedlex SPARQL run in preview mode and inspect the Cloud Logging
output on the platform-control service. Expected log lines:

- `retention_purge` — absent (no retention policy for CH).
- Structured acquire calls in the deterministic-HTTP or Fedlex code path
  should bounce against the 60 rpm / 4-concurrent budget. Watch CPU: even a
  100-document run will stay under 1 rps per host with this cap.

When a bundle is published, pull the manifest and confirm the attribution
block is attached:

```bash
gsutil cat gs://evidara-raw-artifacts-staging/runs/<run_id>/<bundle_manifest_id>.json \
  | jq '.bundle_metadata.attribution'
# Expect:
# {
#   "required": true,
#   "text": "Source: Fedlex — Swiss Federal Chancellery (open-data programme).",
#   "contact_url": "https://evidara.ai/contact"
# }
```

## Post-flight

- [ ] Migration summary (before/after versions, wall time, row counts)
      posted to Linear.
- [ ] At least one preview run against `jur_ch` confirms limiter +
      attribution are live.
- [ ] Update the "Last verified" header of this runbook with the date and
      environment.

## Follow-ons tracked separately

- [#252](https://github.com/philipplukas/evidara/issues/252) — adaptive
  AIMD rate limiter (this runbook governs the static static-ceiling path).
- [#254](https://github.com/philipplukas/evidara/issues/254) —
  `PLATFORM_CONTROL_FIRECRAWL_WEBHOOK_RECORD_DIR` wiring on Cloud Run.
- [#256](https://github.com/philipplukas/evidara/issues/256) — retention
  sweep on Temporal cron.
