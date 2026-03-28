# Minimal Test Matrix

## Purpose

Show the smallest credible test set for the entire Evidara platform. This matrix defines what a 1–3 person team must have in place for MVP confidence.

---

## Test Matrix

| Component | Test Type | Minimal MVP Requirement | Confidence Provided | Later Expansion |
|-----------|-----------|------------------------|--------------------|-----------------| 
| **platform-control** | Unit tests | State transition tests for runs and approvals | Run lifecycle is correct | Full CRUD coverage |
| **platform-control** | Contract tests | `RawArtifactEnvelope` schema validation | Boundary payloads are valid | All API schemas |
| **platform-control** | Smoke tests | One source family: create source → trigger run → record artifact | Source lifecycle works end-to-end | Multiple source families |
| **platform-control** | Drift checks | Artifact count not zero, content type check | Sources are still producing | Size/distribution checks |
| | | | | |
| **document-intelligence** | Unit tests | Parsing helpers, section construction logic | Core processing is correct | Full parser coverage |
| **document-intelligence** | Schema tests | `Document`, `Section`, `Citation` validation | Canonical output shape is correct | Full field validation |
| **document-intelligence** | Golden tests | 10–20 representative documents | Processing quality is stable | Expanded per source family |
| **document-intelligence** | Invariants | Lineage present, sections ordered, required fields | Critical properties always hold | Distribution-based checks |
| **document-intelligence** | Drift checks | Section count change, citation count change, null rate spikes | Semantic degradation is detectable | Statistical monitoring |
| | | | | |
| **legal-search (backend)** | Unit tests | Projection builder, query builder | Serving logic is correct | Full API coverage |
| **legal-search (backend)** | Contract tests | Search/detail API response validation | API shape is stable | Pagination, filters |
| **legal-search (backend)** | Smoke tests | Index 3–5 docs, run known queries | Search works for basic cases | Query quality monitoring |
| **legal-search (backend)** | Parity check | Canonical docs eligible vs docs indexed | Index is complete | Per-field parity |
| | | | | |
| **legal-search (frontend)** | Render tests | Search page renders, detail page renders | Pages load without crashing | Component-level tests |
| **legal-search (frontend)** | User flow test | Search → results → detail page | Core user path works | Mobile/responsive tests |
| **legal-search (frontend)** | Filter test | Apply jurisdiction filter → results update | Filtering works | All filter combinations |
| **legal-search (frontend)** | Error state test | Empty results / error handling | Edge cases handled | Offline / slow network |
| | | | | |
| **contracts** | Schema checks | JSON Schema validity, OpenAPI lint | Schemas are well-formed | Full compatibility checks |
| **contracts** | Payload validation | Core payloads pass schema validation | Examples match schemas | Automated on schema change |
| | | | | |
| **infra** | Format / validate | `terraform fmt`, `terraform validate` | Config is syntactically correct | Policy checks |
| **infra** | Plan generation | `terraform plan` runs without errors | Changes are reviewable | Drift detection |
| **infra** | Doc consistency | Infra docs match actual structure | Documentation is trustworthy | Automated sync checks |
| | | | | |
| **end-to-end slice** | Full path test | Source → run → artifact → process → index → search | The whole system works for one path | Multiple paths, error paths |
| **end-to-end slice** | Broken path test | Processing failure is surfaced, not silent | Failures are visible | Alerting integration |

---

## Reading This Matrix

- **Minimal MVP Requirement:** what must exist before shipping anything to users
- **Confidence Provided:** the question this test answers
- **Later Expansion:** natural next step once MVP is stable

## Key Insight

The total MVP test count is small — roughly:

- ~15–20 unit tests across all components
- ~5 contract/schema tests
- ~10–20 golden sample tests (document-intelligence)
- ~5 invariant checks
- ~5 smoke tests
- 1 end-to-end slice
- 5 frontend behavior tests

This is intentionally modest. A small team should not maintain tests it cannot keep green.
