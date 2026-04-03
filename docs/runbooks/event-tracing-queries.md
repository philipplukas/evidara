# Event Tracing — Cloud Logging Query Patterns

Owner: Platform team
Last reviewed: 2026-04-03
Applies to: dev, staging, prod

## Overview

All three services emit structured JSON logs with a shared field schema.
These queries let operators trace events end-to-end and diagnose failures.

### Field Reference

| Field | Description | Present in |
|-------|-------------|-----------|
| `event` | Log event name | All services |
| `service` | Service identifier | All services |
| `event_type` | Domain event type | All services |
| `event_id` | Unique event identifier | All services |
| `correlation_id` | Run ID that ties the flow together | All services |
| `run_id` | Explicit run ID from provenance | DI, PC |
| `message_id` | Pub/Sub message ID | DI consumer |
| `delivery_attempt` | Pub/Sub delivery attempt number | DI consumer |
| `status` | Outcome (inserted/duplicate/applied/stale/etc) | All services |
| `error_class` | permanent or transient | DI, LS |
| `error_type` | Exception class name | All services |
| `duration_ms` | Processing duration in milliseconds | All services |

---

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

- [DLQ triage and replay runbook](./dlq-triage-and-replay.md)
- [Document intelligence release gates](./document-intelligence-release-gates.md)
