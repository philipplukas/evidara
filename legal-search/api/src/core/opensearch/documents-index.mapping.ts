/**
 * Canonical OpenSearch mapping for the legal-search `documents`
 * projection index — the single source of truth (SoT).
 *
 * Every producer of the documents index MUST derive its mapping from
 * here instead of hand-maintaining a parallel copy:
 *   - `scripts/seed-from-opencaselaw.ts` (local OpenCaseLaw seed)
 *   - `scripts/opensearch-alias-cutover.ts` (versioned reindex/cutover)
 *   - the runtime startup bootstrap in `main.ts` (Hetzner / self-hosted)
 *
 * The property set is the union of:
 *   - the fields written by `ProjectionsService.buildProjection` and
 *     `buildCommentaryProjection` (see `projections.repository.ts`
 *     `SearchProjectionDocument`) — the authoritative event-projection
 *     shape, including the projection-only keyword fields `record_kind`,
 *     `jurisdiction_ids`, `authority_ids`, `source_document_ids`;
 *   - the richer OpenCaseLaw seed fields (`court`, `docket_number`,
 *     `regeste`, `content`, `related_*_count`);
 *   - the fields the search adapter (`search/opensearch.adapter.ts`)
 *     queries, filters, and aggregates on.
 *
 * Facet aggregations run on the `.keyword` sub-field (e.g.
 * `jurisdiction.keyword`), while term filters use the bare field name.
 * Fields used both ways are declared as `keyword` WITH a `keyword`
 * sub-field so both resolve; relying on dynamic mapping instead gave the
 * projection-only fields no analyzer/type parity guarantee.
 *
 * THIS FILE IS THE CONTRACT, NOT A DESCRIPTION OF WHAT IS DEPLOYED (#675).
 * The live index drifted from it — it was created by a hand-maintained
 * mapping in a shell script rather than from this definition, so it lacks
 * the `.keyword` sub-fields and dynamic-mapped `jurisdiction_ids` /
 * `authority_ids` as `text`. Aggregating a field that does not exist is
 * not an error in OpenSearch; it silently returns empty buckets, which is
 * why the facet rail was dead. The fix is to make index creation apply
 * THIS mapping and to reindex — never to weaken the query to match the
 * drift. `scripts/check-opensearch-mapping-drift.ts` compares a live index
 * against this definition so the drift cannot recur unnoticed.
 */

/**
 * German-first legal analysis chain: standard tokenizer + lowercase +
 * german_normalization, as used since the first seed mapping. All
 * `text` fields analyze with `legal_text`.
 */
export const DOCUMENTS_INDEX_ANALYSIS = {
  analyzer: {
    legal_text: {
      type: 'custom',
      tokenizer: 'standard',
      filter: ['lowercase', 'german_normalization'],
    },
  },
} as const;

/** Keyword field that is also aggregatable via a `.keyword` sub-field. */
const facetKeyword = {
  type: 'keyword',
  fields: { keyword: { type: 'keyword' } },
} as const;

/** Full-text field analyzed with `legal_text`, plus an exact `.keyword`. */
const legalText = {
  type: 'text',
  analyzer: 'legal_text',
  fields: { keyword: { type: 'keyword' } },
} as const;

/**
 * Canonical documents-index property map. Keys are the field names the
 * projection/seed pipelines write; the test in
 * `documents-index.mapping.spec.ts` asserts this covers every field
 * `buildProjection`/`buildCommentaryProjection` emit.
 */
export const DOCUMENTS_INDEX_PROPERTIES = {
  // ── Identity / discriminator ──
  document_id: { type: 'keyword' },
  record_kind: { type: 'keyword' },

  // ── Full-text + display ──
  title: legalText,
  authority_name: legalText,
  official_citation: {
    type: 'text',
    analyzer: 'legal_text',
    fields: { keyword: { type: 'keyword' } },
  },
  regeste: { type: 'text', analyzer: 'legal_text' },
  content: { type: 'text', analyzer: 'legal_text' },
  content_preview: { type: 'text' },
  structural_path: { type: 'text', fields: { keyword: { type: 'keyword' } } },

  // Learned-sparse representation of `content` (ADR-0054). `rank_features` and
  // not `knn_vector` on purpose: `index.knn` is a **static** setting the live
  // `documents-*` indices do not carry and cannot gain without a reindex and an
  // alias cutover, and HNSW graphs live in off-heap memory the 2Gi OpenSearch
  // node does not have. This is an ordinary inverted index, so it can be added
  // to a live mapping and costs no off-heap memory.
  //
  // Keys are `t<token-id>` from BGE-M3's tokenizer, never decoded token strings:
  // a multilingual vocabulary contains `.`, which OpenSearch reads as object
  // nesting, so decoded names would silently produce a different field structure
  // for some tokens and not others. Produced by
  // `document_intelligence.jobs.embedding_backfill`; see ADR-0054 D8 on why the
  // field and its producer land together.
  content_sparse: { type: 'rank_features' },

  // ── Faceted keywords (bare filter + `.keyword` aggregation) ──
  jurisdiction: facetKeyword,
  document_type: facetKeyword,
  language: facetKeyword,
  jurisdiction_ids: facetKeyword,
  authority_ids: facetKeyword,
  // Rank in the hierarchy of norms (ADR-0033), derived from the document's
  // jurisdiction — not from its text. Faceted so `norm_hierarchy()` can bucket
  // a place's governing law by level in one aggregation.
  level: facetKeyword,

  // ── Norm-hierarchy relations (ADR-0033) ──
  // `subordinate_to`: the jurisdictions whose law outranks this document —
  // derived from the jurisdiction tree. Subordination in law is scope-wide (a
  // communal ordinance is subordinate to the WHOLE body of cantonal and federal
  // law, not to one act), so the edge points at superior scopes, not documents.
  subordinate_to: { type: 'keyword' },
  // `delegates_to`: the competence a norm hands DOWN — the cantonal statute
  // that lets a commune legislate at all. NOT derivable from the tree: it is an
  // assertion made BY a norm's text, so it needs extraction or manual curation
  // and is UNPOPULATED today. The shape is declared here so the edge has a home
  // and the index does not need a second migration once it can be filled.
  delegates_to: {
    type: 'nested',
    properties: {
      target_level: { type: 'keyword' },
      target_jurisdiction_id: { type: 'keyword' },
      section_id: { type: 'keyword' },
      scope: { type: 'text', analyzer: 'legal_text' },
    },
  },

  // ── Plain keywords ──
  original_language: { type: 'keyword' },
  translation_status: { type: 'keyword' },
  source_id: { type: 'keyword' },
  source_version_id: { type: 'keyword' },
  source_document_ids: { type: 'keyword' },
  run_id: { type: 'keyword' },
  processing_manifest_id: { type: 'keyword' },
  lifecycle_status: { type: 'keyword' },
  court: { type: 'keyword' },
  docket_number: { type: 'keyword' },

  // ── Booleans / numerics / dates ──
  is_official: { type: 'boolean' },
  sections_count: { type: 'integer' },
  citations_count: { type: 'integer' },
  related_decisions_count: { type: 'integer' },
  related_commentary_count: { type: 'integer' },
  document_revision: { type: 'long' },
  processed_at: { type: 'date' },
  effective_date: { type: 'date', format: 'strict_date_optional_time||yyyy-MM-dd' },
  // Temporal validity (ADR-0033). `in_force_from` falls back to
  // `effective_date` at projection time so there is a single field to
  // range-query; `in_force_until` is the last date the norm WAS in force
  // (inclusive) and its absence means "not repealed as far as we know".
  in_force_from: { type: 'date', format: 'strict_date_optional_time||yyyy-MM-dd' },
  in_force_until: { type: 'date', format: 'strict_date_optional_time||yyyy-MM-dd' },
} as const;

/**
 * Build the full create-index body (`settings` + `mappings`) from the
 * canonical analysis chain and property map.
 *
 * @param numberOfReplicas defaults to 0 — correct for the single-node
 *   self-hosted (Hetzner) and local OpenSearch clusters so the index
 *   reports green. Multi-node deploys can pass 1.
 */
export function documentsIndexDefinition(numberOfReplicas = 0): Record<string, unknown> {
  return {
    settings: {
      number_of_shards: 1,
      number_of_replicas: numberOfReplicas,
      analysis: DOCUMENTS_INDEX_ANALYSIS,
    },
    mappings: {
      properties: DOCUMENTS_INDEX_PROPERTIES,
    },
  };
}

/** Field names covered by the canonical mapping. */
export function documentsIndexFields(): string[] {
  return Object.keys(DOCUMENTS_INDEX_PROPERTIES);
}
