# Backend/BFF + OpenAPI Contract Plan

This document defines the naming, boundaries, and contract workflow between Next.js (`web`) and NestJS (`bff`) for Legal Search.

## Naming

For the current repository and future growth, prefer domain-first naming:

- `apps/legal-search-web` — Next.js frontend (user-facing UI)
- `apps/legal-search-bff` — NestJS backend-for-frontend
- `packages/legal-search-contracts` — OpenAPI source and generated clients/types

For this repo's current layout, keep the existing app directory and introduce contract assets under `contracts/`.

## BFF boundary

The frontend should call only BFF endpoints. The BFF can aggregate search, metadata, and relationships.

Contract-facing endpoints:

- `POST /v1/search`
- `GET /bff/articles/{id}`
- `GET /bff/documents/{id}/summary`
- `GET /bff/documents/{id}/related`

## OpenAPI source of truth

- Source contract: `contracts/openapi.yaml`
- Generated frontend client/hooks: `src/lib/api/generated/`
- Generation config: `orval.config.ts`

### Workflow

1. Update `contracts/openapi.yaml` in the same PR as endpoint changes.
2. Regenerate frontend client (`npm run openapi:generate`).
3. Commit generated artifacts.
4. CI verifies no contract drift.

## TanStack Query integration

Use Orval with the React Query mode so generated hooks integrate with `@tanstack/react-query`.

Examples of generated hook shapes:

- `usePostV1Search(...)`
- `useGetBffArticlesId(...)`

The generated hooks should be wrapped in app-level hooks where needed for query-key normalization and app-specific stale times.

## OpenSearch in the BFF

OpenSearch access should stay behind the BFF service layer:

- NestJS module: `SearchModule`
- Service: `SearchService` (query building + response mapping)
- Controller: `SearchController` exposing stable BFF DTOs

The frontend never depends on raw OpenSearch query DSL or index schema.
