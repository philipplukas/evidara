# Extraction Review Routing

Owner: Platform team  
Last reviewed: 2026-07-13  
Last verified: 2026-07-13 (ADR-0031 — Argilla removed; policy retained)  
Applies to: dev, staging (platform-control API + admin)

## Purpose

Define how platform-control routes uncertain extraction results to human review, and how an
operator's decision comes back.

This replaces `argilla-review-routing-and-sync.md`. The **routing policy below is unchanged** —
it is a good policy and it never depended on Argilla. What changed (ADR-0031) is the review
*surface*: the queue is the `review_tasks` table, read by `platform-control/admin`, not a hosted
annotation tool.

## Routing policy

Threshold defaults:

- `highThreshold = 0.90`
- `lowThreshold = 0.70`

| Record confidence | Routing |
|---|---|
| `>= 0.90` | Auto-accept. Route a **5% random audit sample** to review anyway. |
| `0.70 – 0.90` | Sampled review — **at least 20%**. |
| `< 0.70` | **Mandatory** review. |
| Any extractor conflict (`conflict=true`) | **Mandatory** review, independent of confidence. |

The audit sample on the auto-accept band is the part most easily dropped and most worth keeping:
it is the only signal that would catch a confidently-wrong extractor.

## The loop

1. **Route.** The extraction path calls `POST /v1/reviews/tasks` with a producer-supplied
   `external_id` (the dedupe key — unique, so re-routing the same record is a `409` rather than a
   second queue entry), the `wizard_run_id`, and the payload the reviewer needs to judge it.

   Persisting the task **is** the enqueue. There is no outbound push to a review tool; the queue
   is the table.

2. **Review.** An operator works the queue in `platform-control/admin`.

3. **Decide.** `POST /v1/reviews/tasks/{task_id}/decision` with `{"decision": ..., "reviewed_by": ...}`
   moves the task to `completed` and stores the verdict in `decision_payload`. A task that already
   carries a decision returns `409` — a second verdict never silently overwrites the first.

`GET /v1/reviews/tasks/{task_id}` reads one back.

## Verify the loop by hand

```bash
BASE=http://localhost:8080

TASK=$(curl -sS -X POST "$BASE/v1/reviews/tasks" -H 'content-type: application/json' -d '{
  "wizard_run_id": "wrn_...",
  "external_id": "rec-2026-07-13-001",
  "payload": {"fields": {"title": "Some decision"}, "metadata": {"recordConfidence": 0.66}}
}' | jq -r .review_task_id)

curl -sS -X POST "$BASE/v1/reviews/tasks/$TASK/decision" \
  -H 'content-type: application/json' \
  -d '{"decision": "accept", "reviewed_by": "you@evidara"}' | jq '.status, .decision_payload'
# => "completed"
```

## Draining a wizard run

`ReviewDrainWorkflow` gates a scaled wizard run until every `ReviewTask` for the run reaches a
terminal status (polling every 30 min, capped at 24 h). It no longer enqueues anything — it only
waits. Note the workflow only runs when a Temporal worker is deployed, and per ADR-0031 none is;
the review loop above works without it.

## History

Tasks were once also POSTed to a hosted Argilla instance, and reviewer outcomes were polled back
in batches via `POST /v1/reviews/sync-from-argilla`. That integration was deleted in ADR-0031: it
duplicated a review surface the admin app already provides, its client could very likely not talk
to a real argilla-server 2.x at all, and it swallowed every failure while reporting success
(#563). Argilla's real edge — multi-annotator agreement, dataset versioning — is for building ML
training sets, which is not the current need.

## Related

- ADR-0031: Disposition of Temporal, Argilla, and Firecrawl —
  `docs/adr/0031-temporal-argilla-firecrawl-disposition.md`
- [Platform Control component](../components/platform-control.md)
- [Platform Control API](../api/platform-control.md)
