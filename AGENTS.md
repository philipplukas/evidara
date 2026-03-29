# AGENTS.md

## Purpose

This is the Evidara monorepo — a document intelligence platform for legal research. It contains:

- **legal-search** — Next.js frontend + NestJS BFF for search and document detail
- **platform-control** — Source lifecycle, runs, approvals, reference data (Cloud Run)
- **document-intelligence** — Raw-to-canonical processing pipelines (Databricks)
- **contracts** — OpenAPI specs, JSON Schemas, event schemas (build-time only)
- **infra** — Terraform, deployment configs, environment definitions
- **docs** — Architecture, ADRs, runbooks, testing strategy, component docs

## Core rules

1. **Small, production-safe changes.** Prefer focused commits over sweeping refactors.
2. **Follow existing patterns.** Before introducing a new abstraction, check if the repo already has one. Grep before you create.
3. **Edit over duplicate.** Prefer modifying existing files over creating parallel abstractions.
4. **Generated over handwritten.** Prefer generated reference docs (OpenAPI, terraform-docs, TypeDoc) over manually maintained reference tables.
5. **Contract-first.** APIs are defined in `contracts/api/`, not invented inline. The spec is the source of truth.

## Change classification

Every change should be classified as one or more of:

- `internal-refactor` — restructuring without behavior change
- `user-visible-behavior` — changes what users see or experience
- `contract-change` — API specs, event schemas, shared entity shapes
- `infra-change` — Terraform, deployment, cloud resources
- `pipeline-change` — Databricks processing, data quality
- `architecture-change` — domain boundaries, storage decisions, communication patterns
- `docs-only` — documentation without code

## Required sync checks by change type

### user-visible-behavior

Update as applicable:

- Focused tests (narrowest test that proves the change)
- Feature docs in `docs/components/` or `legal-search/docs/`
- Runbook if operator flow changed

### contract-change

Update as applicable:

- OpenAPI spec in `contracts/api/`
- JSON Schema in `contracts/schemas/` or `contracts/events/`
- Generated clients (`npm run openapi:generate` in `legal-search/`)
- Contract tests and schema validation

### infra-change

Update as applicable:

- Terraform docs (generate, don't hand-maintain)
- `docs/setup/` guides
- Runbook if deployment or recovery changed

### pipeline-change

Update as applicable:

- Data quality checks
- Pipeline docs
- Failure-mode notes and recovery instructions

### architecture-change

Update as applicable:

- `structurizr/workspace.dsl` (canonical architecture)
- ADR in `docs/adr/` for significant decisions
- `docs/architecture/` for narrative docs
- Mermaid diagrams only in docs pages for explanation

## Evidara-specific rules

### Contract location

All shared contracts live at `contracts/` (monorepo root). Never inside a component folder. See ADR-0004.

### legal-search stack

`legal-search/` is an npm workspace with two packages:

- `frontend/` — Next.js application (user-facing search and document detail)
- `api/` — NestJS application (search and document endpoints, OpenSearch adapter)

**frontend:**

- **Design tokens** live in `globals.css` as CSS custom properties. Use `var(--token)` everywhere, never hardcoded colors.
- **Biome** for linting and formatting (not ESLint). Config in `legal-search/biome.json`.
- **Vitest** for tests. Config in `legal-search/vitest.config.ts`.
- **Orval** generates typed clients from OpenAPI. Two outputs: fetch client (Server Components) and React Query hooks (client components). See ADR-0007.
- **`npm run check`** is the pre-commit quality gate (typecheck + lint + test).
- **`npm run openapi:check`** is the CI drift gate (generate + git diff).

**api:**

- **NestJS** with TypeScript. See ADR-0008 for full conventions.
- **Repository interface pattern** — OpenSearch logic only in adapters, never in controllers or services.
- **Spec-first** — `contracts/api/legal-search.openapi.yaml` is canonical. Swagger decorators are additive for dev UI only.
- **Global pipes/filters** — ValidationPipe (whitelist, transform), AllExceptionsFilter, CorrelationIdMiddleware.
- Test layers: unit (fast, mocked), integration (Testcontainers OpenSearch), smoke (HTTP-level).

### platform-control stack

- **FastAPI** with Python 3.12+. See ADR-0009 for full conventions.
- **Pydantic v2** for request/response validation.
- **SQLAlchemy + Alembic** for ORM and migrations.
- **uv** for dependency management.
- **Retool** is the ops UI — connects via direct Postgres (reads) and platform-control API (business actions). See ADR-0006.
- **Action-focused API** — API endpoints handle state transitions and webhooks; Retool reads directly from Postgres.
- Test layers: unit (state machines, service logic), integration (Testcontainers Postgres), smoke (HTTP-level).
- **`ruff check` + `ruff format`** for linting and formatting (not flake8/black).
- **`pytest`** for all tests.
- **`pyproject.toml`** is the single config file — no `setup.py`, no `requirements.txt`.

### Language split

| Component | Language | Why |
|-----------|----------|-----|
| `legal-search/frontend` | TypeScript / Next.js | User-facing UI |
| `legal-search/api` | TypeScript / NestJS | Search and document API |
| `platform-control` | Python / FastAPI | Consistent with data infrastructure |
| `document-intelligence` | Python / Databricks | Data processing pipelines |
| `infra` | HCL / Terraform | Infrastructure as code |

The pre-commit hooks and CI workflows must run the same checks. If you add a check to one, add it to the other. `scripts/` is the shared entry point.

### Source of truth hierarchy

| Thing | Source of truth |
|---|---|
| Architecture | `structurizr/workspace.dsl` |
| API interfaces | `contracts/api/*.openapi.yaml` |
| Entity shapes | `contracts/schemas/*.json` |
| Event payloads | `contracts/events/*.json` |
| Infra resources | `infra/terraform/` |
| Design tokens | `legal-search/src/app/globals.css` |
| Tests | Test files adjacent to code |
| Narrative docs | `docs/` |

## Testing policy

Always add or update the **narrowest test** that proves the change:

- Unit test for local logic
- Integration/contract test for interfaces
- Smoke/e2e only when required for user-visible flows

Do not add large brittle tests when a small test proves the change.

## Documentation policy

Update docs when any of these change:

- User-visible behavior
- Setup/run workflow
- Architecture boundaries
- Dependencies between systems
- Contracts or schemas
- Operator procedures

If no docs change is needed, explain why in the PR.

## PR completion rules

A PR is not complete if applicable sync surfaces were ignored.

Before finalizing, verify:

- [ ] Code is updated
- [ ] Tests are updated (or explain why not)
- [ ] Contracts are updated if needed
- [ ] Docs are updated if needed
- [ ] Architecture is updated if needed

## Review guidance for AI

Flag or warn if:

- Behavior changed but no test changed
- Contract changed but schema/spec/docs did not
- Terraform changed but docs were not regenerated
- Architecture boundary changed but Structurizr was not updated
- Docs were manually edited where generation should be used
- Changes are large, duplicative, or inconsistent with repo patterns
- Design tokens are hardcoded instead of using CSS custom properties
- OpenAPI clients are hand-written instead of generated
- New patterns conflict with established conventions
