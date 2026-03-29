# Doc Types and Authority

## Purpose

Define the types of documentation in Evidara and which source is authoritative when information conflicts.

---

## Document Types

### Architecture Docs (`docs/architecture/`)

**What:** System-level design — component boundaries, communication patterns, storage model, clean-room principles.

**Authority:** These define the intended architecture. If code deviates from architecture docs, the code should be fixed or an ADR should be written.

**Owner:** Whole team.

### ADRs (`docs/adr/`)

**What:** Architecture Decision Records — why specific decisions were made.

**Authority:** ADRs are historical records. They are never updated after initial acceptance. If a decision is reversed, a new ADR supersedes the old one.

**Owner:** Whoever made the decision.

### Component Docs (`docs/components/`)

**What:** Per-component descriptions — purpose, responsibilities, boundaries, current state, tasks.

**Authority:** These describe current reality. If code and component doc disagree, the doc should be updated.

**Owner:** The component's primary developer.

### Contract Files (`contracts/`)

**What:** Schemas, OpenAPI specs, event definitions — the formal interface between components.

**Authority:** **Contracts are the highest-authority documentation.** If prose docs and contract files disagree, the contract file is correct. Prose docs should reference contracts, not duplicate them.

**Owner:** Jointly owned by producing and consuming components.

### Testing Docs (`docs/testing/`, `docs/components/testing/`)

**What:** Testing strategy, principles, and per-component testing guides.

**Authority:** These describe the intended testing approach. Actual test code is the ground truth for what is tested.

**Owner:** Whole team.

### Setup Docs (`docs/setup/`)

**What:** Developer setup instructions — how to get a development environment running.

**Authority:** These must match reality. If setup docs don't work, they are broken and should be fixed immediately.

**Owner:** Whoever last changed the setup process.

### Runbooks (`docs/runbooks/`)

**What:** Operational procedures — deployment, reindexing, recovery, incident response.

**Authority:** Runbooks describe procedures. The `Last verified` date indicates confidence. An unverified runbook is advisory, not authoritative.

**Owner:** Named in the `Owner` field of each runbook.

### Documentation Governance (`docs/documentation/`)

**What:** Rules for writing, updating, and maintaining documentation itself.

**Authority:** These are process docs. They describe how we work, not what the system does.

**Owner:** Whole team.

---

## Authority Hierarchy

When information conflicts, resolve in this order:

1. **Contract files** (`contracts/`) — highest authority for interface definitions
2. **Code** — ground truth for behavior
3. **Architecture docs** (`docs/architecture/`) — intended design
4. **Component docs** (`docs/components/`) — intended scope and responsibilities
5. **ADRs** (`docs/adr/`) — historical context
6. **Prose documentation** — explanatory, may lag behind

---

## Key Rule

**Prose docs should reference contract files, not duplicate them.**

Instead of:

> "The `raw_artifact.available` event contains `source_id`, `source_version_id`, `run_id`, `artifact_id`, `storage_path`, `content_type`, and `metadata`."

Write:

> "The `raw_artifact.available` event is defined in `contracts/events/raw-artifact-available.schema.json`."

This prevents prose from going stale when contracts evolve.
