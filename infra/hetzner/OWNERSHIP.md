# Who owns what under `infra/hetzner/`

On 2026-09-07 the shared cluster layer moved to
**[philipplukas/research-platform](https://github.com/philipplukas/research-platform)**, and an
Argo CD Application named `platform` now reconciles it. This directory still contains the
files it moved, and they are **frozen**.

## Why the files are still here

Deleting them the day the controller was switched on would have spent evidence nobody had
collected. They are the fallback while it earns trust. Deletion is the last step of the
cutover, not this one.

## Why they are frozen

A fallback that people keep editing is not a fallback — it is a second owner. That was the
condition the extraction existed to end: one cluster, two half-owners, each reading the
other's definitions as duplicates of its own. It produced real conflicts, including a
`deploy-stage1.sh` that applied CloudNativePG 1.24.0 over a cluster running 1.25.4 —
a downgrade under the one database the estate cannot lose.

An edit made here today **does not reach the cluster**. Argo reconciles from the other
repository. It changes nothing and silently forks the estate again.

`scripts/check_platform_ownership.py` enforces this, from the hashes in
`infra/PLATFORM-OWNED.txt`, via pre-commit. `--list` prints what is covered.

## Frozen (31 files) — change these in `research-platform`

| Here | There |
|---|---|
| `values/minio.yaml` | `data/minio/values.yaml` |
| `values/nats.yaml` | `data/nats/values.yaml` |
| `values/nessie.yaml` | `data/nessie/values.yaml` |
| `values/opensearch.yaml` | `data/opensearch/values.yaml` |
| `values/trino.yaml` | `data/trino/values.yaml` (merged with fsts's capture) |
| `values/zitadel.yaml` | `identity/zitadel/values.yaml` |
| `values/kube-prometheus-stack.yaml` | `observability/kube-prometheus-stack/values.yaml` |
| `values/argocd.yaml` | `gitops/argocd/values.yaml` |
| `minio-policies/` | `secrets/minio-policies/` |
| `runners/` | `ci/runners/` |
| `auth/letsencrypt-issuer.yaml` | `ingress/certs/letsencrypt-issuer-http01.yaml` |
| `auth/basicauth-middleware.yaml` | `ingress/basicauth-middleware.yaml` |
| `provision-minio-users.sh`, `verify-minio-scoping.sh` | `secrets/` |
| `00-namespace.yaml` | `data/00-namespace.yaml` |
| `nats-stream-init.job.yaml` | `data/nats/stream-init.job.yaml` |
| `deploy-stage{1,2,3,8}.sh`, `deploy-observability.sh`, `deploy-runners.sh` | `scripts/` |
| `deploy-argocd.sh` | `gitops/argocd/deploy-argocd.sh` |

The copies there are not byte-identical, deliberately: paths were repointed, the CNPG
downgrade was removed from stage 1, the two Trino values files were merged, and the runner
images were pinned to a digest. **The versions in `research-platform` are the current ones.**

## Not frozen — this repository still owns these

- `apps/` — the workloads, synced by the `evidara-apps` Application
- `argocd/application-evidara-apps.yaml` — its Application
- `auth/ingress-tls.yaml` — Evidara's own hostnames
- `marketing/` — the marketing deployment
- `observability/` — scrape targets, pipeline alerts, the funnel dashboard
- `postgres-cluster.yaml` — the `evidara-pg` Cluster. The CNPG **operator** is platform;
  this **Cluster CR** is an application object and stays here.
- `deploy-stage4.sh`, `deploy-stage5.sh` — app deploy, API keys, BasicAuth secret, TLS
- `README.md` — still describes all nine stages; the platform half now lives in
  `research-platform/docs/deploy-stages.md`

## Two dependencies that cross the boundary

Neither is visible from the side that depends on it:

1. **Stage 1 no longer creates a database.** The platform's `deploy-stage1.sh` installs
   MinIO and checks the CNPG operator version; applying `postgres-cluster.yaml` is this
   repository's job and happens after it.
2. **Stage 5 creates a Secret a platform object needs.** `evidara-basicauth` is created
   here; the Traefik `Middleware` referencing it lives in `research-platform`. Applying that
   Middleware without this Secret yields a 500 on two public hostnames.

## Finishing the cutover

When `research-platform/scripts/platform-watch.sh --report` shows roughly 14 clean days,
delete the frozen files, `infra/PLATFORM-OWNED.txt`, `scripts/check_platform_ownership.py`
and its pre-commit hook in one commit. Do not edit the manifest to match a change — that
defeats the guard rather than satisfying it.
