# Testing Principles

## Purpose

Define the core testing philosophy for Evidara.

## Core Principles

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
