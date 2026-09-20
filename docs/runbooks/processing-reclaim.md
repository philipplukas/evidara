# Processing reclaim — terminating documents that never came out

Owner: Platform team  
Last reviewed: 2026-09-20  
Last verified: 2026-09-20 (#1045 — the 116 were quarantines; see below)  
Applies to: the Hetzner k3s cluster (`evidara` namespace)

## What this is for

`processing_status_updates` records a document's journey through
document-intelligence. Until #1038 it had no way to say *this one stopped*. The
status `processing` meant both **in flight** and **the worker died holding
this**, and nothing in the stack distinguished them.

Measured against production on 2026-09-19:

| | |
|---|---|
| Documents with no terminal status | **116** |
| Runs holding them | `run_01m26a84j0gdmeh9g5f8b1k36k` (58, from 2026-09-10), `run_01m2q5fsqmarc3mxvfpsw1jjdt` (58, from 2026-09-17) |
| Status both runs report | `completed` |
| Oldest stranded row | 2026-09-10 18:49:37Z — 8d22h |
| Rows ever written with an `error_code` | 0 |
| Documents known to platform-control | 1,901 |
| Documents in the search index | 1,785 = 1,901 − 116 |

The arithmetic closing exactly is what makes this a silent loss rather than a
backlog: the documents are absent from search and nothing said so.

Those counts are **documents**. Counted as processing *units*
(`processing_manifest_id`, which is what the reconciler and the sweep both key on)
the same population is **117**, split 58 / 59 — one document was attempted twice.
Re-measured 2026-09-20 and unchanged since; nothing new has stranded.

## The two halves

**The reclaim sweep** writes the terminal status. It runs as a CronJob
(`infra/hetzner/apps/processing-reclaim-cronjob.yaml`, hourly at :20) and invokes
the `platform-control-processing-reclaim` console script. A unit that has held no
terminal status for longer than the deadline (24h by default) gets a `failed` row
with `error_code=processing_deadline_exceeded`.

It runs in the control plane, on a clock, deliberately: a `finally:` in the
consumer cannot close this hole because the consumer is what dies.

**The reconciler** reports the gap. `GET /v1/runs/{run_id}/pipeline-health`
carries a `processing_reconciliation` block — units started, units finished, units
stranded, and a verdict — and the `document_intelligence` stage can no longer
report `ok` while any unit is unterminated. Before #1038 that stage was resolved
from the run's single newest status row, so a run whose newest row was a
`canonical_ready` read as healthy while holding 58 documents that nothing
downstream had ever seen.

## Reading the verdict

| Verdict | Meaning | Action |
|---|---|---|
| `reconciled` | Every unit the run started reached a terminal status. | None. |
| `unterminated` | At least one unit started and never finished. | Check `unterminated_units_past_deadline`: non-zero means the sweep will terminate them on its next pass, zero means the run is still legitimately in flight. |
| `nothing_observed` | The run has no processing rows at all. | **Not a pass.** A run that published bundle events and produced no status row is a worker that died before it said anything. Check the DI consumer for restarts and the DLQ. |

## The one-off backfill

Documents stranded before the CronJob was deployed are reclaimed by it like any
others — the sweep has no cutoff. Run it deliberately if you want it now, with
the dry run first:

```bash
# Report only. This is the default; the script refuses to write without --apply.
scripts/reclaim-stuck-processing.sh

# One run at a time, to stage it.
scripts/reclaim-stuck-processing.sh --run-id run_01m26a84j0gdmeh9g5f8b1k36k --apply
scripts/reclaim-stuck-processing.sh --run-id run_01m2q5fsqmarc3mxvfpsw1jjdt --apply

# Everything.
scripts/reclaim-stuck-processing.sh --apply
```

The sweep runs inside the platform-control pod, which already holds the database
credentials; no secret is materialised on the workstation. `pc processing reclaim`
is the same implementation for anyone already in a shell with the environment.

## What the reclaimed row claims, and what it refuses to

Read `failed` / `processing_deadline_exceeded` as **the control plane stopped
waiting** — never as *document-intelligence reported a failure*. DI reported
nothing, which is the problem. The `error_summary` says so in words and names the
last status it saw and when.

The cause is genuinely not known from the control plane. At least three are live
candidates:

- the worker died mid-document (#1012's OOM, since fixed);
- the status event was published and lost;
- DI made a terminal decision it never published. Until #1045, ADR-0047's quarantine
  path emitted `accepted` and `processing` and then stopped, so a quarantined
  document left exactly this fingerprint.

**The third one was the answer, and it is now fixed at the source.** Measured
2026-09-20, before #1045 shipped: all 117 stranded units had a `quarantined` row in
DI's own `processing_manifests` table — the two sets are equal, not overlapping —
every one of them `below_content_floor`. They were refusals the control plane was
never told about. #1045 makes the quarantine path emit a terminal `quarantined`
status carrying the ADR-0047 reason slug as `error_code`, so from that deploy
onwards a refusal reconciles as `reconciled` and the sweep sees only genuine
silence.

`withdrawn` and `skipped_duplicate` are still declared in `ProcessingStatus` and in
`contracts/events/document-processing-status-updated.schema.json` with nothing
emitting them; `document-intelligence/src/document_intelligence/events/status_updated.py`
carries the register and `tests/test_status_producers.py` fails if a new status
joins them silently.

### The 117 already in the table

They predate the fix, so they still hold `{accepted, processing}`, and the sweep —
`scripts/reclaim-stuck-processing.sh`, above — would stamp them `failed` /
`processing_deadline_exceeded`. That row is honest about *who wrote it* and wrong
about the cause, which we now know: they were quarantined.

There is **no quarantine backfill tool**, and this runbook does not pretend
otherwise. The operator has two options and they are not equivalent:

1. Reclaim them as `failed` / `processing_deadline_exceeded` anyway. Cheap, and it
   ends the silence, but it files 117 refusals under a deadline slug and
   `/v1/acquisition-coverage` will still report `quarantined_documents: 0` for
   `jur_ch_zh`.
2. Write the 117 `quarantined` rows from DI's `processing_manifests` table, where
   the reason slug and evidence already sit, then let the sweep run. The join key is
   `processing_manifest_id`; the two sets were verified equal on 2026-09-20.

Option 2 is what makes the counter true. Until one of them is done the sweep stays
suspended, because its first pass forecloses option 2.

## A reclaimed document is not a recovered one

The sweep makes a stranded document **visible**. It does not put it in the corpus.
Getting it there is a replay — `scripts/replay-nats-dlq.sh` when the event is in
the DLQ, or a fresh acquisition run — and that is a separate decision.

## Verify it ran

```bash
kubectl -n evidara get cronjob platform-control-processing-reclaim
kubectl -n evidara logs job/<latest> | tail -1
```

The summary line is one row:

```
processing reclaim: deadline_hours=24 units_examined=0 units_past_deadline=0 \
  units_reclaimed=0 duplicates=0 runs_touched=0
```

`units_examined=0` on a healthy estate is the expected reading, and it is
distinguishable from the job not having run at all — which is why
`failedJobsHistoryLimit` is 5 and the Job exits non-zero on failure.

`platform_control_processing_units_reclaimed_total` is the Prometheus counter. It
is not a pipeline error rate: it is the rate at which document-intelligence stops
reporting on work it accepted.
