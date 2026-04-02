# Drift Detection

## Purpose

Document how Evidara detects and responds to drift.

## Drift Categories

### Source / Layout Drift

Sources change shape without warning. Bundle contents or content types shift and downstream parsing degrades.

### Schema Drift

Examples:

- A required field is removed from `ArtifactBundleManifest`
- A consumer stops understanding `document.processed`
- Example payloads are not updated with schema changes

### Semantic Drift

Examples:

- Sectionization changes unexpectedly
- Citation extraction regresses
- Jurisdiction defaults drift

### Serving / Index Drift

Examples:

- A reindex skips document revisions
- Projection logic drops required fields
- Withdrawal events are ignored
