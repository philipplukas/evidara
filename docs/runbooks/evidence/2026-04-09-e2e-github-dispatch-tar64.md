# TAR-64 — two GitHub Actions E2E Smoke Dev dispatches (2026-04-09)

Dispatched via `gh workflow run "E2E Smoke Dev"` against `philipplukas/evidara`.

| Run | URL | Outcome (at capture) |
|-----|-----|----------------------|
| 1 | [24204759149](https://github.com/philipplukas/evidara/actions/runs/24204759149) | **failure** — step 7 timed out waiting for DI `canonical_ready` + `document.processed` (see uploaded log artifact) |
| 2 | [24204762875](https://github.com/philipplukas/evidara/actions/runs/24204762875) | **failure** — same class of failure expected (parallel dispatch) |

## Follow-ups

1. **Infra:** Debug Pub/Sub → DI → platform-control using **Strategic phases** in [m5-evidence-checklist.md](../m5-evidence-checklist.md#strategic-phases) (what “green” means, flow diagram, phases A–D, quick-reference table, plus the detailed numbered checklist below it).
2. **Workflow:** `Summarize smoke result` used `python`; self-hosted runner only had `python3` — fixed in [e2e-smoke-dev.yml](https://github.com/philipplukas/evidara/blob/main/.github/workflows/e2e-smoke-dev.yml) (and staging workflow). **Re-dispatch** after merge for a clean summary step.

**Definition of done for TAR-64:** two **green** runs with logs attached; these URLs are evidence of **attempts** until the pipeline is green.
