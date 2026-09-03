# Runbook — MinIO least-privilege cutover (#813)

Owner: Platform team
Last reviewed: 2026-09-03
Last verified: **never — see [Status](#status-not-yet-executed)**
Applies to: prod (self-hosted Hetzner k3s, ADR-0029)

## Status: not yet executed

Written against the cluster manifests and the MinIO/`mc` IAM behaviour, not against a
run. Nothing here has been applied: no `kubectl apply`, no `helm upgrade`, no
`provision-minio-users.sh` invocation. The policy documents and the deny matrix are
committed and guarded by `scripts/check_hetzner_minio_credentials.py`, but the first
person to run Step 1 is also the first person to prove it. Treat Step 2's output as the
gate — it fails before anything has been cut over.

**Cluster:** self-hosted Hetzner k3s, namespace `evidara` (ADR-0029).
**Est. duration:** 20–30 minutes, with two short windows where a workload is restarting.

## What this changes

Before: `platform-control-api`, `platform-control-retention-sweep`, `di-consumer`,
`document-service`, `projection-bridge` and both Trino pods authenticated to MinIO as
**root**, out of one shared Secret. That credential grants full access to
`evidara-raw-artifacts`, `evidara-lakehouse` **and** `evidara-pg-backups` — the Postgres
PITR backups that exist to recover from a compromise of exactly those services.

After: one MinIO user per workload, each scoped by an IAM policy to the buckets and
actions its code actually performs, each in its own Secret. Root becomes administrative
only, used by `infra/hetzner/provision-minio-users.sh` and an operator at a console, and
by no running workload.

The scope table, and the `file:line` reasoning behind each scope, is in
[`infra/hetzner/README.md`](../../infra/hetzner/README.md#per-workload-minio-service-accounts).
The machine-readable source of truth is
[`infra/hetzner/minio-policies/accounts.json`](../../infra/hetzner/minio-policies/accounts.json).

Issue #792 closed the *leak* (the credential was committed and live). This closes the
*blast radius*, which #792 deliberately left alone.

## Preconditions

- `KUBECONFIG` points at `evidara-k3s` **via the tailnet IP** — 6443 is dropped on the
  public NIC (see the README's prerequisites).
- `kubectl get nodes` returns `Ready`.
- The branch for #813 is merged, so `infra/hetzner/` on disk matches what you deploy.
- A recent Postgres base backup exists (`kubectl -n evidara get backup`). The
  `cnpg-backup` account is reconciled by this cutover; do not run it while a backup is
  mid-flight.
- **Do not** rotate the MinIO root credential in the same window. Root rotation
  re-encrypts MinIO's IAM data and orphans users; combining the two makes a failure
  impossible to attribute.

## Step 0 — record the "before" state

```bash
NS=evidara
POD=$(kubectl -n $NS get pod -l app=minio -o jsonpath='{.items[0].metadata.name}')
kubectl -n $NS exec "$POD" -- sh -c \
  'mc --config-dir /tmp/c alias set r http://localhost:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null \
   && mc --config-dir /tmp/c admin user list r'
# Expected before cutover: cnpg-backup, console
kubectl -n $NS get secret evidara-app-secrets -o jsonpath='{.data}' | tr ',' '\n' | cut -d'"' -f2
# Expected before cutover: PLATFORM_CONTROL_DATABASE_URL, PLATFORM_CONTROL_S3_*, DI_S3_*
```

Keep that output. Step 6's verification is "these two lists changed in exactly the
expected way".

## Step 1 — provision the accounts

```bash
bash infra/hetzner/provision-minio-users.sh
```

Idempotent. It creates or reconciles `platform-control`, `di-consumer`,
`document-service`, `trino` and `cnpg-backup`, each with its policy from
`infra/hetzner/minio-policies/`, and applies the matching Kubernetes Secret. Passwords
are generated with `openssl rand -hex 24`, never printed and never committed.

**`cnpg-backup` keeps its existing password.** The script reads the password back out of
the existing Secret and re-applies it, so a live Postgres backup credential is never
rotated by a re-run. The same protection applies to every account on any later re-run.

## Step 2 — prove the scoping before anything depends on it

```bash
bash infra/hetzner/verify-minio-scoping.sh
```

Every line must be `PASS`. The script asserts, per account, `list` / `read` / `write`
against all three buckets — including that `document-service` **cannot write** the
lakehouse and `platform-control` **cannot read** raw artifacts back.

If anything fails, stop here. Nothing has been cut over yet: every workload is still
running on the old shared credential and is unaffected.

## Step 3 — Trino

Trino is first because it is the easiest to roll back and touches no write path the apps
depend on.

```bash
NS=evidara
helm upgrade --install trino trino/trino -n $NS -f infra/hetzner/values/trino.yaml --wait
```

Check:

```bash
kubectl -n $NS get pods -l app.kubernetes.io/name=trino
# a query against the Iceberg catalog must still return rows
```

## Step 4 — the apps

`deploy-stage4.sh` rewrites `evidara-app-secrets` **without** the MinIO keys and refuses
to continue if any `evidara-s3-*` Secret is missing.

```bash
GHCR_TOKEN=<github PAT with read:packages> bash infra/hetzner/deploy-stage4.sh
```

This applies `apps/`, which adds the per-workload `secretRef`s. Then restart the
workloads so they pick up the new environment:

```bash
NS=evidara
kubectl -n $NS rollout restart deploy/platform-control-api deploy/di-consumer \
  deploy/document-service deploy/projection-bridge
kubectl -n $NS rollout status deploy/platform-control-api deploy/di-consumer \
  deploy/document-service deploy/projection-bridge
```

> The manifests list each `evidara-s3-*` Secret **after** `evidara-app-secrets` in
> `envFrom`, so the scoped credential wins even if a stale copy of the old keys is still
> in the shared Secret. That is deliberate: it makes a half-finished cutover safe rather
> than ambiguous.

## Step 5 — exercise each write path once

The deny tests prove what is *denied*. These prove what still *works*:

1. **platform-control writes an artifact** — start a small run from the admin UI, or the
   `ch-fedlex` canary (`scripts/ch-fedlex-fast-loop.sh`), and confirm the run's
   `RawArtifact` rows get an `s3://evidara-raw-artifacts/...` `storage_path`.
2. **di-consumer writes canonical** — that same run should reach `document.processed`;
   confirm the Delta surfaces advanced.
3. **document-service reads canonical** — `GET /v1/documents/{id}/lean` must return real
   `title`/`sections`, not the thin fallback. A fallback response means the read
   credential is wrong (see Troubleshooting).
4. **retention sweep deletes** — do not wait for 04:00 UTC; run it once by hand:

   ```bash
   kubectl -n evidara create job --from=cronjob/platform-control-retention-sweep \
     retention-sweep-cutover-check
   kubectl -n evidara logs job/retention-sweep-cutover-check
   ```

5. **CNPG still backs up** — `kubectl -n evidara get cluster evidara-pg -o yaml` should
   show no `lastFailedBackup` newer than the cutover.

## Step 6 — confirm root is unused

```bash
NS=evidara
kubectl -n $NS get secret evidara-app-secrets -o jsonpath='{.data}' | tr ',' '\n' | cut -d'"' -f2
# MUST be exactly: PLATFORM_CONTROL_DATABASE_URL

# No workload may name the root Secret:
kubectl -n $NS get deploy,cronjob,statefulset -o yaml | grep -c 'minio-root' || true
# MUST be 0
```

`scripts/check_hetzner_minio_credentials.py` enforces the same invariant on the committed
files, in pre-commit and in CI, so it cannot come back by edit. It cannot see the live
cluster — that is what this step is for.

## Rollback

Rollback is per-workload and does not require reverting the merge.

**A single app fails on the new credential.** Restore the shared key for that workload
only, diagnose, then redo:

```bash
NS=evidara
kubectl -n $NS patch deploy/<name> --type=json \
  -p='[{"op":"remove","path":"/spec/template/spec/containers/0/envFrom/<index-of-evidara-s3-*>"}]'
# then re-add PLATFORM_CONTROL_S3_* / DI_S3_* to evidara-app-secrets from minio-root
```

**Trino fails.** Revert `values/trino.yaml`'s two `secretKeyRef` names to `minio-root` /
`rootUser` / `rootPassword` locally and `helm upgrade` again. Do not commit that revert;
it fails the CI guard, which is the point.

**Everything fails.** `git revert` the #813 merge and re-run `deploy-stage4.sh` plus the
Trino `helm upgrade`. The MinIO users and their Secrets are harmless if left in place —
nothing references them after a revert — so leave them for the retry rather than deleting
credentials under a live cluster.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Pod starts, first S3 call returns `AccessDenied` | policy narrower than the code path | widen the policy document **and** the account's `allow` entry in `accounts.json` in one PR — the guard fails if the policy is wider than the declared scope |
| `GET /v1/documents/{id}/lean` returns the thin fallback | `document-service` cannot read `evidara-lakehouse/canonical/*` | `bash infra/hetzner/verify-minio-scoping.sh document-service` |
| CNPG `lastFailedBackup` appears right after Step 1 | `cnpg-backup`'s Secret and MinIO disagree | `bash infra/hetzner/provision-minio-users.sh cnpg-backup`, then `verify-minio-scoping.sh cnpg-backup` |
| `verify-minio-scoping.sh` says "credential is not accepted by MinIO" | the IAM user was orphaned by a root rotation | re-run `provision-minio-users.sh <user>` and restart that user's workloads |
| `mc: command not found` inside the pod | non-MinIO image matched `-l app=minio` | check `kubectl -n evidara get pod -l app=minio` returns the MinIO pod only |

## What this does not cover

- **`k8s/gitops/`** — the Argo/MacConfig tree reads object-storage credentials from a
  `ClusterSecretStore` (`k8s/gitops/base/platform-control-api.yaml`,
  `base/di-nats-consumer.yaml`), both pointing at one `evidara/object-storage` vault
  entry. That tree targets a different, platform-owned environment and is not deployed by
  this runbook. Splitting that vault entry per workload is the same fix in a different
  place and needs its own change.
- **`docker-compose.local.yml`** — local development runs MinIO with `minioadmin`
  root over a throwaway container. There is no cross-tenant blast radius on a laptop.
- **CI runners.** The ARC runners share the node but hold no MinIO credential of their
  own; their PAT and GHCR token are Kubernetes Secrets in the cluster
  (`docs/runbooks/hetzner-runner-secret-capture.md`). Nothing in this cutover touches
  them. Note that anyone with `kubectl get secret` in `evidara` can still read every
  Secret here — per-workload scoping reduces what a *compromised workload* reaches, not
  what a cluster-admin reaches. Namespace-level RBAC is a separate piece of work.
