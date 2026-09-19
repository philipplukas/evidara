# Event tracing — the logs for one run

Owner: Platform team
Last reviewed: 2026-09-19
Last verified: 2026-09-19 for the LogQL section (every query executed against Loki
3.3.2 loaded with the line shapes these services actually produce). The Cloud
Logging section below is unverified and has been since 2026-04-03.
Applies to: the Hetzner cluster (LogQL) and the GCP Cloud Run deployments
(Cloud Logging)

## Two surfaces, and they are not the same

Production runs on the Hetzner k3s cluster (ADR-0029), where logs are container
stdout collected by Alloy into Loki and queried with **LogQL**. The Cloud Run
deployments keep their own logs in **Cloud Logging**, queried with
`jsonPayload.*`. Everything from "Cloud Logging" downwards on this page applies
only to the second.

The Loki and Alloy manifests are owned by
[research-platform](https://github.com/philipplukas/research-platform)
(`observability/loki/`, `observability/alloy/`); see
[`infra/hetzner/OWNERSHIP.md`](../../infra/hetzner/OWNERSHIP.md). What this
repository owns is the run-scoped dashboard they are queried through —
`infra/hetzner/observability/dashboard-run-logs.yaml`.

## What a run-scoped query can actually find

The previous version of this page opened with *"all three services emit
structured JSON logs with a shared field schema"*. Measured on 2026-09-19, that
is true of one of them. Read this table before concluding anything from an empty
result:

| Service | Carries a correlation id | Reaches stdout | Shape on stdout |
|---|---|---|---|
| document-intelligence (`di-consumer`, `projection-bridge`) | yes — `correlation_id` is the run id, set at publish time (`run_service.py:1963`) and carried through the event envelope | **yes** | `<date> <time> <LEVEL> {json}` — a `logging.basicConfig` line whose *message* is JSON, **not** a JSON line |
| platform-control | yes — `correlation_and_logging_middleware` (`main.py:93`) builds an `http_request` payload with it | **no** — #1047 | nothing. The API runs under `uvicorn` with no `--log-config` and calls no `basicConfig`, so the root logger stays at WARNING and every `INFO` record is dropped before formatting. Probed live: a request with `X-Correlation-Id: probe-892-logcheck` returned the header and left zero matching lines in the pod log |
| legal-search/api | yes, per request (`CorrelationIdMiddleware`) | n/a | the Nest default logger, ANSI-coloured, with the correlation id in **no** line |

So today a run-scoped query answers *"what did document-intelligence say about
this run"* and nothing else. That is the half the 2026-09-17 investigation
needed, and it is still half.

### Field reference (document-intelligence lines)

`observability/event_logging.py` sets `event`, `service` and `environment` on
every line, plus whichever of these are not `None`:

| Field | Description |
|-------|-------------|
| `event_type` | Domain event type |
| `event_id` | Unique event identifier |
| `correlation_id` | The run id that ties the flow together |
| `run_id` | Explicit run id from provenance |
| `message_id` | Broker message id |
| `delivery_attempt` | Delivery attempt number |
| `document_id` | The document the line is about |
| `status` | Outcome (inserted/duplicate/applied/stale/…) |
| `error_class` | `permanent` or `transient` |
| `error_type` | Exception class name |
| `duration_ms` | Processing duration in milliseconds |

`service` is **`di-consumer` on both consumers**. The projection bridge defines
`BRIDGE_SERVICE` and uses it for its NATS connection name and health server, but
`log_event` hardcodes `_SERVICE = "di-consumer"`
(`observability/event_logging.py:11`), so `| json | service="di-consumer"` does
not separate the two. Split them on the `container` label instead — Alloy sets it
from the pod spec and it is right by construction.

---

## LogQL: from a run to that run's logs

Grafana → **Dashboards → Evidara → "Evidara — logs for one run"**, or straight to
the URL, which is the form the admin panel can link to:

```
/d/evidara-run-logs/evidara-run-logs?var-run=run_01jq7a3s9b7j4dndd9sgv6pb9d
```

To type them by hand, in Grafana → Explore with the Loki datasource:

```logql
# Everything that named this run. No parsing, so it survives a format change,
# and it is the only form that can show a line from a service whose structured
# output is broken.
{namespace="evidara"} |= "run_01jq7a3s9b7j4dndd9sgv6pb9d"

# Which containers named it — how far the run got, by who talked about it.
sum by (container) (count_over_time({namespace="evidara"} |= "run_01jq7a3s9b7j4dndd9sgv6pb9d" [24h]))

# Structured events, fields extracted.
{namespace="evidara"} |= "run_01jq7a3s9b7j4dndd9sgv6pb9d"
  | pattern "<_> <_> <_> <msg>" | line_format "{{.msg}}" | json
  | correlation_id="run_01jq7a3s9b7j4dndd9sgv6pb9d"

# Only the failures.
{namespace="evidara"} |= "run_01jq7a3s9b7j4dndd9sgv6pb9d"
  | pattern "<_> <_> <_> <msg>" | line_format "{{.msg}}" | json
  | correlation_id="run_01jq7a3s9b7j4dndd9sgv6pb9d" | error_class != ""
```

### The trap: `| json` on its own returns zero and means nothing of the kind

`pattern "<_> <_> <_> <msg>" | line_format "{{.msg}}"` strips the three-token
`2026-09-19 09:22:17,989 INFO` prefix. Without it, `| json` fails on every
document-intelligence line — measured, `__error__: JSONParserErr`,
`__error_details__: "Value looks like object, but can't find closing '}' symbol"`
— and the moment you add a field filter after it, the query returns **zero
lines**:

```logql
# WRONG. Returns 0 lines whether or not the run exists.
{namespace="evidara"} |= "correlation_id" | json | correlation_id="run_…"
```

Zero lines reads as *"this run logged nothing"* and means *"the parser gave up"*.
That is exactly the unknown-vs-zero confusion ADR-0052 is about, in the one tool
an operator reaches for when something is already broken. The upstream
`deploy-observability.sh` still prints the unprefixed form as its verification
step; it is wrong for our lines.

### A stack trace is not run-scoped

Python writes a traceback as one record and many stdout lines. Alloy ships each
line separately, and the continuation lines carry no run id — so they match
neither the substring filter nor the parsed one. Use the run-scoped panels to get
the **pod and the timestamp**, then read around it:

```logql
{namespace="evidara", pod="di-consumer-b8d8fb5bb-2wzxj"}
```

---

## Cloud Logging (GCP Cloud Run deployments only)

The queries below use `jsonPayload.*` and apply to the Cloud Run deployments, not
to the Hetzner cluster. They have never been verified against a live project.

## Query 1: Trace a Run End-to-End

Find all log entries for a specific run across all three services:

```
jsonPayload.correlation_id="run_01jq7a3s9b7j4dndd9sgv6pb9d"
```

Add service filter to narrow:

```
jsonPayload.correlation_id="run_01jq7a3s9b7j4dndd9sgv6pb9d"
jsonPayload.service="di-consumer"
```

## Query 2: Find All Processing Failures (Transient)

Messages that failed and will be retried or have been dead-lettered:

```
jsonPayload.event="message_processing_failed"
jsonPayload.error_class="transient"
```

## Query 3: Find Permanent Rejections

Messages that were acked immediately because they are known-bad:

```
jsonPayload.event="message_rejected_permanent"
```

To see what error types are common:

```
jsonPayload.event="message_rejected_permanent"
-- Group by jsonPayload.error_type
```

## Query 4: Check Projection Outcomes

All projection events:

```
jsonPayload.service="legal-search"
jsonPayload.event=~"projection_.*"
```

Only failures:

```
jsonPayload.event="projection_apply_failed"
```

Only skipped (stale/duplicate):

```
jsonPayload.event="projection_skipped"
```

## Query 5: Platform-control Event Recording

Check if PC is successfully recording DI events:

```
jsonPayload.service="platform-control"
jsonPayload.event=~".*_recorded"
```

Find duplicates being recorded:

```
jsonPayload.service="platform-control"
jsonPayload.status="duplicate"
```

## Query 6: Correlate DI Processing to PC Recording

Trace a single event across DI → PC:

```
jsonPayload.event_id="evt_01jq7bhgy7g0pkj4f1d03f8f8c"
```

This should return two entries: `message_processed` from DI and `processing_status_recorded` from PC.

## Query 7: Slow Processing Detection

Find DI processing that took > 10 seconds:

```
jsonPayload.service="di-consumer"
jsonPayload.event="message_processed"
jsonPayload.duration_ms>10000
```

Find slow projection applies:

```
jsonPayload.service="legal-search"
jsonPayload.event="projection_applied"
jsonPayload.duration_ms>5000
```

## Query 8: DLQ-Related Investigation

After receiving a DLQ alert, find the original failures:

```
jsonPayload.event="message_processing_failed"
jsonPayload.delivery_attempt>"5"
```

Then cross-reference with the DLQ subscription:

```bash
gcloud pubsub subscriptions pull \
  document-intelligence-artifact-bundle-available-dlq-sub \
  --project=PROJECT_ID \
  --limit=5 \
  --auto-ack=false \
  --format=json
```

## Related Resources

- [Observability on the Hetzner cluster](../setup/hetzner-observability.md) — deploying
  the stack, and what it costs
- [ADR-0059](../adr/0059-an-event-is-a-fact-a-log-is-an-explanation.md) — why logs are
  aggregated at all, and the event-versus-log rule
- [DLQ triage and replay runbook](./dlq-triage-and-replay.md)
- [Document intelligence release gates](./document-intelligence-release-gates.md)
