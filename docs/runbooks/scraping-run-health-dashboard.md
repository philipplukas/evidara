# Scraping Run Health Dashboard & Drill-Down

Owner: Platform team
Last reviewed: 2026-04-05
Last verified: Not yet verified
Applies to: dev, staging, prod

## Purpose

Define the minimum dashboard and run drill-down workflow for scraping/acquisition confidence.

This runbook is intentionally small-team friendly: it focuses on a short list of high-signal metrics and repeatable triage queries.

## Dashboard Panels (Minimum Set)

## 1) Run Success Rate

**What:** Percent of runs that end in `completed` vs `failed`/`cancelled` over the last 24 hours.

**Why:** First indicator of acquisition health regression.

## 2) Run Latency p50 / p95

**What:** Duration from run creation to terminal state.

**Why:** Detects provider slowness, worker backlog, and callback delays.

## 3) Error Category Breakdown

**What:** Count by error category (timeout, upstream_4xx/5xx, webhook_validation, parsing_mismatch, empty_output).

**Why:** Helps prioritize fixes quickly and avoid generic “something is failing” alerts.

## 4) Last Successful Run by Source Version

**What:** Latest successful timestamp grouped by `source_version_id`.

**Why:** Catches silent source outages and stale source versions.

## 5) Duplicate Delivery / Idempotency Counter

**What:** Count of duplicate webhook receipts and duplicate event recordings.

**Why:** Ensures idempotency protections are actually active.

## 6) Artifact Volume Distribution

**What:** Captured-resource and raw-artifact counts per run (p50/p95 and outliers).

**Why:** Detects discovery regressions and accidental over-crawling.

## Suggested Alert Thresholds

Start with conservative thresholds and tune after one week of baseline data:

- run success rate < 95% over 30 minutes
- run latency p95 > 15 minutes over 30 minutes
- duplicate/idempotency count spikes > 3x rolling 7-day median
- source version without success for > 24 hours (if expected daily)

## Drill-Down Workflow (Single Run)

When a panel degrades, use this sequence:

1. Pick one affected `run_id`.
2. Pull run details from platform-control API (`/v1/runs/{run_id}`).
3. Trace correlated logs using `correlation_id=run_id` in Cloud Logging.
4. Inspect webhook receipts and provider job status.
5. Validate artifact and bundle-manifest outputs.
6. Confirm downstream handoff signal (`artifact_bundle.available`) was emitted.

## Copy/Paste Query Patterns

### A) End-to-end run trace

```
jsonPayload.correlation_id="run_<id>"
```

### B) Scraping failures

```
jsonPayload.service="platform-control"
severity>=ERROR
```

### C) Duplicate/idempotency signals

```
jsonPayload.service="platform-control"
jsonPayload.status="duplicate"
```

### D) Slow run processing events

```
jsonPayload.service="platform-control"
jsonPayload.duration_ms>10000
```

## Operator Checklist

- [ ] Dashboard shows healthy run success rate
- [ ] p95 latency within expected bounds
- [ ] No unexplained spike in duplicate events
- [ ] No canary source version is stale
- [ ] Drill-down path works for at least one recent run

## Related

- [Scraping QA Standard](../testing/scraping-qa-standard.md)
- [Scraping Nightly Canary](scraping-nightly-canary.md)
- [Event Tracing Queries](event-tracing-queries.md)
