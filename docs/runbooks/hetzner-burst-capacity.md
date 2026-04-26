# Hetzner Burst Capacity Plan

Owner: Platform / DevEx  
Last reviewed: 2026-04-26  
Last verified: Not yet implemented  
Applies to: low-cost Kubernetes burst capacity for dev/staging workloads

## Purpose

Use Hetzner as the low-cost burst layer for workloads that can tolerate
preemption, cold starts, and manual operator review. This is a planning note only:
it does not introduce product code, workflow changes, or new GCP resources.

## Stance

- Keep the owned Hetzner k3s baseline as the default runtime for dev/staging while
  GCP billing is disabled or intentionally avoided.
- Add a Hetzner Cloud autoscaled worker pool only when queue pressure or replay
  demand justifies it.
- Set burst pool size to `min=0` and `max=N`, where `N` is approved by the
  operator for the current cost envelope.
- Do not add new GCP billing surfaces for burst capacity. Cloud Run, GKE, Artifact
  Registry, or other GCP paths remain opt-in fallbacks only when explicitly
  approved elsewhere.
- Avoid exact provider pricing in this repo unless it is verified against the
  current Hetzner price list during the change.

## Target shape

| Layer | Role | Notes |
|-------|------|-------|
| Owned Hetzner k3s baseline | Always-on control and stateful runtime | Runs cluster system components, ingress, secrets integration, storage-backed services, and required dev/staging app surfaces. |
| Hetzner Cloud burst workers | Elastic compute pool | Autoscaled from `0` to approved `N`; used for disposable workers, CI runners, replay jobs, and stateless processing. |
| GitHub / Argo operators | Human control plane | Operators approve max size, label/taint policy, and routing of workloads before enabling burst scheduling. |

## Node labels and taints

Use labels for positive placement and taints to keep baseline workloads off burst
nodes by default.

| Node class | Labels | Taints |
|------------|--------|--------|
| Baseline | `evidara.node-role=baseline`, `evidara.storage=true` | None by default. |
| Burst | `evidara.node-role=burst`, `evidara.capacity=hetzner-cloud`, `evidara.lifecycle=ephemeral` | `evidara.node-role=burst:NoSchedule` |
| Runner burst | `evidara.node-role=burst`, `evidara.workload=ci-runner` | `evidara.workload=ci-runner:NoSchedule` |

Workloads must opt in with both:

- `nodeSelector` or node affinity for the intended burst label.
- A matching toleration for the burst taint.

## Suitable burst workloads

Route these to burst workers after a human confirms the pool size and expected
runtime:

- GitHub Actions runner pods for light/heavy self-hosted jobs once runner labels
  are stable.
- Stateless document replay, backfill, extraction, or projection rebuild jobs
  that can be restarted safely.
- Batch validation and smoke jobs with bounded runtime and clear logs.
- Temporary indexing helpers that write through normal, rebuildable serving
  paths and do not own persistent state.
- CPU-heavy one-shot analysis where failure only delays the run.

## Keep on baseline or storage nodes

Do not schedule these on burst nodes unless a separate architecture decision says
otherwise:

- Kubernetes control-plane components, ingress, cert management, external DNS,
  and cluster observability.
- Postgres / CNPG, OpenSearch data nodes, object/artifact PVC owners, and any
  other stateful workload with local disk or quorum expectations.
- platform-control API/admin and legal-search API/frontend surfaces needed for
  operator demos or acceptance checks.
- Long-running workers that depend on continuous polling semantics and cannot
  safely tolerate scale-to-zero.
- Secret bootstrap, GitOps controllers, and runner controller/listener components
  that manage the burst pool itself.

## Human review points

Require an operator review before each of these changes:

1. Setting or raising `max=N` for the Hetzner Cloud worker pool.
2. Adding a new workload toleration for `evidara.node-role=burst`.
3. Moving Docker/image builds, Playwright, or replay jobs from GitHub-hosted or
   baseline runners to burst workers.
4. Enabling workloads that may create external traffic spikes, provider API
   pressure, or large artifact writes.
5. Changing storage, ingress, or controller scheduling rules that could place
   stateful/control-plane pods on burst nodes.

Record the approved `N`, expected workload class, and rollback path in the
relevant runbook or change ticket.

## Rollback and guardrails

- Set burst pool `max=0` to stop new burst capacity.
- Remove burst tolerations from the workload first if pods keep landing on burst
  nodes after scale-down.
- Keep PodDisruptionBudgets and retry semantics aligned with the workload class:
  batch jobs should retry; baseline app surfaces should not depend on burst
  workers.
- Use queue duration, pending pods, and runner registration health as the first
  signals before increasing `N`.
- If cost or scheduling behavior is unclear, keep the workload on the owned
  baseline and collect one more measurement cycle before scaling out.

## Open decisions

- Confirm the exact autoscaler mechanism in MacConfig before product repos rely
  on labels or taints.
- Decide whether CI burst runners need a separate Docker-capable pool or should
  remain outside the generic light/heavy pools.
- Define the first approved `max=N` per environment after measuring queue time
  and replay demand.
