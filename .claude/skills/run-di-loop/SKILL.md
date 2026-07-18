---
name: run-di-loop
description: Bring up the full document-intelligence loop locally and prove it end-to-end — acquisition → DI processing → document lifecycle → projection → searchable in legal-search (issue #628 / M13, ADR-0029/0033). Use when asked to run/verify the DI pipeline, populate a run's "DI Processing Status" / "Document Lifecycle" sections, debug why a run stays "pending", or observe NATS/MinIO/consumer state. Runs an ISOLATED docker compose stack (own project, remapped ports) so it never collides with a locally-running API/admin/legal-search.
---

# Run the document-intelligence loop (isolated, end-to-end)

The loop is: platform-control acquires → publishes `artifact-bundle-available` to NATS →
`di-consumer` reads the bundle from MinIO, processes it, publishes `document.processed` +
status events → `projection-bridge` forwards those to legal-search (searchable) and back to
platform-control `/v1/di/events` (so run pipeline-health leaves `pending`). Supported driver:
`scripts/ch-fedlex-compose-e2e.sh`.

## Why an isolated stack

A dev box usually already has a hand-run API (`:8000`), admin (`:3100`), Postgres (`:5432`),
and maybe legal-search. The compose stack publishes the same host ports and collides. Run it
as its **own project** (`-p evidara-di-e2e`) with **all ports remapped** via
[`di-e2e.override.yml`](di-e2e.override.yml) (uses `ports: !override` — plain YAML lists get
*appended*, not replaced, so you MUST use `!override` or the base `5432/8000` bind again).

## Prereqs / gotchas learned the hard way

- **`!override` on every remapped `ports:`** — otherwise both the base and remapped host ports
  bind and you get `port is already allocated` (needs Docker Compose ≥ 2.24; verified on 5.3.1).
- **`di-consumer` needs `DI_S3_*`** to read bundles from MinIO. The base `docker-compose.local.yml`
  omitted them, so every message dead-lettered with `BundleLoadError`. This override sets them
  (endpoint `http://minio:9000`, `minioadmin`/`minioadmin`). A permanent fix belongs in
  `docker-compose.local.yml` itself.
- **fedlex uses SPARQL, not firecrawl** — template `fedlex_sparql_constitution_de` needs no
  provider key, just outbound network to `https://fedlex.data.admin.ch/sparqlendpoint`
  (check it returns 200 first, or the run is `provider_failed`).
- **In-memory sink → metadata stub**: with DI surfaces unset the consumer does NOT persist
  canonical text, so legal-search indexes a stub (placeholder title, no body). The event/
  pipeline path goes fully green (all 4 stages `ok`), but `ch-fedlex-compose-e2e.sh`'s
  *search-by-title* assertion returns `search_failed`. Closing that last mile needs a real
  persistence surface (see base compose `lean-stack` profile / `document-service`).

## Bring it up

```bash
export PLATFORM_CONTROL_EVENT_PUBLISHER_BACKEND=nats \
       PLATFORM_CONTROL_ARTIFACT_STORE_BACKEND=s3 \
       EVIDARA_OPENSEARCH_HTTP_PORT=19200 EVIDARA_OPENSEARCH_METRICS_PORT=19600
OVR=.claude/skills/run-di-loop/di-e2e.override.yml
docker compose -p evidara-di-e2e \
  -f docker-compose.yml -f docker-compose.local.yml -f "$OVR" \
  --profile apps --profile nats --profile minio --profile search \
  up -d --build --wait \
  platform-control-api legal-search-api legal-search-seed nats-init di-consumer projection-bridge minio-init
# (naming the subset skips the two heavy Next.js images — admin + legal-search-frontend —
#  which the API-level e2e doesn't need)
```

Remapped host ports: platform-control-api `:18000`, legal-search-api `:13102`, nats `:14222`
(monitor `:18222`), minio `:19000` (console `:19001`), opensearch `:19200`, postgres `:15432`.

## Drive it

```bash
bash scripts/ch-fedlex-compose-e2e.sh \
  --pc-url http://localhost:18000 --ls-url http://localhost:13102 --query Bundesverfassung
```

Green looks like: `captured=1, html=1, DI accepted/processing/canonical_ready=1/1/1,
lifecycle processed=1`, and pipeline-health stages acquisition/document_intelligence/
projection/search all `ok`. (search-by-title assertion caveat above.) Evidence + per-poll JSON
land in `/tmp/ch-fedlex-compose-e2e/<ts>/`.

## Observe / debug

```bash
P="docker compose -p evidara-di-e2e"
$P ps
$P logs -f di-consumer        # where BundleLoadError / processing shows
$P logs projection-bridge     # NATS -> legal-search / platform-control forwarding
curl localhost:18000/v1/runs/<run>/{processing-status,document-lifecycle,pipeline-health}
```
- NATS JetStream + dead-letters: http://localhost:18222/jsz?streams=1
- MinIO bucket `evidara-raw-artifacts-dev`: http://localhost:19001 (minioadmin/minioadmin)
- See it in the admin run detail: start the admin with `PLATFORM_CONTROL_API_URL=http://localhost:18000`
  (see the `run-admin-panel` skill) and open `/#/runs-v2/<run>` — DI Processing Status +
  Document Lifecycle accordions populate.

## Tear down

```bash
docker compose -p evidara-di-e2e down -v
```
