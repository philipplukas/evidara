# ADR-0056: Agentic flows are visible in the operator panel

## Status

Accepted — **amends [ADR-0022](adr-0022-agentic-cli-workflow-control-surface.md)** (does not supersede it).

## Date

2026-09-09

## Context

ADR-0022 made `tools/evidara-cli` the bounded control surface agents act through, with
`platform-control` as the durable system of record for runs, step history and approvals. That was
right, and its safety properties are still right.

What it did not say — and what everyone reasonably inferred — is that agents therefore get **no UI**.
The consequence is that the operator agent is invisible.

That is not hypothetical. `tools/evidara-cli/src/evidara_cli/agent_loop.py` (246 lines, #909) is the
operator agent's decision layer: a pure function over
`GET /v1/acquisition-coverage/queue` that proposes, per jurisdiction, what to do next. It is
careful work. It is enforced by a test named `test_no_refusal_is_ever_agent_actionable`. And
**nothing in the product renders any of it.**

A control plane nobody can see cannot be shown, cannot be sold, and — the part that matters for
[#958](https://github.com/philipplukas/evidara/issues/958) — cannot be *trusted*, because trust in an
automated system is built by watching it decide and then agreeing with it. ADR-0022's own rule that
"human approval remains mandatory before irreversible actions" presumes a human who can see what
they are approving. Today the approval screen can neither approve nor render its evidence (#949),
which is the same gap from the other end.

The choice is not between a safe CLI and an unsafe UI. It is between an agent whose reasoning is
observable and one whose reasoning is not.

## Decision

**The operator panel may initiate agent runs and stream their progress, evidence and refusals.**

Five constraints, all carried unchanged from ADR-0022, define what "may" means:

1. **One control surface.** The panel calls the same `platform-control` HTTP contract the CLI calls
   — the drift-gated generated OpenAPI (ADR-0034). No endpoint may exist for the UI's convenience
   that the agent surface lacks, and no agent capability may exist that only the UI can reach.
   A second control plane is the failure this ADR is most concerned with, because the easier path
   becomes the real policy and it is usually the weaker one.
2. **`platform-control` remains the system of record.** The panel *renders* the journal
   (`WizardRunLedger.state_transitions`); it does not hold it, and closing the tab loses nothing.
3. **The autonomy boundary stays server-side.** #854 moved the ADR-0030 two-key guard into
   `platform-control`: flipping `enabled: true` requires bound acceptance evidence plus a human
   acknowledgement, and the server refuses otherwise with a machine-readable code. The UI must not
   offer any path around it, and "the button was disabled in the client" is not enforcement.
4. **A refusal is an outcome to display, never a retry affordance.** `agent_loop.py` states the
   reasoning: a refused run is a decision a person made — a closed config key is how an operator
   stops traffic at a portal when an authority complains about load — and an agent that retried it
   would be overriding a human by persistence rather than by permission. The CLI enforces this with
   `test_no_refusal_is_ever_agent_actionable`. **The panel needs its own equivalent**, because a
   "Retry" button beside a refusal is exactly that override, performed by the operator's own hand
   without being told what they are doing. (#954 is this defect already present.)
5. **Human approval before irreversible or governance-significant actions remains mandatory**, per
   ADR-0022.

## What this does not authorise

**The legal-reasoning MCP server.** ADR-0033 §4 stands: *do not build the MCP server first.* That
guardrail is about a thin tool layer over an untrustworthy corpus producing "a demo that lies
convincingly", and #958 exists precisely because the corpus is not yet trustworthy.

The distinction #909 drew is the one that matters and it is easy to get wrong in both directions:
**an operator agent drives acquisition; a reasoning agent drives the corpus.** Making acquisition
visible does not license making reasoning visible. When #958's acceptance test passes — the dog
question answered *and* correctly refused — that decision can be revisited on its own evidence.

## Consequences

### Positive

- The loop ADR-0033 calls the deliverable becomes watchable: blueprint → source version →
  acceptance run → evidence → `enabled: true` → approval.
- The human gate gets the evidence it was always supposed to have (#949).
- An agent that must render its reasoning is an agent whose reasoning gets reviewed. Several defects
  in this repo survived because nothing displayed them.
- Refusals become visible product behaviour rather than log lines, which is what #911's refusal
  ledger is for.

### Negative

- The panel gains streaming state, which it has not needed before, and a class of failure —
  a stream that dies silently — that must not read as "the agent finished". Per this repo's rules
  that needs a guard that cannot abstain.
- Constraint 1 is easy to state and easy to erode. Any PR adding a `platform-control` endpoint
  should be checked against it.
- More surface area on the contended admin lane (#913), which is serial internally.

### Neutral

- ADR-0022's verb family (`inspect`/`propose`/`apply`/`verify`/`compensate`) is still only partly
  built — `proposal.py:46` is the sole member. This ADR does not change that; it makes finishing it
  more valuable, since the panel would render those verbs.
