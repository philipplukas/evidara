/**
 * Sprint 2 (#425): commentary vs primary-document discriminator. Rows with
 * no `record_kind` are treated as `document` for backwards compatibility.
 */
export type SearchRecordKind = 'document' | 'commentary';

/**
 * Internal entity representing a single search hit from OpenSearch.
 * This is NOT exposed via the API — the service layer transforms
 * it into a SearchResultView via mappers.
 *
 * Fields align with contracts/schemas/search-projection.schema.json
 * plus runtime fields (snippet, relevance_score) from query enrichment.
 */
export interface SearchHitEntity {
  document_id: string;
  title: string;
  snippet?: string;
  jurisdiction?: string;
  document_type?: string;
  authority_name?: string;
  official_citation?: string;
  original_language?: string;
  translation_status?: 'original' | 'machine_translated' | 'translation_unavailable';
  is_official?: boolean;
  effective_date?: string;
  lifecycle_status?: string;
  relevance_score?: number;
  structural_path?: string;
  language?: string;
  sections_count?: number;
  citations_count?: number;
  related_decisions_count?: number;
  related_commentary_count?: number;
  /**
   * Sprint 2 (#425): mixed-result discriminator. Defaulted to `document` by
   * the adapter when the indexed row has no `record_kind` field.
   */
  record_kind?: SearchRecordKind;
  /**
   * Sprint 2 (#425): commentary-only — primary documents this commentary
   * annotates. Empty/undefined for primary-document hits.
   */
  source_document_ids?: string[];
  /** Sprint 2 (#425): canonical jurisdiction IDs (e.g. jur_ch_federal). */
  jurisdiction_ids?: string[];
  /** Sprint 2 (#425): canonical authority IDs (e.g. auth_fedlex). */
  authority_ids?: string[];
  /**
   * Sprint 2 (#425): primary-document-only — number of commentary records
   * indexed in this query that point at this document via
   * `source_document_ids`. Computed via a single sub-aggregation, not a
   * per-hit round-trip.
   */
  commentary_support_count?: number;
}

export interface AggregationBucket {
  key: string;
  doc_count: number;
}

export interface SearchAggregations {
  jurisdiction?: AggregationBucket[];
  document_type?: AggregationBucket[];
  language?: AggregationBucket[];
  court_level?: AggregationBucket[];
  legal_area?: AggregationBucket[];
}

/**
 * Internal search result container returned by the repository.
 */
export interface SearchResultEntity {
  total: number;
  hits: SearchHitEntity[];
  aggregations: SearchAggregations;
}

/**
 * Context-level aggregations for the search context bar.
 * Query-independent and cacheable.
 */
export interface ContextAggregations {
  jurisdictions: AggregationBucket[];
  languages: AggregationBucket[];
  source_types: AggregationBucket[];
}
