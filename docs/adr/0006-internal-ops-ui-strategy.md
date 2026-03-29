# ADR-0006: Internal Ops UI Strategy

## Status

Accepted

## Date

2026-03-28

## Context

The platform needs internal administrative interfaces for managing sources, approvals, runs, and operational workflows. We need to decide how to build these interfaces and whether they belong in legal-search.

## Decision

- Internal ops/admin UI is handled **separately from legal-search**.
- **Retool** (or similar low-code/internal tool platform) may be used for internal control workflows.
- legal-search is exclusively for external/user-facing search experiences.

## Rationale

- **Different audiences.** Internal ops users (administrators, data operators) have different needs than legal-search users (lawyers, researchers, compliance teams).
- **Different change frequencies.** Internal ops UIs change frequently as workflows evolve. User-facing search UIs have higher stability requirements.
- **Faster iteration.** Low-code tools like Retool allow rapid prototyping of admin workflows without frontend engineering overhead.
- **Boundary clarity.** Keeping ops UI out of legal-search prevents the search frontend from becoming cluttered with admin features.

## Consequences

- platform-control APIs must be designed to support both programmatic access and Retool/admin UI consumption.
- Internal ops UI is not part of the legal-search deployment.
- Retool (if used) connects to platform-control APIs, not directly to databases.
- A future dedicated admin frontend may replace Retool as complexity grows.
