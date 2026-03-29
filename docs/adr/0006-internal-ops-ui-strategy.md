# ADR-0006: Internal Ops UI Strategy

## Status

Accepted

## Date

2026-03-28

## Context

The platform needs internal administrative interfaces for managing sources, approvals, runs, and operational workflows. We need to decide how to build these interfaces and whether they belong in legal-search.

## Decision

- Internal ops/admin UI for v1 is **Retool**.
- legal-search is exclusively for external/user-facing search experiences.
- Retool uses a **hybrid connection model**:
  - **Direct Postgres connection** for read views (list sources, view runs, filter, sort). No API layer needed for these.
  - **REST API calls to platform-control** for business actions with logic (approve version, trigger run, reject, state transitions).
- Platform-control APIs must be designed with this in mind: reads can go directly to Postgres via Retool; the API surface is focused on business actions and webhooks.

## Rationale

- **Different audiences.** Internal ops users (administrators, data operators) have different needs than legal-search users (lawyers, researchers, compliance teams).
- **Different change frequencies.** Internal ops UIs change frequently as workflows evolve. User-facing search UIs have higher stability requirements.
- **Faster iteration.** Low-code tools like Retool allow rapid prototyping of admin workflows without frontend engineering overhead.
- **Boundary clarity.** Keeping ops UI out of legal-search prevents the search frontend from becoming cluttered with admin features.

## Consequences

- platform-control's FastAPI surface is focused on **business actions**, not full CRUD. Retool handles reads via direct Postgres.
- Retool connects to the platform-control API (not directly to the service's internal code).
- Internal ops UI is not part of the legal-search deployment.
- A future dedicated admin frontend may replace Retool as complexity grows, consuming the same platform-control API.
- Retool resource configurations (queries, apps) should be treated as configuration artefacts; document any non-trivial Retool logic in `docs/runbooks/`.
