# Lakehouse spike — Nessie + Trino + Iceberg (ADR-0036 Phase 0)

Proves the claim behind ADR-0036: a canonical surface can be written through a
**catalog** (a *named table*, not a hardcoded URI) and read back with **plain SQL** —
no delta-rs, no file paths anywhere in the consumer.

Runs on its own docker project + ports, so it coexists with the M13 loop stack
(which owns `9000/9001` for its MinIO).

## Run it

```bash
docker compose -p lakehouse-spike -f spikes/lakehouse/docker-compose.spike.yml up -d

# Write a canonical surface through the catalog. Run *in-network*: Nessie vends
# server-side storage config (it advertises `minio:9000`), so the data-file write
# only resolves from inside the compose network — which is also how the DI
# consumer runs.
NET=$(docker network ls --format '{{.Name}}' | grep lakehouse-spike | head -1)
docker run --rm --network "$NET" -v "$PWD/spikes/lakehouse:/spike" -w /spike python:3.12-slim \
  sh -c "pip install -q 'pyiceberg[s3fs,pyarrow]' && python write_surface.py"

# Read it back with SQL.
docker exec lakehouse-spike-trino-1 trino --execute \
  "SELECT document_id, title, in_force_from, in_force_until FROM iceberg.evidara.published_documents ORDER BY document_id"
```

Teardown: `docker compose -p lakehouse-spike -f spikes/lakehouse/docker-compose.spike.yml down -v`

## What it proved

- Nessie serves a working **Iceberg REST catalog** (`/iceberg/main/v1/config` → `warehouse: s3://warehouse`), with MinIO as the warehouse.
- `pyiceberg` creates the namespace + table and appends rows — **no Spark**.
- Trino sees the catalog (`SHOW SCHEMAS FROM iceberg` → `evidara`) and reads the surface by name.
- The ADR-0033 **temporal-validity** query, which is bespoke delta-rs code today, becomes a plain SQL filter:

  ```sql
  SELECT document_id, title FROM iceberg.evidara.published_documents
  WHERE in_force_from <= DATE '2026-07-18'
    AND (in_force_until IS NULL OR in_force_until >= DATE '2026-07-18')
  ```

## Ports

| service | url |
|---|---|
| Nessie (Iceberg REST) | http://localhost:19120 — catalog at `/iceberg/main` |
| Trino | http://localhost:18080 |
| MinIO / console | http://localhost:9010 / http://localhost:9011 (minioadmin) |

## Gotcha worth remembering

Nessie **vends storage config to clients**, overriding client-side `s3.endpoint`.
A host-run writer fails with `EndpointConnectionError: … http://minio:9000` even
when you pass `localhost:9010`. Run writers inside the compose network (as the DI
consumer will), or configure Nessie to advertise a host-reachable endpoint.
