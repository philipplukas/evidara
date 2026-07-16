# ADR-0009: FastAPI Conventions for platform-control

## Status

Accepted

## Date

2026-03-29

## Context

`platform-control` is the internal API backend for source lifecycle, run orchestration, approvals,
and reference data. Its primary ops UI is the code-managed React-admin app under
`platform-control/admin` (ADR-0015). The audience for the API is:

1. **React-admin** — operator read models and business action endpoints
2. **document-intelligence** — webhooks reporting run results
3. **Future programmatic access** — CI triggers, external integrations

Because Python is already the language of `document-intelligence` (Databricks) and the broader
data/ops side of the platform, FastAPI is the natural fit. It gives automatic OpenAPI generation,
strong validation via Pydantic, and aligns the Python runtime across the platform's operational
backend work.

## Decision

### Framework and language

- **FastAPI** with Python 3.12+
- **Pydantic v2** for request/response validation and schema definition
- **SQLAlchemy** (async) for ORM
- **Alembic** for database migrations
- **uv** for dependency management

### Repository layout

```
platform-control/
  pyproject.toml
  alembic.ini
  alembic/
    versions/
  src/
    platform_control/
      main.py           ← FastAPI app creation, lifespan, middleware
      config.py         ← Pydantic settings, validated at startup
      database.py       ← async SQLAlchemy engine and session
      routers/          ← feature routers (one per business domain)
        sources.py
        runs.py
        approvals.py
        health.py
      models/           ← SQLAlchemy ORM models
        source.py
        run.py
        approval.py
      schemas/          ← Pydantic request/response schemas (DTOs)
        source.py
        run.py
        approval.py
      services/         ← business logic, state machines, validation
        source_service.py
        run_service.py
        approval_service.py
      events/           ← Pub/Sub event emission
        publisher.py
  tests/
    unit/               ← pure service and domain logic tests
    integration/        ← database tests (Testcontainers Postgres)
    smoke/              ← HTTP smoke tests (app boots, health, one happy path)
```

### Router scope

The FastAPI API surface remains action-heavy, but it now also includes explicit operator read models
for the React-admin app. The browser does not read Postgres directly; the API handles both
state transitions and the read surfaces the operator workflow needs.

Representative endpoints:

```
POST   /v1/sources                          ← create source
GET    /v1/sources                          ← list sources for the operator UI
POST   /v1/sources/{id}/versions            ← create version
GET    /v1/sources/{id}/versions            ← list source versions for source setup
POST   /v1/versions/{id}/submit             ← submit for approval
POST   /v1/versions/{id}/approve            ← approve (emits event)
POST   /v1/versions/{id}/reject             ← reject
GET    /v1/runs                             ← list runs for preview/production monitoring
POST   /v1/runs/{id}/complete               ← webhook: doc-intelligence reports back
GET    /v1/runs/{id}                        ← run status (programmatic access)
GET    /v1/runs/{id}/captured-resources     ← operator diagnostics
GET    /v1/runs/{id}/raw-artifacts          ← operator diagnostics
GET    /v1/runs/{id}/provider-jobs          ← operator diagnostics
GET    /v1/runs/{id}/preview-summary        ← operator preview review
GET    /health                              ← health check
```

### OpenAPI / spec alignment

**Superseded by [ADR-0034](0034-generated-platform-control-contract.md).** This section
used to say both "the contract spec in `contracts/api/` remains canonical" and "do not
hand-edit the generated spec — change the Pydantic schemas and let FastAPI regenerate
it", and claimed CI validated the two against each other with `redocly lint` or
`openapi-diff`. It did not. The contradiction resolved itself the way unchecked
contradictions do: the hand-maintained file drifted to 4 of 11 acquisition providers and
took two production bugs with it (#614, #616 — see #618).

There is now one spec. `contracts/api/platform-control.openapi.yaml` is **generated** from
this app by `scripts/generate_platform_control_contract.py` and gated for drift by
`scripts/check-platform-control.sh` (pre-commit + CI). Change the Pydantic schemas or
routes and regenerate; never hand-edit the file.

### Validation and error handling

Pydantic v2 validates all request bodies automatically. Domain errors (invalid state transitions, not found) raise typed Python exceptions mapped to HTTP responses via FastAPI exception handlers. HTTP status codes are never hardcoded in service logic.

### Configuration

`pydantic-settings` with a `Settings` class. All config comes from environment variables, validated at startup. No `os.environ` access outside `config.py`.

### Testing

Three testing levels:

1. **Unit tests** (`tests/unit/`): pure service logic, state machine transitions — no database, no HTTP
2. **Integration tests** (`tests/integration/`): database interactions using Testcontainers (real Postgres), tests for all state transitions that write to DB
3. **Smoke tests** (`tests/smoke/`): HTTP-level tests — app boots, health returns 200, one source creation and approval flow

## Rationale

- **Python** consistency with `document-intelligence` — one runtime for the data/ops side of the platform.
- **FastAPI + Pydantic** gives automatic OpenAPI generation, which removes the spec-maintenance step entirely: the contract *is* that output (ADR-0034). "Closely matches the hand-authored contract spec" was the original claim here, and it was never checked — see #618 for how far apart the two actually drifted.
- **API-backed operator workflow** — the admin UI stays fully code-managed and browser-safe by
  reading through supported endpoints instead of direct Postgres access.
- **SQLAlchemy + Alembic** is the standard Python/Postgres stack with a long track record and good async support.
- **uv** for dependency management — fast, deterministic, the current Python standard for new projects.

## Consequences

- `platform-control/` is Python, `legal-search/` is TypeScript. These are separate runtimes with no shared code.
- The React-admin app consumes the platform-control API only; direct database access stays on the
  backend side of the boundary.
- CI runs separate lint/test pipelines for `platform-control/` (Python/Ruff/pytest) vs `legal-search/` (TypeScript/Biome/Vitest).
- A new platform-control endpoint lands in the routers and schemas, then `contracts/api/platform-control.openapi.yaml` is regenerated in the same PR — the drift gate fails the build otherwise (ADR-0034). ADR-0004's contract-first principle still governs contracts designed across a boundary before they are built; it is the wrong tool for a spec whose whole job is to describe a service that already exists.
