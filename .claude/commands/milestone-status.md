---
description: Summarize status of one roadmap milestone — issues, open PRs, blockers, next action
argument-hint: <M1|M2|M3|M4|M5|M6>
---

Summarize the state of milestone **$1** from the #279 roadmap.

## 1. Resolve milestone → issues

Hard-coded mapping (source: issue #279, handover #281):

| Milestone | Target | Issues |
|---|---|---|
| M1 | 2026-04-25 | #274, #278 |
| M2 | 2026-04-30 | #253 |
| M3 | 2026-05-09 | #264, #258 |
| M4 | 2026-05-23 | #259, #260 |
| M5 | 2026-06-13 | #270, #271, #272, #273 |
| M6 | backlog | #277 |

If `$1` doesn't match M1–M6, stop and ask the user.

## 2. Fetch state in parallel

For each issue in the milestone, run `gh issue view <N> --json state,title,labels,comments`.

Also run `gh pr list --state open --search "in:title,body #<N>" --json number,title,labels,mergeable,statusCheckRollup` once per issue to find in-flight PRs.

## 3. Per-issue row

Render a short table:

| Issue | Title | State | In-flight PR | Blockers |
|---|---|---|---|---|
| #274 | … | triage | — | — |
| #278 | … | triage | #285 (UNSTABLE) | #274 failing image build |

For the "Blockers" column, infer from failing checks + the memory in `project_pr_workflow.md`. Do not speculate — only cite what's present in the fetched data.

## 4. Sequencing reminders

Cite the sequencing rule from #279 / #281 for this milestone if any:
- **M3**: #264 must merge before #258.
- **M5**: #270 → #271; then #272 ‖ #273.
- **M1**: #274 first (unblocks #266).
- **M4**: serial, either order.

## 5. Recommended next action

Exactly one sentence. Examples:
- "Start #274 — blocks #266 + the rest of M1."
- "Wait on #264 review — #258 is ready but gated."
- "Nothing on deck for M6; defer per #279."

Do not auto-assign, auto-label, or open issues/PRs. Reporting only.
