---
name: coverage-acceptance-loop
description: Drive the Evidara coverage loop — bring a blueprint template from inert to searchable and capture ADR-0030 acceptance evidence. Use when asked to onboard a new source/corpus/jurisdiction, run an acceptance run, find out why a template will not run or is "locked"/"disabled", diagnose a run stuck PENDING or a document that never reaches search, or decide whether a run counts as evidence for flipping `enabled: true`. Covers the two-key lock, which run mode to use, the compose env vars whose defaults silently break the loop, and the refusals that must never be talked past.
---

# Drive the coverage loop

The loop that brings a corpus online, end to end:

```
blueprint template → source + version → readiness → approve version →
acceptance run → DI processing → projection → searchable → evidence → enabled: true
```

**Scope guardrail, first.** This is operator tooling. It is *not* ADR-0033 step 6, the
MCP server — §4 of that ADR forbids building it before hybrid retrieval exists, because
over today's corpus it would demo convincingly and lie. If you find yourself designing a
protocol server or a retrieval/reasoning tool surface, you have drifted; stop.

## 0. Setup

```bash
cd tools/evidara-cli && uv sync --group dev
export EVIDARA_PLATFORM_CONTROL_URL=http://localhost:8000   # default
export EVIDARA_LEGAL_SEARCH_URL=http://localhost:3102       # default
```

Every command below prints one JSON envelope on stdout (`--human` to indent) and exits
nonzero when it refuses. Branch on the **codes**, never on the prose.

## 1. Find something to work on

```bash
uv run evidara workflow coverage templates --human
```

Each template gets a machine-readable verdict. The field that matters is `blocker`, and
its `remedy` says *who* can unblock it:

| `blocker` | `remedy` | Meaning |
|---|---|---|
| `null` | `none` | Both ADR-0030 keys turned. Any mode dispatches. |
| `provider_awaiting_evidence` | `run_acceptance_loop` | Provider works, nobody captured evidence. **You can do this yourself.** |
| `template_never_enabled` | `run_acceptance_loop` | Config key never turned; acceptance waives it. |
| `template_disabled_by_operator` | `reopen_config_key` | Someone's kill switch. Acceptance does **not** waive it. Ask before reopening. |
| `provider_scaffold` | `engineering` | `start_run` is a stub. No mode dispatches. Do not try. |

To list exactly what an operator can unblock today without an engineer:

```bash
uv run evidara workflow coverage templates --blocker provider_awaiting_evidence
```

Filters: `--overlay`, `--provider`, `--template`, `--readiness`, `--blocker`, `--mode`.

> If `ok: false` with `disagreements_with_server`, **stop and report it.** The CLI mirrors
> the two-key lock client-side; a disagreement with the server's `launchable` means the
> mirror has drifted and its verdicts are untrustworthy. `/v1/runs/readiness` is
> authoritative.

## 1b. When there is no template yet — the source-lifecycle half

`coverage templates` inventories what `source_blueprints.yaml` already ships. For a
source with **no** blueprint template, the entry point is `workflow source`, whose five
steps map onto the same loop: `inspect` → `propose` → `apply` → `verify` →
`compensate`.

```bash
uv run evidara workflow source inspect --human                 # reachability + discovery
uv run evidara workflow source propose --seed-url <url> --human
uv run evidara workflow source apply --display-name '<name>' --seed-url <url> \
  --jurisdiction-id <id> --human
uv run evidara workflow source verify --source-id <id> --human   # or --run-id
uv run evidara workflow source compensate --source-id <id> --reason '<why>' --human
```

Every one of these returns the ADR-0022 envelope
(`contracts/schemas/workflow-command-envelope.schema.json`), and two fields decide what
you may do next:

- **`side_effect_level`** — `none` for `inspect`/`propose`/`verify`, `reversible` for
  `apply` and `compensate`. Only `apply` mutates, and it creates a **draft** source.
- **`status`** — `passed`, `needs_human`, `failed_retriable`, `failed_terminal`, or
  `compensated`. This is the field to branch on.
- **`decision.recommended_action`** — advisory, and **not** the same as `status`.

`propose`'s duplicate check is where that distinction bites. `proposal.py:68` defines the
domain as `none` / `low` / `high`, and both backends grade it the same way — rule-based at
`:102-108`, DSPy at `:187-194`. Then `workflow_cmd.py:261` marks the evidence item
`passed = duplicate_risk != "high"`, and `:267` derives `status` from it. So:

| `duplicate_risk` | `status` | exit | `recommended_action` |
|---|---|---|---|
| `none` | `passed` | 0 | `apply` |
| `low` | `passed` | 0 | `needs-human` |
| `high` | `needs_human` | 1 | `needs-human` |

**Only `high` stops the command.** At `low` — the display name appears *inside* an
existing source's name — the envelope is `passed` and exit 0, and the only signal is
`recommended_action: needs-human` plus the evidence item's `value`. An agent branching on
`status` alone will sail past it. Read `artifacts.proposal.duplicate_risk` before `apply`;
do not create a second source for a corpus the platform already holds.

`compensate` is a **real corrective action**, not an in-memory undo: it cancels the run
(`POST /v1/runs/{id}/cancel`) and rejects the latest `pending_approval`/`draft` version
(`POST /v1/versions/{id}/reject`). With nothing pending it records intent only and
still reports `compensated` — read `artifacts` to see what it actually did.

Adding a *provider* rather than a source is a code change, and two things about it are
easy to get wrong in ways nothing catches:

- whether the captured bytes are law → `validate-acquisition-provider` skill
- what `in_force_until` means at your upstream → `provider-temporal-semantics` skill

## 2. Pre-flight — before creating anything

```bash
uv run evidara workflow coverage preflight --overlay ch --template <template_id> --human
```

Read-only. Resolves the lock, resolves the acquisition spec via
`POST /v1/sources/blueprint-preview`, and checks both services. Use it because
`/v1/runs/readiness` needs a source **and** a version to already exist — without this,
the only way to learn a template is inert is to create both and be refused.

Read `plan_notes` before running. They are the provider's own account of what it will do
(seed URLs, coverage limits, config errors) and are where a "this only enumerates part of
the corpus" caveat lives.

`recommended_mode` is the mode that will actually dispatch, and `next_command` is the
driver invocation with that mode already filled in.

## 3. Run the loop

Do **not** hand-roll create → approve → dispatch with `curl`, and do not reimplement it.
The driver already exists and owns the content gates and the evidence bundle:

```bash
bash scripts/ch-fedlex-compose-e2e.sh \
  --overlay ch --template <template_id> --mode <recommended_mode> \
  --expect-content-type <mime> --jurisdiction-id <id> --authority-id <id> \
  --expect-language <code> --expect-title '<regex>' --query '<search term>'
```

Despite the name it is corpus-parameterised. Pass the corpus-shape flags: without
`--expect-content-type` a PDF corpus reports `provider_failed` while working correctly,
and without `--expect-language` / `--expect-title` the harness falls back to the template
id — the `_de`/`_fr`/`_it` suffix, and a hardcoded list of three Fedlex titles. For any
other template those gates do not run at all and are recorded as **`excluded`**: honest,
but the run then proves nothing about the title or the language facet (#735, #744).

### Bringing the stack up

```bash
bash scripts/dev-loop-stack.sh up       # rebuild, start, then verify
bash scripts/dev-loop-stack.sh verify   # check a stack that is already running
```

Prefer this over a hand-rolled `docker compose up`. It exists because the loop has
settings that are inert by default and silent when wrong, and its `verify` re-derives
them from the repo instead of trusting that every container reports healthy — which,
in each of these failures, they all do:

- `PLATFORM_CONTROL_EVENT_PUBLISHER_BACKEND` defaults to `noop` and
  `PLATFORM_CONTROL_ARTIFACT_STORE_BACKEND` to `local`. platform-control then captures
  the documents, reports the run `completed`, and **publishes nothing**, so DI sits idle
  and the harness times out waiting for a document it was never handed.
- **`platform-control-worker` must be running.** `RunService._should_dispatch_via_worker()`
  forces worker dispatch for `_ASYNC_PROVIDER_NAMES` — currently `ris_ogd`, i.e. every AT
  RIS template — no matter what `PLATFORM_CONTROL_RUN_DISPATCH_BACKEND` says. With no
  worker the run sits `PENDING` forever with `refused: false` and no `failure_reason`,
  which reads like a broken provider and is not one.
- The worker's artifact-store and event-publisher backends must match the API's. It owns
  acquisition dispatch, so *its* backends decide whether anything reaches DI; a worker on
  `local`/`noop` writes bundle manifests the consumer cannot read while the run still
  reports `completed`.
- `--profile search` is required alongside `apps`, or compose refuses the whole project.

If you do bring compose up by hand, pass `--profile apps --profile nats --profile minio
--profile search` and both env vars above, then run `dev-loop-stack.sh verify` anyway.

## 4. Watch a run, and diagnose a stall

```bash
uv run evidara workflow coverage watch --run-id <run_id> --until processed --human
```

`--until run` waits for a terminal run status; `--until processed` also waits for DI and
projection. `--timeout 0` polls once and reports. On a stall it returns a `cause` code
instead of a bare timeout:

| `cause` | What to do |
|---|---|
| `run_refused_by_lock` | Not a stall. The two-key lock refused it and persisted a FAILED run with `refused: true`. Read `failure_reason`; go back to step 1. |
| `no_dispatch_worker` | Run never left PENDING — nothing dispatched it. `platform-control-worker` is down or was never started; `bash scripts/dev-loop-stack.sh verify` names this directly. |
| `publish_path_disabled` | Completed with zero DI events. `PLATFORM_CONTROL_EVENT_PUBLISHER_BACKEND` is on `noop`. See §3. |
| `di_consumer_silent` | DI got events but stopped. Check the consumer container. |
| `projection_stalled` | DI processed, nothing projected. Check the projection bridge. |

## 5. Evidence — and the refusals

```bash
uv run evidara workflow run evidence --run-id <run_id> --human
```

Read `artifacts.acceptance_verdict`. If `is_acceptance_evidence` is false, the run **may
not** be cited to justify flipping `enabled: true`. The refusal codes:

- `execution_mode_shadow` — **the one to never talk past.** A SHADOW version replays
  cassette fixtures and never touches the live portal, so a fully green SHADOW run proves
  nothing about it (ADR-0030 §2). Re-run with a `live` execution mode.
- `mode_not_acceptance` — evidence must come from a run recorded `mode=acceptance`, so it
  is self-labelling and cannot later be mistaken for production ingest.
- `run_refused_by_lock`, `run_not_completed`, `no_captured_resources` — nothing happened
  to evidence.

**A pass justifies only the gates that actually ran**, and *why* a gate did not run
decides whether the run is still evidence. The harness's **Gate coverage** section, and
`checks.gate_coverage` in `summary.json`, name both:

| outcome | means | verdict |
|---|---|---|
| `excluded` | Nobody asked for it — this template declares no title pattern, no language to assert. | Unverified, but not a hole. The run is still acceptance evidence for what did run. |
| `not_evaluated` | It was asked for and could not run — legal-search unreachable, projection never queryable, nothing processed to assert over. | A hole. The run is **not** acceptance evidence until the gate runs. |

`checks.skipped_gates` is still emitted as the union of the two, so it no longer answers
the question on its own. A bundle that predates the split (no `gate_coverage` key) has
every entry read as `not_evaluated` — the safe direction, and free in practice because
every persisted bundle reports `skipped_gates: []`.

The CLI does not see any of this unless you hand it the file — platform-control stores
no gate ledger:

```bash
uv run evidara workflow run evidence --run-id <run_id> \
  --evidence-bundle <run_dir>/summary.json --human
```

With the bundle, two more refusal codes can appear in `acceptance_verdict.refusals`:
`gate_not_evaluated` (names each gate and its reason) and `gate_coverage_unknown` (the
bundle reported no coverage at all). Both refuse the flip in §6. Without the bundle only
the run-level rules above run, and a hole in the gates stays invisible.

Persist the bundle under `docs/runbooks/evidence/`. **`ch-fedlex-compose-e2e.sh` has
no `--copy-evidence` flag** — its own comment says so (`:64-65`); pass `--out-dir` and
copy it yourself. `--copy-evidence` exists on `scripts/ch-fedlex-fast-loop.sh` (`:185`) and
`scripts/ch-bger-fast-loop.sh` (`:149`), which run against a deployed environment rather
than local compose. `--url-pattern` and `--corpus-slug` exist on **`ch-fedlex-fast-loop.sh`
only** (`:113`, `:129`) — `ch-bger-fast-loop.sh` has 18 flags and neither is among them.

Whether the captured bytes were law at all is a separate question this harness does not
answer — see the `validate-acquisition-provider` skill before citing a run as coverage.

## 6. Flip the key

Two keys, two owners, and only one is yours.

**Config key** — `template.enabled`. Flip it with the CLI, citing the run:

```bash
uv run evidara workflow coverage enable \
  --overlay ch --template <template_id> --evidence-run-id <run_id> \
  --evidence-bundle docs/runbooks/evidence/<dir>/summary.json \
  --note "Evidence bundle: docs/runbooks/evidence/<dir>" --human
```

Pass `--evidence-bundle`. Without it the command cannot tell a gate the operator
excluded from a gate that could not run, and the flip is decided on the run-level rules
alone (#744). This is the one part of the guard that stays client-side after #854: the
bundle is a local harness file and platform-control stores no gate ledger, so the server
cannot derive it however much of the rest moves there.

**Everything else is server-side, so a hand-rolled `PUT` meets the same rules (#854).**
The guard used to live only in the CLI while the admin panel required just a non-empty
note, which made this command's guard advisory — an operator refused here could type one
character into the panel and get the same state. Now
`PUT /v1/sources/blueprint-templates/{overlay}/{template}/enablement` re-derives the
acceptance verdict, binds the run to the template, checks both ADR-0030 ordering rules
and reads the write back. Still prefer the command: it applies the gate-coverage refusal
the server cannot see, carries the citation into the audit note, corroborates the
server's read-back against the template listing, and returns the whole thing as an
envelope. If `verification.applied` is false, the key is **not** flipped; say so and
stop.

Refusals come back as HTTP **409** and write nothing:

| refusal | what to do |
|---|---|
| `no_evidence_run_cited` | Go capture evidence (§3–§5). The key is turned after evidence, not on confidence. |
| `evidence_run_not_found` | The run id does not exist. Do not retype it from memory; list runs. |
| `evidence_run_is_not_acceptance_evidence` | Read `acceptance_verdict.refusals` — usually `execution_mode_shadow`, or `gate_not_evaluated` when a cited bundle reports a gate that could not run. Re-run live, or run the missing gate. |
| `evidence_run_provider_unresolved` | Nothing ties the run to this template. Do not "assume it's fine"; find the right run. |
| `evidence_run_provider_mismatch` | You cited a run from another corpus. |
| `evidence_run_template_mismatch` | You cited a run from a **different template on the same provider** — the LexFind trap. Cite this template's own run. |
| `evidence_run_template_unbindable` | The run's version has no blueprint provenance and its spec is not this template's. Nothing binds them; find the right run. |
| `evidence_run_capture_count_unknown` | The run reports no capture count, so that check did not run. A check that cannot run is not a pass. |
| `no_audit_note_recorded` | Say why, in both directions. A flip with no reason is indistinguishable from one made by guessing. |
| `classification_disagrees_with_server` | The CLI's lock mirror has drifted from the server's `launchable`. Do not write against a derivation you cannot trust — report it. (The only refusal still derived client-side; the server cannot check itself against its own `launchable`.) |
| `provider_not_live_not_acknowledged` | **Move the code key first.** ADR-0030 §2 wants LIVE before `enabled: true`; the invariant test that enforces it covers only `source_blueprints.yaml`, never the override table this writes. `--acknowledge-provider-below-live` arms it anyway. |
| `operator_kill_switch_not_acknowledged` | **Ask the operator first.** `--reopen-operator-kill-switch` exists so reopening is a deliberate act, not an accident. |

The one refusal that is *not* "nothing happened" is a read-back failure after the write:
it comes back `write_attempted: true`. The key's state is then whatever the read-back
reports, not what you asked for. Go look.

**Evidence now binds to the template, not to its provider (#846).** The run's source
version records the blueprint template it was created from, and the server reads it
directly, so one canton's LexFind run no longer satisfies the check for the other 26.
`artifacts.evidence_binding` reports the strength:

- `template` — exact. Nothing left to confirm.
- `acquisition_spec` — the version has no blueprint provenance but its spec equals this
  template's. Allowed, and reported `needs_human`: confirm by hand.
- `provider` / `none` — refused.

A `200` is not a flip. The server reads its own write back and reports the outcome; read
`verification.problems`:

| code | what it means |
|---|---|
| `read_back_disagrees` | The `PUT` returned 200 and the read model still reports the old effective key. **The key was not flipped.** |
| `no_override_recorded` | The effective key is what you asked for, but the read model still attributes it to the shipped default. `set_enabled` always writes an override row, so the write did not land and the value merely happens to agree. |

Two things the command still will **not** decide for you, so a successful flip comes back
`needs_human` rather than `passed` whenever either applies — read every evidence item
marked `passed: false` before calling it done:

- **A binding weaker than `template`.**
- **Arming the config key ahead of the code key**, and reopening somebody's kill switch.

Turning the key **off** takes no evidence, but it does take a note — now required by the
server, in both directions — and it is a real write even when the key merely reads `false`
today: a `never_turned` key is waived by acceptance mode, an operator's `false` is not
(#768). Do not read "it's already off" as "the portal is shut".

The admin panel's Blueprints inventory does the same flip through the UI and meets the
same guard: it sends the evidence run id and the acknowledgements, renders the returned
refusal codes, and reports on the server's `applied` read-back rather than the status
code. See the `run-admin-panel` skill.

**Code key** — moving a provider from `awaiting_evidence` to `live` is a **code change**
in platform-control. Attach the evidence to that request; do not flip it on confidence.
Enabling the config key does not open it: `coverage enable` reports which modes the lock
still admits when the provider is short of `live`.

## Boundaries

- Never weaken a gate, a query, or an assertion to make a run pass. Fix the thing it
  caught.
- Never reopen an operator's closed config key without asking — it is somebody's
  deliberate kill switch, and the refusal code exists to keep you from misreading it as an
  un-earned key. Read it off `config_key == closed_by_operator`, **not** off `blocker`:
  `blocker` is a single priority-ordered value, and a `provider_scaffold` outranks and
  hides the kill switch. `scaffold` is also the server's fail-closed default for a
  provider it cannot resolve, so keying off `blocker` turns a fail-closed signal into a
  fail-open one.
- `acceptance` mode is a rehearsal. Reporting it as "the lock is open" is exactly the
  overstatement ADR-0030 exists to prevent.

## Reference

- [ADR-0030](../../../docs/adr/0030-acquisition-provider-enablement-lifecycle.md) — the lifecycle, the two-key lock (§2), the evidence workflow (§5), `RunMode.ACCEPTANCE` (§6)
- [ADR-0033](../../../docs/adr/0033-agentic-legal-reasoning.md) §4 — the build order, and why not to build the MCP server
- [ADR-0022](../../../docs/adr/adr-0022-agentic-cli-workflow-control-surface.md) — the envelope every `workflow` command returns
- `tools/evidara-cli/src/evidara_cli/coverage.py` — the classification rules, with their platform-control counterparts cited
- `tools/evidara-cli/src/evidara_cli/gate_coverage.py` — the excluded / not-evaluated split and the one implementation of the rule that escalates it
- `scripts/ch-fedlex-compose-e2e.sh` — the driver
- `.Codex/skills/validate-acquisition-provider/SKILL.md` — whether the captures were law
- `.Codex/skills/provider-temporal-semantics/SKILL.md` — `in_force_from` / `in_force_until` for a new provider
- `.Codex/skills/opensearch-mapping-drift/SKILL.md` — why a document reaches the index and the query still returns nothing
- `.Codex/skills/run-admin-panel/SKILL.md` — driving the admin UI to flip the config key
