# Doc Types And Authority

## Key Rule

**Prose docs should reference contract files, not duplicate them.**

Instead of:

> "The `artifact_bundle.available` event contains bundle lineage, origin facts, and a manifest ref."

Write:

> "The `artifact_bundle.available` event is defined in `contracts/events/artifact-bundle-available.schema.json`."

This prevents prose from going stale when contracts evolve.
