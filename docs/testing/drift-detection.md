# Drift Detection

## Purpose

Document how Evidara detects and responds to drift — gradual, often silent changes in system behavior that degrade data quality or correctness over time.

## Core Truth

**Drift cannot be prevented completely.**

Sources change format. Parsing logic evolves. Search indexes get rebuilt. Each of these introduces opportunities for subtle degradation. The goal is not prevention — it is **early detection and safe recovery**.

---

## Drift Categories

### Source / Layout Drift

**What:** The format, structure, or layout of a legal source changes without warning.

**Examples:**
- A government website redesigns its document pages
- HTML class names change, breaking scrapers
- A new document type appears that the parser does not handle

**Impact:** Raw artifacts look different. Parsing produces unexpected results or fails silently.

### Schema Drift

**What:** The shape of data exchanged between components changes in ways that break consumers.

**Examples:**
- A required field is removed from `RawArtifactEnvelope`
- An event payload gains a new field that a consumer does not expect
- A JSON Schema is updated but example payloads are not

**Impact:** Contract violations. Components may reject or misinterpret messages.

### Semantic Drift

**What:** Processing output changes meaning even though the pipeline still runs.

**Examples:**
- A parsing update causes sections to be split differently
- Citation extraction misses a class of citations
- Jurisdiction assignment defaults to the wrong value

**Impact:** Canonical truth degrades. Downstream search results become less accurate.

### Serving / Index Drift

**What:** The search index diverges from canonical truth.

**Examples:**
- A reindex skips documents due to a filter bug
- Projection logic strips fields that the frontend expects
- Index mapping changes cause fields to be analyzed differently

**Impact:** Users cannot find documents that should be findable. Detail pages show incomplete data.

---

## Minimal Anti-Drift Strategy

These techniques are achievable for a 1–3 person team and provide meaningful coverage.

### Golden Samples

Maintain 10–20 representative documents as golden samples. Process them regularly and compare outputs against expected baselines.

- Catches: source/layout drift, semantic drift
- Cost: low (maintain a small set of known-good inputs and outputs)
- Frequency: every PR or nightly

### Invariants

Define conditions that must always hold, regardless of input.

- Every document has a `source_id` and `run_id`
- Every section belongs to exactly one document
- Citation counts are non-negative
- Document processing produces at least one section

- Catches: semantic drift, processing bugs
- Cost: very low (simple assertions)
- Frequency: every test run

### Simple Distribution Checks

Monitor aggregate statistics and alert when they change significantly.

- Average section count per document type
- Citation count per document
- Null rate for key fields (`title`, `jurisdiction`)
- Document count per source family

- Catches: semantic drift, source/layout drift
- Cost: low (compute stats, compare to baseline)
- Frequency: nightly or weekly

### Canary Runs

Process a small set of real source data through the full pipeline and verify outputs before processing the full batch.

- Catches: source/layout drift, integration issues
- Cost: medium (requires a subset of real data)
- Frequency: before full batch runs

### Query Smoke Tests

Run 3–5 known queries against the search index and verify expected results appear.

- Catches: serving/index drift
- Cost: very low
- Frequency: after every reindex, nightly

### Indexing Parity Checks

Compare the number of canonical documents eligible for indexing against the number actually indexed.

- Catches: serving/index drift, reindex failures
- Cost: very low (count comparison)
- Frequency: after every reindex

---

## Recovery Approach

When drift is detected:

1. **Do not panic.** Drift is expected. The system is designed to recover.
2. **Identify the category.** Determine whether the drift is source, schema, semantic, or serving.
3. **Assess impact.** Is this affecting live users? How many documents are affected?
4. **Fix forward or reprocess.** Depending on the category:
   - Source drift → update scraper/parser, reprocess affected artifacts
   - Schema drift → update contract, coordinate with consuming components
   - Semantic drift → fix processing logic, rerun golden tests, reprocess
   - Serving drift → fix projection, reindex
5. **Add a regression test.** If the drift exposed a gap, add a golden sample or invariant that would catch it next time.

---

## What NOT to Build Early

- Full statistical monitoring dashboards
- Automated drift remediation pipelines
- Complex anomaly detection models
- Source format change prediction

These are valuable later. For MVP, golden samples + invariants + smoke tests cover the most ground.
