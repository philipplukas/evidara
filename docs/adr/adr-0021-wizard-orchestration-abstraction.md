# ADR-0021: Wizard Orchestration Abstraction (API-First)

## Status

Accepted — **superseded in part by ADR-0031**.

The `Orchestrator` abstraction below stands, and is the reason keeping Temporal is cheap. But
two of its decisions no longer hold:

- **"Use Argilla for review ingestion and queue lifecycle."** Reversed. The Argilla integration
  is deleted; the review queue is the `review_tasks` table, worked in `platform-control/admin`.
  The confidence-band routing policy is retained. See
  `docs/runbooks/extraction-review-routing.md`.
- **Temporal is deployed in no environment**, so `PLATFORM_CONTROL_WIZARD_ORCHESTRATOR_BACKEND`
  stays `in_memory`.

## Date

2026-04-07

## Context

Platform-control needs a durable, human-gated wizard flow for discovery and extraction. We must ship stable operator APIs quickly, but we also need long-running workflow capabilities (signals, retries, child workflows) without hardwiring API behavior to a single runtime implementation too early.

## Decision

Adopt an API-first architecture with an orchestration abstraction:

- Introduce an `Orchestrator` service interface in platform-control.
- Implement `InMemoryOrchestrator` for fast local/test transition validation.
- Implement `TemporalOrchestrator` adapter behind the same interface, with signal methods and child-workflow stubs.
- Keep state transition guard logic in platform-control domain/service layer, not in router code.
- Use Argilla for review ingestion and queue lifecycle instead of building custom review tooling.

## Consequences

### Positive

- API contracts can stabilize before full Temporal runtime rollout.
- Domain logic is testable without Temporal infra in CI.
- Temporal integration can be phased in without endpoint changes.
- Human review flow remains tool-backed (Argilla) instead of custom UI build.

### Negative

- Two orchestration implementations must be maintained during transition.
- Some runtime behavior is temporarily simulated in `in_memory` mode.
- Temporal adapter remains partial until child workflows are fully implemented.

### Neutral

- Additional configuration surface (`wizard_orchestrator_backend`, Temporal namespace/task queue) is required.

## Alternatives Considered

### Direct Temporal coupling from routers

Rejected because it tightly couples external API behavior to workflow runtime details and makes contract testing slower and harder in CI.

### Build custom workflow engine in platform-control

Rejected because it duplicates mature orchestration capabilities already available in Temporal.

### Review queue built in custom admin UI

Rejected because Argilla already provides review workflows and avoids reimplementing annotation/review infrastructure.

## References

- `docs/architecture/temporal-argilla-wizard-architecture.md`
- `docs/runbooks/extraction-review-routing.md`
- `docs/adr/0031-temporal-argilla-firecrawl-disposition.md`
- `platform-control/src/platform_control/services/orchestrator.py`
