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
evidara workflow coverage templates --blocker provider_awaiting_evidence
evidara workflow coverage preflight --overlay ch --template <template_id>
evidara workflow coverage watch --run-id <run_id> --until processed
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
`--evidence-run-id`; the command re-derives the ADR-0030 acceptance verdict for that run
and refuses when it does not earn the flip. Refusal codes:

| code | meaning |
|---|---|
| `no_evidence_run_cited` | ADR-0030 §5: the key is turned after evidence, not on confidence. |
| `evidence_run_is_not_acceptance_evidence` | The run failed the verdict — read `acceptance_verdict.refusals`. |
| `evidence_run_provider_unresolved` | The run's provider could not be resolved, so nothing ties it to this template. Refused rather than skipped-and-passed (#744). |
| `evidence_run_provider_mismatch` | The run used a different acquisition provider. |
| `evidence_run_capture_count_unknown` | The run reports no `captured_resources_count`, so that check did not run. |
| `classification_disagrees_with_server` | The client-side lock mirror disagrees with the server's `launchable`. This is the one command where that derivation gates a write, so a disagreement is disqualifying. |
| `provider_not_live_not_acknowledged` | ADR-0030 §2 admits `enabled: true` only for a LIVE provider. `test_blueprint_provider_parity.py` asserts that over `source_blueprints.yaml` but **not** over the override table this writes, so the ordering is enforced here. `--acknowledge-provider-below-live` arms it anyway. |
| `operator_kill_switch_not_acknowledged` | The key was shut by an operator. Pass `--reopen-operator-kill-switch` only after asking them. Keyed off `config_key`, never off `blocker` — `blocker` is single and priority-ordered, so a `provider_scaffold` (the server's fail-closed default for an unresolvable provider) hides the kill switch. |

A refusal writes nothing (`side_effect_level: none`). What the three `side_effect_level` values mean, and what a consumer is expected to do differently for each, is written up in [docs/components/workflow-command-envelope.md](../../docs/components/workflow-command-envelope.md).

**"Already in the desired state" is a pair, not a boolean** — the requested value *and*
an `override` provenance. `--disable` on a key that merely reads `false` today still
writes: `never_turned` is waived by ADR-0030's acceptance mode and an operator's `false`
is not (#768), so short-circuiting on the boolean would report a kill switch that was
never installed while live traffic kept flowing. The mirror case writes too — a key open
only by shipped default has no evidence citation recorded against it.

A flip that lands still comes back `needs_human` rather than `passed` when a check did
not pass: the provider-level evidence binding always, and arming the key ahead of the
code key. `ok` tracks the write; `status` tracks whether a human still has something to
confirm.

**The `200` is not the proof.** After the `PUT` the command re-reads
`/v1/sources/blueprint-templates` and requires *both* that the effective key is what was
asked for **and** that the read model attributes it to an operator `override`. Either
alone is also satisfied by a write that silently did nothing — the failure mode behind
#631 and #713 — so a mismatch exits nonzero with `verification.problems`
(`read_back_disagrees`, `no_override_recorded`).

Flipping the config key does not open the code key: when the provider is short of `live`
the envelope says which modes the lock still admits. Turning the key **off** is a kill
switch — it needs no evidence but does need `--note`.

The binding between the cited run and the template is **provider-level**, reported as
`artifacts.evidence_binding`. `SourceVersionResponse` exposes no `overlay_id` /
`provider_template_id`, so a same-provider run of a different template also satisfies the
check — and for `lexfind` that is all 26 cantons plus Bund behind one name, so one run
covers every LexFind template. The envelope marks that check `passed: false` so it is
confirmed by a human rather than read as proven; #846 tracks binding it near-exactly by
comparing the version's acquisition spec against `POST /v1/sources/blueprint-preview`.

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
