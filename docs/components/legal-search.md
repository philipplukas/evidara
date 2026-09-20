# Legal Search

## Purpose

Serve legal and document search and detail experiences to users. Legal-search is the user-facing serving layer that consumes published canonical surfaces from document-intelligence and turns them into OpenSearch projections and UI/API responses.

## Current state

The `legal-search/` folder contains:

- **Frontend (Next.js 16):** Full workspace UI with resizable panels, filter panel, result list, detail panel with tabs, mobile layout. 43 components using shadcn/radix primitives and a custom design system. Default runtime uses the live BFF via generated clients; e2e keeps an explicit mock mode for deterministic smoke checks.
- **BFF (NestJS):** Search and document detail endpoints wired to OpenSearch. Contract-first ViewModel mappers (ADR-0011, ADR-0012) with vocabulary-driven labels and observable fallbacks. 104 tests passing. Labels are in German (ADR-0013).
- **OpenSearch adapters:** Search with multi_match, faceted aggregations (jurisdiction, document type, language), highlight-based snippets. Document detail with sections and citations.
- **Seed pipeline:** Script to ingest Swiss court decisions from opencaselaw.ch into a local OpenSearch index.
- **Contracts:** OpenAPI spec, search projection schema with provenance, controlled vocabularies for jurisdiction and document type.

The frontend is connected to the live BFF using generated API clients. Projection ingestion endpoints for `document.processed` and `document.withdrawn` are implemented, with idempotency and revision-order checks in the projection history layer.

## Source of truth

- Published canonical surfaces from document-intelligence are read-only inputs
- OpenSearch holds serving projections only
- `contracts/api/legal-search.openapi.yaml` defines the user-facing API
- `contracts/api/document-intelligence.openapi.yaml` defines the **Document Service** calls the BFF uses for document body reads (ADR-0010); configure `DOCUMENT_INTELLIGENCE_BASE_URL` in `legal-search/api` (see `.env.example`)

## Responsibilities

### Minimal v1

- Build search projections from published DI surfaces
- Maintain OpenSearch indices and aliases
- Maintain projection manifest/history for replay and audit
- Expose search and detail APIs
- Serve a minimal frontend search experience

### Boundary

- **Does own:** frontend, BFF, projection logic, OpenSearch mappings and aliases, indexing workflows
- **Does NOT own:** canonical truth, source management, parsing, reference data governance

## The hierarchy of norms

`GET /v1/norm-hierarchy/{jurisdiction_id}` answers *what governs this place, at each
level* — the traversal ADR-0033 builds the agentic layer on. It is not a search: the
governing chain is derived from the jurisdiction tree, not from text similarity.

**Where each piece comes from.** platform-control owns the jurisdiction tree and each
jurisdiction's `level` (`constitutional` / `international` / `federal` / `cantonal` /
`municipal` — ranked in `contracts/vocabularies/norm-level.json`). legal-search must not
call platform-control at request time for reference data that cannot change between
deploys, so the tree is **exported at build time** by
`scripts/generate_jurisdiction_hierarchy_vocab.py` into
`contracts/vocabularies/jurisdiction-hierarchy.json` and loaded like any other
vocabulary. CI fails if the export drifts from the seed.

**What the projection derives** (`core/norm-hierarchy`, applied in
`ProjectionsService.buildProjection`):

| Field | Derived how |
|---|---|
| `level` | From the document's **jurisdiction**, never guessed from its text. Most specific jurisdiction wins. A document may declare `constitutional` for itself — the one level no jurisdiction can supply, since the BV is enacted by `jur_ch_federal` exactly like the TSchG. A declared level that would *demote* the norm is ignored. |
| `subordinate_to` | The jurisdictions whose law outranks it. A Zurich communal ordinance → `jur_ch_zh`, `jur_ch_federal`. The edge points at **scopes, not documents**: subordination in law is scope-wide, so a document→document edge would be a fiction. |
| `in_force_from` / `in_force_until` | `in_force_from` coalesces `effective_date`, so there is one field to range-query. `in_force_until` is the **last date the norm WAS in force** (inclusive). |
| `delegates_to` | **Not derived — unpopulated.** Delegation is an assertion made *by a norm's text* (the cantonal clause that lets a commune legislate at all), so it needs extraction or curation. The shape is declared in `contracts/schemas/document.schema.json` so the edge has a home. |

**Why `jur_ch_federal` is reachable from a canton.** In the seed, `jur_ch_federal` is a
*child* of `jur_ch`, and the cantons are its *siblings* — so walking parents alone would
never reach federal law from Zurich, and preemption would be unanswerable. The rule is
therefore: the scopes governing a jurisdiction are its ancestors, **plus each ancestor's
children at the same level**. A same-level child is a refinement of its parent's scope,
not a tier beneath it.

**Temporal validity is four-valued, not boolean.** `in_force_state` is `in_force`,
`not_yet_in_force`, `repealed`, or `unknown`. A norm marked `repealed` with no date
resolves to `unknown` — inventing `in_force` from a missing field is the confident
fabrication the platform exists to prevent. `in_force_at` filtering excludes only norms
*known* to be outside force; unknown-dated norms are kept and flagged, because dropping
them would hide law and silence is indistinguishable from absence.

**Coverage is load-bearing.** `coverage.missing_levels` names the levels that bind a
place but for which the corpus holds nothing. "I do not have the communal ordinance for
this place" is a correct answer (ADR-0033 §2); reasoning past a missing level is not.

## Corpus coverage

`GET /v1/coverage` (ADR-0042) answers *what do we hold for this scope* — grouped by
jurisdiction, authority, document type or norm level, optionally as of a date. It exists
because `coverage.missing_levels` above, while real, is **level-granular**, and the
failure it must prevent is instrument-granular: in the M13 iteration-2 measurement the
federal level was covered by the Bundesverfassung while TSchG and TSchV were absent, so
`missing_levels` was correct and silent about the only thing that mattered (#709).

**What it may be read to mean.** `holding: not_held` means *the search index contains no
document matching this scope*. It is a claim about our holdings, in the first person. It
is **not** a claim that the norm does not exist. The enum has exactly two members —
`held` and `not_held` — precisely so no caller can find a value meaning "confirmed absent
in law", and no such value will be added. The corpus is a subset of the law by
construction; no endpoint over it can be evidence of what the law does not contain. The
strongest claim it supports is a refusal, which per ADR-0033 §2 is a *correct* answer.

**Absence is reported, not inferred.** A terms aggregation produces no bucket for a value
absent from the index, so a jurisdiction the caller names explicitly always comes back as
a group — `documents: 0, holding: not_held` when we hold nothing. That positive statement
of absence is the point; without it a caller is back to inferring absence from emptiness,
which #672 showed is one filter bug away from being wrong.

**An unrecognized id is not a coverage answer.** A jurisdiction id the platform does not
know produces no group and is listed in `unrecognized_jurisdiction_ids`. Answering "we
hold nothing for `jur_ch_zurich`" would read as a coverage fact when the truth is that
the caller misspelled `jur_ch_zh`.

**Freshness is not currency.** `last_processed_at` is when the newest document in the
group entered the corpus — *not* when the source was last checked, and therefore not
evidence that no newer law exists. A jurisdiction whose law changed last week and whose
last acquisition ran a year ago reports a year-old timestamp with no staleness signal.
"When did we last check?" is run history, and it lives in platform-control (ADR-0042 §4).

**No completeness score.** "We hold 41 federal acts" is not "we hold all federal acts".
Nothing in the platform knows the denominator, so no percentage is reported; inventing
one would be the most dangerous field this endpoint could carry.

**Deployment note.** `level`, `subordinate_to`, `in_force_from` and `in_force_until` are
new mapping fields. Documents indexed before this change carry none of them and will not
appear in any level bucket until reprojected — see
`docs/runbooks/projection-reindex-backfill.md`.

## Search refusal on coverage grounds

`GET /v1/search` can decline to answer. When the query **names** a sub-federal
jurisdiction the index holds nothing for, the response carries a `refusal` object and an
empty `results` array instead of the best-scoring documents of some other canton (#986).

**This is not a relevance threshold, and there is no score floor.** Measured against
production's 889-document ZH corpus, `"Statistikgesetz Kanton Zürich"` (answerable) and
`"Hundegesetz Kanton Bern"` (not) score **identically**, 14.01. The ZH *Hundegesetz*
genuinely is in the corpus; the second query is wrong about the *canton*, not the topic,
so nothing about relevance differs. The in-corpus and out-of-corpus score populations
overlap end to end (lowest in 5.60, highest out 14.01), and a floor fitted to that sample
would withhold real answers on the next corpus.

**Refusal requires three positive findings, and the absence of any one answers normally:**

1. **The query names a jurisdiction.** Names come from
   `contracts/vocabularies/subdivisions.json` and are joined to canonical jurisdiction ids
   through the seed's slug (`CH-BE` → `jur_ch_be`); there is no hand-written canton list.
   A name alone is **not** enough — a tier marker must sit beside it (`Kanton Bern`,
   `canton de Berne`, `Bern (Kanton)`) or the ISO code must appear (`CH-BE`). Half the
   cantons are also ordinary words or cities: `Zug` is a train, `Jura` is a mountain
   range, and `Zürich`, `Bern`, `Basel` and `Genf` are cities. A bare "Mietrecht Bern" is
   therefore detected as nothing and searched exactly as before.
2. **The corpus's holdings are known.** A `jurisdiction_ids` terms aggregation over the
   read alias — the index *is* the corpus — cached for five minutes. A failed lookup, or
   one returning no buckets, is reported as **unknown** and refuses nothing. Empty buckets
   are what a drifted mapping produces (#675), so treating them as "holds nothing" would
   turn a mapping defect into a refusal of every jurisdictional query.
3. **None of the named jurisdictions is held.** "Kanton Bern und Kanton Zürich" against a
   ZH corpus is **answered**: a partial answer beats no answer.

The bias is deliberate and one-directional: **under-refuse, never over-refuse.** A false
answer is what this fixes, but a false refusal hides law a user is entitled to and — unlike
a wrong result — the caller cannot detect it.

**A refusal is not an empty result set.** `totalResults: 0` with no `refusal` still means
the query ran and matched nothing. The two are different answers and callers must not
flatten them into "no results" (#984). `holding: not_held` on a refused jurisdiction
carries exactly the meaning it does on `/v1/coverage` above: a statement about our
holdings, never about whether the law exists.

**Not yet consumed by the frontend.** The API produces the refusal and the generated
client types it; rendering it as something other than "no results" is follow-up work.

## Jurisdiction mentions as a ranking signal

When the corpus *does* hold the canton a query names, the question is no longer whether to
answer but which canton's law to answer with. `jurisdiction_ids` was indexed, filterable and
faceted, and contributed nothing to ranking — so the words "Kanton Bern" in a question moved
nothing, and a Zurich document whose title merely contains *Bern* outranked Bern's actual
Hundegesetz (measured against production, 9.76 vs 8.99; #975 gap A).

Search now passes the named jurisdictions to the ranker as a `should` clause on
`jurisdiction_ids.keyword`. Three properties define it:

1. **It is the same detection the refusal uses.** `detectSubdivisionMentions` runs once per
   query and feeds both, so a place is either understood for both purposes or for neither. A
   bare city name is still not a mention — see the refusal section above.
2. **It carries the whole governing-scope chain, not the canton alone.** `getGoverningScopes`
   resolves `jur_ch_zh` to `{jur_ch, jur_ch_federal, jur_ch_zh}` out of the jurisdiction seed,
   so an AT or DE overlay gets the same shape without a code change. Boosting the canton by
   itself pushed the federal Tierschutzgesetz from rank 15 out of the top 20 of the dog
   question entirely — a cantonal question in Swiss law always has a federal rung above it,
   and ADR-0033's acceptance test needs both.
3. **It re-ranks; it never filters.** The clause is `should`, so documents of every other
   jurisdiction are still returned and the hit total is unchanged — verified identical with
   and without the signal on all six labelled queries. A `filter` here would answer a
   question nobody asked and would hide the federal act.

**The weight is 1, and that is a measurement rather than a preference.** It is the smallest
integer weight that makes the property hold across a labelled set spanning ZH, BE and BS in
both query shapes, and it is deliberately worth less than one extra keyword match in
`title^4`: naming the canton breaks a near-tie, it does not override topical relevance. The
honest consequence is that "Tierschutz Hunde Kanton Zürich" still ranks two Bernese and
Basler ordinances above the first Zurich hit, because they outscore it topically by ~5
points. A weight large enough to flip that would be large enough to promote an off-topic
Zurich document over an on-topic federal act — the fixture trap #891 rejected and #975 warns
about by name. `search.integration.spec.ts` holds the labelled set; raising the weight means
re-measuring it.

## Minimal next tasks

- [x] Define search projection schema
- [x] Define minimal NestJS BFF endpoints
- [x] Connect frontend to live BFF (replace mock data with Orval-generated client)
- [x] Define initial OpenSearch mapping and alias strategy
- [x] Define projection manifest/history model
- [x] Implement `document.processed` ingestion and projection writer (consume events, read published refs, transform to projection schema, upsert to OpenSearch)
- [x] Implement `document.withdrawn` ingestion and deindex/tombstone behavior, including replay ordering tests
- [x] Define reindex workflow
- [x] Internationalization: BFF locale-awareness and frontend `next-intl` (ADR-0013, Phases 1–2)

## Minimal v1 Outcome

A user can:

1. Search documents by text
2. Open a document detail page
3. Filter by a small set of metadata fields

## Later expansion

| Phase | Capability |
|-------|-----------|
| Next | Section-level search |
| Next | Citation-aware search |
| Next | i18n: French and Italian UI (ADR-0013) |
| Next | Five-country content overlays (CH/AT/DE/FR/IT) for consistent filter and detail semantics |
| Later | Facets and ranking improvements |
| Later | Per-language OpenSearch analyzers |
| Later | Semantic search |
| Later | Richer document exploration |

Content scaling reference:

- `docs/components/five-country-content-rollout.md`
- `legal-search/frontend/docs/multi-country-content-spec.md`

## Dependencies

| Dependency | Purpose |
|-----------|---------|
| OpenSearch | Search index and query engine |
| Published DI surfaces | Projection input |
| Pub/Sub | Consume `document.processed`, `document.withdrawn`, and `index_update.requested` |
| Cloud Run | Runtime for BFF and frontend |

## Platform Capabilities We Reuse

- Versioned physical indices plus aliases for zero-downtime cutover
- Bulk indexing APIs for replay and rebuild

These replace the need for custom index-lifecycle semantics in shared contracts. The shared contracts only need to carry projection inputs, ordering, and withdrawal signals.

## Key Contracts

- **Consumes:** `document.processed`
- **Consumes:** `document.withdrawn`
- **Consumes:** `index_update.requested`
- **API:** `contracts/api/legal-search.openapi.yaml`
- **Reads:** published DI surfaces referenced by event refs

## Citation graph

Per [ADR-0033](../adr/0033-agentic-legal-reasoning.md), legal reasoning is *traversal*, not
similarity: "RAG to enter, graph to reason." The citation graph is what steps 3–4 of that
workflow walk, and it lives in two OpenSearch indices, both with a managed mapping in
`legal-search/api/src/core/opensearch/citation-graph-index.mapping.ts` and bootstrapped on
startup (`citation-graph-bootstrap.ts`):

| Index | Role | Written by |
|---|---|---|
| `citations` | **Edges.** One row per citation string found in a document, carrying `normalized_reference` — the canonical `{type}:{value}` key (`sr:210`) that DI's `normalize_citation()` emits. | `ProjectionsService.extractCitations` |
| `citation-targets` | **Nodes.** One row per identifier a document *is* — `sr:101` is the Bundesverfassung. | `ProjectionsService.extractCitationTargets` |

An edge exists when a citation's key matches a target's key. That join is the entire graph.

**Where a document's own identifier comes from.** The Fedlex SPARQL provider emits a title,
a short title and an ELI URI — but no SR number. So a Swiss federal law declares its SR
number only in its **masthead**: the raw title (`Bundesverfassung ... (SR 101)`) and the
opening line of the body (`Vom 18. April 1999 (Stand am 1. Januar 2024), SR 101.`). Target
extraction therefore scans the raw (un-normalized) title, plus a bounded masthead window of
the body, and only for `document_type: law`. The bound is deliberate: an SR number past the
masthead is a citation to a *different* norm, and letting a decision register itself as
`sr:210` would make every citation of the civil code in the corpus resolve to it. **A wrong
edge is worse than a missing one.**

**Traversal is keyed, not denormalized.** `GET /v1/citations/citing` joins on the canonical
key, not on the `target_document_id` written onto a citation at projection time. That field
is only set if the cited document already existed when the citing document was projected —
so a graph traversed through it silently loses every edge whose endpoints arrived in the
wrong order.

`GET /v1/documents/{id}` no longer depends on it either (#990). Document detail used to build
its reference links from `target_document_id` alone, so an out-of-order pair rendered as an
unlinked string forever; `DocumentsService.joinUnresolvedCitations` now re-joins any citation
that carries a key but no target, at read time, through the same `citation-targets` port
`/v1/citations/resolve` uses. (`GET /v1/documents/{id}/cited_by` still reads
`target_document_id` and is correspondingly order-dependent — use `/v1/citations/citing`.)

**One resolution rule, two callers.** The decision "does this key name exactly one norm?"
lives once, in `modules/citations/citation-resolution.ts`, and the write path
(`ProjectionsService.resolveCitations`), the read join and `/v1/citations/resolve` all call
it. It previously existed twice and the copies disagreed: the read path refused an ambiguous
key, while the projection adapter built a `Map<key, match>` and let the last search hit win —
persisting one arbitrarily chosen `target_document_id` with `resolved: true`. That is a wrong
edge, written into the index and thereafter indistinguishable from a real one.

**A citation row records whether resolution was attempted.** `resolution_status`
(`resolved` | `unresolved`) and `unresolved_reason` (`not_normalizable` |
`no_target_in_corpus` | `ambiguous`) are written alongside `resolved`. An **absent**
`resolution_status` means resolution was never attempted — a row written before the field
existed, or one whose lookup against `citation-targets` failed. An outage is *unknown*, not
*no target*, and the index must be able to say which (ADR-0052).

**The resolution rate is part of the contract.** `GET /v1/citations/stats` reports what
share of extracted citations actually resolve, and attributes the remainder:

- `not_normalizable` — DI could not key the citation at all (a fuzzy form like a BGE
  reference, or `§ 4 Hundegesetz` — a spelled-out cantonal title is not yet an identifier).
  An **extractor** gap.
- `unresolved_target` — the key is valid but names a norm not in the corpus. A **coverage** gap.
- `ambiguous` — several *different* documents are addressable by the key. Refused rather than
  guessed; `/v1/citations/resolve` returns the rivals unranked so the caller can disambiguate
  on evidence the corpus does not hold.

These are reported rather than hidden because an unresolved citation is a *broken edge*, and
consumers read a missing edge as "no such relation exists" (see [ADR-0032](../adr/0032-pipeline-observability.md)).
The same numbers are exported as Prometheus metrics (`legal_search_citation_resolution_rate`,
`legal_search_citations_projected_total{keyed}`) and alerted on in
`infra/hetzner/observability/alerts.yaml` (`evidara.citation-graph`).

**Article references resolve deterministically, without search** (#594, shipped by #701).
The previous revision of this section recorded `Art. 36 BV` as an unresolved gap awaiting
search-based resolution. Measuring first showed that was the wrong tool: the short title
*is* an identifier, and Fedlex publishes it as `title_short`, so the short-form-to-norm
mapping is a fact the corpus supplies rather than an inference. Two things landed:

- **A precision gate.** An `Art. N <token>` match whose trailing token is not
  abbreviation-shaped (>= 2 capitals: `BV`, `OR`, `ZGB`, `StGB`) is not recorded as a
  citation at all — the BV's own headings ("Art. 36 Einschränkungen von Grundrechten")
  were scoring as citations to a statute called "Einschränkungen", and 98.5% of `article`
  matches across the golden corpus were such phantoms, padding the denominator of
  `resolution_rate`. This is a **shape** test, never a dictionary
  (`legal-search/api/src/modules/citations/citation-key.ts:64-76`).
- **Deterministic resolution.** `Art. 36 BV` keys to `abbrev_art:BV/36` on both sides —
  DI at extraction (`nlp/citation_extractor.py:699-703`) and the BFF for a string typed by
  a human or an agent (`citation-key.ts:119-124`). `ProjectionsService` mints the matching
  nodes: `abbrev:BV` for the statute and one `abbrev_art:BV/36` per article-level section,
  carrying `section_id` / `section_anchor` so a citation resolves to an openable provision
  rather than a 525 KB statute (`projections.service.ts:1070-1113`). There is no
  confidence score and no threshold anywhere.

**What this does not cover.** Node minting has real preconditions, and a document that
misses them mints nothing rather than guessing: only `document_type: law`
(`projections.service.ts:1075`), only when the source publishes an abbreviation-shaped
`title_short` (`:1078`), and only for sections that carry a `section_id` and a title
beginning `Art. N` (`:1092-1098`). Still reported unresolved, never guessed:

- **Ambiguity.** Short titles are not globally unique, so a key naming several *different*
  documents comes back `unresolved_reason: 'ambiguous'` with every candidate returned
  **unranked** — narrowing is not resolving (`citations.service.ts:108-126`).
- **BGE references**, **German statute paragraphs** (`de_statute:BGB` names a statute but
  not a provision), and **cross-lingual short titles** (`Cst.` / `Cost.` are the BV's
  French and Italian names; nothing links them to `BV`).
- **Swiss `§` citations against a spelled-out cantonal title** (`§ 4 Hundegesetz`). Since
  #769 these are *extracted* and carry `resolved=false`, so a Zürich ordinance presents as
  a document with an unsatisfied dependency rather than one with no references — but they
  are not keyed, because `citation-targets` mints short-title nodes from `title_short` and
  a cantonal statute publishes none (`nlp/citation_extractor.py:705-718`).

## Operator references

- `docs/runbooks/projection-reindex-backfill.md` — alias-cutover reindex pattern.
- `docs/runbooks/staging-projection-replay.md` — projection replay against staging.
- `docs/runbooks/hitl-rollout.md` — HITL rollout (canonical `jur_*`/`auth_*` filters, commentary records, mapping change + replay).

## Testing

See [Legal Search Testing](testing/legal-search-testing.md) for the full testing strategy.

Key tests:

- Projection builder unit tests
- Search and detail API contract tests
- Indexing smoke test with sample docs
- Fixed search smoke queries
- Parity checks between published DI surfaces and indexed documents

## Drift risks

| Risk | Mitigation |
|------|-----------|
| Search index diverges from canonical data | Projection manifest/history and parity checks |
| Projection logic drops fields | Projection builder unit tests |
| Search serves a withdrawn document | Withdrawal event tests and alias-safe replay |
| Out-of-order events overwrite fresh data | `document_revision` ordering checks |
