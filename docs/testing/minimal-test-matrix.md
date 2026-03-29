# Minimal Test Matrix

| Component | Test Type | Minimal MVP Requirement | Confidence Provided | Later Expansion |
|-----------|-----------|------------------------|--------------------|-----------------|
| **platform-control** | Unit tests | State transition tests for runs and approvals | Run lifecycle is correct | Full CRUD coverage |
| **platform-control** | Contract tests | `ArtifactBundleManifest` schema validation | Boundary payloads are valid | All API schemas |
| **platform-control** | Smoke tests | One source family: create source → trigger run → record bundle manifest | Source lifecycle works end-to-end | Multiple source families |
| **document-intelligence** | Unit tests | Parsing helpers and section construction | Core processing is correct | Full parser coverage |
| **document-intelligence** | Schema tests | `Document`, `Section`, `ProcessingManifest` validation | Canonical output shape is correct | Full field validation |
| **legal-search (backend)** | Unit tests | Projection builder and query builder | Serving logic is correct | Full API coverage |
