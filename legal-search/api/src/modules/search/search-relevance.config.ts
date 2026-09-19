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

// ─── Jurisdiction mention boost (#975 gap A) ───

/**
 * What a named jurisdiction is worth, as a `should` clause on
 * `jurisdiction_ids.keyword` (#975 gap A).
 *
 * The query "Hundehaltung Kanton Bern Vorschriften" used to return a ZURICH
 * document first — "Vetsuisse-Fakultät der Universitäten Bern und Zürich",
 * which merely has the word *Bern* in its title — above Bern's actual
 * Hundegesetz. Measured against production 2026-09-19:
 *
 *   without this clause   9.76  jur_ch_zh  Vetsuisse-Fakultät ...
 *                         8.99  jur_ch_be  Hundegesetz            <- asked for
 *   with it               9.99  jur_ch_be  Hundegesetz
 *                         9.76  jur_ch_zh  Vetsuisse-Fakultät ...
 *
 * **Why 1 and not a number that makes Zürich win.** #975 is explicit that the
 * fix is not a weight tuned until one canton tops one query — that is the
 * fixture trap #891 rejected. So this is the SMALLEST integer weight that makes
 * the property hold across a symmetric labelled set (ZH, BE, BS; six queries,
 * both query shapes), and it is deliberately worth less than one additional
 * keyword match in a `title^4` field. Naming the canton breaks a near-tie; it
 * cannot override topical relevance. Measured consequence of that choice, and
 * it is the honest one: "Tierschutz Hunde Kanton Zürich" still ranks two
 * Bernese and Basler animal-welfare ordinances above the first Zurich hit,
 * because they outscore it topically by ~5 points. A weight large enough to
 * flip that would be a weight large enough to promote an off-topic Zurich
 * document over an on-topic federal act.
 *
 * Raising this is a measurement, not an opinion:
 * `search.integration.spec.ts` holds the labelled set.
 */
export const JURISDICTION_MENTION_BOOST = 1;
