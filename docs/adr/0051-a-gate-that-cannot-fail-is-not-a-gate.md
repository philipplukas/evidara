# ADR-0051: A gate that cannot fail is not a gate

## Status

Proposed

## Date

2026-09-03

## Context

ADR-0040 sorted untrustworthy green runs into three causes and closed with an admission:

> No guard exists for section C in general. Assertion strength is currently enforced by
> review alone, and review is exactly what missed `toBeGreaterThanOrEqual(1)`. A
> mutation-testing spike on the narrowest high-value surface is the obvious probe; nothing
> is scheduled.

ADR-0048 added the adjacent case — *"a gate that never runs is the same as no gate"* — after
the mapping drift comparator sat unrun against production for months.

The spike happened, unscheduled, on 2026-09-03, and this ADR is its result. The case it
turns up is the one neither ADR covers: a gate that **runs**, is **green**, and **cannot go
red**.

### Seven of them, all from one day, all in green PRs

1. **A deny probe against an object that does not exist.** ADR-0049 §3 records it in its own
   words: the first `verify-minio-scoping.sh` probed an absent key, so `NoSuchKey` satisfied
   every `expect=deny` assertion unconditionally. The same ADR names the second half — a
   write-deny probe placed *outside* the account's granted prefix is denied for the prefix,
   not for the permission, so it proves nothing about the permission it is cited for.

2. **A refusal keyed off a priority-ordered value.** `evidara workflow coverage enable`
   shipped a kill-switch guard that read `template["blocker"]`, a single value
   `classify_template` computes by priority. `provider_scaffold` outranks
   `template_disabled_by_operator`, so for a scaffold provider the closed key never
   surfaced and the refusal never fired — and `scaffold` is the server's fail-closed default
   for any provider the registry cannot resolve, so a fail-closed server signal became a
   client-side fail-open. Caught in review of #832, fixed before merge, and the reason is
   now a docstring at `tools/evidara-cli/src/evidara_cli/coverage.py:515-521`.

3. **A gate that abstains by construction.** `assess_legal_text_density`
   (`platform-control/src/acquisition_core/content_gate.py:91-120`) returns
   `is_legal_text=True, marker_count=0` for any `content_type` outside
   `_ASSESSABLE_CONTENT_TYPES` (`:56-58`). `application/pdf` is not in that set. The
   abstention is deliberate and documented — and it is returned in the same field, with the
   same value, as a pass. On every PDF the legal-text floor cannot fail. (#862, open, widens
   the wiring to nine providers; it does not change the abstention.)

4. **A guard that cannot fire in the gate documented to run it.** `scripts/ci_skip_guard.py:61-63`
   reads `os.environ["CI"]`; neither `scripts/check-platform-control.sh` nor
   `scripts/check-document-intelligence.sh` sets it, so no local invocation of the documented
   gate can fire the guard, in any combination of extras. #840 ran `461 passed, 11 skipped`,
   `ruff` clean, and `exit 1` in CI. #863 (merged 2026-09-03) took the second option in
   commitment 4 below — the guard still cannot fire from those scripts, and the `CLAUDE.md`
   gate table now says so and tells the reader to prefix `CI=true`.

5. **A test whose interleaving was on the wrong side of the guard.** Reported in the review
   of #844: the first attempt at the lost-approval race committed the concurrent expiry
   *before* calling `approve_run`, and **passed on the unfixed code**, because SQLAlchemy
   refreshed the guard's read. The window only exists after the guard. A test can reproduce
   the wrong window and read exactly like one that reproduces the right one.

6. **A feature deletable with 286 tests green**, and **a deny-assertion that could never
   fail** — both found by systematically deleting guard predicates and observing what
   noticed (`.claude/workflows/README.md:207-208`).

7. **A claim of enforcement that was real but at the wrong granularity.** ADR-0049's CI guard
   was *"real but bucket-granular rather than per-item"* (`.claude/workflows/README.md:170-172`):
   granting `s3:PutObject` on `evidara-lakehouse/canonical/*` to a read-only account changes
   no bucket set, so bucket-set equality would have passed it. ADR-0049 §4 now requires the
   guard to assert buckets, actions *and* object prefix. A claim that reads as covered is
   worse than no claim, because it stops anyone looking.

### What separates these from ADR-0040's cases

ADR-0040's three causes are all about the *run*: what it touched, whether it happened, how
loudly it asserted. These are about the *guard's own predicate*. Every one of them passes
every check ADR-0040 proposes — isolated run, reachable by a CI job, assertion present and
specific — and still asserts nothing, because the condition it tests is satisfied for a
reason unrelated to the property it is cited for.

There is exactly one way to tell the difference, and this repo has now used it repeatedly.

### The counter-practice already works here

| Change | Mutation | Result |
|---|---|---|
| #864 | each of 21 refusals removed one at a time | 21 killed; e.g. `evidence_run_is_not_acceptance_evidence` → 6 failed, 57 passed |
| #834 | delete the CAS predicate `WizardRun.progress_version == version` | Postgres test `assert 2 == 12` — 10 of 12 concurrent shard reports lost |
| #858 | drop the run-status guard on publication | `assert ['art_01m1kjg…'] == []`; the over-broad variant fails 6 |
| #840 | revert the source fix | `test_dry_run_exits_zero_every_time` red — and `test_real_run_exits_zero_every_time` stays green, with a docstring saying so rather than implying it caught something |

The last row is the one worth noticing. Mutation does not only prove a test works; it tells
you which of your tests is decoration, and #840 wrote that down instead of taking credit for
it.

## Decision

**A guard is not shipped until it has been observed failing.** Four commitments.

1. **Every guard ships with a mutation record.** The predicate deleted or inverted, the named
   test that turns red, and the counts. It goes in the PR body — the form this repo already
   uses — and it is a review item, not an optional flourish. This makes ADR-0040's
   "self-tested in both directions" a specific, cheap procedure rather than an aspiration:
   the cost of one mutation is one gate run.

2. **Prefer a guard that cannot abstain; where it must, abstention is a third outcome.**
   `assess_legal_text_density` folds "I did not inspect this" into `is_legal_text=True`,
   which every caller reads as a pass. The correct shape is a verdict a caller must handle
   — `not_assessed` beside `pass` and `fail` — so that adding a format the gate cannot read
   is a compile-or-review event rather than a silent widening of what the gate approves.
   ADR-0030 §5 already applies this reasoning to the acceptance harness's skipped gates
   ("treat a skipped gate as unverified, not as verified-and-green"); it is the same rule,
   one level down.

3. **The probe must be capable of the observation.** Before asserting a denial, state what
   the probe would have to see in order to fail, and make it see that: an object that
   exists, inside the granted prefix, with the interleaving on the far side of the guard. A
   probe whose failure mode is indistinguishable from its success mode is not evidence, and
   this is where five of the seven cases above went wrong.

4. **A guard that cannot fire in the gate documented to run it is not a gate for that
   surface.** Either the gate invokes it under the conditions it needs, or the gate table
   says plainly that it does not and how to arm it — which is what #863 did. A local gate
   quietly narrower than CI is the defect class #664 and #688 already cost this repo twice.

**Scope, stated narrowly on purpose.** This applies to *guards* — code whose only job is to
refuse — not to the suite at large. Mutation is productive at a guard predicate and
expensive everywhere else, and this ADR proposes no coverage metric, no mutation score, and
no threshold.

## Consequences

### What gets better

- A refusal that is cited as a safety property has been seen refusing. #864's 21-for-21 is
  the standard, and it took one afternoon.
- "The tests pass" and "the guard holds" become different sentences, with different
  evidence, in review.
- The technique finds the defects nothing else does. Six of the seven cases above were
  invisible to review, to type checking, and to a green suite.

### What gets harder

- **Every guard is now two pieces of work.** Writing the predicate, then arranging to break
  it. For a guard behind Docker or a live cluster, arranging to break it is the larger half.
- **A mutation run needs a green baseline first, and getting that wrong inverts the
  result.** A fresh worktree with no `node_modules` and no populated virtualenv produces a
  gate that dies in setup, which reads as *"nothing noticed"* — and would mark every guard
  in the repo as decoration. `.claude/workflows/README.md:210-218` builds its harness around
  a mandatory green baseline with a test count, abandoning any batch whose baseline is not
  green. Anyone doing this by hand owes the same discipline.
- **Mutation records rot.** They cite a line that moves and a count that changes. They are
  evidence about the day they were produced, not a standing assertion — the standing
  assertion is the test they justify. Treat a stale record as history, not as a claim.

### Not covered

- **Nothing here forces the record to be checked.** A CI-enforced mutation budget was
  considered and is not proposed: it costs a gate run per mutant per surface, on self-hosted
  runners (ADR-0024), to re-derive a fact a reviewer can read in the PR body. If guard
  regressions start slipping through, that is the next step, not this one.
- **This closes ADR-0040's section-C gap for guards only.** Assertion strength in ordinary
  tests — a `toBeGreaterThanOrEqual(1)` where `toHaveLength(1)` was meant — is still
  enforced by review alone, and ADR-0040's "Remaining, unowned" entry stands for that half.
- **Abstention-as-a-third-outcome is a decision, not a migration.** Changing
  `assess_legal_text_density`'s return shape touches every call site and belongs with the
  work that widens its wiring (#862), not here.

## References

- [ADR-0040](0040-test-result-trust.md) — the three causes; this ADR closes its section-C
  item for guards and leaves the rest open
- [ADR-0048](0048-completeness-crosses-the-boundary-by-projection.md) — *"a gate that never
  runs is the same as no gate"*; this is the case where it runs
- [ADR-0049](0049-workloads-never-hold-the-object-store-root-credential.md) §3 — the deny
  probe against an absent key, and the prefix rule
- [ADR-0030](0030-acquisition-provider-enablement-lifecycle.md) §5 — a skipped gate is
  unverified, not verified-and-green (#744)
- #832 (the `blocker` keying, caught in review), #834, #840, #844, #862, #864 — and
  #858 / #863, both merged 2026-09-03
- `.claude/workflows/README.md` — the mutation harness and its baseline requirement
