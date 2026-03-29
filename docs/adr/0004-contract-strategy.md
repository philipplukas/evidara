# ADR-0004: Contract Strategy

## Status

Accepted

## Date

2026-03-28

## Context

Components need a shared language to communicate. We need to decide how to define and manage the contracts between components.

## Decision

- **OpenAPI** for synchronous APIs (REST endpoints).
- **JSON Schema** for shared domain entities and async event payloads.

All contracts live in the `contracts/` folder:

```text
contracts/
  api/           # OpenAPI specs
  schemas/       # JSON Schemas for domain objects
  events/        # JSON Schemas for event payloads
  ids/           # ID naming and formatting conventions
```

## Rationale

- **OpenAPI** is the industry standard for REST API definitions. It enables code generation, documentation, and validation.
- **JSON Schema** is widely supported, language-agnostic, and can be used for both validation and documentation.
- **Co-locating contracts** in a single folder makes them easy to find, review, and version together.
- **Separating API specs from event schemas** makes the distinction between sync and async clear.

## Consequences

- All inter-component communication must be defined in contracts.
- Contract changes require PR review and may require ADRs for breaking changes.
- Generated clients/validators can be built from these contracts in the future.
- Contracts start minimal and grow incrementally.
