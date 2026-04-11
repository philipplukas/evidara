---
name: evidara-cli-workflow
description: >-
  When to use evidara-cli vs Playwright for Evidara; env vars, smoke script, and
  OpenAPI discovery. Use for API smoke, operator checklists, or avoiding UI tests
  for backend-only validation.
---

# Evidara CLI vs UI smoke (agent router)

## When to use what

| Goal | Tool |
|------|------|
| Platform-control + legal-search **reachable**, auth headers | `evidara` CLI: `platform-control ping`, `legal-search ping` |
| **Both pings in one shot** (script) | `EVIDARA_CLI_SMOKE=1 bash scripts/smoke-evidara-cli.sh` (repo root) |
| **Search / document** against live BFF | `evidara legal-search search`, `evidara legal-search document` |
| **Wizard path** (if deployed) | `evidara platform-control wizard-smoke` |
| **List OpenAPI paths** (no HTTP) | `evidara openapi paths platform-control` / `legal-search` |
| **List OpenAPI operation tags** (no HTTP) | `evidara openapi tags platform-control` / `legal-search` (filter output for **`agent-discovery`** to see read-only MVP discovery operations tagged in the canonical specs) |
| **Browser journeys**, RBAC, screenshots, release evidence | Playwright — [interaction-flow-validation.md](../../../docs/runbooks/interaction-flow-validation.md), `scripts/run-interaction-flow-local.sh` |

Do **not** use the CLI to assert **UI layout**, **client-side routing**, or **cross-surface header** behavior; use Playwright.

## Invariants

- API shapes live in **`contracts/api/`** (canonical). The CLI aligns with those specs; do not invent paths.
- **Never** commit API keys, bearer tokens, or URLs with embedded credentials. Use env vars from Secret Manager / operator runbook.

## Env vars (names only)

See [tools/evidara-cli/README.md](../../../tools/evidara-cli/README.md) and [environment-strategy.md](../../../docs/setup/environment-strategy.md) (`EVIDARA_PLATFORM_CONTROL_*`, `EVIDARA_LEGAL_SEARCH_*`).

## Install / run (typical)

```bash
cd tools/evidara-cli && uv sync --group dev && uv run evidara --help
```

## Operator runbooks (human checklist)

- [evidara-cli-environment-smoke-matrix.md](../../../docs/runbooks/evidara-cli-environment-smoke-matrix.md)
- [evidara-cli-remote-smoke-operator.md](../../../docs/runbooks/evidara-cli-remote-smoke-operator.md)

## Contributing / hooks

Touching `tools/evidara-cli/**` or related workflows: see [CONTRIBUTING.md](../../../CONTRIBUTING.md) and run `pre-commit run evidara-cli-check --all-files` when applicable.
