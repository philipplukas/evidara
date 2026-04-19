---
description: Triage all open PRs — flag stale, unlabeled, conflicting, or check-failing PRs for decision
---

Produce a short triage list of all open PRs that need human attention. Do **not** close, label, or merge automatically.

## 1. Fetch all open PRs

`gh pr list --state open --limit 50 --json number,title,author,createdAt,updatedAt,isDraft,headRefName,labels,mergeable,statusCheckRollup`

## 2. Bucket each PR

Classify into exactly one bucket (prefer higher bucket on ties):

1. **Stale & conflicting** — `mergeable == CONFLICTING` AND last update > 5 days ago → likely abandon.
2. **Stale & no state label** — no `state:*` label AND last update > 5 days ago → needs decision (ship or close).
3. **Blocked by tracked issue** — failing check attributable to an open issue in `memory/project_pr_workflow.md` (e.g. platform-control image build → #274).
4. **Blocked by new breakage** — failing check, no tracked issue → new problem.
5. **Ready for review** — all checks green, `state:review`.
6. **In QA** — `state:qa`, checks green.
7. **Draft** — `isDraft == true` → ignore unless > 7 days old.

## 3. Report

One line per PR in each bucket. Include the number (linked), title (first 50 chars), last-updated (relative), and the reason.

End with a **Recommendations** section listing:
- PRs you'd propose closing (bucket 1) — but do not close them.
- PRs the user should rebase or relabel.
- PRs ready to merge (bucket 5 + 6 with all green).

Explicitly do not run `gh pr close`, `gh pr edit --add-label`, or `gh pr merge`. This command is read-only.
