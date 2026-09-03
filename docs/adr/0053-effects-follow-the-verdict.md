# ADR-0053: Effects follow the verdict

## Status

Proposed

## Date

2026-09-03

## Context

### A run could fail after its documents were already in the corpus

Until #858 merged on 2026-09-03, `_dispatch_run`
(`platform-control/src/platform_control/services/run_service.py`) did four things in this
order:

1. persisted the provider's inline resources and built the bundle events,
2. set `run.status = RunStatus.COMPLETED`,
3. **then** — if the provider returned an `inline_failure_reason` — set
   `run.status = RunStatus.FAILED`,
4. and handed the batch to `_publish_pending_dispatch_events`, which iterated
   `pending.raw_artifact_ids` and `pending.bundle_events` and published every one. **There
   was no reference to `run.status` anywhere in that function**, at any of its three call
   sites.

So a run whose row read FAILED had already published its documents. #858's verification
found the reason it had not bitten: every provider gates its failure reason on
`if not resources`, at eight named sites. #845 was the first provider to want the other
combination — a capture that arrived *and* is not to be trusted, because the mirror diverged
from its source — and fixed it provider-side, one provider at a time.

The label and the effect disagreed, and the label is what an operator reads.

**Steps 2 and 3 are unchanged on `main` today** (`:1373`, then `:1376-1381`), and that is the
point rather than an oversight: the fix #858 landed is a guard at step 4, where
`_publish_pending_dispatch_events` now reads `run.status` as the first thing it does
(`:1797-1804`) and routes a FAILED or unresolvable run to `_withhold_dispatch_publication`
(`:1834`). The ordering inside `_dispatch_run` was never the invariant. The boundary was.

### Two more of the same shape

**A verdict written from a stale read.** `wizard_service.approve_run`
(`platform-control/src/platform_control/services/wizard_service.py:177-185`) reads the row,
makes a **network round trip** to the orchestrator (`signal_approve`), then assigns
`wizard_run.state` from the object it read before that round trip and commits. No predicate,
no re-read. As soon as anything else can write that row — and #844 gives the workflow a write
path for its own outcome, including a terminal `GateExpired` — an operator's approval
silently overwrites a terminal state, and the operator is told it was accepted.

The review of #844 records the part that makes this ADR necessary rather than obvious: the
first attempt at a test for that race committed the expiry *before* calling `approve_run`,
and **passed on the unfixed code**, because SQLAlchemy refreshed the guard's read. The window
exists only after the guard. The defect is narrow, real, and nearly invisible to a test
written from the description.

**A write that skipped its own discipline.** #834 §4: `wizard_service.start_pilot_run` — the
third writer to `progress` — assigned the column outright from a snapshot, with no predicate
and without bumping `progress_version`, which the model's own docstring forbids. Not
currently reachable (the human gate blocks before any shard starts), and a defect regardless:
the missing version bump is the half nobody downstream could have detected.

### The common shape

A decision and its effect are two separate writes, and nothing orders them. Sometimes the
effect leaves before the verdict is final (`_publish_pending_dispatch_events`); sometimes the
verdict is written from a value read before something else changed it (`approve_run`,
`start_pilot_run`). Both produce the same class of outcome: the system's record of what it
decided does not describe what it did.

For this platform that is not a generic correctness bug. The corpus is the thing legal
answers are drawn from, and ADR-0033 stakes the product on being able to say what is in it
and why.

## Decision

**The verdict gates the effect, and the effect is ordered after it. A write conditioned on a
read is a compare-and-set.** Four commitments.

1. **Publication, not persistence, is the boundary into the corpus.** This is #858's
   invariant, generalised beyond the dispatch path it now holds. A document enters the corpus when its event is published, not when
   its row is written. Every path that emits an event resolves the current status of the
   thing it emits for, and refuses to emit for one that is terminal-failed — and refuses,
   too, when it cannot resolve that status, because an unresolvable status is not a pass.

2. **Withhold the effect; keep the evidence.** When publication is withheld, the persisted
   rows stay. #858's four reasons, lifted here because they generalise:
   - The rows are the evidence of what the source served. For a mirror-fidelity failure
     (#845) the diverged bytes *are* the finding; deleting them destroys the reason the run
     failed.
   - Nothing downstream reads them without an event. document-intelligence is a NATS
     JetStream consumer (ADR-0029) with no path to these rows.
   - Deleting them collapses *"captured 12, published 0"* into a run indistinguishable from
     one that captured nothing — the precise legibility defect M15 exists to remove.
   - Withholding is a publication decision, not a storage one. Conflating the two means the
     platform's own distrust check destroys evidence.

   The consequence is recorded beside the cause, not in place of it: the provider's
   `failure_reason` says *why the run failed*; a `run_metadata` marker says *what was
   withheld*, next to the existing `refused` (ADR-0035) and `dispatch_publish_failed`
   markers. And **captured and published become separate numbers in the read model**, never
   collapsed and never defaulted to a fabricated `0`.

3. **A write conditioned on a read is a compare-and-set, and the writer learns whether it
   won.** `WHERE <column> = <the value the decision was made against>`, returning success or
   conflict. This binds whenever anything other than this writer can change the row — which
   now includes a workflow persisting its own outcome, an expiry, and a concurrent shard.
   #834's `update_wizard_progress` (CAS on `progress_version`, re-applying its mutation on
   top of the winner) and #844's `persist_wizard_outcome` (`expected_states`, returning
   whether it claimed the transition) are the two shapes; there should not be a third.

4. **A losing write is a conflict, not a silent success.** `ProgressWriteConflictError`
   rather than a dropped update; and where the loser is a human decision, the human is told.
   #844's `test_an_approval_that_loses_the_race_is_a_conflict_not_a_false_success` is the
   assertion, and its own history (above) is why the interleaving in such a test must be
   placed deliberately — see ADR-0051 §3.

## Consequences

### What gets better

- A FAILED run means nothing of it reached the corpus. That sentence is currently false and
  is the reason this ADR exists.
- The corpus's contents become decidable from the runs' verdicts, which is the precondition
  for ADR-0042's coverage claims and ADR-0048's completeness projection meaning anything.
- Concurrency defects fail loudly instead of silently losing a write. #834 measured the
  silent version: deleting the CAS predicate loses 10 of 12 concurrent shard reports against
  real Postgres.

### What gets harder

- **Every effect path acquires a status read it did not need.** #858 resolves once per batch
  rather than per artifact, which keeps it cheap; a path that publishes one event at a time
  pays a round trip per event.
- **CAS makes writers contend, and losers are loud.** #834 measured 70 concurrent writers:
  17 raised and 53 of 70 shards recorded before jittered backoff was added. Contention is
  quadratic in the fan-out and **still uncapped** (#561 §5, open). Loud failure is the right
  default, but a writer that exhausts its budget is a shard missing from the operator's
  view, and this ADR does not fix that.
- **Race tests are expensive and easy to get wrong.** A deterministic interleaving needs a
  genuinely separate writer and the commit placed on the correct side of the guard; #844
  needed a `sqlite3` connection outside SQLAlchemy's session to get it. A cheap version of
  such a test passes on the unfixed code.

### Not covered

- **Withheld rows accumulate with no reaper.** The retention sweep owns raw artifacts, and
  nothing distinguishes a withheld capture from a live one at sweep time. It is bounded
  debt, not a leak, but it is debt.
- **This orders effects inside one service.** It says nothing about an effect already
  delivered to a third party. The requests a provider sent to a government portal while a
  key was armed are not withdrawable — the distinction #865 drew between `side_effect_level`
  (the recoverability of a step's own write) and the permanence of its consequences. A
  second field was proposed there and deliberately not taken; this ADR does not take it
  either.
- **It does not make the run's status a distributed transaction.** The guard is a read
  immediately before the emit, not a lock across it. A status that changes between the read
  and the emit is a race this does not close; the case it closes is the ordinary one, where
  the verdict was already final and nobody consulted it.
- **Nothing here is amended into ADR-0030's lock.** A refused run and a failed-after-capture
  run are different states with different evidence; this ADR concerns the second.

## References

- #853 (the defect), #858 (merged 2026-09-03) — the publication boundary and the rollback
  decision this ADR generalises
- #844 (open) — the read-modify-write across a network round trip, and the race test that
  passed on the unfixed code
- #834 / #561 §3–§5 — the CAS writer, the `assert 2 == 12` mutation, and the uncapped
  contention that remains open
- #845 — the first provider to capture something it does not trust
- [ADR-0029](0029-self-hosted-hetzner-runtime.md) — document-intelligence is an event
  consumer, which is why publication is the boundary
- [ADR-0035](0035-operator-reachable-blueprint-enablement.md) — the `run_metadata` marker
  precedent (`refused`)
- [ADR-0051](0051-a-gate-that-cannot-fail-is-not-a-gate.md) §3 — a race test must reproduce
  the window the guard protects
