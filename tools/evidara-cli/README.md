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

# Platform-control
evidara platform-control ping
evidara platform-control wizard-smoke
evidara platform-control ris-bootstrap --max-pages 1

# Workflow
evidara workflow mvp-acceptance

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

This command is the CLI-owned surface for scenarios 1–4 in [`docs/runbooks/mvp-acceptance-scenario-pack.md`](../../docs/runbooks/mvp-acceptance-scenario-pack.md):

- platform-control health + sources reachability
- legal-search query pack
- legal-search detail fetch and contract-shaped field checks
- legal-search/admin frontend proxy reachability

Browser-only validation remains owned by Playwright interaction-flow coverage in [`docs/runbooks/interaction-flow-validation.md`](../../docs/runbooks/interaction-flow-validation.md).

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
