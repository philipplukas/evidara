# First End-to-End Slice

## Purpose

Define the minimal first end-to-end test that proves the entire Evidara pipeline works — from source creation to a searchable, displayable document.

---

## The Happy Path

This test verifies the full lifecycle of a single document:

```
platform-control          document-intelligence          legal-search
      │                          │                            │
      ├─ source exists           │                            │
      ├─ run is created          │                            │
      ├─ raw artifact stored ────┤                            │
      │                          ├─ artifact received         │
      │                          ├─ document processed        │
      │                          ├─ canonical doc created ────┤
      │                          │                            ├─ doc indexed
      │                          │                            ├─ search returns it
      │                          │                            └─ detail page shows it
      │                          │                            
```

### Steps

1. **Source exists in platform-control**
   - A source is registered with a valid jurisdiction and authority
   - A source version exists

2. **Run is created**
   - A run is initiated for the source version
   - Run state transitions correctly (e.g., `pending` → `running` → `completed`)

3. **Raw artifact is stored**
   - The run produces a raw artifact stored in object storage
   - A `raw_artifact.available` event is emitted
   - The event payload conforms to the `RawArtifactEnvelope` schema

4. **document-intelligence processes the artifact**
   - The artifact is received and processing begins
   - Parsing, segmentation, and metadata extraction succeed

5. **Canonical document is created**
   - A `Document` with valid `document_id`, `source_id`, `run_id`, `artifact_id`
   - At least one `Section` with proper ordering
   - Citations extracted (if applicable)
   - Lineage is fully traceable
   - A `document.processed` event is emitted

6. **legal-search indexes it**
   - The projection builder creates a search-ready representation
   - The document is indexed in OpenSearch
   - Indexing parity: 1 canonical doc → 1 indexed doc

7. **Search query returns it**
   - A search query matching the document title returns it in results
   - The result contains expected fields (title, jurisdiction, snippet)

8. **Detail page/API can display it**
   - The detail endpoint returns the full document with sections
   - All expected fields are present and populated

### Assertions

| Assertion | What it proves |
|-----------|---------------|
| Run completes successfully | platform-control lifecycle works |
| Event payload is schema-valid | Boundary contract is honored |
| Document has lineage | IDs propagate correctly across boundaries |
| Document has sections | Processing produced meaningful output |
| Document appears in search | Indexing and search work |
| Detail shows full content | Serving projection is complete |

---

## The Broken Path

One test must verify that failures are visible — not silently swallowed.

### Scenario

Processing fails or produces a low-quality result:

- A raw artifact is malformed or contains unexpected content
- document-intelligence cannot parse it cleanly
- The result has zero sections or missing required fields

### Expected behavior

- The processing failure is recorded (logged, event emitted, status updated)
- The bad document is **not** silently indexed as if it were good
- The issue is surfaceable — a human or monitoring system can find out what went wrong
- No downstream component treats the bad output as trusted

### Assertions

| Assertion | What it proves |
|-----------|---------------|
| Processing failure is recorded | System does not silently swallow errors |
| Bad document not indexed | Search does not serve garbage |
| Issue is discoverable | Team can identify and investigate failures |

---

## Implementation Notes

### When to implement this test

This test should be the **last test added during MVP** — after individual component tests exist. It depends on all components being at least minimally functional.

### How to run it

- Initially: manual script or test harness that orchestrates the steps
- Later: automated E2E test in CI (runs on merge to main or nightly)

### What to use as test data

Use one golden sample from `tests/golden/inputs/` as the raw artifact. This ensures the E2E test and the golden dataset tests reinforce each other.

### Environment requirements

- Requires all three components running (or mocked at boundaries)
- Requires object storage (can use local emulator or test bucket)
- Requires message queue (can use local emulator or test topic)
- Requires OpenSearch (can use local instance or test container)
