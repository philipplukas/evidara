# Agent workflows (multi-agent orchestration scripts)

The other two documents in this directory describe how **people** parallelise work across this
monorepo: which streams can move at once, and which artifacts are single-owner seams. This one
describes how **agents** do the same thing, and — more importantly — the constraints that carry
over unchanged.

The scripts live in [`.claude/workflows/`](../../.claude/workflows/README.md). That README is the
catalogue; this page is the process view.

## Why they exist

Two shapes of work in this repo are worth orchestrating rather than doing linearly.

**Verification.** Given a change, is it right? Running five review dimensions in parallel and then
re-deriving each finding with a different agent catches a class of defect that reading a diff does
not. Every finding that mattered was found by re-running something, never by reading: a feature
that could be deleted entirely with all 286 tests still passing; a deny-assertion that probed a
nonexistent key and so could never fail; an operator kill-switch that could be flipped with
`exit 0`; a change that would have duplicated the federal corpus at every future consolidation. All
four sat in PRs whose own gates were fully green.

**Discovery.** Given a surface, what is weak? Same backbone, opposite input. This repo's culture is
evidence or silence, so a discovery workflow that returns "add more tests" or "consider extracting a
helper" is worse than one that returns nothing — it costs a reader the review and teaches them to
skip the next report. Three rules in every discovery script prevent that: each finding is anchored
to a re-derivable fact (a `file:line`, a measured number, a reproduced behaviour, a mutation that
did not turn a test red), an adversarial stage tries to refute it, and the output is ranked and
capped rather than exhaustive.

## The serialization rules apply to agents too

These are the same seams as
[Max parallel execution § Serialization gates](max-parallel-execution.md), and a workflow is not
exempt from them just because it finishes in ten minutes:

| Seam | Rule for a workflow |
|---|---|
| Same OpenAPI file | One agent per run may regenerate `contracts/api/platform-control.openapi.yaml`. It is generated from the FastAPI app (ADR-0034), so a second regenerating agent is a write race, not a second opinion. |
| Same Alembic migration batch | No workflow in the catalogue authors a migration. |
| Same GitHub Actions workflow file | No workflow in the catalogue edits `.github/`. |
| Cross-service behavior | Contract or event shape first, then parallel implementation — unchanged. |

There is one rule that is specific to agents, and it is the one that bites first:

> **A stage that mutates the working tree must never run concurrently with a stage that reads it.**

Ten agents sharing one checkout is not ten lanes; it is one lane with ten writers. Where a workflow
needs both, the mutating stage is either serialized after the parallel one
(`cross-surface-gate-sweep.js` runs generate-then-diff gates last, one at a time) or isolated in a
throwaway git worktree (`guard-efficacy-mutation.js`). For the same reason: **do not run two
workflows at once in the same checkout.**

## The gate table is the contract

Several workflows run per-surface gates. They use the table in
[`CLAUDE.md` § Per-surface quality gates](../../CLAUDE.md), which is the CI-equivalent set, and they
report `PASS` / `FAIL` / `DID-NOT-RUN` as three distinct outcomes. That third outcome is the point:
a gate that fell over during setup did not pass, and this repo has a documented collection of ways
a gate's result misreports what it actually did:

- the wrong Node major, which makes every Vitest result dishonest while still exiting 0;
- a missing `pyyaml` reporting `Ran 144 tests ... FAILED (errors=11)` when the suite is 201, so
  57 tests that never ran read as 11 that broke;
- missing `document-intelligence` extras dropping a whole test module at collection;
- an absent Docker daemon skipping the only layer that meets a real index mapping;
- `scripts/check-platform-control.sh` wrapping its entire admin half in
  `if [[ -f admin/package.json ]]` (`:18`), which skips it **silently** and still exits 0;
- `scripts/check_country_overlay_files.py` exiting 2 on argparse when its required `--country` is
  omitted, having checked nothing.

The counter-example is worth stating too, because it is the shape to aim for: missing
`platform-control/admin/node_modules` in a fresh worktree used to be one of these, and is not any
more — `check-platform-control.sh:36-42` detects it, prints the checkout path and the exact
`npm ci` remedy, and exits non-zero. A gate that cannot run should say so loudly; the workflows
exist for the ones that do not.

Note that [`.claude/commands/merge-readiness.md`](../../.claude/commands/merge-readiness.md) carries
an **older, narrower** gate table — it prescribes `cd platform-control && uv run pytest`, which
`CLAUDE.md` explicitly calls narrower than CI. The workflows use the `CLAUDE.md` table and report
the disagreement rather than silently preferring one. If you update one table, update the other;
the same "add a check to one, add it to the other" rule that governs pre-commit and CI applies here.

## Boundaries a workflow does not cross

Encoded in every script, and stated in
[`.claude/workflows/_house-rules.md`](../../.claude/workflows/_house-rules.md):

- No crawler, fetcher or browser is pointed at a **public-sector host**. LexFind's terms were never
  confirmed with the Schweizerische Staatsschreiberkonferenz.
- No **acquisition run** is dispatched, in any mode.
- No **config key** is flipped. `enabled: true` on a blueprint template is the operator's act under
  ADR-0030, turned against captured acceptance evidence; a provider's `readiness` is the code key.
  Neither is an agent's to turn.
- No PR is merged or commented on, nothing is pushed, no branch is deleted.
- Nothing shaped like the MCP server is built (ADR-0033 §4).

A workflow that reaches one of these stops and produces a **decision memo** naming what a human must
decide. `cantonal-onboarding-dry-run.js` is built entirely around that pattern: it drafts and
validates blueprint templates for the cantons that have none, and its expected output for most of
them is a precise blocker. The `entity_ids` value used to be one: it was derivable from this repo
for exactly three cantons, and inventing a plausible one produces a template that runs against the
wrong canton and looks like it worked. `coverage scaffold` now reads it from LexFind's published
entity table and refuses on no match or an ambiguous one, so the remaining blocker per canton is
the acceptance run, not the number.

## Status

**None of these scripts has been executed.** They are syntax-checked
(`bash .claude/workflows/check-syntax.sh`) and reviewed. Treat a first run as one to supervise.

## Related

- The catalogue, with per-script cost and "when not to use it":
  [`.claude/workflows/README.md`](../../.claude/workflows/README.md)
- Shared prompt conventions: [`.claude/workflows/_house-rules.md`](../../.claude/workflows/_house-rules.md)
- [Parallel work streams (by component)](parallel-work-streams.md)
- [Max parallel execution](max-parallel-execution.md)
- Change classification and required sync checks: [AGENTS.md](../../AGENTS.md)
