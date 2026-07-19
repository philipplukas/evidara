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
import { SEARCH_FACET_AGG_FIELDS } from './facet-fields';

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
