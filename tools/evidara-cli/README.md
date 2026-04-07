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
| `EVIDARA_PLATFORM_CONTROL_API_KEY` | _(empty)_ | `X-API-Key` when the API requires it |
| `EVIDARA_LEGAL_SEARCH_URL` | `http://localhost:3102` | Legal-search BFF base URL (see OpenAPI `servers`) |
| `EVIDARA_LEGAL_SEARCH_TOKEN` | _(empty)_ | `Authorization: Bearer …` when configured |
| `EVIDARA_LEGAL_SEARCH_API_KEY` | _(empty)_ | `X-API-Key` when the API requires it |
| `EVIDARA_CLI_HUMAN` | `0` | Set to `1` for indented JSON (same as `--human`) |
| `EVIDARA_REPO_ROOT` | _(auto)_ | Optional override for `evidara openapi paths`; otherwise walks up from cwd for `contracts/api/` |

## Commands (wave 1)

```bash
# Discovery — finds monorepo root from cwd (e.g. tools/evidara-cli or repo root)
evidara openapi paths platform-control
evidara openapi paths legal-search

# Platform-control
evidara platform-control ping
evidara platform-control wizard-smoke

# Legal-search (needs OpenSearch + API running for ping/search)
evidara legal-search ping
evidara legal-search search --q "your query"
evidara legal-search document doc_001
```

Default stdout is **single-line JSON** suitable for agents; use `--human` or `EVIDARA_CLI_HUMAN=1` for readable formatting.

Errors print a JSON object with `ok: false`, `status_code`, and a truncated `body`, then exit with code 1.

## Checks

```bash
cd tools/evidara-cli
uv run ruff check src tests
uv run ruff format --check src tests
uv run pytest
```
