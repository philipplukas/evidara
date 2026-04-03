# Local Vertical Slice Setup

## Goal

Run the core runtime flow locally with enough infrastructure to validate:

1. ingestion/control-plane actions (`platform-control`)
2. document processing runtime (`document-intelligence`)
3. search-serving projection/API behavior (`legal-search/api`)

## Start shared runtime dependencies

From repo root:

```bash
bash scripts/local-vertical-slice.sh up
bash scripts/local-vertical-slice.sh status
```

This starts:

- `postgres` (platform-control)
- `opensearch` (legal-search API)
- `pubsub` emulator (event-driven wiring)

Print recommended local env wiring:

```bash
bash scripts/local-vertical-slice.sh env
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

Expected health check:

```bash
curl -fsS http://127.0.0.1:3001/health
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
bash scripts/local-vertical-slice.sh down
```
