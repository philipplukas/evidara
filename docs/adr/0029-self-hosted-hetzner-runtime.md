# ADR-0029: Self-Hosted Hetzner Runtime — Retire GCP Managed Services

## Status

Proposed

## Date

2026-06-28

## Context

Evidara's runtime was built on Google Cloud managed services: Cloud Run (services +
jobs), Pub/Sub (events, DLQs, OIDC push), GCS (artifact + manifest object storage),
Cloud SQL (Postgres), Secret Manager, OpenSearch-on-GCE, and Databricks for
`document-intelligence`. This stack is **usage-billed** and several pieces are
always-on (a `min=max=1` Cloud Run worker, Cloud SQL, an OpenSearch VM), with
`enable_billing_budget = false` in prod (`infra/terraform/gcp/.../billing_guardrails.tf`).

The project paused active development around 2026-04-29. Since then the five scheduled
nightlies that exercise live dev/staging (`e2e-smoke-dev`, `e2e-smoke-staging`,
`scraping-nightly-canary`, `interaction-flow-staging-evidence`, `release-readiness`)
have failed every day — not from code regression (no code merged) but from
**environment decay**: the live GCP runtime they depend on is degraded while still
potentially billing.

The owner's goal is a **fixed monthly cost** posture — pay for Hetzner dedicated
capacity, not per-request cloud usage — and to consolidate onto self-hosted
infrastructure. This is the natural completion of a migration the repo already
started: `vendor/platform-contract.yaml` (MacConfig), `k8s/gitops/`, `service-template/`,
`docs/migration/`, and `.sops.yaml` already chose a self-hosted GitOps + Vault target.

### What makes this tractable

A migration-surface audit (2026-06-28) found the application is **already abstracted
away from GCP**, selected by config enums rather than hardcoded SDK calls:

| Dependency | Access pattern | Difficulty | Evidence |
|---|---|---|---|
| Object storage (GCS) | `ArtifactStore` Protocol + factory on `artifact_store_backend`; `Local`/`Gcs` adapters | Easy | `platform-control/.../services/artifact_store.py:15` |
| DI bundle reads | `DispatchingBundleLoader` routes by URI scheme; local loader exists | Easy | `document-intelligence/.../ingest/loaders.py:59` |
| Postgres (Cloud SQL) | plain `create_async_engine(database_url)`, no Cloud SQL connector | Trivial | `platform-control/.../database.py:19` |
| Secrets (Secret Manager) | **zero** SDK usage in app code; all env/config via Pydantic Settings | Easy | grep `secretmanager` in app code: 0 hits |
| Messaging — publish | `RawArtifactPublisher` Protocol; `Noop`/`LocalOutbox`/`PubSub` adapters | Easy | `platform-control/.../events/publisher.py:16` |
| Messaging — **consume (DI)** | hardcoded `pubsub_v1.SubscriberClient().pull()/.acknowledge()` + Pub/Sub DLQ | **Hard (only real rework)** | `document-intelligence/.../jobs/runtime_consumer.py:149` |
| Canonical persistence | `CanonicalSink` interface; Spark/Databricks opt-in (`use_spark_delta=False` default) | Easy | `document-intelligence/.../persist/sinks.py:211` |

`pyspark`/`databricks` are **not** runtime dependencies (only pure-Python `deltalake`),
so DI runs today as a plain containerized queue-consumer. The whole platform already
boots GCP-free in `docker-compose.local.yml` (local artifact store, `noop` publisher).

The single concentrated engineering task is replacing the **DI Pub/Sub consumer** and
reproducing its redelivery/DLQ semantics on a self-hosted broker.

## Decision

Migrate the Evidara runtime to a self-hosted, fixed-cost stack on Hetzner, replacing
each GCP managed service with a self-hosted equivalent delivered via the existing
MacConfig + Argo CD GitOps path.

> **Note:** decisions D1–D3 reflect the owner's stated direction and the
> recommended defaults as of 2026-06-28. This ADR is **Proposed** until they are
> confirmed; flip to **Accepted** once execution on Slice 1 begins.

### Target mapping

| GCP service | Self-hosted replacement |
|---|---|
| Cloud Run (services + jobs) | Kubernetes Deployments / Jobs on Hetzner, delivered by Argo CD (per `vendor/platform-contract.yaml`) |
| Pub/Sub | **NATS JetStream** (broker + persistence + redelivery/DLQ) |
| GCS | **MinIO** (S3-compatible) via a new `S3ArtifactStore` adapter + an `s3://` branch in the DI bundle dispatcher |
| Cloud SQL | Self-hosted Postgres on the cluster (e.g. CloudNativePG operator) |
| Secret Manager | **sops** + External Secrets `shared-vault` ClusterSecretStore (already in the platform contract) |
| OpenSearch-on-GCE | OpenSearch StatefulSet on the cluster |
| Databricks | Plain DI consumer container; `DeltaCanonicalSink` (pure-Python) or a Postgres sink. Spark stays opt-in only. |

### Key decisions

- **D1 — Compute substrate:** Kubernetes **directly on Hetzner dedicated servers**
  now (fastest revival on the already-scaffolded MacConfig/Argo path). OpenStack is
  **deferred**: it may host other workloads later but is explicitly *not* on
  Evidara's critical path, to avoid an extra IaaS control plane to operate solo.
- **D2 — Broker:** **NATS JetStream** — lightest to run for a single-cluster,
  single-operator, fixed-cost setup; built-in persistence and redelivery cover the
  current DLQ needs. (RabbitMQ DLX and Kafka/Redpanda considered; see Alternatives.)
- **D3 — GCP wind-down:** **scale to zero first, then destroy.** Stop the spend
  immediately while the Hetzner stack is unproven; preserve Cloud SQL + GCS data
  until cutover is validated, then `terraform destroy`. Risk is low because canonical
  data is seed YAML in-repo. (Cloud SQL has `deletion_protection=true`.)

### Execution slices

1. **Stop the bleed (in-repo, done in this change):** disable the five GCP-dependent
   nightly schedules (keep `workflow_dispatch`); document the GCP cost-stop /
   wind-down procedure (`docs/runbooks/gcp-cost-stop.md`).
2. **Broker abstraction:** extract a DI publisher Protocol; add NATS JetStream
   adapters for publish on both services; add a `nats` service to compose for local
   end-to-end exercise (today's only non-GCP messaging is `noop`).
3. **DI consumer rewrite:** replace `runtime_consumer.py`'s Pub/Sub pull/ack/DLQ loop
   with a JetStream consumer; reproduce redelivery + DLQ semantics; test against the
   compose broker.
4. **Storage + secrets:** `S3ArtifactStore` (MinIO) adapter + `s3://` DI loader branch;
   wire External Secrets / sops for runtime config.
5. **Cluster manifests:** author the real product manifests under `k8s/gitops/`
   (MinIO, NATS, Postgres, OpenSearch, the services) following `service-template/`.
6. **Cutover + GCP destroy:** validate the Hetzner environment, repoint the
   (re-enabled) smokes at it, then `terraform destroy` the GCP runtime stack.

## Consequences

### Positive

- Fixed, predictable monthly cost; no usage-billed surprises; no always-on Cloud Run /
  Cloud SQL / OpenSearch-VM spend with budgets disabled.
- Consolidation onto one self-hosted, GitOps-managed cluster the owner controls.
- Most of the app needs no code change — only config + a handful of new adapters.

### Negative / costs

- The DI consumer rewrite is real work and must faithfully reproduce DLQ/redelivery.
- Operating the cluster (Postgres, OpenSearch, NATS, MinIO) is now self-managed —
  backups, upgrades, and capacity become the owner's responsibility.
- A coexistence window where compose/local proves the broker before cluster manifests
  exist.

## Alternatives considered

- **Stay on GCP, just add budgets/scale-to-zero.** Rejected: keeps the usage-billed
  model the owner wants to leave and the always-on cost floor.
- **RabbitMQ instead of NATS.** Mature, DLX maps directly to current DLQ semantics, but
  heavier to run than NATS JetStream for this volume/operator count. Reconsider if
  classic AMQP routing is later needed.
- **Kafka / Redpanda.** Strongest for replay/event-sourcing, but operationally heavy and
  overkill for current throughput.
- **OpenStack as the immediate IaaS under k8s.** Deferred (D1): adds a full IaaS control
  plane to operate solo, working against the "low ops / fixed cost" goal; not required to
  revive the system.

## Progress

- **Slice 1 — done** (2026-06-28): nightly schedules disabled; `gcp-cost-stop.md` runbook.
- **Slice 2 — in progress** (2026-06-28):
  - platform-control `NatsRawArtifactPublisher` (JetStream, `Nats-Msg-Id` dedup),
    `event_publisher_backend="nats"` config + factory wiring, unit-tested.
  - document-intelligence `EventPublisher` Protocol extracted (publish surface typed
    against it) — unblocks the Slice 3 NATS consumer without call-site churn.
  - `docker-compose.local.yml` gains a `nats` profile (JetStream broker + `EVIDARA`
    stream bootstrap) for local end-to-end exercise.
  - Remaining: NATS adapter for the DI publisher (lands with Slice 3, where the async
    broker context is natural).
- **Slice 3 — done** (2026-06-28):
  - `jobs/nats_consumer.py`: JetStream consumer reproducing the Pub/Sub semantics —
    ack on success, `term` (drop) on permanent/content-driven errors, `nak`+backoff on
    transient, and app-level DLQ (`term` + republish to the DLQ subject) once
    `max_deliver` is exhausted. Decision logic in `dispatch_message`, unit-tested for
    all four outcomes against a fake message/broker.
  - `NatsDocumentEventPublisher` (async) + `AsyncEventPublisher` port for DI status /
    document.processed events, with `Nats-Msg-Id` dedup.
  - Broker-agnostic helpers factored into `jobs/_consumer_common.py` (shared by both
    consumers); the Pub/Sub consumer now reuses them.
  - `di-consumer` service added to `docker-compose.local.yml` (`nats` profile) +
    `document_intelligence_nats_consumer` console script; `nats-py` is a DI dependency.
  - Remaining for cutover (Slice 6): retire the Pub/Sub `runtime_consumer.py`; real
    broker integration/e2e test (testcontainers-NATS) under CI-with-Docker.
- **Slice 4 — done** (2026-06-28):
  - platform-control `S3ArtifactStore` (boto3, path-style for MinIO) implementing the
    `ArtifactStore` port; `artifact_store_backend="s3"` config + factory wiring; unit-tested.
  - document-intelligence `S3BundleLoader` + `s3://` branch in `DispatchingBundleLoader`;
    `_parse_s3_uri`; reads via boto3 with `DI_S3_*` env config; unit-tested.
  - `boto3` is a dependency on both services.
  - `docker-compose.local.yml` gains a `minio` profile (MinIO + bucket bootstrap); PC
    artifact-store backend parameterized (default stays `local`).
  - **GCS is now fully replaceable.** All managed-service code paths have self-hosted
    equivalents; the remaining work is infrastructure (Slice 5) and cutover (Slice 6).
- **Slice 5 — in progress** (2026-06-28):
  - `k8s/gitops/base/` product manifests for all 7 workloads (platform-control api /
    admin / worker, legal-search api / frontend, document-service, di-nats-consumer):
    Deployment + Service + Ingress + Vault-backed ExternalSecret, only contract-allowed
    kinds. `dev/` and `staging/` overlays set namespace (`evidare-*`), image tags,
    `evidara-config`, and ingress hosts; `prod/` stays empty until staging is proven.
    Placeholder ConfigMaps removed.
  - Stateful stores (Postgres, OpenSearch, NATS, MinIO) are platform-owned (MacConfig)
    or external (OpenStack) — `StatefulSet`/`PVC`/CRDs are forbidden for product
    manifests — and are consumed via `evidara-config` + ExternalSecrets.
  - Remaining (needs operator input): real registry owner, ingress hostnames, store
    service endpoints, and Vault paths; MacConfig must provide the `shared-vault`
    ClusterSecretStore, the namespaces, and the backing stores; the Argo `Application`
    objects live in the cluster repo, not here.
- **Slice 6 — operator-driven** (runbook ready):
  - `docs/runbooks/hetzner-cutover.md` — end-to-end cutover checklist (stores → secrets
    → images → migrate → Argo deploy → validate → GCP destroy), staging-first.
  - `document-intelligence/tests/test_nats_integration.py` — opt-in real-NATS
    (testcontainers) round-trip proving publish dedup + a real message acked through the
    consumer adapter; gated on `EVIDARA_NATS_IT=1` + the `it` extra. Recommended before
    trusting cutover.
  - Still open at cutover: retire the Pub/Sub `runtime_consumer.py`; re-point/re-enable
    the disabled nightlies at the new environment.

## References

- Migration-surface audit, 2026-06-28 (this session).
- `docs/migration/README.md` — MacConfig GitOps strangler migration.
- `vendor/platform-contract.yaml` — platform contract (nginx, Let's Encrypt, External Secrets/Vault).
- `docs/runbooks/gcp-cost-stop.md` — GCP wind-down procedure (companion to this ADR).
- `docs/runbooks/hetzner-cutover.md` — Slice 6 cutover checklist (companion to this ADR).
- ADR-0016 (Cloud Run services vs jobs) and ADR-0003 (storage strategy) — superseded for runtime hosting by this ADR once Accepted.
