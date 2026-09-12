# evidara-cli

Agent- and operator-friendly CLI for **platform-control** and **legal-search**, aligned with the canonical OpenAPI specs under `contracts/api/`.

## Install

From the monorepo root:

```bash
cd tools/evidara-cli
uv sync --group dev
uv run evidara --help
```

Or install the package into an environment of your choice (`pip install -e .` / `uv pip install -e .`).

## Environment

| Variable | Default | Purpose |
|----------|---------|---------|
| `EVIDARA_PLATFORM_CONTROL_URL` | `http://localhost:8000` | Platform-control base URL |
| `EVIDARA_PLATFORM_CONTROL_TOKEN` | _(empty)_ | `Authorization: Bearer …` for private Cloud Run (IAM) |
| `EVIDARA_PLATFORM_CONTROL_API_KEY` | _(empty)_ | `X-API-Key` when the API requires it |
| `EVIDARA_PLATFORM_CONTROL_ADMIN_URL` | `http://localhost:3100` | Platform-control admin base URL for workflow checks |
| `EVIDARA_LEGAL_SEARCH_URL` | `http://localhost:3102` | Legal-search BFF base URL (see OpenAPI `servers`) |
| `EVIDARA_LEGAL_SEARCH_FRONTEND_URL` | `http://localhost:3101` | Legal-search frontend base URL for workflow checks |
| `EVIDARA_LEGAL_SEARCH_TOKEN` | _(empty)_ | `Authorization: Bearer …` when configured |
| `EVIDARA_LEGAL_SEARCH_API_KEY` | _(empty)_ | `X-API-Key` when the API requires it |
| `EVIDARA_CLI_HUMAN` | `0` | Set to `1` for indented JSON (same as `--human`) |
| `EVIDARA_REPO_ROOT` | _(auto)_ | Optional override for `evidara openapi paths`; otherwise walks up from cwd for `contracts/api/` |
| `EVIDARA_CLI_SMOKE` | _(unset)_ | Set to `1` to run [`scripts/smoke-evidara-cli.sh`](../../scripts/smoke-evidara-cli.sh) (both `ping` subcommands) |

## Commands (wave 1)

```bash
# Discovery — finds monorepo root from cwd (e.g. tools/evidara-cli or repo root)
evidara openapi paths platform-control
evidara openapi paths legal-search
evidara openapi tags platform-control
evidara openapi tags legal-search

# Platform-control
evidara platform-control ping
evidara platform-control wizard-smoke
evidara platform-control ris-bootstrap --max-pages 1

# Workflow
evidara workflow mvp-acceptance

# Coverage loop (ADR-0030) — see below
evidara workflow coverage queue --actor agent
evidara workflow coverage templates --blocker provider_awaiting_evidence
evidara workflow coverage preflight --overlay ch --template <template_id>
evidara workflow coverage watch --run-id <run_id> --until processed
evidara workflow coverage drive --source-id <id> --source-version-id <id> \
  --requests-per-attempt 60 --max-attempts 3 --max-upstream-requests 500 --preflight-only
evidara workflow run evidence --run-id <run_id>
evidara workflow coverage enable --overlay ch --template <template_id> --evidence-run-id <run_id>

# Legal-search (needs OpenSearch + API running for ping/search)
evidara legal-search ping
evidara legal-search search --q "your query"
evidara legal-search document doc_001
```

Default stdout is **single-line JSON** suitable for agents; use `--human` or `EVIDARA_CLI_HUMAN=1` for readable formatting.

Errors print a JSON object with `ok: false`, `status_code`, and a truncated `body`, then exit with code 1.

## MVP acceptance workflow

Run the repeatable API-level MVP acceptance path across `platform-control`, `legal-search`, and the deployed/proxied web surfaces:

```bash
uv run evidara workflow mvp-acceptance
uv run evidara workflow mvp-acceptance --human
```

Against **private Cloud Run** (staging/dev), prefer the repo helper that logs in, discovers URLs, mints tokens, then runs this workflow:

```bash
./scripts/evidara-cloud-run-operator-session.sh dev
```

See [`docs/setup/gcp-local-cloud-run-auth.md`](../../docs/setup/gcp-local-cloud-run-auth.md) §4.1.

This command is the CLI-owned surface for scenarios 1–4 in [`docs/runbooks/mvp-acceptance-scenario-pack.md`](../../docs/runbooks/mvp-acceptance-scenario-pack.md):

- platform-control health + sources reachability
- legal-search query pack
- legal-search detail fetch and contract-shaped field checks
- legal-search/admin frontend proxy reachability

Browser-only validation remains owned by Playwright interaction-flow coverage in [`docs/runbooks/interaction-flow-validation.md`](../../docs/runbooks/interaction-flow-validation.md).

## Coverage loop (ADR-0030)

The operator path that brings a corpus online:

```
blueprint template → source + version → readiness → approve version →
acceptance run → DI processing → projection → searchable → evidence → enabled: true
```

`evidara workflow coverage` covers the parts that previously had to be hand-rolled with
`curl`. It deliberately does **not** re-implement the driver —
[`scripts/ch-fedlex-compose-e2e.sh`](../../scripts/ch-fedlex-compose-e2e.sh) already owns
create → approve → dispatch, the content gates and the evidence bundle. These commands
bracket it.

This is not ADR-0033 step 6 (the MCP server); see [ADR-0033](../../docs/adr/0033-agentic-legal-reasoning.md) §4.

### `coverage queue` — what to work on, and who may do it

```bash
uv run evidara workflow coverage queue --human
uv run evidara workflow coverage queue --actor agent      # what an agent may do itself
uv run evidara workflow coverage queue --actor human      # what it must hand over
```

The step the loop was missing (#909). Every other command here acts on a template or a
run you already chose; nothing read the denominator to *choose*. An agent without that
onboards enthusiastically and cannot say afterwards whether coverage improved — which
is why the coverage ledger (#907) was its hard dependency.

It reads `GET /v1/acquisition-coverage/queue` and splits the result by **actor**:

| Action | Actor | Why |
|---|---|---|
| `enumerate_denominator` | agent | Nothing states how much this jurisdiction publishes; every other answer is unstatable until it does. |
| `run_acceptance` | agent | A denominator exists and we hold less. An acceptance run is the ADR-0030 evidence primitive. |
| `await_pipeline` | agent | Captured, not yet processed. Re-running acquisition would lengthen the queue it is waiting on. |
| `investigate_holdings` | **human** | We hold *more* than the source publishes — a dedup failure or a wrong denominator. No run fixes it. |
| `resolve_refusal` | **human** | A refused run is a decision someone made. |

Two things it deliberately does not do.

**It does not re-rank.** The server states its ordering rule in the payload and this
echoes it verbatim. A second ranking in the client is how one rule ends up enforced
twice with the weaker copy winning.

**It never retries a refusal.** #854 moved the ADR-0030 two-key guard server-side, so
a key flip is refused where it cannot be bypassed — but the server cannot tell a
legitimate retry from an agent grinding at a refusal until it succeeds; both arrive as
ordinary requests. A closed config key is how an operator stops traffic at one portal
when an authority complains about load, and retrying it would override a human by
persistence rather than by permission. So `resolve_refusal` is always `human`, and
`test_no_refusal_is_ever_agent_actionable` fails if that changes.

Note `coverage enable` below is an **operator** command. No action this plan emits maps
to it.

A plan reports `complete: false` when the queue carried a reason this client does not
know, or when the server could not speak about every jurisdiction. *"There is no work"*
and *"there is work I do not understand"* are different answers.

### `coverage templates` — inventory by blocker, not by symptom

```bash
uv run evidara workflow coverage templates --human
uv run evidara workflow coverage templates --blocker provider_awaiting_evidence
```

Every row carries `blocker` and `remedy` codes so an agent branches on a code rather than
string-matching English:

| `blocker` | `remedy` | Dispatchable modes |
|---|---|---|
| `null` | `none` | acceptance, preview, production |
| `provider_awaiting_evidence` | `run_acceptance_loop` | acceptance |
| `template_never_enabled` | `run_acceptance_loop` | acceptance |
| `template_disabled_by_operator` | `reopen_config_key` | *(none — a kill switch acceptance never waives)* |
| `provider_scaffold` | `engineering` | *(none)* |

Filters: `--overlay`, `--provider`, `--template`, `--readiness`, `--blocker`, `--mode`.

The derivation is a **client-side mirror** of `RunService._require_launchable`. Because
platform-control already carries two copies that must stay in sync, this third one never
asserts alone: it cross-checks against the server's `launchable` field and exits nonzero
with `disagreements_with_server` when they diverge. `/v1/runs/readiness` stays
authoritative wherever a source version exists.

### `coverage preflight` — before anything is created

```bash
uv run evidara workflow coverage preflight --overlay ch --template <template_id> --human
```

`/v1/runs/readiness` needs a source *and* a version to already exist, so without this the
only way to learn a template is inert is to create both and be refused. Preflight is
read-only: it resolves the lock, resolves the acquisition spec through
`POST /v1/sources/blueprint-preview` (surfacing provider config errors and `plan_notes`),
and checks both services. It returns `recommended_mode` and a ready-to-run
`next_command`.

### `coverage watch` — a stall diagnosis, not a bare timeout

```bash
uv run evidara workflow coverage watch --run-id <run_id> --until processed
```

Joins `/v1/runs/{id}` with `/v1/runs/{id}/pipeline-health` and returns a `cause` code:
`run_refused_by_lock`, `no_dispatch_worker`, `publish_path_disabled`,
`di_consumer_silent`, `projection_stalled`. The last two-thirds of that list are the
failure modes that actually cost time driving the loop — notably
`PLATFORM_CONTROL_EVENT_PUBLISHER_BACKEND` defaulting to `noop`, which lets a run report
`completed` having published nothing.

`--until run` waits for a terminal run status; `--timeout 0` polls once and reports.

### `coverage drive` — the loop itself, inside a budget

```bash
uv run evidara workflow coverage drive \
  --source-id <source_id> --source-version-id <source_version_id> \
  --requests-per-attempt 60 --max-attempts 3 --max-upstream-requests 500 --human
```

Composes pre-flight → launch (`mode=acceptance`) → watch → diagnose → stop, and returns a
**journal**: what it did, what it spent, and why it stopped. It is the only command here
that dispatches a run on its own, so the budget is not optional and is stated on the
command line rather than hidden in agent code.

`--preflight-only` reports the budget and the readiness verdict and launches nothing. Use
it first against any source you have not driven before — it makes no upstream request.

**The three bounds, and why each is where it is:**

| Bound | Flag | What it stops |
|---|---|---|
| Attempts per source | `--max-attempts` (3) | "Retry until it works". N launches, then stop and report. |
| Upstream requests, whole loop | `--max-upstream-requests` (1000) | The bound a per-attempt cap misses — 10 bounded attempts is still an unbounded loop. |
| Backoff | `--backoff` (30s), `--backoff-factor` (2), `--max-backoff` (300s) | Bursting a portal that is already struggling. |

`--requests-per-attempt` is **required and has no default**: platform-control does not
report how many upstream requests a run made (`estimated_request_count` is computed when a
provider plans and is never persisted or serialised), so the ceiling can only charge a cost
the caller declares from the spec. It is reconciled **upward** after each attempt against
the run's captured/artifact counts — a lower bound on what was fetched — and never
downward.

**What it will not do**, each with a test that fails if the property is removed:

- **retry a refusal** — pre-flight, launch or diagnosis; the loop stops with attempts and
  ceiling unspent. No server-side check can catch a retried refusal: it is an ordinary
  request.
- **rewrite the spec.** `POST /v1/sources/{id}/versions` is reachable and unused — a new
  spec is exactly what the declared per-attempt cost cannot bound.
- **flip `enabled: true`.** ADR-0030's second key is a human's (#854); `coverage enable`
  below is an operator command.

It only ever answers a **failed run** with another attempt. An environment defect
(`no_dispatch_worker`, `publish_path_disabled`) or downstream backlog is reported, because
another run would add load and no information.

### `workflow run evidence` — the ADR-0030 acceptance verdict

```bash
uv run evidara workflow run evidence --run-id <run_id> --human
```

`artifacts.acceptance_verdict.is_acceptance_evidence` decides whether the run may justify
flipping `enabled: true`. It refuses a SHADOW-mode version outright — cassette replay
never touches the live portal, so a green SHADOW run proves nothing about it (ADR-0030
§2) — as well as a refused run, a non-acceptance mode, and a run that captured nothing.
A pass still carries the reminder that it justifies only the gates that actually ran
(#744).

### `coverage enable` — flip the config key, then prove it flipped

```bash
uv run evidara workflow coverage enable \
  --overlay ch --template <template_id> --evidence-run-id <run_id> \
  --note "Evidence bundle: docs/runbooks/evidence/<dir>" --human
```

The loop's last step, and the one worth getting wrong quietly. Enabling **requires** an
`--evidence-run-id`.

**The guard lives in platform-control, not in this command (#854).** It used to derive
the refusals here, while the admin panel — hitting the same endpoint — required only a
non-empty free-text note. Two clients, two rules, and the easier path was the weaker one,
so this command's guard was advisory. `PUT /v1/sources/blueprint-templates/{overlay}/
{template}/enablement` now re-derives the acceptance verdict, binds the cited run to the
template, checks both ADR-0030 ordering rules and reads the write back; it answers **409**
with the codes below, and this command reproduces them verbatim in
`artifacts.refusals`. The codes are unchanged in spelling and meaning — they are a public
interface — and are the same ones the admin panel now renders.

| code | meaning |
|---|---|
| `no_evidence_run_cited` | ADR-0030 §5: the key is turned after evidence, not on confidence. |
| `evidence_run_not_found` | No run exists with the cited id, so nothing was re-derived. |
| `evidence_run_is_not_acceptance_evidence` | The run failed the verdict — read `acceptance_verdict.refusals`. |
| `evidence_run_provider_unresolved` | The run's provider could not be resolved, so nothing ties it to this template. Refused rather than skipped-and-passed (#744). |
| `evidence_run_provider_mismatch` | The run used a different acquisition provider. |
| `evidence_run_template_mismatch` | The run's source version was created from a **different** blueprint template. Same provider is not the same template — for `lexfind` that would be 26 cantons plus Bund off one canton's run (#846). |
| `evidence_run_template_unbindable` | The run's version records no blueprint provenance and its acquisition spec is not this template's, so it cannot be bound to this template at all (#846). |
| `evidence_run_capture_count_unknown` | The run reports no `captured_resources_count`, so that check did not run. |
| `no_audit_note_recorded` | A flip in either direction has to say why. Shutting a portal off with no recorded reason is as unauditable as arming one. |
| `classification_disagrees_with_server` | The client-side lock mirror disagrees with the server's `launchable`. **The one refusal still derived here** — the server producing `launchable` cannot check itself against it — and this is the one command where that derivation gates a write. |
| `provider_not_live_not_acknowledged` | ADR-0030 §2 admits `enabled: true` only for a LIVE provider. `test_blueprint_provider_parity.py` asserts that over `source_blueprints.yaml` but **not** over the override table this writes, so the ordering is enforced here. `--acknowledge-provider-below-live` arms it anyway. |
| `operator_kill_switch_not_acknowledged` | The key was shut by an operator. Pass `--reopen-operator-kill-switch` only after asking them. Keyed off the config key's *provenance*, never off `blocker` — `blocker` is single and priority-ordered, so a `provider_scaffold` (the fail-closed default for an unresolvable provider) hides the kill switch. |

A refusal writes nothing (`side_effect_level: none`). The one exception is a refusal the
server raises *after* writing the override row, when its own read-back does not confirm
the flip: that comes back `write_attempted: true` and `side_effect_level: reversible`,
because claiming nothing happened would be false.

What the three `side_effect_level` values mean, and what a consumer is expected to do differently for each, is written up in [docs/components/workflow-command-envelope.md](../../docs/components/workflow-command-envelope.md).

**"Already in the desired state" is a pair, not a boolean** — the requested value *and*
an `override` provenance. `--disable` on a key that merely reads `false` today still
writes: `never_turned` is waived by ADR-0030's acceptance mode and an operator's `false`
is not (#768), so short-circuiting on the boolean would report a kill switch that was
never installed while live traffic kept flowing. The mirror case writes too — a key open
only by shipped default has no evidence citation recorded against it.

A flip that lands still comes back `needs_human` rather than `passed` when a check did
not pass: an evidence binding weaker than template-exact, arming the key ahead of the code
key, and reopening somebody's kill switch. `ok` tracks the write; `status` tracks whether
a human still has something to confirm.

**The `200` is not the proof.** The server re-reads the template after writing and
requires *both* that the effective key is what was asked for **and** that the read model
attributes it to an operator `override` — either alone is also satisfied by a write that
silently did nothing (#631, #713) — and reports that as `applied`. This command re-reads
`/v1/sources/blueprint-templates` as well and exits nonzero if the two disagree.

Flipping the config key does not open the code key: when the provider is short of `live`
the envelope says which modes the lock still admits. Turning the key **off** is a kill
switch — it needs no evidence but does need `--note`.

**The binding between the cited run and the template is exact** where the run's source
version records a blueprint template, which is every version created from one. Reported as
`artifacts.evidence_binding`:

| strength | meaning |
|---|---|
| `template` | The version records this overlay and provider template. Exact; nothing left to confirm. |
| `acquisition_spec` | The version has no blueprint provenance, but its spec equals this template's resolved spec. Near-exact — allowed, and reported `needs_human`. |
| `provider` / `none` | Too weak to enable on. Refused, not reported. |

This is what #846 fixed. Provider-level agreement used to be enough, and all 26 cantons
plus Bund sit behind the single `lexfind` provider, so one canton's run satisfied the
check for every LexFind template.

**Agent skill:** `.claude/skills/coverage-acceptance-loop/SKILL.md` routes the whole loop,
including the compose env vars whose defaults silently break it.

### RIS OGD vertical slice (delegates to repo script)

Runs [`scripts/bootstrap-ris-source.py`](../../scripts/bootstrap-ris-source.py): create AT RIS source, version, approve, preview run.

```bash
cd tools/evidara-cli
uv run evidara platform-control ris-bootstrap --max-pages 1
# Optional: --applikation Vfgh --process-di
```

Uses the same `EVIDARA_PLATFORM_CONTROL_*` env vars as `ping` / `wizard-smoke`. The script prints human-readable progress to stdout/stderr (not JSON).

## Checks

```bash
bash scripts/check-evidara-cli.sh
```

Or from `tools/evidara-cli`:

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run pytest
```

CI: `.github/workflows/evidara-cli.yml` runs `scripts/check-evidara-cli.sh` when this package or the bootstrap script changes.

Manual **remote** smoke (Actions → run workflow; pick GitHub **environment** `dev` or `staging`, OIDC mints Cloud Run Bearer tokens; optional repository API-key secrets): `.github/workflows/evidara-cli-remote-smoke.yml`.

**Operator runbooks:** [environment smoke matrix](../../docs/runbooks/evidara-cli-environment-smoke-matrix.md) (dev/staging/prod checklist), [GitHub secrets for remote smoke](../../docs/runbooks/evidara-cli-remote-smoke-operator.md). **Cursor:** project skill `.cursor/skills/evidara-cli-workflow/SKILL.md` (CLI vs Playwright router for agents).

**Operator runbooks:** [environment smoke matrix](../../docs/runbooks/evidara-cli-environment-smoke-matrix.md) (dev/staging/prod checklist), [GitHub secrets for remote smoke](../../docs/runbooks/evidara-cli-remote-smoke-operator.md). **Cursor:** project skill `.cursor/skills/evidara-cli-workflow/SKILL.md` (CLI vs Playwright router for agents).

Pre-commit runs the same check when files under `tools/evidara-cli/` (or related scripts/workflow) change.

## Roadmap (extend on demand)

Add new **workflow** subcommands when a second golden path is repeated often (wrap `scripts/*.py` or short HTTP sequences). Prefer **not** mirroring every OpenAPI operation in the CLI. Candidates discussed: vertical-slice command (platform-control seed + legal-search query), richer `evidara openapi` (methods per path), optional OpenAPI-generated types.
