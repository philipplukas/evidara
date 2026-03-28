# Contracts

## Purpose

Provide the shared language between all Evidara components. Contracts define the explicit, versioned interfaces through which components communicate.

## Current state

Repository structure exists. ID conventions are defined. Core schemas (`RawArtifactEnvelope`, `Document`, `Section`, event schemas) are planned but not yet created.

## Source of truth

- `contracts/` directory is the single source of truth for all interface definitions
- Prose documentation should reference contract files, not duplicate them
- See [Doc Types and Authority](../../docs/documentation/doc-types-and-authority.md) for the authority hierarchy

## Structure

```
contracts/
  api/           # OpenAPI specs for synchronous REST APIs
  schemas/       # JSON Schemas for shared domain objects
  events/        # JSON Schemas for async event payloads
  ids/           # ID naming and formatting conventions
```

## Minimal next tasks

- [x] Define ID conventions (`contracts/ids/README.md`)
- [ ] Define `RawArtifactEnvelope` schema
- [ ] Define `Document` schema
- [ ] Define `Section` schema
- [ ] Define `document.processed` event schema
- [ ] Define minimal platform-control OpenAPI spec
- [ ] Define minimal legal-search OpenAPI spec

## Minimal v1 Outcome

All components can exchange a small, versioned, explicit set of payloads:

- Raw artifact envelopes flow from platform-control to document-intelligence
- Processed document events flow from document-intelligence to legal-search
- Search and control APIs are defined in OpenAPI

## Later expansion

| Phase | Capability |
|-------|-----------|
| Next | `Citation` schema |
| Next | `EvidenceRef` schema |
| Later | `ResearchWorkflowRun` schema |
| Later | More event schemas |
| Later | Generated clients from OpenAPI/JSON Schema |

## Dependencies

| Dependency | Purpose |
|-----------|---------|
| JSON Schema (Draft 2020-12) | Schema definition format |
| OpenAPI 3.x | API specification format |
| All components | Contracts are consumed by every component |

## Governance

- All contract changes require PR review.
- Breaking changes require an ADR.
- Contracts start minimal and grow by addition (backwards-compatible by default).
- Contract ownership is shared: both producer and consumer must agree on changes.

## Testing

See [Contracts Testing](testing/contracts-testing.md) for the full testing strategy.

Key tests:

- JSON Schema validity checks (all schemas parse and validate)
- Example payload validation (core payloads pass schema validation)
- OpenAPI lint/validation
- Example payloads updated together with schema changes

## Drift risks

| Risk | Mitigation |
|------|-----------|
| Schema changes without example updates | CI validates examples against schemas |
| Breaking changes introduced silently | PR review required, breaking changes need ADR |
| Prose docs duplicate and diverge from schemas | Update rules require referencing, not duplicating |
| Stale contract files no longer match implementation | Contract tests validate payloads in CI |
