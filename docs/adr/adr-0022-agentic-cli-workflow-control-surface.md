# ADR-0022: Agentic CLI Workflow Control Surface

## Status

Proposed

## Date

2026-04-08

## Context

Evidara already has an agent- and operator-friendly CLI in `tools/evidara-cli`, but cross-component workflows still lack a single architectural pattern for:

- bounded agent action surfaces
- durable per-step feedback and evidence
- compensation or recovery semantics after partial side effects
- explicit human gates before irreversible actions
- narrow learning loops for proposal or evaluation tasks

Without a shared pattern, agent-driven flows risk becoming a mix of direct API calls, ad hoc scripts, and opaque retry behavior that is hard to audit or improve.

## Decision

Adopt an agentic workflow architecture with these rules:

- `tools/evidara-cli` is the bounded control surface exposed to agents through MCP.
- `platform-control` is the durable workflow system of record for workflow runs, step history, approvals, and auditability.
- Workflow commands should use a small verb family: `inspect`, `propose`, `apply`, `verify`, and `compensate`.
- Each workflow step should return a consistent JSON envelope including workflow identity, step identity, side-effect level, evidence, and recommended next actions.
- Reasoning backtracking and side-effect compensation are distinct; mutating actions require explicit compensation rather than implicit undo.
- Human approval remains mandatory before irreversible or governance-significant actions.
- DSPy may be used only for bounded proposal or evaluation tasks with explicit inputs, outputs, and measurable quality signals.

The detailed proposed design lives in `docs/architecture/agentic-cli-workflow-architecture.md`.

## Consequences

### Positive

- Agents operate through a narrower, safer interface.
- Workflow execution becomes auditable step by step.
- Retry and recovery behavior becomes explicit instead of implicit.
- Bounded learning can improve proposal quality without owning approvals or durable state.
- The design reuses existing ownership boundaries rather than inventing a second control plane.

### Negative

- More up-front design work is required for command envelopes, journal models, and compensation semantics.
- Some workflow APIs and read surfaces will need to be added to `platform-control`.
- The CLI will need stronger conventions and tests than a simple smoke-only utility.

### Neutral

- Existing service-specific commands can continue to exist alongside workflow-oriented commands.
- Some workflows may remain synchronous in the CLI initially before moving to durable orchestration.
- Read-only OpenAPI helpers (`evidara openapi paths`, `evidara openapi tags`) are part of the bounded discovery surface and do not execute workflows or mutate cloud state.

## Alternatives Considered

### Direct Raw API Access From Agents

Rejected because it spreads workflow logic across agents, reduces auditability, and makes retries or compensation inconsistent.

### General-Purpose Autonomous Agent Platform

Rejected because it is broader than the current Evidara need. The immediate requirement is safe workflow execution across known system boundaries, not a new generic agent runtime.

### Learned Decision-Making For High-Stakes Actions

Rejected because approvals, irreversible mutations, and audit-trail truth require deterministic policy and explicit human control.

## References

- `docs/architecture/agentic-cli-workflow-architecture.md`
- `tools/evidara-cli/README.md`
- `docs/architecture/system-context.md`
