# ADR-0052: Declared means produced

## Status

Proposed

## Date

2026-09-03

## Context

### An absent field is a question; a declared, unwritten field is an answer

Ask a corpus whether a norm delegates competence downward. If the field is absent, the
system does not know what you are asking and says so. If the field is declared and nothing
has ever written it, the system answers **"none"** — confidently, in the shape you expected,
with no error anywhere. `AGENTS.md` records the mechanism twice: *"because OpenSearch returns
empty buckets rather than an error for a missing field, both presented as query bugs for
months"* (#675, #713). ADR-0048 measures the consequence — one of `/v1/coverage`'s four
`group_by` dimensions and its entire temporal filter are dead in production, silently.

This is the reason ADR-0033 exists in one sentence: a legal-research system that answers
"none" when it means "not yet" is worse than one that refuses.

### Six declarations with no producer, found on 2026-09-03

| Declaration | Declared at | Producer |
|---|---|---|
| `delegates_to` | `contracts/schemas/document.schema.json:104`, `contracts/schemas/search-projection.schema.json:119`, `legal-search/api/src/core/opensearch/documents-index.mapping.ts:114`, `scripts/opensearch/documents-index.mapping.json:124` | none |
| `di_overrides.quarantine_min_extracted_chars` / `_min_legal_markers` | `contracts/schemas/artifact-bundle-manifest.schema.json:190,195`; read at `document-intelligence/src/document_intelligence/normalize/quarantine.py:198-199` | none in `platform-control/src` |
| `searchParamsCache` | `legal-search/frontend/src/lib/search-params.ts:101` | no consumer in `src/` |
| `canonicalization_rules` | `platform-control/src/acquisition_core/normalization.py:37` | no caller passes it |
| `refused` | built by ADR-0035 (#634), on `RunResponse` and `?refused=true` | no admin view renders it |
| `side_effect_level: "irreversible"` | `contracts/schemas/workflow-command-envelope.schema.json:48` | zero call sites emit it |

Each deserves a sentence, because they are not the same failure.

**`delegates_to` is the good case, and it shows the cost of doing this by hand.**
`projections.repository.ts:111` says *"Declared, not yet produced."*
`projections.service.ts:250` says it is not derivable from the jurisdiction tree. The schema
description says `UNPOPULATED TODAY`. `docs/components/legal-search.md:64` says *"Not derived
— unpopulated"*. `marketing/src/lib/content.ts:17,132` cites it as the reason a capability
sits in `NOT_YET`. ADR-0048 calls it *"a third case"* not fixed by a reindex or a
re-projection. Six surfaces agree, every one of them hand-written, every one of them a note
somebody added after being misled once. Hand-maintenance is the thing this repo already
decided against for contracts (ADR-0034).

**`quarantine_min_*` is ADR-0047's own lever with no handle.** The ADR argues at `:174-176`
that quarantine floors must be per-source config rather than global constants, because *"the
honest minimum for a cantonal act is not the honest minimum for a one-article communal
ordinance"*; #841 landed the *reader*. A consumer is not a producer, and re-verification
after #841 confirms the writer still does not exist (`.claude/workflows/README.md:190`).

**`searchParamsCache` is the compound failure**: no consumer *and* prose claiming otherwise.
Its module docstring said the cache was used by Server Components while it had none, and —
in the words of the correction now on `main` at `search-params.ts:89-99` — *"that claim is
what let five call sites drift unnoticed (#822)"*. The correction is exactly right, and it
is a comment.

**`canonicalization_rules` is inert with a passing test.** The only production caller,
`run_service.py:1438`, calls `pipeline.normalize(run_id=..., resources=...)` and passes no
rules, so every capture is normalised with `strip_query_params=set()` and
`collapse_trailing_slash=False`. `test_acquisition_core_normalization.py:29` exercises the
parameter and passes. It proves the parameter works; it does not prove anything uses it.

**`refused` is a produced field with no reader.** ADR-0035 built the refusal record and the
`?refused=true` filter; on `main` no admin view renders it — the only `refused` strings in
`platform-control/admin/src` outside generated types are copy in the enablement dialog and
the readiness messages. M15 names this; #861 (open) is the first renderer. It is the mirror
image of the others and belongs in the same class: a declaration that reaches nobody.

**`irreversible` is the one that stings.** It was found in the very component the OSS survey
proposed for publication as the repo's cleanest boundary (#865, open). Every `build_envelope`
call site in `workflow_cmd.py` and `coverage_cmd.py` passes `none` or `reversible`. The
distinctive third of the distinctive field has no producer, and #865 adds a conformance test
for it *precisely because nothing exercises it* — which tests the schema, not the platform.

### Why this one is different from the other three defect classes

It is the only one of the four that is **mechanizable end to end**. Declarations live in
files with a schema; producers are assignments and literals. The rule can be a gate rather
than a discipline, and that is the whole argument for writing it down as an ADR.

## Decision

**A field or enum value declared in a contract, schema or index mapping must have a producer
— or must declare that it does not, in a form a machine reads.**

1. **The gate.** A checker (`scripts/check_declared_fields_produced.py`) walks
   `contracts/schemas/*.json`, `contracts/events/*.json`,
   `contracts/api/platform-control.openapi.yaml` and the generated
   `scripts/opensearch/documents-index.mapping.json`, and for each declared leaf field and
   each declared enum value looks for a writer in the producing surfaces. Zero writers is a
   failure. It runs from `scripts/`, so pre-commit and CI invoke the same check, per the
   `AGENTS.md` rule.

2. **The escape hatch is the load-bearing half.** A field may be declared ahead of its
   producer by carrying a machine-readable marker — an `x-unproduced` keyword in JSON
   Schema, an `UNPRODUCED:` tag in the TypeScript mapping comment — with a reason and an
   issue number. The gate reads it, prints the register on every run, and **fails when a
   registered field acquires a producer**, so the register cannot outlive the debt. This is
   ADR-0040's rule verbatim (*"debt is registered, not silenced"*) and the same shape as
   `ALLOWED_SKIPS` and `KNOWN_UNREACHABLE`.

3. **Enum values are declarations.** `irreversible` sits inside a field that is abundantly
   produced; a field-level check waves it through. The unit is the declared *value*.

4. **A consumer is not a producer.** #841 landed the reader for `quarantine_min_*` and the
   declaration stayed dead. The gate must not accept a read, a type definition, a fixture or
   a test as satisfying a declaration.

5. **Where the producer is deliberately external, name it.** A field a client writes, or an
   upstream system supplies, is registered with that as the reason. That is not a gap; it is
   a different producer, and the register is where the platform says which.

**What the marker buys the reader** is the thing six hand-written notes were buying for
`delegates_to`: an answer to "is this empty because there is nothing, or because nobody has
written it yet?" — available at the declaration, not four files away.

## Consequences

### What gets better

- The read path stops answering "none" where it means "not yet", or says so at the point of
  declaration.
- A new schema field cannot ship inert without saying it is inert. `refused`,
  `quarantine_min_*` and `irreversible` would each have been a build failure or a registered
  entry on the day they landed.
- The `delegates_to` notes collapse from six hand-maintained prose statements to one marker
  the gate reads — and the prose that remains is explanation rather than load-bearing fact.

### What gets harder

- **The gate will produce false positives, and this is its main cost.** A producer that
  builds its payload dynamically — `**request.model_dump()`, a dict comprehension, an object
  spread, a `setattr` loop — is invisible to a static walk. Those will be registered too,
  with "produced, but not statically visible" as the reason. That category is honest and it
  erodes the register's meaning if it grows: **the gate must print the two categories
  separately, and the size of the second is the health metric for the gate itself.** If it
  outgrows the first, the gate is measuring its own blindness and should be narrowed to the
  surfaces where producers are statically legible.
- **The gate answers "does a writer exist", not "does it run".** A field written only on a
  branch nothing takes passes. That question is ADR-0048's (a projection that ran) and
  ADR-0030's (acceptance evidence), and this ADR does not claim to answer it.
- **Registering is easier than producing.** A lane under pressure will register. Same trade
  ADR-0040 made, same mitigation: printed on every run, requires a reason and an issue, and
  goes stale loudly.
- **First adoption will be noisy.** The six above are the ones found by hand in a day; a
  mechanical walk will find more, and the honest first move is to register what it finds
  rather than to fix it all at once — the same reasoning ADR-0040 gives for `KNOWN_UNREACHABLE`
  over a check that cannot go green on `main`.

### Not covered

- **Prose is out of scope.** A `README` or ADR naming a field that does not exist — ADR-0030
  §5's `--url-pattern`, #855's `--copy-evidence` — is the same defect class and this gate
  does not see it. That is ADR-0050's territory and it has no mechanism yet.
- **Unread produced fields are only partly covered.** `refused` is produced and rendered by
  nothing; the gate as specified checks producers, not consumers. Extending it to "declared
  and never read by any surface" is a larger and much noisier question — a contract field
  legitimately exists for consumers outside the repo — and is deliberately not proposed
  here. M15 owns the specific case.

### Relationship to existing ADRs

Amends **ADR-0004** in one respect: declaring a field at `contracts/` is now a commitment
with a build consequence rather than a free forward reference. It changes nothing about where
contracts live or who owns them. It extends **ADR-0034**'s argument — a hand-maintained
artifact describes the past — from whole documents to individual fields, and it gives
**ADR-0047**'s override lever and **ADR-0048**'s `delegates_to` a mechanism instead of a
paragraph.

## References

- #675, #713, #728 — a missing field is silent, not an error
- #822 — the `searchParamsCache` claim, and the five call sites it hid
- #841 — the `quarantine_min_*` consumer, landed without a writer
- #865 — `irreversible`, found in the component proposed for publication (open)
- #861, M15 — `refused` reaching a screen (open)
- [ADR-0034](0034-generated-platform-control-contract.md) — hand-maintained artifacts drift
- [ADR-0040](0040-test-result-trust.md) — debt is registered, not silenced
- [ADR-0047](0047-quarantine-unhandled-document-classes.md) — per-source quarantine floors
- [ADR-0048](0048-completeness-crosses-the-boundary-by-projection.md) — `delegates_to` as
  "a third case", and the empty buckets it produces
