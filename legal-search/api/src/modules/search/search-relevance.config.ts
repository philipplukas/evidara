/**
 * Search relevance configuration.
 *
 * Centralises all tunable relevance parameters so they can be adjusted
 * in one place once the corpus is large enough for meaningful evaluation.
 *
 * BM25 parameters are recorded here for documentation even though they
 * are currently set at the OpenSearch index level (defaults).
 */

// ─── Field weights for multi_match queries ───

export type FieldWeight = `${string}^${number}` | string;

export const SEARCH_FIELD_WEIGHTS: readonly FieldWeight[] = [
  'title^4',
  'authority_name^3',
  'official_citation^3',
  'structural_path^2',
  'regeste^2',
  'content',
  'content_preview',
  'docket_number^2',
] as const;

// ─── Phrase boost fields (match_phrase "should" clauses) ───

export type PhraseBoostEntry = readonly [field: string, boost: number];

export const PHRASE_BOOST_FIELDS: readonly PhraseBoostEntry[] = [
  ['title', 8],
  ['official_citation', 6],
  ['authority_name', 5],
  ['structural_path', 4],
  ['docket_number', 4],
] as const;

// ─── BM25 parameters (OpenSearch index-level defaults) ───

export interface Bm25Parameters {
  /** Term-frequency saturation. Higher = more weight on term frequency. */
  k1: number;
  /** Field-length normalisation. 0 = no length norm, 1 = full length norm. */
  b: number;
}

export const BM25_DEFAULTS: Readonly<Bm25Parameters> = {
  k1: 1.2,
  b: 0.75,
};

// ─── Query classification thresholds ───

export interface QueryClassificationThresholds {
  /** Maximum number of whitespace-separated tokens for a "short legal" query. */
  maxTokens: number;
  /** Maximum character length for a "short legal" query. */
  maxChars: number;
}

export const SHORT_LEGAL_THRESHOLDS: Readonly<QueryClassificationThresholds> = {
  maxTokens: 3,
  maxChars: 32,
};
