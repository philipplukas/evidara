# ADR-0008: NestJS Conventions for legal-search API

## Status

Accepted

## Date

2026-03-29

## Context

The `legal-search` component consists of a Next.js frontend and a NestJS API server. The NestJS server exposes the search and document endpoints defined in `contracts/api/legal-search.openapi.yaml` and connects to OpenSearch for serving queries.

We need agreed conventions for how to structure, test, and document the NestJS API to keep it understandable, onboardable, and safe to change for a small team.

## Decision

### Repository layout

The `legal-search/` folder uses an npm workspace structure:

```
legal-search/
  package.json          ← workspace root (shared scripts and tooling config only)
  tsconfig.base.json    ← shared TypeScript base config
  frontend/             ← Next.js application
    package.json
    src/
  api/                  ← NestJS application
    package.json
    nest-cli.json
    tsconfig.json       ← extends ../tsconfig.base.json
    src/
      main.ts
      app.module.ts
      core/             ← global pipes, filters, guards, interceptors, config
      modules/          ← feature modules
```

### Module structure

Feature modules are the primary unit of organisation. Each module represents a business capability.

Modules for v1:

- `SearchModule` — document search
- `DocumentsModule` — document detail and sections
- `HealthModule` — health endpoint

Modules start flat and grow into subdirectories only when they exceed ~8 files:

```
# Small module (flat — preferred for v1)
modules/search/
  search.module.ts
  search.controller.ts      ← thin: validate, call service, map response
  search.service.ts         ← orchestration, calls repository
  search.repository.ts      ← interface: SearchRepository
  opensearch.adapter.ts     ← implementation: OpenSearchSearchRepository
  dto/
    search-query.dto.ts
    search-response.dto.ts
  search.service.spec.ts    ← unit tests
  opensearch.adapter.spec.ts ← integration tests (Testcontainers)

# Larger module (expanded when needed)
modules/search/
  search.module.ts
  presentation/
  application/
  domain/
  infrastructure/
  tests/
```

### Controller rules

Controllers must be thin. They:

- Accept and validate request DTOs
- Call one service or use-case
- Map the result to a response DTO
- Return the response

Controllers must not contain business logic, ORM code, or OpenSearch query DSL.

### DTO rules

DTOs are used at transport boundaries only. Request DTOs use class-validator. Response DTOs are plain classes with `@ApiProperty` decorators.

DTOs must not be passed into domain logic. Map to domain types at the service boundary.

Global validation pipe configuration:

```ts
app.useGlobalPipes(new ValidationPipe({
  whitelist: true,
  forbidNonWhitelisted: true,
  transform: true,
}));
```

### OpenSearch integration

OpenSearch concerns are isolated behind a repository interface:

- `SearchRepository` interface lives at the module level
- `OpenSearchSearchAdapter` implements the interface in the same module
- Controllers and services never import the OpenSearch client directly
- OpenSearch query DSL lives only in adapters
- Client setup and connection config live in `core/opensearch/`

### Error handling

A global exception filter maps domain errors to HTTP responses. Domain/service code throws typed domain exceptions (`DocumentNotFoundError`, `SearchUnavailableError`). The exception filter maps these to consistent HTTP error shapes. HTTP exceptions are never thrown inside service or domain code.

### OpenAPI / Swagger

The contract in `contracts/api/legal-search.openapi.yaml` is the canonical source of truth. NestJS Swagger decorators (`@ApiProperty`, `@ApiOperation`, `@ApiTags`) are used on DTOs and controllers for the development Swagger UI, but they are not the source of truth.

CI runs `npm run openapi:check` to detect drift between the contract spec and the generated NestJS spec.

### Configuration

Typed config via `@nestjs/config`. Config validated at startup. No `process.env` access outside config files. The `core/config/` folder contains typed config classes for app, OpenSearch, and auth.

### Cross-cutting concerns

Set up globally in `core/`:

- `ValidationPipe` — global, as above
- `AllExceptionsFilter` — global exception filter
- `LoggingInterceptor` — logs requests with correlation ID
- `CorrelationIdMiddleware` — attaches a request ID to each request
- `AuthGuard` — JWT validation on protected routes

### Testing

Three testing levels:

1. **Unit tests** (`.spec.ts` adjacent to code): pure logic, service methods with mocked repository
2. **Integration tests** (`.spec.ts` adjacent to adapter): `opensearch.adapter.spec.ts` uses Testcontainers with a real OpenSearch container
3. **Smoke tests** (`api/test/smoke/`): HTTP-level tests that verify the app boots, health endpoint returns 200, and one search flow works end-to-end

## Rationale

- **Flat-first modules** reduce folder navigation overhead at small scale and grow naturally.
- **Repository interface pattern** decouples service logic from OpenSearch specifics, making unit tests fast and adapters independently testable.
- **Spec-first OpenAPI** preserves the contract-first principle from ADR-0004 and ADR-0007.
- **Naming `api/` not `bff/`** is clearer to new engineers — it describes what the folder is, not an architectural pattern name.
- **Thin controllers** keep business logic in the service layer where it can be tested without HTTP overhead.

## Consequences

- New feature modules follow the flat-first structure and expand only when needed.
- OpenSearch logic never appears in controllers or services — only in adapters.
- `contracts/api/legal-search.openapi.yaml` must be updated before or alongside any API endpoint change.
- `npm run openapi:check` blocks merge if the generated spec drifts from the contract.
