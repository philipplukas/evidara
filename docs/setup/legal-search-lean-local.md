# Local legal-search + Document Service (lean) — quick stack

Use this when you need **search + projections + `GET …/lean`** without staging URLs: metadata/TAR-89 work, projection replay, or UI checks.

## Prerequisites

- **Docker**
- **jq** on the host only if you use **up-split** or run `validate-tar89-metadata-local.sh` locally. The **lean-stack** Compose path installs `jq` inside the bootstrap container — you do not need it on the host for `docker compose --profile lean-stack up`.
- **curl** (for `replay` / `smoke` from the host)
- **Node / npm** for the frontend and admin apps

Notes:

- `shellcheck` is workstation-managed — install it with your OS package manager.
- Docker should come from the workstation baseline (for example MacConfig-managed machine setup), not from the repo.

OpenSearch’s `/_cluster/health?wait_for_status=…` long-poll and **HEAD** on index names have proven flaky with some local setups; `validate-tar89-metadata-local.sh` uses short **GET** polls and **GET + HTTP status** for index existence instead.

## All-in-one (recommended): Compose profile `lean-stack`

From the **monorepo root**:

```bash
docker compose --profile lean-stack up -d --build
```

Or the wrapper (equivalent):

```bash
./scripts/dev-lean-search-stack.sh up
```

This starts **OpenSearch**, **Document Service** (fixture: `scripts/fixtures/tar89-demo-content/`), a one-shot **bootstrap** job (indices, `documents-read` → `documents-write`, stale demo doc), and **legal-search-api-lean** on **3102** with `DOCUMENT_INTELLIGENCE_BASE_URL` set to the Document Service.

Then:

```bash
./scripts/dev-lean-search-stack.sh replay
```

Stop:

```bash
./scripts/dev-lean-search-stack.sh down
```

Host port overrides: `EVIDARA_OPENSEARCH_HTTP_PORT`, `EVIDARA_DOCUMENT_SERVICE_PORT`, `EVIDARA_LEGAL_SEARCH_API_PORT`.

## Cross-surface live workflow

For day-to-day legal-search ↔ control-panel validation, use the repo-root launcher:

```bash
npm run dev:cross-surface:live
```

This starts:

- the lean backend stack (`legal-search-api` on `3102`, plus OpenSearch and Document Service)
- legal-search frontend on `3101`
- platform-control admin on `3100`

The launcher waits for a local preflight before it reports ready.
If Docker is missing, the launcher now fails immediately with a setup hint instead of failing later inside Compose.

To run the same readiness check on demand:

```bash
npm run preflight:cross-surface:live
```

Use this loop:

1. UI work: mocked Playwright + Vitest
2. Flow validation: `npm run dev:cross-surface:live`, then backend-backed Playwright
3. Final confidence: run a staging smoke before shipping

The live browser flow expects:

- legal-search frontend: `http://localhost:3101`
- control-panel admin: `http://localhost:3100`
- legal-search API: `http://localhost:3102`

## Host BFF (hot reload) instead of the API container

```bash
./scripts/dev-lean-search-stack.sh up-split
eval "$(./scripts/dev-lean-search-stack.sh print-env)"
cd legal-search/api && npm run dev
```

`up-split` starts only OpenSearch + Document Service and runs bootstrap **on the host** (needs **jq**).

When running the split setup, use the preflight after the API comes up:

```bash
./scripts/dev-lean-search-stack.sh up-split
eval "$(./scripts/dev-lean-search-stack.sh print-env)"
cd legal-search/api && npm run dev
# in another shell, from repo root:
npm run preflight:cross-surface:live
```

## Optional checks

```bash
./scripts/dev-lean-search-stack.sh smoke   # Document Service /health + /lean only
```

## Full Compose “apps” stack

`docker-compose.local.yml` still provides **legal-search-api** with OpenCaseLaw seeding; it does **not** wire `DOCUMENT_INTELLIGENCE_BASE_URL`. For **lean + projections**, use **`lean-stack`** above.

## Related

- [Metadata quality plan status](../runbooks/metadata-quality-plan-status.md) (TAR-89 acceptance draft and reference trace in sections 3.5 and 6.8)  
- [scripts/README.md](../../scripts/README.md)
