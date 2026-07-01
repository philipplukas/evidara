# Product GitOps (Kubernetes)

Product manifests synced by Argo CD `Application` objects (path convention
`k8s/gitops/<env>`). Authored in ADR-0029 Slice 5 as part of the GCP → self-hosted
(Hetzner) runtime migration.

## Layout

| Path | Use |
| --- | --- |
| [`base/`](base/) | Environment-agnostic workloads (Deployment / Service / Ingress / ExternalSecret). Referenced by every overlay; not synced directly. |
| [`dev/`](dev/) | Dev overlay → `evidare-dev`: image tags, `evidara-config`, ingress hosts. |
| [`staging/`](staging/) | Staging overlay → `evidare-staging`. Preferred-first environment for real manifests. |
| [`prod/`](prod/) | **Empty** until the staging Argo path is proven; activation steps in its `kustomization.yaml`. |

Render an overlay locally with `kubectl kustomize k8s/gitops/dev`. CI renders all three
env roots via `scripts/validate_k8s_gitops_kustomize.sh`.

## Evidara-owned vs platform-owned

Only the contract-allowed kinds appear here (Deployment, Service, Ingress, ExternalSecret;
see [`../../vendor/platform-contract.yaml`](../../vendor/platform-contract.yaml)). The
**stateful backing services are NOT in this tree** — `StatefulSet` / `PVC` / CRDs are
forbidden for product manifests, so they are platform-owned (MacConfig) or external
(OpenStack):

| Service | Provided by | Consumed via |
| --- | --- | --- |
| Postgres | platform / external | `PLATFORM_CONTROL_DATABASE_URL` (ExternalSecret) |
| OpenSearch | platform / external | `OPENSEARCH_NODE` (config) + `OPENSEARCH_*` (ExternalSecret) |
| NATS JetStream | platform / external | `*_NATS_SERVERS` / `NATS_SERVERS` (config) |
| MinIO / S3 | platform / external | `*_S3_ENDPOINT_URL` (config) + `*_S3_*` keys (ExternalSecret) |

## Before first sync — fill in placeholders

These are intentionally placeholders in the overlays:

- **Image registry owner** — `ghcr.io/philipplukas/evidara-*` (adjust if the registry differs).
- **Ingress hosts** — `*.dev.evidara.example` / `*.staging.evidara.example`.
- **Service endpoints** — `*.evidara-platform.svc` addresses for Postgres/OpenSearch/NATS/MinIO.
- **Vault paths** — `evidara/*` keys in the `ExternalSecret`s; the `shared-vault`
  ClusterSecretStore and its policies are owned by MacConfig.

See also: [MacConfig migration docs](../../docs/migration/README.md),
[ADR-0029](../../docs/adr/0029-self-hosted-hetzner-runtime.md).
