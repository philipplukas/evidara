# Implementation Principles

## Core Principles

### 1. Canonical truth is separate from serving projections

Delta tables hold the canonical, authoritative representation of all processed document intelligence. OpenSearch holds derived, search-optimized projections. Serving projections can be fully rebuilt from canonical truth. Canonical truth is never rebuilt from serving projections.

### 2. Elasticsearch/OpenSearch is not source of truth

OpenSearch is a serving layer. It is optimized for fast, user-facing queries. It is not durable storage and it is not the system of record. If OpenSearch data is lost, it is rebuilt from Delta. No business logic should depend on OpenSearch being the only place data exists.

### 3. AI may propose changes but not silently mutate production state

Any AI-driven process (e.g., AI-assisted classification, jurisdiction assignment, or content enrichment) may propose changes, but those changes must be reviewed and approved before becoming production truth. AI proposals are tracked as proposals until explicitly accepted.

### 4. Contracts must be explicit

All inter-component communication happens through contracts defined in `contracts/`. No component may depend on the internal implementation details of another component. If a dependency is not in a contract, it does not exist.

### 5. Events are used for async pipeline progression

When one component's output triggers another component's processing, the mechanism is an event (e.g., `raw_artifact.available`, `document.processed`). Events decouple the producer from the consumer and allow independent scaling and failure handling.

### 6. APIs are used for control and query interactions

Synchronous interactions — such as creating a source, querying run status, or searching documents — use REST APIs defined in OpenAPI specs. APIs are the mechanism for request-response interactions where the caller needs an immediate answer.

### 7. Storage is chosen by access and change pattern

Each storage technology is selected based on the data's access pattern, change frequency, and query requirements. See [Storage Model](storage-model.md) for details. No single database is forced to serve all use cases.

### 8. Boundaries are enforced at the folder level

Each top-level folder in the monorepo represents a component with clear ownership. Components do not reach into each other's internal code. Cross-component interactions go through contracts.

### 9. Document everything that is not obvious

Architecture decisions are captured in ADRs. Component responsibilities are documented in component docs. Contracts are explicit schemas. If a design choice could surprise a new contributor, it should be documented.

### 10. Start minimal, expand deliberately

Every new feature, schema, and API starts with the smallest viable version. Expansion is driven by concrete needs, not speculative completeness. Each expansion step is deliberate, documented, and reviewed.
