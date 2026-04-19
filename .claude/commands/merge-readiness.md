---
description: Check whether a PR is ready to merge — runs narrowest surface gates + check rollup
argument-hint: <pr-number>
---

Report merge readiness for PR **#$1** against the evidara quality bar. Do not merge automatically. Surface findings and wait for a human decision.

## 1. Fetch PR state

Run these in parallel:

- `gh pr view $1 --json number,title,state,isDraft,mergeable,mergeStateStatus,reviewDecision,headRefName,labels,additions,deletions`
- `gh pr view $1 --json statusCheckRollup --jq '.statusCheckRollup[] | {name, conclusion: (.conclusion // .state), url: (.detailsUrl // .targetUrl)}'`
- `gh pr diff $1 --name-only` — to detect changed surfaces

## 2. Classify each failing/pending check

For every check where `conclusion` is not `SUCCESS`, `NEUTRAL`, or `SKIPPED`:
- Quote the check name, conclusion, and URL.
- If the failure matches a known open issue (e.g. platform-control image builds → #274, temporal-test-server 403 → #278), call that out explicitly so the user knows it's a tracked blocker vs. new breakage.

## 3. Map surfaces → gates

From `gh pr diff $1 --name-only`, dedupe path prefixes and map to the gate table:

| Prefix | Gate |
|---|---|
| `platform-control/admin/` | `cd platform-control/admin && npm run check` |
| `platform-control/` (non-admin) | `cd platform-control && uv run pytest` |
| `legal-search/api/` | `cd legal-search/api && npm test` |
| `legal-search/frontend/` | `cd legal-search/frontend && npm run check` |
| `country-overlays/` or `platform-control/seeds/` | `python scripts/check_country_overlay_files.py` |
| scraping-touching | `bash scripts/check-scraping-qa.sh` |

Do **not** run a gate if nothing in its surface changed. List the gates that would apply, but only execute those whose surface is actually touched.

## 4. Label & state sanity

- Check labels from step 1. Flag if missing both a `state:*` and a `role:*` label — rocky-agents won't pick it up without them (see `memory/project_pr_workflow.md`).
- If `mergeStateStatus` is `UNSTABLE` or `BLOCKED` but all required checks are green, surface that the branch is behind `main` and suggest rebase.

## 5. Report

Emit a concise verdict:
- **READY** — all required checks green, mergeable clean, required labels present.
- **BLOCKED by known issue #N** — failing check attributed to a tracked issue.
- **NEEDS REBASE** — conflicts or behind main.
- **NEEDS LABEL** — missing `state:*` / `role:*`.
- **BLOCKED by new breakage** — failing check with no tracked issue → link the failing job URL.

Do **not** run `gh pr merge`. Reporting only.
