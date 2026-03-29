# Testing Levels

## Level 3: Contract Tests

**Purpose:** Validate schemas and event contracts at component boundaries.

**What it catches:**

- Schema violations in API payloads, events, and stored data
- Breaking contract changes between components
- Missing required fields and invalid enum values

**Expected frequency:** Run on every commit.

**Required in MVP:** Yes. Schema validation for core contracts (`ArtifactBundleManifest`, `Document`, `Section`, `ProcessingManifest`, events) is required from day one.
