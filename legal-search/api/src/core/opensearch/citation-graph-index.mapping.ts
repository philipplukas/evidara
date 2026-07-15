/**
 * Canonical OpenSearch mappings for the two indices that make up the
 * citation graph — the single source of truth (SoT), mirroring the
 * pattern established for `documents` in `documents-index.mapping.ts`.
 *
 *   `citations`         — the EDGES. One row per citation string found in
 *                         a document. Carries `normalized_reference`
 *                         (`sr:210`), the canonical key produced by DI's
 *                         `normalize_citation`.
 *   `citation-targets`  — the NODES a citation can point AT. One row per
 *                         (identifier_type, identifier_value) that a
 *                         document in the corpus *is*. `sr:101` -> the BV.
 *
 * An edge resolves when a citation's `normalized_reference` matches a
 * target's `{identifier_type}:{identifier_value}`. That join is the whole
 * citation graph (ADR-0033, "graph to reason").
 *
 * Why these need managed mappings at all: an index with no managed mapping
 * gets whatever OpenSearch guesses on first write. `citation-targets` never
 * existed on the cluster, so its shape was undefined; `citations` was created
 * by dynamic mapping, which types every string as `text` + a `.keyword`
 * sub-field. Queries therefore filter on `<field>.keyword`.
 *
 * To stay compatible with the dynamically-mapped `citations` index that is
 * already live (504 rows, ADR-0033), identifier fields are declared as
 * `keyword` WITH a `keyword` sub-field, so BOTH `normalized_reference` and
 * `normalized_reference.keyword` resolve. That lets one query shape work
 * against a fresh managed index and the legacy dynamic one alike.
 */

/** Keyword field that also answers to `<field>.keyword` (dynamic-mapping parity). */
const dualKeyword = {
  type: 'keyword',
  fields: { keyword: { type: 'keyword' } },
} as const;

/**
 * Canonical `citations` property map — the graph's edges.
 *
 * Written by `ProjectionsService.extractCitations` /
 * `ProjectionOpenSearchAdapter.bulkIndexCitations`; read by the
 * citation-graph traversal adapter and `documents`' `cited_by`.
 */
export const CITATIONS_INDEX_PROPERTIES = {
  citation_id: { type: 'keyword' },

  // ── Edge tail: who is doing the citing ──
  source_document_id: dualKeyword,
  source_section_id: dualKeyword,

  // ── Edge head: what is being cited ──
  // `normalized_reference` is the canonical key (`sr:210`) and is the
  // ONLY order-independent way to traverse: `target_document_id` is a
  // write-time denormalization that is null whenever the cited document
  // had not yet been projected. Traversal must not depend on it.
  normalized_reference: dualKeyword,
  target_document_id: dualKeyword,
  target_title: { type: 'text', fields: { keyword: { type: 'keyword' } } },

  citation_text: { type: 'text', fields: { keyword: { type: 'keyword' } } },
  citation_type: dualKeyword,
  resolved: { type: 'boolean' },
} as const;

/**
 * Canonical `citation-targets` property map — the graph's addressable nodes.
 *
 * `_id` is `{identifier_type}:{identifier_value}` (see
 * `bulkIndexCitationTargets`), which makes writes idempotent and makes the
 * document key exactly the string `normalize_citation` emits.
 */
export const CITATION_TARGETS_INDEX_PROPERTIES = {
  /** The document that IS this norm. */
  document_id: dualKeyword,
  /** `sr` | `celex` | `ecli` | `at_bgbl` | `official_citation` | ... */
  identifier_type: dualKeyword,
  /** `101`, `32016R0679`, `ECLI:CH:BGER:2023:...` */
  identifier_value: dualKeyword,
  title: { type: 'text', fields: { keyword: { type: 'keyword' } } },
  document_type: dualKeyword,
  jurisdiction: dualKeyword,
} as const;

function definition(
  properties: Record<string, unknown>,
  numberOfReplicas: number,
): Record<string, unknown> {
  return {
    settings: {
      number_of_shards: 1,
      number_of_replicas: numberOfReplicas,
    },
    mappings: { properties },
  };
}

/**
 * Build the create-index body for `citations`.
 *
 * @param numberOfReplicas defaults to 0 — correct for the single-node
 *   self-hosted (Hetzner) and local clusters so the index reports green.
 */
export function citationsIndexDefinition(numberOfReplicas = 0): Record<string, unknown> {
  return definition(CITATIONS_INDEX_PROPERTIES, numberOfReplicas);
}

/** Build the create-index body for `citation-targets`. */
export function citationTargetsIndexDefinition(numberOfReplicas = 0): Record<string, unknown> {
  return definition(CITATION_TARGETS_INDEX_PROPERTIES, numberOfReplicas);
}
