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

  // ── Faceted keywords (bare filter + `.keyword` aggregation) ──
  jurisdiction: facetKeyword,
  document_type: facetKeyword,
  language: facetKeyword,
  jurisdiction_ids: facetKeyword,
  authority_ids: facetKeyword,

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
