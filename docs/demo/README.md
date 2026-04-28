# Demo readiness

Status: **Scaffolding only — content TBD.** Three documents in this folder support a ≤ 2-week investor / strategic / prospect demo against the existing 12-document Swiss-federal-law corpus on prod. The narrative copy and final query selection belong to the demo presenter.

| Doc | What it is | Owner |
|---|---|---|
| [`script.md`](script.md) | The narrative — queries, deep-dive doc, 3-min and 10-min variants, mixed-audience framing | Presenter |
| [`detail-view-audit.md`](detail-view-audit.md) | Per-document trust-signal checklist; run before T-7 against the deep-dive doc | Demo engineer |
| [`failover.md`](failover.md) | Recorded-webm fallback + failover triggers | Demo engineer |

Engineering scaffold — see [`legal-search/frontend/e2e/demo-queries.spec.ts`](../../legal-search/frontend/e2e/demo-queries.spec.ts) (separate PR) — pins the rehearsed queries with assertions so they cannot silently regress before the demo.

## Why these exist

[`docs/runbooks/phase-5-go-no-go-memo.md`](../runbooks/phase-5-go-no-go-memo.md) covers engineering release-readiness (signed off 2026-04-21). [`docs/runbooks/interaction-flow-validation.md`](../runbooks/interaction-flow-validation.md) covers acceptance journeys. Neither is a *demo plan*. This folder is the missing seam.

## Anti-scope

Same as the parent plan: no new content jurisdictions, no new search capability, no design-system migration, no contract / wire changes. The 2-week budget is for risk reduction on the existing surface.
