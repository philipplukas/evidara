# Local Vertical Slice Setup

## Goal

Run the core runtime flow locally with enough infrastructure to validate:

1. ingestion/control-plane actions (`platform-control`)
2. document processing runtime (`document-intelligence`)
3. search-serving projection/API behavior (`legal-search/api`)

## Start shared runtime dependencies

From repo root:

```bash
bash scripts/local-vertical-slice.sh up search
bash scripts/local-vertical-slice.sh status search
```

Dependency modes:

- `lite`: `postgres` only (lowest RAM)
- `search` (default): `postgres` + `opensearch`
- `full`: `postgres` + `opensearch` + `pubsub` emulator

For RAM planning and recommended machine profiles, see
`docs/setup/local-dev-ram-guide.md`.

### One-command full local stack with Docker Compose

If you want to avoid individual app startup commands, use Compose for both
infra and app services:

```bash
# starts postgres + opensearch + app services (API/admin/search/frontend)
bash scripts/local-vertical-slice.sh up-all search
bash scripts/local-vertical-slice.sh status-all search
```

`up-all`/`status-all`/`down-all` use isolated host ports for infra by default to avoid
collisions with existing local services:

- Postgres host port: `15432` (`EVIDARA_POSTGRES_HOST_PORT`)
- OpenSearch host HTTP port: `19200` (`EVIDARA_OPENSEARCH_HTTP_PORT`)
- OpenSearch metrics port: `19600` (`EVIDARA_OPENSEARCH_METRICS_PORT`)
- Pub/Sub host port (full mode): `18681` (`EVIDARA_PUBSUB_HOST_PORT`)

For full runtime wiring (adds pubsub emulator):

```bash
bash scripts/local-vertical-slice.sh up-all full
bash scripts/local-vertical-slice.sh status-all full
```

This compose path includes one-shot init/seed containers for:

- `platform-control` migrations + reference data seed
- `legal-search/api` search index seed

Optional `just` wrappers (if `just` is installed):

```bash
just up-search
just check-search
just up-full
just check-full
```

Health endpoints after startup:

- `http://127.0.0.1:8000/health` (platform-control API)
- `http://127.0.0.1:3100` (platform-control admin)
- `http://127.0.0.1:3102/health` (legal-search API)
- `http://127.0.0.1:3101` (legal-search frontend)

Automated check:

```bash
bash scripts/local-vertical-slice.sh check-all search
```

Examples:

```bash
# 4 GB machines: platform-control focused work
bash scripts/local-vertical-slice.sh up lite

# 8 GB machines: search API + UI work
bash scripts/local-vertical-slice.sh up search

# Full runtime wiring sessions
bash scripts/local-vertical-slice.sh up full
```

Print recommended local env wiring:

```bash
bash scripts/local-vertical-slice.sh env search
```

## Bootstrap platform-control

```bash
bash scripts/platform-control-demo.sh sync
bash scripts/platform-control-demo.sh migrate
bash scripts/platform-control-demo.sh seed
bash scripts/platform-control-demo.sh api
```

Expected health check:

```bash
curl -fsS http://127.0.0.1:8000/health
```

## Run legal-search API against local OpenSearch

```bash
cd legal-search/api
npm ci
npm run seed:index
npm run dev
```

`seed:index` creates the `documents` index with the canonical mapping
(`src/core/opensearch/documents-index.mapping.ts`) and points **both** the
`documents-read` (search) and `documents-write` (projection) aliases at it, so
the seeded Swiss caselaw surfaces immediately via `GET /v1/search`. `npm run
dev` performs the same idempotent bootstrap on startup.

Expected health check:

```bash
curl -fsS http://127.0.0.1:3102/health
```

## Run document-intelligence runtime services

Start runtime ingress consumer:

```bash
cd document-intelligence
uv sync
uv run document_intelligence_runtime_ingress
```

Optional: start document service surface for local detail reads:

```bash
uv run document_intelligence_document_service
```

## Validate end-to-end slice

- create/update a source + version and trigger a run in `platform-control`
- confirm downstream processing status and lifecycle events are visible in run detail endpoints
- query `legal-search/api` and verify projected content is searchable

## Teardown

```bash
bash scripts/local-vertical-slice.sh down search
```

If you started the full compose app stack:

```bash
bash scripts/local-vertical-slice.sh down-all search
```
