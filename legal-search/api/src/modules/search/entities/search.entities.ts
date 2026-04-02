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
  effective_date?: string;
  relevance_score?: number;
  structural_path?: string;
  language?: string;
  sections_count?: number;
  citations_count?: number;
  related_decisions_count?: number;
  related_commentary_count?: number;
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
