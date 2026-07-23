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
and without `--expect-language` / `--expect-title` those gates **self-skip while still
reporting a pass** (#735, #744).

### The stack env vars whose defaults silently break the loop

```bash
PLATFORM_CONTROL_EVENT_PUBLISHER_BACKEND=nats \
PLATFORM_CONTROL_ARTIFACT_STORE_BACKEND=s3 \
  docker compose -f docker-compose.yml -f docker-compose.local.yml \
    --profile apps --profile nats --profile minio --profile search up -d --wait
```

Both env vars are required. The defaults are `noop`/`local`: platform-control captures
the documents, reports the run `completed`, and **publishes nothing**, so DI sits idle
and the harness times out waiting for a document it was never handed. `--profile search`
is required too, or compose refuses the whole project.

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
| `no_dispatch_worker` | Run never left PENDING — nothing dispatched it. The local compose stack does not start a worker for every provider. |
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

**A pass justifies only the gates that actually ran.** Before recommending
`enabled: true`, read the harness's Gate coverage section / `checks.skipped_gates` in
`summary.json` and treat every skipped gate as unverified, not as verified-and-green
(#744). Persist the bundle under `docs/runbooks/evidence/` (the harness `--copy-evidence`
flag does this).

## 6. Flip the key

Two keys, two owners, and only one is yours:

- **Config key** — `template.enabled`. An operator flips it from the admin panel's
  Blueprints inventory (or `PUT /v1/sources/blueprint-templates/{overlay}/{template}/enablement`),
  recording the evidence link in `note`. See the `run-admin-panel` skill to drive the UI.
- **Code key** — moving a provider from `awaiting_evidence` to `live` is a **code change**
  in platform-control. Attach the evidence to that request; do not flip it on confidence.

## Boundaries

- Never weaken a gate, a query, or an assertion to make a run pass. Fix the thing it
  caught.
- Never reopen a `template_disabled_by_operator` key without asking — it is somebody's
  deliberate kill switch, and the remedy code exists to keep you from misreading it as an
  un-earned key.
- `acceptance` mode is a rehearsal. Reporting it as "the lock is open" is exactly the
  overstatement ADR-0030 exists to prevent.

## Reference

- [ADR-0030](../../../docs/adr/0030-acquisition-provider-enablement-lifecycle.md) — the lifecycle, the two-key lock (§2), the evidence workflow (§5), `RunMode.ACCEPTANCE` (§6)
- [ADR-0033](../../../docs/adr/0033-agentic-legal-reasoning.md) §4 — the build order, and why not to build the MCP server
- `tools/evidara-cli/src/evidara_cli/coverage.py` — the classification rules, with their platform-control counterparts cited
- `scripts/ch-fedlex-compose-e2e.sh` — the driver
- `.claude/skills/run-admin-panel/SKILL.md` — driving the admin UI to flip the config key
