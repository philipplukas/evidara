# Testing Principles

## Purpose

Define the core testing philosophy for Evidara.

## Core Principles

### A test result must be trustworthy before it is useful

This document says what to test. [ADR-0040](../adr/0040-test-result-trust.md) says
when to believe the answer, and it takes precedence where the two disagree.

Its three conditions, which must hold **in this order**:

1. **Isolation** — the run's inputs come from the checkout under test, not from
   an ambient server, container, port, or module-resolution path.
2. **Coverage honesty** — every committed test file is collectable by some CI
   job, every skip is argued for, and the local gate collects the same
   population as CI.
3. **Assertion strength** — the assertion's passing condition matches the
   property being claimed.

The ordering is the point: a tolerance argument is meaningless if the run might
not be hitting your code, and knowing which specs run is meaningless if what
runs asserts nothing.

Two guards enforce this today —
[`scripts/check_test_reachability.py`](../../scripts/check_test_reachability.py)
(no committed test file may be unreachable from CI) and
[`platform-control/tests/ci_skip_guard.py`](../../platform-control/tests/ci_skip_guard.py)
(CI may not skip without an allowlisted reason).

### Maximize confidence with minimal effort

A small team cannot maintain thousands of tests. Every test must justify its existence.

### Stabilize IDs and boundary contracts first

Before testing complex behavior, ensure IDs, revisions, and boundary contracts are stable and validated.

### Test canonical truth separately from serving projections

Canonical data and search projections serve different purposes and must be tested separately.

### Use golden examples, invariants, and smoke tests

- **Golden examples** — known-good inputs with expected outputs
- **Invariants** — conditions that must always hold
- **Smoke tests** — basic end-to-end checks

## Test Type Definitions

### Contract tests

Validate that payloads conform to agreed schemas.

- **Example:** an `ArtifactBundleManifest` payload passes JSON Schema validation.

### Integration tests

Test the interaction between two or more components.

- **Example:** publishing an `artifact_bundle.available` event results in a canonical-ready document revision.
