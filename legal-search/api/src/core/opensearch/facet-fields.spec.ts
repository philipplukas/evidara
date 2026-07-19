/**
 * Pins the facet aggregation convention to the canonical mapping (#675).
 *
 * This is the guard that directly catches the wrong fix, as opposed to the
 * drift checker which catches the underlying drifted index. Under the canonical
 * mapping both `jurisdiction` and `jurisdiction.keyword` aggregate correctly, so
 * no behavioural test — not even one against a real OpenSearch — can tell the
 * two apart. Only a structural assertion can.
 */
import { describe, expect, it } from 'vitest';
import { DOCUMENTS_INDEX_PROPERTIES } from './documents-index.mapping';
import { COVERAGE_DIMENSION_AGG_FIELDS, SEARCH_FACET_AGG_FIELDS } from './facet-fields';

type FieldDefinition = { type?: string; fields?: Record<string, { type?: string }> };
const properties = DOCUMENTS_INDEX_PROPERTIES as unknown as Record<string, FieldDefinition>;

describe('SEARCH_FACET_AGG_FIELDS', () => {
  it('targets the `.keyword` sub-field the canonical mapping declares', () => {
    for (const [facet, aggField] of Object.entries(SEARCH_FACET_AGG_FIELDS)) {
      // If this fails because someone switched to a bare field name: the bare
      // name is not the fix. Aggregations follow the canonical mapping, and the
      // index gets rebuilt to match it — see `mapping-drift.ts`.
      expect(aggField, `facet "${facet}" must aggregate on a .keyword sub-field`).toMatch(
        /\.keyword$/,
      );
    }
  });

  it('names only fields the canonical mapping actually declares as facetable', () => {
    for (const [facet, aggField] of Object.entries(SEARCH_FACET_AGG_FIELDS)) {
      const [base, subfield] = aggField.split('.');

      expect(base, `facet "${facet}" targets an undeclared field`).toBe(facet);
      const definition = properties[base];
      expect(definition, `"${base}" is not in the canonical mapping`).toBeDefined();

      // A `terms` aggregation needs an exact-match field. `keyword` base type
      // plus a declared `keyword` sub-field is what `facetKeyword` guarantees.
      expect(definition?.type).toBe('keyword');
      expect(
        definition?.fields?.[subfield]?.type,
        `"${aggField}" has no declaration in the canonical mapping`,
      ).toBe('keyword');
    }
  });
});

describe('COVERAGE_DIMENSION_AGG_FIELDS', () => {
  it('targets the `.keyword` sub-field the canonical mapping declares', () => {
    for (const [dimension, aggField] of Object.entries(COVERAGE_DIMENSION_AGG_FIELDS)) {
      // Same rule, same history as the search facets above: the bare field name
      // aggregates under the canonical mapping and NOT under the dynamically
      // mapped GCP index, so only a structural assertion catches the regression.
      expect(aggField, `dimension "${dimension}" must aggregate on a .keyword sub-field`).toMatch(
        /\.keyword$/,
      );
    }
  });

  it('names only fields the canonical mapping declares as facetable', () => {
    for (const [dimension, aggField] of Object.entries(COVERAGE_DIMENSION_AGG_FIELDS)) {
      const [base, subfield] = aggField.split('.');
      const definition = properties[base];

      expect(definition, `"${base}" is not in the canonical mapping`).toBeDefined();
      expect(definition?.type, `dimension "${dimension}" needs an exact-match field`).toBe(
        'keyword',
      );
      expect(
        definition?.fields?.[subfield]?.type,
        `"${aggField}" has no declaration in the canonical mapping`,
      ).toBe('keyword');
    }
  });

  it('groups jurisdictions by the multi-valued scope field, not the display field', () => {
    // `jurisdiction` is a single-valued display string; `jurisdiction_ids` is
    // what search and norm-hierarchy filter on. Coverage counted over the
    // display field would disagree with every other endpoint about what is held.
    expect(COVERAGE_DIMENSION_AGG_FIELDS.jurisdiction).toBe('jurisdiction_ids.keyword');
  });
});
