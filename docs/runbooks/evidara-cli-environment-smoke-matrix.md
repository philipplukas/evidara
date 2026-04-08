# Evidara CLI — environment smoke matrix (operator checklist)

Owner: Platform team
Last reviewed: 2026-04-08
Last verified: 2026-04-08
Applies to: local, dev, staging, prod

Use this as a **repeatable checklist** per environment (dev, staging, prod). Fill in **where you resolve base URLs and credentials** (Secret Manager, Cloud Run console, internal wiki — not this file).

CLI covers **HTTP APIs only**, not browser UX. For UI journeys use [Interaction flow validation](interaction-flow-validation.md) and Playwright.

## Before you run

From repo root (or `cd tools/evidara-cli`):

```bash
uv sync --group dev
```

Export env vars per [Environment strategy](../setup/environment-strategy.md) (section **Evidara CLI env vars (dev / staging / prod)**).

For workflow-level acceptance checks, also set:

- `EVIDARA_PLATFORM_CONTROL_ADMIN_URL`
- `EVIDARA_LEGAL_SEARCH_FRONTEND_URL`

## Matrix (copy and record results)

| Step | Command | dev | staging | prod | Notes |
|------|---------|-----|---------|------|-------|
| 1 | `uv run evidara platform-control ping` | | | | Expect `ok: true` JSON |
| 2 | `uv run evidara legal-search ping` | | | | Needs BFF + OpenSearch healthy |
| 3 | `uv run evidara legal-search search --q "test"` | | | | Optional; uses live search |
| 4 | `uv run evidara legal-search document <id>` | | | | Optional; needs known document id |
| 5 | `uv run evidara platform-control wizard-smoke` | | | | Only if wizard path deployed |
| 6 | `uv run evidara workflow mvp-acceptance` | | | | Canonical API-level MVP acceptance path; expects API + frontend/admin base URLs |
| 7 | `EVIDARA_CLI_SMOKE=1 bash scripts/smoke-evidara-cli.sh` | | | | From repo root; both pings |

Mark cells with pass/fail/date or link to a ticket.

## GitHub Actions (optional)

For the same two pings without a local machine: [Evidara CLI remote smoke — secrets](evidara-cli-remote-smoke-operator.md) and workflow **Evidara CLI remote smoke**.

## What this does not replace

- **Next.js / admin UI**, header links, RBAC denial UX → Playwright (`npm run e2e:interaction-flow`, staging interaction-flow workflow).
- **Contract correctness** → `contracts/api/` + CI; use `evidara openapi paths` for quick path discovery only.
