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

## Wizard KPIs and SLOs

Track these in the same dashboard for wizard-enabled discovery/extraction runs.

### Workflow KPIs

- Lead time from `PilotRun` start to `FinalizePublish`.
- Percentage of runs blocked at `HumanGateApproval`.
- Retry count per 1,000 processed source nodes.

### Quality KPIs

- Field-level acceptance rate after review.
- Audit edit rate on auto-accepted records.
- Extractor conflict rate by source family.

### Review operations KPIs

- Review queue age (p50/p95).
- Review throughput (tasks per operator/day).
- End-to-end review sync lag from enqueue to applied decision.

### Initial SLO targets

- `RunCompletionSLO`: 95% of scheduled runs reach terminal state within 6 hours.
- `ReviewFreshnessSLO`: 90% of mandatory review tasks are resolved within 24 hours.
- `PublishQualitySLO`: critical-field audited error rate remains below 2%.
- `WorkflowAvailabilitySLO`: wizard and run-control endpoints maintain 99.5% monthly availability.

### Wizard-specific alert thresholds

- `run_stuck_state_minutes > 60`
- `mandatory_review_backlog > 1000`
- `critical_field_error_rate > 0.03` (rolling 24h)
- `drift_break_rate > 0.20` for any source family (rolling 7d)

## Drill-Down Workflow (Single Run)

When a panel degrades, use this sequence:

0. **Ask the run detail first, before any of the below.** The admin panel's run page
   (`/#/runs/{run_id}/show`) now answers, without a JSON payload:
   - **Was it refused?** A banner leads the page when the ADR-0030 two-key lock blocked the
     dispatch. Nothing was fetched; the remedy is a key on the blueprint template, not
     provider debugging. The run queue has a **Refused only** preset
     (`GET /v1/runs?refused=true`) for the same question across the queue.
   - **Why did nothing happen?** A named stall cause from the same vocabulary
     `evidara workflow coverage` prints — `no_dispatch_worker`, `publish_path_disabled`,
     `di_consumer_silent`, `projection_stalled`, `search_projection_pending`,
     `run_refused_by_lock`, `run_failed`. `publish_path_disabled` is the one that hides
     behind a *green* run, and `run_failed` quotes the run's own `failure_reason` rather
     than deriving a cause from stage state.

     Two of the outcomes are **not** findings and must not be actioned as one:
     `too_early_to_diagnose` (the run is still acquiring, so its downstream stages are
     pending by construction) and `unknown` (nothing matched, or pipeline health could not
     be read). Both are "no answer yet", not "nothing is wrong" — ADR-0052. Until #950 the
     first of those was reported as `projection_stalled`, which sent operators to debug a
     bridge that was not involved, and a failed run with a recorded reason was reported as
     `unknown`.
   - **Is the pipeline still moving, or did it stop?** `overall_status` answers this, and
     `stalled` is the value to read carefully (#951). It means the run itself ended but
     downstream stages never reported, and — unlike `in_progress` — that nothing further
     is scheduled, so no amount of waiting changes it. Pair it with the stall cause above:
     `stalled` says *that* the pipeline stopped, `projection_stalled` /
     `publish_path_disabled` say *where*.

     A completed run does **not** immediately become `stalled`. Acquisition finishing is
     not the pipeline finishing — DI, projection and search land afterwards, and measured
     against production on 2026-09-19 that lag reached 5h58m on the largest run. Only
     after 24h does the run report `stalled`; before that it is honestly `in_progress`.
   - **What did it capture, publish and refuse?** A capture ledger with `captured` and
     `published` as separate numbers, the per-resource refusal slugs grouped by reason, and
     the mirror-fidelity spot check. Anything the provider did not record renders as `—`,
     never as `0`.
   - **Does it justify flipping the key?** The ADR-0030 acceptance verdict, with the
     `execution_mode` joined from the source version. `skipped_gates` and `environment` are
     shown as **unavailable**, because the harness writes them into a bundle under
     `docs/runbooks/evidence/` that no runtime serves — treat them as unverified, never as
     passed.

   Two things the panel still cannot tell you: **quarantined documents** (ADR-0047 records
   them on the DI-owned processing-manifest surface and emits no further status event, and
   platform-control's `ProcessingStatus` has no `quarantined` member — so a clean DI
   Processing Status list is *not* evidence that nothing was withheld), and **who** attempted
   a refused dispatch (ADR-0035 records what and why, not who).

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

- Dashboard shows healthy run success rate
- p95 latency within expected bounds
- No unexplained spike in duplicate events
- No canary source version is stale
- Drill-down path works for at least one recent run

## Related

- [Scraping QA Standard](../testing/scraping-qa-standard.md)
- [Scraping Nightly Canary](scraping-nightly-canary.md)
- [Event Tracing Queries](event-tracing-queries.md)
