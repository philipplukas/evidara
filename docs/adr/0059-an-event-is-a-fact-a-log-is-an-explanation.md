# ADR-0059: An event is a fact another component acts on; a log is an explanation for a human

## Status

Proposed

## Date

2026-09-18

## Context

Twice on 2026-09-17 the answer to "why did this fail" was in a log line that a
container restart had already destroyed, and both times the alternative was to
infer. Both inferences were wrong.

### The two failures, and what each one needed

**The projection bridge stopped forwarding.** The operator API key had been
rotated with a trailing newline, so `httpx` refused the header:

```
projection_forward_failed ... ValueError: Invalid header value b'…\n'
```

That line is a complete diagnosis. It existed, it was correct, and
`kubectl logs --previous` on the next crash returned three startup lines. No
component should branch on it — it is narrative, and narrative is a log. The
defect is that it did not survive a restart.

**58 documents reached `accepted` + `processing` and no terminal status.** No
error code, no DLQ entry, nothing queued or in flight. The root cause is still
unknown: two hypotheses were proposed and measurement refuted both, and the logs
that would settle it are gone.

Part of that gap is not a logging problem at all. `nats_consumer.py:147-165`
records `dead_lettered` — a terminal outcome platform-control's read model must
act on — **only in a log**. That is a domain fact written to stdout, and
ADR-0058 part 1 already decides it becomes an event.

### Why the distinction is the decision

The repo has both mechanisms and no rule for choosing, so each has absorbed some
of the other's work: a terminal outcome lives in a log, while the run read model
carries no way to say "the worker gave up". Adding log aggregation without the
rule would make the wrong half easier to live with.

## Decision

**If another component must change behaviour because of it, it is an event. If it
only helps a human understand why, it is a log.**

Two corollaries, both testable against existing code:

- **A terminal outcome is always an event.** `canonical_ready`, `failed`,
  `quarantined`, `withdrawn`, `skipped_duplicate`. It is contract-governed
  (`contracts/events/`), schema-validated, and consumed. A terminal outcome that
  exists only as a log line is a defect, and there is currently one.
- **A stack trace, a retry, a timing, an upstream's error text is always a log.**
  None of them is a fact the platform acts on, none belongs in a schema, and
  putting them on the bus would make log volume compete with domain events for
  the same stream.

### Logs are aggregated, so they outlive the process that wrote them

**Loki + Grafana Alloy**, in the `monitoring` namespace that already runs
kube-prometheus-stack. Grafana is already the query surface with auth,
dashboards and Alertmanager wired in, so this is a datasource rather than a
system.

Owned by
[`research-platform`](https://github.com/philipplukas/research-platform) —
`infra/hetzner/OWNERSHIP.md` maps `values/kube-prometheus-stack.yaml` to
`observability/kube-prometheus-stack/values.yaml` there, and an edit made in
this repository does not reach the cluster. This ADR is the decision; the
manifests are not in this repo.

### What is deliberately not built

- **No log schema project.** document-intelligence already emits JSON carrying
  `event`, `run_id` and `correlation_id`. That is enough to query on. The gap on
  2026-09-17 was not structure, it was that the lines did not survive a restart.
- **No tracing.** `correlation_id` already spans platform-control, di-consumer
  and the projection bridge. A trace backend would answer a question we have not
  yet failed to answer.
- **No logs on NATS.** The bus is contract-governed and schema-validated; log
  lines are neither.
- **No alerting on log content**, initially. Alertmanager already fires on
  metrics. A log-derived alert needs a pattern, and a pattern chosen before the
  logs exist is a threshold calibrated on nothing — the mistake #1016, #1017 and
  #1019 each paid for in a different place.

## Consequences

### Retention is bounded by the only storage class this cluster has

`local-path` is the sole StorageClass, `Delete` reclaim, no volume expansion. A
Loki PVC is therefore **node-pinned and lost with the node**. That is adequate
for the stated purpose — surviving a pod restart, which is what failed — and it
must not be described as durable. MinIO is already running and is the documented
upgrade path when durability is actually needed.

### `failed` gains its first producer, and the panel must render it

ADR-0058 part 1 becomes load-bearing here: once a dead-letter is an event rather
than a log line, the status enum value reaches consumers that have never seen it.
Additive under the compatibility policy, but the admin panel's status displays
need checking before it ships.

### This does not explain the 58 documents

It makes the next occurrence explainable. Nothing here recovers what was already
lost, and the current root cause stays unknown rather than being replaced with a
third guess.

### The test to hold it to

Would it have shortened 2026-09-17? Three specific answers, which is why this is
worth doing rather than a general good practice:

1. The `Invalid header value` errors, searchable across the restart that
   destroyed them.
2. Whatever di-consumer said about those 58 documents before it died.
3. A `correlation_id=run_…` query spanning three services — which would have
   shown that the dead-lettered documents and the stuck documents were almost
   disjoint sets **before** a replay was built and run to discover it.

The third is the argument. The replay was correct work and recovered 88 real
events; it was also aimed at a population a log query would have ruled out first.
