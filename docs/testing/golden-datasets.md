# Golden Datasets

## Purpose

Document the strategy for building and maintaining golden datasets — small, representative sets of test data with known-good expected outputs.

## Core Philosophy

### Keep golden datasets small

A golden dataset of 10–20 documents provides far more value than a dataset of 1,000 if the 10–20 are well chosen. Larger datasets are harder to maintain, slower to run, and generate more noise.

### Use representative artifacts only

Each golden sample should represent a distinct category of input that the system must handle correctly. One well-chosen statute is better than ten similar statutes.

### Focus on a few coarse assertions, not full annotation

Do not attempt to annotate every field of every golden document. Assert on the things that matter most:

- Document exists and has the right type
- Expected number of sections (within a tolerance)
- Key citations are present
- Jurisdiction and source lineage are correct
- Required fields are populated

### Expand only when justified

Add new golden samples only when:

- A real bug is found that existing samples would not have caught
- A new source family is added
- A significant processing change is made

Do not grow the golden set "just in case."

---

## How to Choose Golden Samples

Select documents that cover:

| Dimension | What to cover |
|-----------|--------------|
| Source family | At least one sample per major source type (statute, regulation, court decision, etc.) |
| Complexity | One simple document, one complex document with many sections |
| Edge cases | Documents with unusual structure (no sections, very long, special characters) |
| Jurisdictions | At least one sample per jurisdiction handled in MVP |
| Known trouble spots | Documents that caused bugs in the past |

### Initial target: 10–20 documents

| Count | Category |
|-------|----------|
| 3–5 | Statutes (various jurisdictions) |
| 3–5 | Regulations |
| 2–3 | Court decisions |
| 1–2 | Edge cases (very short, very long, unusual format) |
| 1–2 | Documents that triggered past bugs |

---

## Where to Store Golden Samples

```
tests/
  golden/
    inputs/
      statute-ch-or-123.html
      regulation-de-by-456.pdf
      decision-at-ogh-789.html
      ...
    expected/
      statute-ch-or-123.json
      regulation-de-by-456.json
      decision-at-ogh-789.json
      ...
    README.md
```

### Rules

- **`inputs/`** — raw artifacts exactly as they would arrive from platform-control
- **`expected/`** — expected canonical output after document-intelligence processing
- **`README.md`** — describes each golden sample: why it was chosen, what it represents, what assertions it supports
- Name files clearly with source family and jurisdiction
- Keep files in version control

---

## What Assertions to Keep

For each golden sample, assert:

| Assertion | Example |
|-----------|---------|
| Document exists | Processing produces a non-null Document |
| Document type correct | `type == "statute"` |
| Section count in range | `sections.length >= 5 && sections.length <= 15` |
| Key sections present | `sections.some(s => s.title.includes("Art. 1"))` |
| Citations extracted | `citations.length >= 2` |
| Jurisdiction correct | `jurisdiction == "CH-OR"` |
| Lineage present | `source_id != null && run_id != null && artifact_id != null` |
| Required fields populated | `title != null && title.length > 0` |

### Use tolerances, not exact matches

Processing improvements should not break golden tests. Assert on structure and key properties, not exact string matches of body content.

---

## How to Add Regression Cases After Bugs

When a bug is found:

1. **Identify the input** that triggered the bug (or create a minimal reproducing input).
2. **Add the input** to `tests/golden/inputs/`.
3. **Fix the bug.**
4. **Capture the correct output** after the fix and add it to `tests/golden/expected/`.
5. **Document in `tests/golden/README.md`** why this sample was added (link to issue/PR).
6. **Add specific assertions** for the condition the bug violated.

This ensures the bug cannot silently reappear.

---

## Golden Dataset Maintenance

- Review the golden set quarterly or when major changes ship
- Remove samples that no longer represent real input categories
- Update expected outputs when intentional processing changes occur (document the change)
- Never update expected outputs to "make the test pass" without understanding why the output changed
