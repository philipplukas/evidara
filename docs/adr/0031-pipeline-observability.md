# ADR-0031: Pipeline Observability — Prometheus, Grafana, and a Funnel That Cannot Lie

## Status

Accepted

## Date

2026-07-13

## Context

The Hetzner k3s cluster (ADR-0029) ran with **no OpenSearch document index at all** for
an extended period. Search returned an empty page for every query. It was found because
a human looked at the UI and asked "why don't I see search results?"

Every failure uncovered in that investigation was silent:

| What was broken | How it was found |
|---|---|
| No document index / aliases (#549) | Human noticed an empty UI |
| Search silently returning 0 hits (#551) | Manual `_cat/aliases` |
| DI status callbacks never sent (#550) | `pipeline-health` contradicted reality |
| Cluster on a 3-week-stale image (#549) | Manually inspecting `dist/` inside the pod |
| `projection-bridge` never deployed | Reading `kubectl get pods` |

Throughout all of it: every pod `Running`, `1/1 Ready`, zero restarts, clean logs.

**The system's failure mode is to look perfectly healthy while doing nothing.** This is
not an accident of these particular bugs — it is structural. A liveness probe answers
*"is the process alive"*. Every probe was green while the core product feature was
completely dead. Nothing in the cluster answered *"is work actually flowing"*, and no
amount of care with the existing probes would have changed that, because that is not
the question they ask.

The repo already had `docs/adr/sli-slo-definitions.md` and an alert-response playbook.
Both describe a **Google Cloud Monitoring** stack that no longer exists — the SLIs name
Cloud Run metrics, Pub/Sub DLQ depth, and Cloud Logging queries. The migration to
Hetzner (ADR-0029) replaced every one of those signal sources and replaced none of the
monitoring built on them. The observability gap was created by the migration and was
never closed.

## Decision

Deploy **kube-prometheus-stack** (Prometheus + Alertmanager + Grafana) into the cluster,
instrument every service with a Prometheus exporter, and express the health of the
system as a **funnel** — one counter per pipeline stage — rather than as a set of
per-service health checks.

### D1 — The funnel is the primary artifact

The core deliverable is not "metrics exist", it is one dashboard where each pipeline
stage is a single number over a window:

```
runs launched            →  12
artifacts captured       →  12
bundle events published  →  12
DI messages processed    →  12
document.processed fwd'd →  12
documents indexed        →   5     ← leak visible instantly
docs searchable now      →   5
search queries           → 340
  ...with hits           →   0     ← outage visible instantly
```

The point is not any individual number. It is that **a leak between two adjacent stages
is a step change you cannot miss**, and a total outage is a zero. Deriving this by hand
took most of a session with `kubectl` and `_cat/aliases`. Reading it takes five seconds.

This is why the metrics are counters at stage boundaries rather than, say, request
latency histograms. Latency tells you a service is slow. The funnel tells you a service
is *lying* — cheerfully accepting work and dropping it.

### D2 — Every counter sits on an existing seam

No new abstractions. Each counter is a one-line addition at a call site that already
emits a structured log event:

| Stage | Metric | Where |
|---|---|---|
| Runs launched | `platform_control_runs_launched_total{provider}` | `RunService._dispatch_run` (covers the API, worker and Temporal paths — all three converge here) |
| Artifacts captured | `platform_control_artifacts_captured_total{path}` | `RunService._persist_inline_resources` **and** `FirecrawlWebhookService._apply_event` (two capture paths; counting one would look like a leak) |
| Bundle events published | `platform_control_bundle_events_published_total` | `RunService._publish_pending_dispatch_events`, `FirecrawlWebhookService._publish_bundle_manifest` |
| DI callbacks received | `platform_control_di_events_received_total{event_type}` | `routers/di_events.py` |
| DI messages processed | `di_messages_total{service,outcome}` | `dispatch_message` — labelled with the outcome string the function already returns |
| Projections forwarded | `di_projection_forwards_total{outcome}` | `forward_message` — same |
| Documents indexed | `legal_search_documents_indexed_total` | `ProjectionOpenSearchAdapter.upsertProjection`, **after** the write succeeds |
| Search queries / zero-hit / errors | `legal_search_search_queries_total`, `..._zero_hits_total`, `legal_search_search_errors_total` | `SearchOpenSearchAdapter.search` |
| Index state | `legal_search_alias_resolved{alias}`, `legal_search_aliases_consistent`, `legal_search_indexed_documents` | `SearchIndexProbe`, refreshed on scrape |

The outcome labels on the DI counters are **the exact strings the dispatch functions
already return**, so the counters cannot drift from the code paths they describe. A
dead-lettered message is counted as dead-lettered, not dropped from the denominator.

### D3 — `legal_search_search_errors_total` is not optional

`SearchOpenSearchAdapter.search` catches OpenSearch failures and returns an empty result
set ("observable degradation"). It was not observable: a dead cluster and a genuinely
unmatched query produce a byte-identical response. The error counter is what separates
them, and it is the reason the zero-result alert can be trusted.

### D4 — Index state is probed at scrape time, not on a timer

`SearchIndexProbe` resolves the `documents-read` / `documents-write` aliases and counts
the documents behind them when Prometheus scrapes. Two cheap OpenSearch calls per
minute, no background loop to leak on shutdown, and no stale gauge.

It **never throws**. A probe that can 500 the `/metrics` endpoint takes every alert that
depends on it offline at exactly the moment they matter. On failure it reports
`legal_search_index_probe_up 0` and leaves the alias gauges at 0 — it fails *loud*, not
silently green.

### D5 — Exporters over hand-rolled endpoints

- **NATS** — the chart's `promExporter` sidecar (`prometheus-nats-exporter`), which
  exposes JetStream consumer lag and redelivery counts natively.
- **DI consumers** — a `/metrics` branch on the health server they *already run*
  (`jobs/_consumer_common.py`), not a second HTTP listener.
- **platform-control** — `prometheus_client` on the existing unauthenticated health
  router.
- **legal-search** — `prom-client` in a global `MetricsModule`, `@Public()` so the
  global `ApiKeyGuard` does not 401 the scraper.

### D6 — Alerts that fire on the failures that actually happened

Day-one alerts (`infra/hetzner/observability/alerts.yaml`), all validated with
`promtool check rules`:

- `DocumentsReadAliasUnresolved` (**page**) — the #549 outage, currently 100% undetected.
- `DocumentsAliasesDiverged` (**page**) — the #551 divergence: projections write to one
  index, search reads another, both "succeed" forever.
- `SearchIndexEmpty` (**page**) — the alias resolves but holds nothing.
- `SearchZeroResultRateHigh` (**page**) — >95% of searches return nothing over 15m, with
  a volume guard so a quiet night does not page.
- `ProjectionPathLeaking` (**page**) — DI processed messages this hour, legal-search
  indexed zero. The funnel leak, as an alert.
- `EvidaraTargetDown` (**page**) — a target Prometheus cannot scrape has taken all of
  its own alerts down with it. This is the alert that keeps the others honest.
- Dead-lettering and JetStream backlog/redelivery alerts at warning tier.

### D7 — k3s defaults are actively harmful and are turned off

kube-prometheus-stack ships scrape configs and alert rules for
`kube-controller-manager`, `kube-scheduler`, `kube-proxy` and `etcd`. On k3s these run
inside a single embedded binary and expose no such endpoints, so the defaults produce
permanently-down targets and permanently-firing alerts. A monitoring stack that cries
wolf on day one is worse than none — it trains the operator to ignore it. They are
disabled in `values/kube-prometheus-stack.yaml`, along with the single-node-hostile
"no redundancy" API-server rules.

## Consequences

**Positive**

- Every failure in the table above becomes a page instead of a human noticing an empty UI.
- The funnel makes a *partial* leak (12 in, 5 out) as visible as a total outage — the
  harder and more common case.
- SLI/SLO definitions get a real signal source again after the GCP migration removed theirs.
- The scrape targets live next to the workloads (`infra/hetzner/observability/`), so
  adding a service means adding a `ServiceMonitor` block, not editing a Helm release.

**Negative / accepted**

- Roughly 2 GiB of RAM and ~22 GiB of disk on a single-node box, at 15d retention.
- Two new runtime dependencies (`prom-client`, `prometheus-client`) — both are the
  standard, dependency-light choice for their ecosystems.
- Alertmanager ships with **no external receiver**. Alerts land in its UI, not in
  anyone's phone. Wiring a Slack webhook is a one-value change
  (`docs/setup/hetzner-observability.md`) and is deliberately left to the operator, who
  owns the credential.

**Deferred**

- **Stale-image-SHA alert** (deployed image != newest `main` image for > N days, the rot
  that caused #549). It needs a GitHub-aware exporter — a genuinely different piece of
  machinery, not a metric any service can emit about itself. Tracked separately.
- **An OpenSearch cluster exporter.** The funnel's "docs in OpenSearch" number comes from
  `SearchIndexProbe`, which reads the alias directly — precisely the thing that was
  broken — and needs no extra component. A cluster-level exporter (shard/JVM/disk health)
  is a separate, lower-urgency concern.

## Alternatives considered

**Keep using structured logs + a log-based alerting stack (Loki).** The services already
emit good structured events; one could alert on their absence. Rejected: "alert when a
log line *stops* appearing" is exactly the query class that is hardest to get right and
easiest to get silently wrong, and it cannot express `legal_search_indexed_documents == 0`
— a *state*, not an event. The failure here was a system that was quiet, and log-based
alerting is weakest against quiet.

**Push metrics to a hosted provider (Grafana Cloud, Datadog).** Rejected: ADR-0029 moved
to Hetzner explicitly for a fixed-cost posture, and usage-billed observability on a
usage-billed egress path reintroduces the exact bill shape that was being eliminated.

## References

- Issue #553 — the outage this ADR responds to; #549, #550, #551 the specific failures
- ADR-0029 — self-hosted Hetzner runtime (created this gap by replacing every GCP signal source)
- `docs/adr/sli-slo-definitions.md` — SLI/SLO targets, now backed by a real signal source
- `docs/setup/hetzner-observability.md` — deploy, verify, and wire a receiver
- `docs/runbooks/alert-response-playbook.md` — what to do when one of these fires
