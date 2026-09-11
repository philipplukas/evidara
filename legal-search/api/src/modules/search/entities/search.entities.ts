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
   * Discriminator from the search projection (PR #434). `legal_document`
   * is the historical default; `commentary_insight` rows are produced
   * from DI commentary insights via the projection's commentary path
   * (PR #441).
   */
  record_kind?: 'legal_document' | 'commentary_insight';
  /**
   * Canonical primary documents this commentary references. Empty /
   * undefined for legal_document rows; non-empty for commentary_insight
   * rows so the frontend can render explain-why source links.
   */
  source_document_ids?: string[];
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

/**
 * Why search declined to answer (#986).
 *
 * A refusal is NOT an empty result set. `totalResults: 0` with no `refusal`
 * means the query executed and matched nothing; a `refusal` means the query was
 * not answered at all, and says what stopped it. #984 is what happens when a
 * layer flattens that distinction, so it is carried as its own object rather
 * than encoded in a count.
 */
export interface SearchRefusalEntity {
  /** Machine-readable reason. One member today; a union so callers must switch. */
  code: 'jurisdiction_not_held';
  /** Operator- and agent-readable explanation naming the jurisdiction. */
  message: string;
  /** The jurisdictions the query named that the corpus holds nothing for. */
  jurisdictions: RefusedJurisdictionEntity[];
}

export interface RefusedJurisdictionEntity {
  /** Canonical platform jurisdiction id, e.g. `jur_ch_be`. */
  jurisdiction_id: string;
  /** ISO 3166-2 code from the subdivisions vocabulary, e.g. `CH-BE`. */
  iso_code: string;
  /** Display name from the jurisdiction seed. */
  label: string;
  /**
   * Always `not_held`. It is a statement about the CORPUS, never about the law
   * — the same two-member discipline `/v1/coverage` uses, so no caller can find
   * a value meaning "confirmed absent in law".
   */
  holding: 'not_held';
}
