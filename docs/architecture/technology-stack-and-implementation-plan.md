# Technology Stack And Implementation Plan

## Status

**Historical planning record. Superseded for runtime hosting and deployment by
[ADR-0029: Self-Hosted Hetzner Runtime](../adr/0029-self-hosted-hetzner-runtime.md).**

> **Read this before the rest of the page.** Everything below that recommends a
> **runtime, deployment, or managed-service** choice — Cloud Run, Cloud Run jobs, Pub/Sub,
> Cloud SQL, GCS, Databricks (workspaces, Lakeflow Jobs, Asset Bundles, Unity Catalog,
> PySpark), Databricks SQL warehouses — **no longer describes how Evidara runs.** The
> system now runs on a self-hosted single-node k3s cluster on a Hetzner dedicated server,
> with NATS JetStream, MinIO, CloudNativePG Postgres, OpenSearch, and Nessie + Trino
> in-cluster. For the actual runtime, see
> [System Context — Deployment Topology](system-context.md#deployment-topology) and
> [Storage Model](storage-model.md).
>
> What in this document **still stands**: the language split (TypeScript for
> user-facing/control-plane services, Python for acquisition and document intelligence,
> SQL for data modeling, HCL for infrastructure), the component boundaries, the
> contract-first posture, and the "no extra backend language without an ADR" rule. Those
> are the parts formalized in
> [ADR-0009: Technology Stack and Language Boundaries](../adr/0009-technology-stack-and-language-boundaries.md).
>
> The page is kept unrewritten as a record of what was planned and why. Do not use it as a
> source of truth for infrastructure.

This document defined the recommended technology choices, language boundaries, tooling, and phased implementation approach for Evidara.

## Purpose

Provide one architecture-level reference for which languages, runtimes, tools, and deployment patterns should be used in each part of the platform.

## Goals

- Keep the system aligned with the documented component boundaries
- Minimize unnecessary language and tooling sprawl
- Choose technologies based on the data shape, access pattern, and operational needs of each domain
- Make implementation order explicit so the stack can grow deliberately

## Decision Summary

Evidara should use a small number of primary technologies:

- TypeScript for user-facing and control-plane application services
- Python for acquisition workers, parsing, NLP, and Databricks processing
- SQL for warehouse-native transformations and tests
- Terraform for infrastructure
- OpenAPI and JSON Schema for contracts

This means the platform is intentionally polyglot, but only in a controlled way:

- TypeScript for APIs and frontend
- Python for data acquisition and document intelligence
- SQL for data modeling
- HCL for infrastructure

Do not add Scala, Java, Go, Rust, or another backend language in MVP unless a later ADR justifies it.

## Architecture Principles

- `platform-control` owns source lifecycle, runs, approvals, connectors, and reference data
- `document-intelligence` owns canonical processing and Delta truth
- `legal-search` owns serving projections and user-facing search
- Contracts live in `contracts/` and remain the only valid cross-component interface
- Delta is the source of truth for processed document intelligence
- OpenSearch is a serving projection, not a system of record
- Start with the narrowest viable stack and expand only when concrete requirements demand it

## Recommended Stack By Area

| Area | Primary language | Runtime | Core tools | Purpose |
|------|------------------|---------|------------|---------|
| platform-control API | TypeScript | Node.js on Cloud Run | NestJS, Postgres, OpenAPI, Pub/Sub client | Control-plane APIs, run orchestration, source management |
| connector workers | Python | Cloud Run jobs or worker processes | provider/API clients, HTTP clients, parsing helpers, GCS client | Fetch upstream content and register artifacts |
| document-intelligence | Python + SQL | Databricks | PySpark, Delta, dbt, spaCy, Docling, Lakeflow Jobs | Parse, normalize, and persist canonical truth |
| legal-search frontend | TypeScript | Next.js App Router | React, TanStack Query, Orval, Biome, Vitest | Search UI and document exploration |
| legal-search BFF | TypeScript | Node.js on Cloud Run | NestJS, OpenSearch client, OpenAPI | Search and detail APIs over serving projections |
| contracts | YAML + JSON | Build-time only | OpenAPI 3.1, JSON Schema 2020-12, validation tooling | Explicit cross-component boundaries |
| infra | HCL + YAML | CI/CD and cloud control plane | Terraform, GitHub Actions, Databricks Asset Bundles | Provisioning and deployment |
| docs and runbooks | Markdown | Repo-native | doc checks, link checks, ADRs | Architecture and operations guidance |

## Languages And Why

## TypeScript

Use TypeScript for application services and the frontend:

- `platform-control`
- `legal-search` frontend
- `legal-search` BFF

Reasons:

- Strong fit for request-response APIs, UI code, and shared OpenAPI-generated clients
- Matches the existing `legal-search` codebase
- Keeps the user-facing and control-plane parts of the platform in one language family
- Works naturally with NestJS and Next.js

Target baseline:

- Node.js 20 or newer for new TypeScript services
- strict TypeScript configuration by default

## Python

Use Python for:

- connector workers
- acquisition helpers
- parsing and normalization
- NLP and extraction
- Databricks jobs

Reasons:

- Best ecosystem fit for document parsing, NLP, scraping, provider SDKs, and Databricks
- Natural fit for spaCy, Docling, and PySpark
- Easier to use for mixed protocol acquisition and text-heavy data processing than forcing everything into TypeScript

Target baseline:

- `pyproject.toml`-based packaging for Python components
- Databricks-runtime-compatible Python for processing jobs
- local Python baselines can remain lightweight during early scaffolding

## SQL

Use SQL for:

- warehouse-native transformations
- canonical shaping after parsing
- QA marts
- analytical projections inside Databricks

Reasons:

- Best fit for tabular transformations once the document has already been normalized into structured records
- Keeps data modeling readable and testable
- Pairs well with dbt and Databricks SQL warehouses

## Terraform

Use Terraform for all infrastructure provisioning:

- GCP
- Databricks
- GitHub automation where needed

Reasons:

- Repo docs already establish infrastructure-as-code as a principle
- Terraform remains the simplest common tool across GCP and Databricks resources

## Component-Level Recommendations

## Platform Control

### Recommended language and framework

- TypeScript
- NestJS
- Cloud Run for runtime
- Postgres on Cloud SQL

### Why

`platform-control` is the operational control plane. It is API-heavy, stateful, and well-served by a typed application framework and relational storage.

NestJS is a good fit because:

- it is built for scalable Node.js server-side applications
- it supports TypeScript natively
- it can run on Express or Fastify
- it has strong support for validation and OpenAPI integration

### Responsibilities

- source CRUD
- source-version CRUD
- run lifecycle APIs
- approvals
- reference data
- connector orchestration metadata
- source snapshot and artifact registration
- bundle-manifest publication and `artifact_bundle.available` emission

### Storage

- Postgres for operational records
- GCS for raw artifact and bundle-manifest storage

### Runtime pattern

- Cloud Run service for the API
- Pub/Sub publisher for pipeline progression

### Connector ownership

Connector ownership stays with `platform-control`, even if connector execution happens in separate workers or jobs.

### Implementation notes

- keep source, source-version, run, artifact, and reference-data models normalized in Postgres
- keep API contracts explicit in `contracts/api/`
- prefer additive schema changes and explicit state machines

## Connector Workers

### Recommended language and runtime

- Python
- Cloud Run jobs for scheduled, backfill, and one-shot runs
- later worker processes only if long-lived queue consumption becomes necessary

### Why

Connector work is upstream-facing and often deals with:

- provider SDKs
- file downloads
- protocol quirks
- scraping
- auth and retries
- content preservation

Python gives the strongest ecosystem for this without coupling acquisition too tightly to the control-plane API service.

### Recommended tool posture

- use provider APIs when available
- use plain HTTP fetching by default for scrape-only sites
- use headless browser automation only when JavaScript rendering is truly required
- preserve raw upstream responses before normalization

### What workers produce

- raw artifacts and bundle manifests in object storage
- artifact metadata and lineage for `platform-control`
- optional acquisition metadata hints

## Document Intelligence

### Recommended language and runtime

- Python as the primary language
- SQL as the secondary language for modeling
- Databricks as the runtime

### Core tools

- PySpark for distributed processing where needed
- Delta tables for canonical truth
- dbt for SQL transforms, tests, and internal marts
- spaCy for rule-based NLP and extraction support
- Docling as an internal document normalization abstraction where useful
- Databricks Lakeflow Jobs for orchestration
- Databricks Asset Bundles for deployment

### Why

This component is fundamentally a document-processing and data-engineering system. Databricks is already the documented canonical runtime for this domain, and Python is the strongest fit for parsing and NLP.

### What to use SQL/dbt for

- table shaping after parsing
- incremental models
- tests
- QA and quality marts
- internal aggregates

### What not to use dbt for

- upstream acquisition
- main parser logic
- scraping
- core spaCy execution

### Data modeling posture

- bronze/raw for ingestion bookkeeping and reproducibility
- silver/canonical for `documents`, `sections`, `processing_manifest`, and later `citations`
- gold/internal only for QA, ops, and analyst-facing marts

Do not use `document-intelligence` gold as a substitute for the serving layer owned by `legal-search`.

### Workflow posture

- start with one source family
- implement `documents` and `sections` from day one
- add citations and canonical jurisdiction assignment after the canonical path is stable
- do not add Dagster or Airflow in MVP

## Legal Search

### Frontend

- TypeScript
- Next.js App Router
- React
- TanStack Query for client-heavy interactive areas
- Orval-generated API clients and hooks
- Biome for lint/format
- Vitest and Testing Library for frontend tests

### BFF

- TypeScript
- NestJS
- Cloud Run

### Why

This aligns with the existing repo, the accepted ADRs, and a server-first UI model. The frontend remains isolated from OpenSearch internals, while the BFF owns search/domain shaping.

### Search engine

- OpenSearch

Use OpenSearch for:

- full-text retrieval
- facets and aggregations
- low-latency serving projections
- later vector search where needed

Do not allow the frontend to query OpenSearch directly.

## Contracts

### Formats

- OpenAPI 3.1 for synchronous REST APIs
- JSON Schema Draft 2020-12 for domain schemas and event payloads

### Tooling

- Redocly for OpenAPI linting
- Orval for TypeScript client generation where appropriate
- JSON Schema validation in CI

### Guidance

- TypeScript clients should be generated from `contracts/`, not handwritten against service internals
- Python runtime code can stay slightly looser while contracts are still settling, but CI-level contract validation should be strict
- once the boundary stabilizes, harden Python adapters against the settled schemas

## Infrastructure And Deployment

## Cloud Platform

Use GCP for:

- Cloud Run
- Cloud SQL
- Cloud Storage
- Pub/Sub
- Secret Manager
- Artifact Registry

Use Databricks for:

- Delta storage and processing
- jobs and data pipelines

### Why this split

- GCP is a good fit for application runtimes, operational databases, messaging, and object storage
- Databricks is a better fit for canonical document processing and Delta-backed analytical storage

## Deployment Tooling

- Terraform for cloud resource provisioning
- GitHub Actions for CI/CD orchestration
- Artifact Registry for container images
- Databricks Asset Bundles for Databricks job deployment

## Secrets And Config

- Google Secret Manager for runtime secrets
- per-environment Terraform variables under `infra/env/`
- no secrets in Git

## Data Stores And Messaging

| Concern | Technology | Owner |
|--------|------------|-------|
| control-plane relational data | Cloud SQL for PostgreSQL | platform-control |
| raw artifacts and bundle manifests | Cloud Storage | platform-control |
| canonical processed truth | Delta tables | document-intelligence |
| search-serving projection | OpenSearch | legal-search |
| async pipeline progression | Pub/Sub | shared via contracts |

## Development Tooling

## Node/TypeScript

- npm for package management to match the current repo state
- Biome for lint and formatting
- TypeScript strict mode
- Orval for generated clients
- Vitest for TypeScript unit tests

## Python

- `pyproject.toml` as the package definition baseline
- keep dependencies minimal in early scaffolds
- favor simple standard-library tests early, then standardize further once the shared Python toolchain is in place

## Databricks

- dbt-databricks for dbt integration
- Databricks Git-backed projects for dbt tasks
- Asset Bundles for deployable job definitions

## Testing Strategy By Area

| Area | Primary test tools | Focus |
|------|--------------------|-------|
| platform-control | TypeScript unit tests, API integration tests | state transitions, validation, contract alignment |
| connector workers | Python unit tests and smoke tests | fetch logic, retries, artifact registration, idempotency |
| document-intelligence | Python unit tests, golden tests, invariant tests, integration tests | parsing quality, lineage, canonical writes |
| legal-search frontend | Vitest, Testing Library | render and user flow |
| legal-search BFF | TypeScript unit tests and API integration tests | query shaping, contract validity, search behavior |
| contracts | schema validation and example validation | drift prevention |
| infra | Terraform validate/plan checks | deployability and consistency |

## What To Avoid In MVP

- no third backend language
- no separate ingestion top-level component
- no Dagster or Airflow before Databricks-native workflows are exhausted
- no direct frontend-to-OpenSearch coupling
- no Scala rewrite of document processing unless performance evidence demands it
- no browser automation as the default acquisition strategy
- no AI-generated content becoming canonical truth without explicit review workflows

## Phased Implementation Plan

## Phase 0: Contract And Stack Alignment

Deliverables:

- finalize overall stack decisions
- align component docs and implementation plans
- keep some boundary adapters loose where contracts are still moving
- settle the first source family and first vertical slice

## Phase 1: Control Plane Foundation

Use:

- TypeScript
- NestJS
- Postgres
- Cloud Run

Deliverables:

- `sources`, `source_versions`, `runs`, and `artifacts`
- reference data tables
- source snapshot and artifact registration
- `artifact_bundle.available` emission

## Phase 2: Connector Foundation

Use:

- Python
- Cloud Run jobs
- GCS

Deliverables:

- one API-based connector
- one scrape-oriented connector if needed
- reproducible artifact registration flow

## Phase 3: Document Intelligence MVP

Use:

- Python
- Databricks
- Delta
- minimal dbt usage

Deliverables:

- event intake
- artifact read path
- HTML normalization
- `documents` and `sections`
- `processing_manifest`
- `document.processed`

## Phase 4: Search MVP

Use:

- Next.js
- NestJS
- OpenSearch

Deliverables:

- projection builder
- search API
- detail API
- minimal search UI and detail UI

## Phase 5: Hardening

Use:

- stricter runtime validation
- stronger observability
- deployment automation
- more source families

Deliverables:

- final hardening of moving contracts
- better failure reporting
- operational runbooks
- reprocessing workflows
- richer search and ranking

## Recommended Near-Term Decisions

These are the most actionable stack decisions to lock now:

1. TypeScript + NestJS for `platform-control`
2. Python connector workers owned by `platform-control`
3. Python + Databricks + Delta + dbt for `document-intelligence`
4. Keep `documents` and `sections` in MVP
5. TypeScript + Next.js + NestJS + OpenSearch for `legal-search`
6. Terraform + GitHub Actions + Artifact Registry + Secret Manager for infrastructure and deployment
7. No Dagster in MVP
8. No extra backend languages in MVP

## Open Decisions To Leave Slightly Loose For Now

- whether `platform-control` should use a specific ORM or stay SQL-first a bit longer
- when to standardize Python test tooling beyond the early scaffolds
- when to introduce strict generated Python contract consumers
- whether some connector types deserve their own deployment shape later
- exactly when vector search becomes part of `legal-search`

These can be hardened in a later pass without changing the core stack direction.
