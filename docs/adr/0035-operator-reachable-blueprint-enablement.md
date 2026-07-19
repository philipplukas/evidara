# ADR-0035: Operator-reachable blueprint enablement (config key to the database)

Status: Accepted
Date: 2026-07-17
Deciders: Platform / Contracts
Related: ADR-0030 (acquisition provider enablement lifecycle), ADR-0033 (agentic legal
reasoning — the coverage loop), ADR-0009 (FastAPI conventions), ADR-0034 (generated
platform-control contract)

## Context

ADR-0030 defined a **two-key lock** on the run-launch path: a run may fire at a live
government portal only when both keys are turned —

- **config-owner key** (`enabled`): *"the config-owner key an operator flips"* after
  capturing acceptance-run evidence, and
- **code-owner key** (`live_ready`): the provider's own assertion that `start_run` is
  not a stub.

Iteration 0 of the ADR-0033 coverage loop (#628) drove a real source through the
platform and found the lock is correct but **unreachable and invisible** (#631–#634).
The specific structural defect (#632): *both keys lived in the repository.* `enabled`
was YAML inside the Python package (`source_blueprints.yaml`), resolved through an
`@lru_cache`. There was no API route, DB table, or env override that could write it.

So "flip the config key" meant: edit the repo → PR → CI → image rebuild → deploy. That
is an **engineer and a release, per template** — which contradicts the ADR-0033 thesis
that a new jurisdiction must cost an *operator*, not an *engineer*, and pins #628's
"cost of the Nth source" metric to a source file. The two keys lived in the same place,
which defeats the point of having two.

## Decision

**Split the two keys across two homes, matched to what each key actually is.**

1. **The config key (`enabled`) becomes operational state in the database.** A new
   `blueprint_template_overrides` table holds an operator's flip for one
   `(overlay_id, provider_template_id)` pair, with an audit trail
   (`enabled`, `note`, `updated_by`, `updated_at`). It is reached through
   `PUT /v1/sources/blueprint-templates/{overlay_id}/{provider_template_id}/enablement`
   — no repo edit, no deploy.

2. **`source_blueprints.yaml` remains the shipped default, and stays fail-closed.** A
   template with no `enabled: true` is still inert on delivery. The effective key is
   resolved as **override ?? shipped default**: an override row wins; its absence means
   "use the shipped default." A template can therefore be enabled by an operator
   without editing code, and re-shipped disabled without losing the operator's intent
   history.

3. **The code key (`live_ready`) stays in code.** It is an engineering assertion — "this
   provider can physically acquire this format" — not operational state, and belongs
   with the provider class. Enabling the config key on a scaffold provider still refuses
   the run on the code key; the two halves are now genuinely independent.

4. **The lock is made visible (#634).** `blueprint-templates` and `blueprint-preview`
   now report `enabled`, `live_ready`, `launchable`, and human-readable `notes`;
   `/v1/runs/readiness` evaluates the lock so the pre-flight no longer reports
   `ready: true` for a run that `POST /v1/runs` then rejects; and the admin create
   wizard marks inert templates at selection time.

`BlueprintEnablementService` owns resolution (`is_enabled`, `get_state`,
`require_enabled`, `set_enabled`). The run-launch lock (`RunService._require_launchable`)
and the readiness pre-flight both consult it, so dispatch and pre-flight never disagree.

## Consequences

- The Nth source no longer costs an engineer and a deploy to enable — it is an
  authenticated API call (or an admin-panel action) with an audit trail. This is the
  precondition for the #628 metric to trend down.
- The generated contract (ADR-0034) gains the enablement route and the lock fields; the
  drift gate keeps them honest.
- A *refused* dispatch is recorded as a terminal FAILED run carrying a `refused` marker,
  and that marker is readable back: `refused` on the run detail and list responses, and
  `GET /v1/runs?refused=true` to audit refusals without them polluting failure triage
  (#634, item 4). Attribution is deliberately **key-shaped, not person-shaped** — `auth.py`
  resolves every human sharing an operator key to the same `Operator` row, so a refusal
  records *what* was attempted and *why* it was blocked, and does not claim to record who.
- `blueprint-preview` also returns `plan_notes` — the provider's own `plan()` output
  (seed URLs, config errors, provider-specific caveats), which until then was reachable
  only from the `plan` CLI (#634, item 3).
- **Not yet addressed (follow-ups):** `supported_portals` is still a provider `ClassVar`,
  so a second commune on an existing provider is still a code change (#632, second half).
  A refusal also produces no *raw artifact* — correctly, since nothing was fetched; the
  run row is the evidence. Tracked and deliberately out of this ADR's scope, which is the
  config key's home.
- SHADOW execution mode remains the operator's rehearsal path and is unaffected: it is
  routed to the cassette provider and never reaches the portal the lock protects.
