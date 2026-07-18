# ADR-0036: Nessie + Trino + Iceberg lakehouse for the DI canonical surfaces

Status: Proposed
Date: 2026-07-18
Deciders: Platform / Document Intelligence
Related: ADR-0029 (containerized DI consumer; Spark/Databricks opt-in), ADR-0010 (Docling
canonical model), ADR-0033 (agentic legal reasoning — citation graph / temporal validity /
hybrid retrieval), #522 (projection bridge), #550 (pipeline-health), #628 (M13 coverage loop)

## Context

document-intelligence publishes four **canonical surfaces** — `published_documents`,
`published_sections`, `processing_manifests`, `published_commentary_insights` — as **Delta**
tables. Access is funnelled through one seam:

- **Config:** `SurfaceUris` (`DI_SURFACES_ROOT_URI` → per-surface URIs), `config/runtime.py`.
- **Writes:** `DeltaCanonicalSink` / `SparkDeltaCanonicalSink` (`persist/sinks.py`), selected in
  `processing_runtime.py`.
- **Reads:** `rescore.py` (`_read_delta_rows`) and the file-backed `document-service`
  (`service/store.py`), both via **delta-rs** against raw URIs.

This works, but couples every consumer to **low-level Delta table access at explicit URIs**:

- No **catalog** — surfaces are file paths, not named tables; no discovery, governance, or
  lineage.
- No **SQL** — ADR-0033's hard queries (citation graph, temporal validity, norm hierarchy) are
  bespoke delta-rs code instead of joins.
- No first-class **reproducibility** across surfaces — Delta time-travel is per-table; there is no
  "the corpus **as of** X" spanning all four surfaces, nor a data-level analogue to the
  evidence-gated coverage loop (#628).

## Decision

Move the four canonical surfaces to **Apache Iceberg** tables in a **Project Nessie** catalog,
queried via **Trino** (SQL). Consumers reference **named tables** (`nessie.evidara.published_documents`)
instead of URIs.

- **Table format → Iceberg.** Open, vendor-neutral, broad engine support. `SparkDeltaCanonicalSink`
  maps cleanly (Spark reads/writes Iceberg too).
- **Catalog → Nessie.** Chosen over Unity Catalog and Polaris because its **git-like model**
  (branches / tags / atomic multi-table commits) is the strongest fit for our own thesis:
  - "Corpus **as of** a date" (temporal validity, ADR-0033) → a Nessie **tag**.
  - Evidence-gated coverage loop (#628) → onboard a source on a **branch**, run the acceptance
    eval against it, **merge** only when green — CI-for-data mirroring the `enabled: true` flip.
  - Reproducible acceptance runs → pin each run to a **commit hash**.
  - Tradeoff accepted: Nessie is versioning-first, **not** fine-grained access control. If
    per-tenant governance becomes a hard requirement, revisit Unity Catalog (which governs Delta
    *and* Iceberg).
- **Query engine → Trino** for reads/analytics/joins; **pyiceberg** for DI's writes (Python-native,
  no Spark). DuckDB is the local stand-in for Trino where a single node suffices.

The `SurfaceUris`/sink/reader **seam already exists**, so this is implementing Iceberg variants
behind it, not a scattered rewrite.

## Phased roadmap (each phase shippable + reversible)

0. **Local spike** — Nessie + Trino + MinIO in compose; create one Iceberg surface; prove
   `pyiceberg` write → Trino read. De-risks the whole plan before touching DI.
1. **Write path** — `IcebergCanonicalSink` behind the sink interface; `register_surfaces` creates
   Iceberg tables/namespaces in Nessie. Gated by `DI_SURFACE_BACKEND=delta|iceberg` (Delta stays
   default until proven).
2. **Read path** — swap `rescore._read_delta_rows` and the `document-service` store to Trino/pyiceberg
   against Nessie; `SurfaceUris` resolves catalog table refs.
3. **Leverage** — move ADR-0033's citation-graph / temporal-validity / norm-hierarchy queries to
   Trino SQL joins; feed the hybrid-retrieval embeddings (ADR-0033 step 5) from Trino.
4. **Reproducibility** — Nessie branches/tags: branch-per-source-onboarding for #628, tag
   "corpus as of date", pin acceptance runs to a commit.
5. **Retire Delta** (or keep a Delta UniForm bridge only if an external Delta reader must remain).

## Consequences

- The lakehouse is the **substrate upgrade** under M13: the loop code is unchanged (it sits above
  the `SurfaceUris` seam), and the *hard* ADR-0033 phases (steps 2–5) become SQL instead of bespoke
  delta-rs. It does **not** block proving the M13 loop, which can land first on Delta.
- New local-dev services (Nessie, Trino) join the stack; the `search`/`nats`/`minio` profiles gain a
  `lakehouse` sibling.
- New deps: `pyiceberg`, a Trino client; Nessie + Trino images.
- Bumps the `document-intelligence` surface contract — coordinate with `document-service` and the
  projection bridge (#522).
