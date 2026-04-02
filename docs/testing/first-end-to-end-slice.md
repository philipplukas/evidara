# First End-to-End Slice

## Purpose

Define the minimal first end-to-end test that proves the entire Evidara pipeline works from governed source setup to searchable document retrieval.

## The Happy Path

This test verifies the full lifecycle of one document revision:

```text
platform-control          document-intelligence          legal-search
      │                          │                            │
      ├─ source exists           │                            │
      ├─ run is created          │                            │
      ├─ bundle manifest stored ─┤                            │
      │                          ├─ bundle received          │
      │                          ├─ document processed       │
      │                          ├─ published refs created ──┤
      │                          │                            ├─ doc indexed
      │                          │                            ├─ search returns it
      │                          │                            └─ detail page shows it
```

### Steps

1. **Source exists in platform-control**
   - A source is registered in a corpus
   - A source version exists and is approved

2. **Run is created**
   - A run is initiated for the approved source version
   - Run state transitions correctly

3. **Artifact bundle is stored**
   - The run produces one or more raw artifacts in object storage
   - An `ArtifactBundleManifest` is written
   - An `artifact_bundle.available` event is emitted

4. **document-intelligence processes the bundle**
   - The bundle is received and processing begins
   - Parsing, segmentation, and metadata resolution succeed

5. **Canonical document revision is created**
   - A `Document` with valid `document_id`, `document_revision`, and provenance
   - At least one `Section`
   - A `ProcessingManifest` with exact published refs
   - A `document.processed` event is emitted

6. **legal-search indexes it**
   - The projection builder reads the published refs
   - The document is indexed in OpenSearch
   - Indexing parity: one published document revision → one indexed document

7. **Search query returns it**
   - A search query matching the title returns it
   - The result contains expected fields

8. **Detail page/API can display it**
   - The detail endpoint returns the full document with sections
   - Expected fields are populated
