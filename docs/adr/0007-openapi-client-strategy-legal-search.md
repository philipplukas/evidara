# ADR-0007: OpenAPI Client Strategy for legal-search

## Status

Accepted

## Date

2026-03-29

## Context

`legal-search` is a Next.js (App Router) frontend sitting in front of a NestJS BFF.
The BFF contract is defined by `contracts/api/legal-search.openapi.yaml`.

We need a strategy for consuming this contract in the frontend that:

- Provides type safety across the Next.js / NestJS boundary
- Works for both Server Components (async data fetching) and client-side interactive areas
- Avoids coupling the frontend to raw OpenSearch internals
- Keeps generated artifacts manageable and CI-verifiable

Two questions drove this decision:

1. **Which tool to use for client generation?**
2. **At which layer do we want generated API abstractions?**

### Options considered

**Option A — Orval (universal, hook-first)**
Generate React Query hooks for every endpoint automatically. Makes client code very concise; becomes the universal contract consumer.

**Option B — openapi-typescript + openapi-fetch (thin, type-only)**
Generate only TypeScript types from the spec. Write fetch calls and query hooks by hand. Works identically on server and client.

**Option C — Selective Orval (hybrid)**
Use Orval for client-heavy interactive areas only. Use a thin typed fetch on the server. Generated hooks coexist with server-first patterns.

## Decision

Use **Selective Orval (Option C)**.

- **Orval** generates typed clients and optionally React Query hooks from the BFF spec, used in client components and interactive workspace areas.
- **Direct typed fetch** (using the same Orval-generated types) is used in Server Components and Server Actions.
- The spec at `contracts/api/legal-search.openapi.yaml` is the single source of truth for both.
- Generated output lives at `src/lib/api/generated/` and is committed to the repository.
- CI validates that generated output is not stale (`openapi:check`).

## Rationale

### Why not Orval universally

`legal-search` is server-leaning, not a classic SPA:

- URL-driven search pages are better served by Server Components with direct async fetches.
- XState machines own exploration semantics; generated hooks would compete with that model.
- TanStack Query should be scoped to true client-side fetch/cache needs, not used everywhere by default.

Universal hook generation would produce helpers that are unused or awkward in server contexts, and would add generated-code churn to every spec change.

### Why not openapi-typescript only

- The interactive workspace (document detail panel, related documents, pivot navigation) is genuinely client-heavy.
- Writing boilerplate query hooks by hand for those areas buys nothing.
- Orval's MSW handler generation is a real advantage for isolated frontend testing.
- The team should not hand-roll what a generator handles well.

### Why selective Orval is the right balance

- Server Components call the BFF with a thin fetch wrapper typed against the same generated types — no framework overhead, works identically server-side.
- Client components in interactive islands use the generated React Query hooks — concise, testable, consistent.
- MSW handlers generated from the same spec enable frontend testing without a running NestJS instance.
- The choice of which layer gets which abstraction is explicit and enforced by convention, not tooling constraints.

### Why spec location matters

The spec lives at `contracts/api/legal-search.openapi.yaml`, not inside `legal-search/`.
This follows ADR-0004: contracts are owned by neither the producer (NestJS) nor the consumer (Next.js).
Both sides generate their artifacts from the same file. Moving the spec into `legal-search/` would make it a frontend implementation detail and break the shared-contract principle.

## Consequences

- `orval` and `@redocly/cli` are pinned in `legal-search/devDependencies`. No bare `npx` downloads at runtime.
- `npm run openapi:generate` must be re-run whenever `contracts/api/legal-search.openapi.yaml` changes.
- `npm run openapi:check` (generate + `git diff --exit-code`) runs in CI and blocks merge if generated files are stale.
- Server Components import types from `src/lib/api/generated/` and call the BFF via a thin `fetch` wrapper — not via generated hooks.
- Client components in interactive islands import generated React Query hooks.
- Orval is NOT used against OpenSearch directly. The BFF keeps OpenSearch an implementation detail.
- If the app becomes predominantly client-driven in future, revisit this decision and consider making Orval the universal default.
