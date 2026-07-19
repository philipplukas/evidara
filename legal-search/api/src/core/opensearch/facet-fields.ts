/**
 * The single declaration of WHICH field each facet aggregation targets (#675).
 *
 * These used to be string literals inlined in two places in
 * `search/opensearch.adapter.ts`. That made the aggregation target a local
 * detail, editable without anything noticing — and it got edited: #675 was
 * first "fixed" by switching all six from `<field>.keyword` to the bare
 * `<field>`, to make them resolve against a live index that had drifted from
 * the canonical mapping and lacked the sub-fields.
 *
 * That change passed every test, including an integration test against a real
 * OpenSearch, because under the CANONICAL mapping these fields are `keyword`
 * and BOTH forms aggregate fine. The drifted index was the only place the
 * difference showed, and matching it was the wrong direction: on the
 * GCP-provisioned index (`infra/env/*\/runtime.gcp.tfvars*`, which declares no
 * mapping at all) every string is dynamic `text` and the bare name does NOT
 * aggregate, while `.keyword` does. No single form works against all three
 * shapes, which is the actual lesson: stop chasing shapes, fix the index.
 *
 * So the convention is pinned here and asserted against the canonical mapping
 * in `facet-fields.spec.ts`. Changing an aggregation to a bare field name now
 * fails the build with this history attached, rather than passing green.
 */

/** Facet key (as returned to the client) → the field its aggregation targets. */
export const SEARCH_FACET_AGG_FIELDS = {
  jurisdiction: 'jurisdiction.keyword',
  document_type: 'document_type.keyword',
  language: 'language.keyword',
} as const;

export type SearchFacetKey = keyof typeof SEARCH_FACET_AGG_FIELDS;
