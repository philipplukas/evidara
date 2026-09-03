# Runbook: GCP cost-stop & wind-down

Owner: Platform team
Last reviewed: 2026-07-01
Last verified: Not yet verified
Applies to: dev, staging, prod

Companion to [ADR-0029](../adr/0029-self-hosted-hetzner-runtime.md). Purpose: stop
usage-based GCP spend while the self-hosted Hetzner runtime is being built, **without**
losing data we cannot cheaply reproduce. Strategy: **scale to zero first, destroy later**
(ADR-0029 D3).

> These steps require GCP operator access and run from your workstation / Cloud Shell,
> not from CI. Replace `<env>` with `dev` / `staging` / `prod` and `<project>` with the
> matching project id (see `infra/terraform/gcp/runtime_stack/<env>/*.tfvars`).

## 0. Prerequisites

```bash
gcloud auth login
gcloud config set project <project>
gcloud config set run/region europe-west6
```

## 1. Stop the daily failing nightlies (already done in-repo)

The five scheduled workflows that hammer live GCP are disabled in
`.github/workflows/` (schedule commented out, `workflow_dispatch` retained):
`e2e-smoke-dev`, `e2e-smoke-staging`, `scraping-nightly-canary`,
`interaction-flow-staging-evidence`, `release-readiness`. No action needed beyond
merging this branch — listed here for completeness.

> **Correction (2026-07-31).** For four of the five, commenting out `schedule:` was
> enough. `interaction-flow-staging-evidence` also had a `push: branches: [main]`
> trigger, which this section did not account for — so it kept firing at the wound-down
> staging environment and was red on every matching push to main from 2026-07-20
> onwards (Playwright's identity check gets HTTP 500 from Cloud Run and aborts before
> any test runs). The `push` block is now commented out too. When auditing a
> "disabled" workflow, check every trigger, not just the one you meant to remove.

## 2. Scale Cloud Run services to zero

Cloud Run services bill while serving; the always-on worker (`min=max=1`) bills
continuously. Set min instances to 0 (and effectively idle them):

```bash
for svc in platform-control-api platform-control-admin platform-control-worker \
           legal-search-api legal-search-frontend \
           document-intelligence-document-service di-consumer; do
  gcloud run services update "${svc}-<env>" --min-instances=0 --max-instances=1 || true
done
```

For the worker/consumer specifically (no inbound traffic to idle them), you can stop
delivery by detaching push subscriptions (step 3) so they scale to zero.

## 3. Pause Pub/Sub push delivery

Detaching push subscriptions stops Pub/Sub from invoking (and thus waking) Cloud Run:

```bash
gcloud pubsub subscriptions list --format='value(name)' | grep '<env>' | while read -r sub; do
  gcloud pubsub subscriptions modify-push-config "${sub}" --push-endpoint="" || true
done
```

Messages accumulate (retained per subscription TTL) rather than being delivered. Fine
for a wind-down; purge later at destroy time.

## 4. Stop Cloud SQL (keep data)

`STOPPABLE` Postgres instances can be stopped without deletion — storage still bills, but
compute does not:

```bash
gcloud sql instances list
gcloud sql instances patch evidara-control-<env> --activation-policy=NEVER
```

> Cloud SQL has `deletion_protection = true` in Terraform. Stopping (not deleting)
> preserves data and avoids the protection flag entirely.

## 5. Stop the OpenSearch GCE VM (keep disk)

```bash
gcloud compute instances list --filter='name~opensearch'
gcloud compute instances stop <opensearch-instance-name> --zone=<zone>
```

The persistent disk is retained (still bills for storage, far less than a running VM).

## 6. (Optional) Snapshot before you stop

If you want a restore point before idling:

```bash
gcloud sql export sql evidara-control-<env> gs://<manifests-bucket>/backups/control-<env>-$(date +%F).sql.gz \
  --database=platform_control
# GCS artifacts already live in versioned buckets; no snapshot needed.
```

## 7. Verify spend has dropped

```bash
# No running Cloud Run revisions serving:
gcloud run services list --format='table(metadata.name, status.traffic)'
# Cloud SQL stopped:
gcloud sql instances describe evidara-control-<env> --format='value(state,settings.activationPolicy)'
# OpenSearch VM terminated:
gcloud compute instances describe <opensearch-instance-name> --zone=<zone> --format='value(status)'
```

Check the billing console after ~24h; the only residual should be storage (GCS + stopped
disks), which is small and fixed.

## 8. Final teardown (AFTER Hetzner cutover is validated — ADR-0029 Slice 6)

Do **not** run this until the self-hosted stack is proven and data is migrated.

```bash
cd infra/terraform/gcp/runtime_stack/<env>
# Cloud SQL deletion protection must be flipped first:
#   set deletion_protection = false in the tfvars / module input, terraform apply, then:
terraform destroy
```

Then delete any leftover GCS buckets / Pub/Sub topics not managed by Terraform, and
revoke the Workload Identity Federation bindings used by the (now-removed) deploy
workflows.

## Rollback

Everything in steps 2–5 is reversible: re-set `--min-instances`, re-attach push configs,
`--activation-policy=ALWAYS`, and `gcloud compute instances start`. Step 8 is not
reversible — only run it post-cutover.
