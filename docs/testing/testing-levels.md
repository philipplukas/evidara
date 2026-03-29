# Testing Levels

## Purpose

Define each testing level used in Evidara, what it catches, how often it runs, and whether it is required for MVP.

---

## Level 1: Unit Tests

**Purpose:** Verify individual functions and logic in isolation.

**What it catches:**

- Logic errors in parsing, transformation, and validation helpers
- Off-by-one errors, null handling, edge cases
- Incorrect state transitions

**Expected frequency:** Run on every commit. Fast — should complete in seconds.

**Required in MVP:** Yes. Every component should have unit tests for core logic.

---

## Level 2: Component Integration Tests

**Purpose:** Verify that a component works correctly with its direct dependencies (database, file system, message queue).

**What it catches:**

- Incorrect database queries or migrations
- Misconfigured connections
- Serialization/deserialization issues at component boundaries

**Expected frequency:** Run on every PR. May require infrastructure (test containers, local database).

**Required in MVP:** Partially. At minimum, test database interactions for platform-control and Delta writes for document-intelligence.

---

## Level 3: Contract / Schema Tests

**Purpose:** Validate that data payloads conform to agreed schemas.

**What it catches:**

- Schema violations in API payloads, events, and stored data
- Breaking contract changes between components
- Missing required fields, wrong types, invalid enum values

**Expected frequency:** Run on every commit. Fast and deterministic.

**Required in MVP:** Yes. Schema validation for core contracts (`RawArtifactEnvelope`, `Document`, `Section`, `Citation`, events) is required from day one.

---

## Level 4: Golden Sample Tests

**Purpose:** Verify processing output against known-good expected results for representative inputs.

**What it catches:**

- Parsing regressions when processing logic changes
- Semantic drift when source formats evolve
- Silent quality degradation

**Expected frequency:** Run on every PR. May be slower if processing involves complex logic.

**Required in MVP:** Yes, for document-intelligence. Start with 10–20 representative documents.

---

## Level 5: End-to-End Tests

**Purpose:** Verify a full workflow across all components — from source creation to searchable result.

**What it catches:**

- Integration failures between components
- Missing handoffs or broken event chains
- ID propagation errors across boundaries

**Expected frequency:** Run on merge to main or nightly. May require full environment.

**Required in MVP:** One slice only. See [First End-to-End Slice](first-end-to-end-slice.md).

---

## Level 6: Operational Smoke Tests

**Purpose:** Verify that deployed services are running and responding correctly.

**What it catches:**

- Deployment failures
- Misconfigured environments
- Infrastructure issues (database unreachable, index missing)

**Expected frequency:** Run after every deployment and optionally as periodic health checks.

**Required in MVP:** Yes. Basic health check endpoints and one query smoke test per service.

---

## Level 7: Drift Detection Checks

**Purpose:** Compare current system behavior against known baselines to detect gradual changes.

**What it catches:**

- Source format changes (layout drift)
- Schema evolution that affects downstream consumers
- Semantic degradation (fewer sections, missing citations)
- Index/serving divergence from canonical truth

**Expected frequency:** Run nightly or weekly. Designed for trend monitoring, not gating.

**Required in MVP:** No, but plan for it. The golden sample tests provide a foundation. Dedicated drift detection can be added after MVP.

---

## Summary Table

| Level | Name | Required in MVP | Runs on |
|-------|------|:-:|---------|
| 1 | Unit tests | ✅ | Every commit |
| 2 | Component integration tests | Partial | Every PR |
| 3 | Contract / schema tests | ✅ | Every commit |
| 4 | Golden sample tests | ✅ (doc-intel) | Every PR |
| 5 | End-to-end tests | 1 slice | Merge / nightly |
| 6 | Operational smoke tests | ✅ | Post-deploy |
| 7 | Drift detection checks | ❌ (plan only) | Nightly / weekly |
