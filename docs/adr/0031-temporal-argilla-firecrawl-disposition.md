# ADR-0031: Disposition of Temporal, Argilla, and Firecrawl

## Status

Accepted

## Date

2026-07-13

## Context

Three third-party integrations are fully coded in this repo and deployed in no
environment: **Temporal** (durable workflow execution), **Argilla** (human
annotation / review queue), and **Firecrawl** (hosted web crawling). All three
default to off and degrade quietly when unconfigured.

An audit prompted by an unrelated production incident (a missing OpenSearch
index, ADR-unrelated, see #549) established their real state:

- **Temporal.** Five workflows in `platform-control/src/platform_control/temporal/`
  — wizard onboarding, scope-shard crawl, review drain, rescore-from-correction,
  retention sweep. The workflow definitions are good: determinism is clean, every
  activity carries a timeout and a retry policy, and `Orchestrator` sits behind a
  `Protocol` (ADR-0021) so the API does not depend on it. Everything around them
  is not: the human gate has no timeout and no notification, so a wizard run parks
  silently and forever (#560); `run_shard_crawl` is not idempotent, so a retry
  re-scrapes a government portal (#561); no activity ever writes a terminal wizard
  state, so the database diverges permanently from the workflow on any failure;
  `Dockerfile.worker` runs the *connector* worker, not the Temporal worker, so the
  image cannot run it at all; and every test that starts a workflow is skipped in
  CI (#564).

- **Argilla.** The client in `services/argilla_enqueue_service.py` was written
  against an aspirational JSON example in a runbook rather than against Argilla's
  API, and its request shape is very likely rejected by argilla-server 2.x. There
  is no pinned dependency, no vendored spec, and no contract test that would catch
  that. Every failure is swallowed and reported as success, so the drain workflow
  would poll for 24 hours and report `drain_complete` having enqueued nothing
  (#563).

- **Firecrawl.** The best-engineered integration in the acquisition layer:
  fail-closed configuration errors, verified HMAC webhook signatures, atomic
  `INSERT … ON CONFLICT` idempotency tested against real Postgres. It is also
  nearly vestigial — it routes exactly one blueprint template (`at/firecrawl_justice_portal`),
  every other authority uses a structured provider, and it is configured in no
  cluster. It carries one serious defect: a commit-ordering race that permanently
  drops a webhook via a poisoned dedupe key (#558).

The decision is not "are these well built" but **"do we have the problem each one
solves, and do we have it now."**

### The cost of keeping code you do not run

The audit's most useful finding is not about any one service. It is that all three
had rotted into code that *looks* alive and is not: a client that cannot talk to
its server, a worker whose Dockerfile runs the wrong entrypoint, tests that never
execute, and — in ADR-0030 — a documented safety control with zero callers (#559).

An unused integration is not free. It accrues debt with a plausible face, and the
next engineer reads the code, or the ADR, and believes it.

## Decision

### 1. Temporal — keep, keep it off, and remove the one thing that must run

Temporal is the right tool for the problem it was chosen for. Source onboarding is
a multi-hour, human-gated, resumable process, and hand-rolling durable execution on
NATS would rebuild a worse Temporal. ADR-0021's abstraction stays.

But the wizard is not in use — sources are onboarded today by running
`scripts/ch-fedlex-fast-loop.sh` by hand — so standing up a Temporal server, its
Postgres, and a worker to orchestrate a workflow nobody invokes buys nothing and
adds a second orchestration substrate alongside NATS.

Therefore:

- `PLATFORM_CONTROL_WIZARD_ORCHESTRATOR_BACKEND` stays `in_memory`. No Temporal
  server is deployed.
- **The retention sweep moves out of Temporal into a Kubernetes CronJob.** Hard-delete
  retention is a legal obligation in some jurisdictions; it currently depends on a
  Temporal worker that is not deployed, which means **it is not running at all**. It
  is a cron. It does not need durable execution.
- #564 is fixed so the remaining Temporal code is exercised in CI and stops rotting.
- #560 and #561 stay open as the explicit gate on any future rollout.

### 2. Argilla — delete it

`platform-control/admin` already has a `preview-review` resource with list and show
pages. That is a review surface for operators.

Argilla's value over that is annotation-specific: multi-annotator agreement, dataset
versioning, purpose-built labelling UX — the things needed to build **ML training
sets**, which is not the current need. The current need is "an operator looks at a
low-confidence extraction and accepts or rejects it," and the admin app does that.

Given the client probably cannot talk to a real Argilla server, deleting is cheaper
than fixing. If genuine annotation workflows are needed later, rebuild against the
real API with a contract test; nothing of value is lost.

Removed: `services/argilla_enqueue_service.py`, the Argilla config fields, the
Argilla columns' write path, and `ReviewDrainWorkflow`'s dependence on it.
`docs/runbooks/argilla-review-routing-and-sync.md` is retired. The **confidence-band
routing policy it documents is retained** — it is a good policy and it is
independent of Argilla — and moves to the review-task model.

### 3. Firecrawl — keep dormant, and fix the platform-wide lock now

Keep the code. It is the only path for portals with no structured API (the Austrian
RIS portal), which is a real category, and it is well built. Leave it unconfigured.

#558 (the webhook race) is a precondition for ever enabling it, not for keeping it.

**#559 is not a Firecrawl issue and must be fixed immediately regardless.**
ADR-0030 — accepted — states that "the run-launch path calls `require_live_ready()`,
so a scaffold can never fire even if a template mistakenly references it."
`require_live_ready` has zero callers, and `enabled` is stripped before dispatch and
never read. The ~15 templates marked `enabled: false` — cantonal courts, court
decisions — are **not blocked from firing at live government portals**. The design in
ADR-0030 is correct; the code must be made to match it.

## Consequences

- The legal-retention sweep starts actually running, decoupled from an undeployed
  workflow engine.
- One less service, one less auth surface, and one less place for review state to
  diverge (Argilla).
- The acquisition layer's advertised safety lock becomes real.
- Temporal remains a deliberate, documented "not yet" rather than an ambiguous
  half-rollout — with #560/#561/#564 as the standing entry criteria.
- If the onboarding wizard becomes a product priority, the decision is revisited and
  those three issues are the work.

## Alternatives considered

**Roll Temporal out now.** Rejected: ~1–2 weeks of correctness work (#560, #561,
#564) plus a server, a worker deployment, and secrets, to orchestrate a workflow with
no current caller.

**Rip Temporal out entirely.** Rejected: the durable-execution problem is real and
will return with the wizard. ADR-0021's abstraction makes keeping it cheap.

**Fix and roll out Argilla.** Rejected: it depends on Temporal being live, duplicates
a review surface that already exists, and the current need is operator review, not
annotation.

**Delete Firecrawl.** Rejected: it is the only escape hatch for portals with no
structured API, and it is the best-engineered code in the acquisition layer. Keeping
it dormant costs little now that #559 makes dormancy actually enforced.
