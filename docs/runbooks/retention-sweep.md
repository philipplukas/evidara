# Retention sweep (legal hard delete)

The retention sweep purges `RawArtifact` rows, their `CapturedResource` children, and the
underlying blobs once the artifact is older than its jurisdiction's
`CompliancePolicy.retention_days`. Hard delete is deliberate: retention windows here come from
GDPR and source-specific obligations, and a soft delete would leave regulated data reachable in
queries and backups.

**This is a legal obligation, not a housekeeping job.** It must run, and you must be able to
prove it ran.

## How it is scheduled

A Kubernetes CronJob — `platform-control-retention-sweep`, daily at **04:00 UTC**, defined in
[`infra/hetzner/apps/retention-sweep-cronjob.yaml`](https://github.com/philipplukas/evidara/blob/main/infra/hetzner/apps/retention-sweep-cronjob.yaml)
and applied by `kubectl apply -k infra/hetzner/apps` (i.e. `infra/hetzner/deploy-stage4.sh`).

It runs the `platform-control-retention-sweep` console script from the platform-control image,
with the same `evidara-config` + `evidara-app-secrets` env as the API.

`concurrencyPolicy: Forbid` — a sweep never races itself.

> **History (ADR-0031).** The sweep used to exist only as `RetentionSweepWorkflow` behind a
> Temporal Schedule. Temporal is deployed in no environment, so the sweep **was not running
> anywhere**. It is a cron; it does not need durable execution. The workflow is still in the
> codebase and now calls the same shared implementation — but if you ever re-create a Temporal
> Schedule for it, delete the CronJob first, or the sweep runs twice.

> **Note on the GitOps path.** `k8s/gitops/base/` cannot host this CronJob: `CronJob` is not in
> `allowedResources` in `vendor/platform-contract.yaml`. Moving the sweep there needs a contract
> minor bump first.

## Run it manually

Same implementation in all three cases — pick whichever fits where you are.

```bash
# 1. In-cluster, ad hoc: fire the CronJob's job immediately.
kubectl -n evidara create job retention-sweep-manual \
  --from=cronjob/platform-control-retention-sweep
kubectl -n evidara logs job/retention-sweep-manual

# 2. From a shell in any pod carrying the platform-control image.
platform-control-retention-sweep --dry-run   # report only, deletes nothing
platform-control-retention-sweep             # perform the purge

# 3. Locally, against a database you have configured (PLATFORM_CONTROL_DATABASE_URL).
cd platform-control && uv run pc retention sweep --dry-run
```

Always start with `--dry-run` when you are validating a new or changed
`CompliancePolicy.retention_days`: it logs and counts everything the real run would delete,
without touching the database or the blob store.

## Verify it ran

The CronJob keeps the last 3 successful and last **5 failed** job pods (failures are kept longer
on purpose — a missed sweep is a compliance event).

```bash
# When did it last fire, and did it succeed?
kubectl -n evidara get cronjob platform-control-retention-sweep
#   NAME                              SCHEDULE    SUSPEND   ACTIVE   LAST SCHEDULE
#   platform-control-retention-sweep  0 4 * * *   False     0        7h

kubectl -n evidara get jobs -l app.kubernetes.io/name=platform-control-retention-sweep
```

Each run prints one summary line, which is the record to screenshot for an audit:

```
retention sweep: policies_applied=2 artifacts_purged=143 resources_purged=1201 blobs_deleted=143
```

and emits it as a structured log event `retention_sweep_completed` with the same counts. Every
individual deletion is logged as a `retention_purge` event carrying `artifact_id`, `run_id`,
`source_id`, `compliance_policy_id`, and the `cutoff` timestamp.

```bash
kubectl -n evidara logs -l app.kubernetes.io/name=platform-control-retention-sweep --tail=100
```

`policies_applied=0` is a legitimate result — it means no policy had any artifact past its
window. It is **not** the same as the job not running: check `LAST SCHEDULE` on the CronJob.

## Failure modes

| Symptom | Cause | Action |
|---|---|---|
| `LAST SCHEDULE` is `<none>` or stale by more than a day | CronJob not applied, or suspended | `kubectl apply -k infra/hetzner/apps`; check `SUSPEND` is `False` |
| Job pods in `Error`, DB connection refused | `evidara-app-secrets` missing or Postgres down | Same DB env as the API — check the API pod is healthy |
| `artifacts_purged` climbing every day into the thousands | A `retention_days` was lowered; the backlog is draining | Expected. Confirm the policy change was intended |
| Blob deletions fail but rows purge | Best-effort blob removal (`ArtifactStore.delete_blob`) | Intended: partial states converge on the next sweep rather than orphaning DB rows |

## Related

- ADR-0031: Disposition of Temporal, Argilla, and Firecrawl —
  `docs/adr/0031-temporal-argilla-firecrawl-disposition.md`
- [Data lifecycle](../architecture/data-lifecycle.md)
- [Compliance policy staging rollout](compliance-policy-staging-rollout.md)
