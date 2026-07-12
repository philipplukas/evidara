# Scaling *down*: retiring a cloud runtime to survive as a solo operator

> A case study in cost-aware architecture. It walks one decision — moving Evidara's
> runtime off usage-billed Google Cloud onto a fixed-cost self-hosted stack — from
> problem to trade-offs. The canonical record is [ADR-0029](../adr/0029-self-hosted-hetzner-runtime.md);
> this is the narrative version.
>
> *Author's note: fill in your own one line of context here — solo project built over
> [timeframe], alongside [work/study]. Everything below is traceable to the repo.*

## The problem

Evidara's runtime was built on Google Cloud managed services — Cloud Run, Pub/Sub, GCS,
Cloud SQL, Secret Manager, OpenSearch-on-GCE, and Databricks for the processing pipeline.
Convenient, and completely reasonable while the system was under active development.

Then development paused (around 2026-04-29). Nothing was wrong with the code — no
regressions, no merges. But the stack was **usage-billed with always-on pieces** (a
`min=max=1` Cloud Run worker, Cloud SQL, an OpenSearch VM) and prod had billing budgets
*disabled*. The five scheduled nightlies that exercised the live environment started
failing every single day — not from code, but from **environment decay**: a degraded
live runtime that was still potentially billing.

That's the trap of managed convenience for a paused, single-owner project: **cost and
operational drift continue even when you stop.** The goal became a *fixed monthly cost*
posture — pay for capacity, not per-request usage — that one person could carry
indefinitely.

## The constraint that shaped everything: one operator

This is not a "migrate to Kubernetes" story in the enterprise sense. Every option had to
pass one filter: **could a single person run it without a team?** That constraint did
more design work than any technical preference — it's why the decision rejected
approaches that would have been "better" at scale.

## Do the boring diligence first: a migration-surface audit

Before choosing a target, I audited *how coupled the application actually was to GCP* —
because the migration's cost is entirely a function of that coupling. The finding was the
whole ballgame: the app was **already abstracted away from the cloud**, selecting
backends by config enum rather than hardcoded SDK calls.

| Dependency | Access pattern | Difficulty |
|---|---|---|
| Object storage (GCS) | `ArtifactStore` Protocol + factory; `Local`/`Gcs` adapters | Easy |
| Postgres (Cloud SQL) | plain `create_async_engine(url)`, no Cloud SQL connector | Trivial |
| Secrets (Secret Manager) | **zero** SDK usage in app code — all via Pydantic Settings | Easy |
| Messaging — publish | `RawArtifactPublisher` Protocol; `Noop`/`LocalOutbox`/`PubSub` adapters | Easy |
| Messaging — **consume** | hardcoded Pub/Sub `pull()/acknowledge()` + DLQ | **Hard — the only real rework** |
| Canonical persistence | `CanonicalSink` interface; Spark/Databricks opt-in, not a runtime dep | Easy |

The audit collapsed a scary-sounding "cloud migration" into **one concentrated task**:
replacing the pipeline's Pub/Sub consumer and faithfully reproducing its redelivery/DLQ
semantics on a self-hosted broker. Everything else was config plus a handful of new
adapters. *The port/adapter discipline paid for itself years after it was written* — the
lesson isn't "migrate," it's "the abstraction you keep letting reviewers talk you into is
what makes the scary thing cheap later."

## The decision

Move the runtime to a self-hosted, fixed-cost Kubernetes stack on Hetzner, replacing each
managed service with a self-hosted equivalent, delivered through an existing GitOps path:

| GCP service | Replacement | Why |
|---|---|---|
| Cloud Run | Kubernetes on Hetzner (Argo CD GitOps) | Reuses infra already scaffolded |
| Pub/Sub | **NATS JetStream** | Lightest broker to *operate solo*; built-in persistence + redelivery cover the DLQ need |
| GCS | **MinIO** (S3) via a new `S3ArtifactStore` adapter | Slots into the existing port |
| Cloud SQL | Self-hosted Postgres (operator-managed) | — |
| Secret Manager | sops + External Secrets / Vault | Already chosen in the platform contract |
| Databricks | Plain pure-Python consumer container | Spark was already opt-in, not a runtime dep |

Two sub-decisions worth calling out, because both were "choose the less powerful option
*on purpose*":

- **NATS JetStream over Kafka/Redpanda or RabbitMQ.** Kafka is stronger for
  replay/event-sourcing; RabbitMQ's DLX maps more directly to the old semantics. Both were
  rejected as **operationally heavier than one person should carry** for this throughput.
  The right tool is the one you can run at 2am alone, not the one with the best feature
  matrix.
- **Kubernetes directly on dedicated servers, deferring OpenStack.** An IaaS control plane
  underneath would be "more correct" but adds a second thing to operate solo — explicitly
  against the low-ops goal.

## Trade-offs I accepted (out loud)

Good architecture writing names its own costs. This one:

- **Self-managed ops.** Backups, upgrades, and capacity for Postgres/OpenSearch/NATS/MinIO
  are now *my* problem. I traded a usage bill for an operations burden — a good trade only
  because the fixed-cost predictability matters more than my time-at-scale here.
- **A real rewrite.** The consumer rewrite had to *faithfully* reproduce four outcomes —
  ack on success, drop on permanent error, nak-with-backoff on transient, DLQ on
  exhausted redelivery — or risk silently losing or duplicating documents. It's unit-tested
  for all four against a fake broker, with an opt-in real-NATS (testcontainers) round-trip
  gated behind a flag before trusting cutover.
- **A coexistence window.** The broker is proven in local compose before cluster manifests
  exist — deliberately, to de-risk cutover rather than flip everything at once.

## Wind-down, sequenced for safety

**Scale to zero first, then destroy.** Stop the spend immediately while the new stack is
unproven, but preserve Cloud SQL + GCS data (deletion-protected) until cutover is
validated — then `terraform destroy`. The risk is genuinely low because canonical data is
seed YAML in-repo, but the sequence still assumes the new thing might fail.

## Where it landed

Slices 1–4 are done: the bleed stopped (nightlies disabled, cost-stop runbook), NATS
publish/consume adapters with DLQ semantics unit-tested, and `S3ArtifactStore` — **GCS is
fully replaceable**. Slice 5 (cluster manifests) is in progress; Slice 6 (cutover +
`terraform destroy`) is an operator-driven runbook. The ADR is deliberately still marked
*Proposed*, not *Accepted*, until execution on the live cluster begins — status honesty
over optimism.

## What I'd do differently

- **Write `gcp-cost-stop.md` on day one, not at pause.** The most expensive part of this
  was the weeks of drift before I noticed. A "how to safely mothball this" runbook should
  ship with any always-on cloud footprint from the start.
- **Budget guardrails should have been on in prod.** `enable_billing_budget = false` is the
  single line that let drift become cost. Cheap insurance, skipped.

---

### For a reviewer skimming this

If you're evaluating the engineering behind Evidara, this decision is a compact window
into it: an **evidence-first audit** before choosing, **constraint-driven** selection (one
operator, not one benchmark), **port/adapter design that made the hard thing cheap**,
**faithful reproduction of failure semantics** rather than a happy-path port, and an ADR
that names its own trade-offs and keeps its status honest. Related: the
[boundary contracts](../architecture/boundary-contracts.md) (canonical truth vs. serving
projection) and the [business-model canvas](../product/business-model-canvas.md) (judgment
under commercial ambiguity).
