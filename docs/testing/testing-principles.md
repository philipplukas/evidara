# Testing Principles

## Purpose

Define the core testing philosophy for Evidara. These principles apply to all components and all contributors — human or AI.

## Core Principles

### Maximize confidence with minimal effort

A small team cannot maintain thousands of tests. Every test must justify its existence by catching something that matters.

### Prefer a few high-value tests over many brittle ones

One well-chosen golden document test that catches parsing regressions is worth more than fifty snapshot tests that break on every style change.

### Stabilize IDs and boundary contracts first

Before testing complex behavior, ensure that IDs are stable and boundary contracts are validated. Everything downstream depends on these.

### Test canonical truth separately from serving projections

Canonical data (Delta) and serving projections (OpenSearch) serve different purposes and require different testing approaches. Never assume that a passing search test proves canonical data is correct.

### Use golden examples, invariants, and smoke tests

These three patterns cover the most ground with the least maintenance:

- **Golden examples** — known-good inputs with expected outputs
- **Invariants** — conditions that must always hold (`document.source_id != null`)
- **Smoke tests** — basic end-to-end checks that the system is alive

### AI-generated code must satisfy the same tests as human-written code

There is no separate quality bar for AI-assisted implementation. Code is code. If a test exists, the code must pass it regardless of who or what wrote it.

### Tests should support drift detection, not just syntax correctness

A pipeline that parses correctly today may produce subtly different outputs tomorrow when source formats change. Tests must detect semantic drift, not just check that code compiles.

### Regression tests should be added for real bugs

When a bug is found and fixed, add a test that would have caught it. This is how the test suite grows organically and usefully.

---

## Test Type Definitions

### Unit tests

Test a single function, method, or class in isolation. No external dependencies (no database, no network, no file system).

- **Example:** a parsing helper correctly extracts a section title from raw HTML.

### Contract tests

Validate that data structures conform to agreed schemas. Contract tests enforce boundary agreements between components.

- **Example:** a `RawArtifactEnvelope` payload passes JSON Schema validation.

### Golden tests

Compare the output of a processing step against a known-good expected result for a specific input.

- **Example:** processing `golden/statute-123.html` produces a Document with 12 sections and 3 citations.

### Smoke tests

Lightweight checks that a system is running and reachable. Fast, deterministic, minimal assertions.

- **Example:** the search API returns HTTP 200 and a non-empty result for a known query.

### Integration tests

Test the interaction between two or more components or between a component and an external dependency (database, message queue, search index).

- **Example:** publishing a `raw_artifact.available` event results in a processed document appearing in Delta.

### End-to-end tests

Verify a full user-facing workflow from entry to exit across all components.

- **Example:** creating a source → triggering a run → processing the artifact → searching for the document.

### Drift detection checks

Automated checks that compare current system behavior or output characteristics against known baselines. Designed to catch gradual degradation.

- **Example:** average section count per document type has not changed by more than 20% since the last baseline.

---

## What NOT to Do Early

- Do not build a large snapshot test suite
- Do not invest in visual regression testing before the UI stabilizes
- Do not create flaky integration tests that block development
- Do not test implementation details — test observable behavior
- Do not duplicate contract validation that already exists in schema checks
