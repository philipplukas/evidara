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
- If the failure matches a **currently open** issue, call that out explicitly so the user knows it's a tracked blocker vs. new breakage. Confirm the issue is open (`gh issue view <n> --json state`) before citing it: this command used to name #274 and #278 as the standing examples and both have since been closed, so a failure attributed to either is new breakage, not a tracked blocker.

## 3. Map surfaces → gates

**The gate table lives in `CLAUDE.md` under "Per-surface quality gates". Read it there —
do not run a gate from memory, and do not copy the table into this file.**

This command used to carry its own copy. It drifted: it told you to run
`cd platform-control && uv run pytest` (narrower than CI — it skips ruff, the OpenAPI
contract-drift gate and the admin gate) and `cd legal-search/api && npm test` (narrower
than `npm run check`), and it had no row at all for `document-intelligence/`,
`marketing/`, `tools/evidara-cli/`, `eval/`, `scripts/`, the e2e spec-coverage gate, or
the `contracts/` manifest version bump. A third copy of a table is how this drifts;
`CLAUDE.md` is the source of truth and gains rows the moment CI does.

So:

1. Read the gate table out of `CLAUDE.md` in this repo, at the commit you are checking.
2. From `gh pr diff $1 --name-only`, dedupe path prefixes and match each against that table.
3. Report the gates that apply. Run **only** those whose surface the PR actually touches —
   do not run a gate for an untouched surface.
4. Reproduce each gate command **verbatim** from `CLAUDE.md`, including its caveats.
   Several rows carry an env var or flag that is load-bearing (`CI=true` for
   document-intelligence, `--with pyyaml` for `scripts/`, `--country` for the overlay
   checker); dropping one makes the run report green over a smaller suite than CI runs.
5. If a PR touches `contracts/api/` or `contracts/events/`, the manifest version-bump
   gate applies **in addition** to any component gate — it is not covered by
   `check-platform-control.sh`.
6. JS surfaces need Node 22 (`.nvmrc`). `ExperimentalWarning: localStorage is not
   available` in the output means the wrong Node and the run is not evidence.

If a surface in the diff has no row in `CLAUDE.md`'s table, say so rather than inventing
a command — an invented gate is worse than an admitted gap.

## 4. Label & state sanity

- Check labels from step 1. Flag if missing both a `state:*` and a `role:*` label, so an agent picking the PR up has the routing it expects. (This step used to cite `memory/project_pr_workflow.md`; no such file exists in the repo or in the project memory directory.)
- If `mergeStateStatus` is `UNSTABLE` or `BLOCKED` but all required checks are green, surface that the branch is behind `main` and suggest rebase.

## 5. Report

Emit a concise verdict:
- **READY** — all required checks green, mergeable clean, required labels present.
- **BLOCKED by known issue #N** — failing check attributed to a tracked issue.
- **NEEDS REBASE** — conflicts or behind main.
- **NEEDS LABEL** — missing `state:*` / `role:*`.
- **BLOCKED by new breakage** — failing check with no tracked issue → link the failing job URL.

Do **not** run `gh pr merge`. Reporting only.
