import { beforeAll, describe, expect, it } from 'vitest';
import type { SearchAggregations } from '../entities/search.entities';
import type { FilterFacetView } from './search-facet.mapper';
import { mapAggregationsToFacets } from './search-facet.mapper';

// ─── Fixtures ───

const fullAggregations: SearchAggregations = {
  jurisdiction: [
    { key: 'CH', doc_count: 142 },
    { key: 'AT', doc_count: 87 },
    { key: 'DE', doc_count: 23 },
  ],
  document_type: [
    { key: 'law', doc_count: 80 },
    { key: 'decision', doc_count: 120 },
    { key: 'commentary', doc_count: 52 },
  ],
  language: [
    { key: 'de', doc_count: 200 },
    { key: 'fr', doc_count: 30 },
  ],
  court_level: [
    { key: 'federal', doc_count: 50 },
    { key: 'cantonal', doc_count: 70 },
  ],
  legal_area: [{ key: 'corporate', doc_count: 45 }],
};

const emptyAggregations: SearchAggregations = {};

// ─── Basic Shape ───

describe('mapAggregationsToFacets', () => {
  it('should produce facets for all present aggregations', () => {
    const facets = mapAggregationsToFacets(fullAggregations);
    const keys = facets.map((f) => f.key);

    expect(keys).toContain('jurisdiction');
    expect(keys).toContain('document_type');
    expect(keys).toContain('language');
    expect(keys).toContain('court_level');
    expect(keys).toContain('legal_area');
    expect(facets).toHaveLength(5);
  });

  it('should return empty array for empty aggregations', () => {
    const facets = mapAggregationsToFacets(emptyAggregations);
    expect(facets).toEqual([]);
  });

  it('should skip aggregations with empty bucket arrays', () => {
    const facets = mapAggregationsToFacets({
      jurisdiction: [{ key: 'CH', doc_count: 10 }],
      document_type: [],
    });
    expect(facets).toHaveLength(1);
    expect(facets[0].key).toBe('jurisdiction');
  });
});

// ─── Jurisdiction Facet ───

describe('jurisdiction facet', () => {
  let jurisdictionFacet: FilterFacetView;

  beforeAll(() => {
    const facets = mapAggregationsToFacets(fullAggregations);
    jurisdictionFacet = facets.find((f) => f.key === 'jurisdiction')!;
  });

  it('should have type "chip"', () => {
    expect(jurisdictionFacet.type).toBe('chip');
  });

  it('should apply human-readable labels', () => {
    const labels = jurisdictionFacet.options.map((o) => o.label);
    expect(labels).toContain('Schweiz');
    expect(labels).toContain('Österreich');
    expect(labels).toContain('Deutschland');
  });

  it('should include iconKey for known jurisdictions', () => {
    const ch = jurisdictionFacet.options.find((o) => o.value === 'CH');
    expect(ch?.iconKey).toBe('ch');
  });

  it('should preserve doc_count as count', () => {
    const ch = jurisdictionFacet.options.find((o) => o.value === 'CH');
    expect(ch?.count).toBe(142);
  });
});

// ─── Document Type Facet ───

describe('document_type facet', () => {
  it('should apply human-readable labels for known types', () => {
    const facets = mapAggregationsToFacets(fullAggregations);
    const typeFacet = facets.find((f) => f.key === 'document_type')!;
    const labels = typeFacet.options.map((o) => o.label);

    expect(labels).toContain('Gesetzs');
    expect(labels).toContain('Gerichtsentscheids');
    expect(labels).toContain('Kommentars');
  });

  it('should fall back to raw key for unknown document types', () => {
    const facets = mapAggregationsToFacets({
      document_type: [{ key: 'regulation', doc_count: 5 }],
    });
    const typeFacet = facets.find((f) => f.key === 'document_type')!;
    expect(typeFacet.options[0].label).toBe('regulation');
  });
});

// ─── Language Facet ───

describe('language facet', () => {
  it('should apply uppercase labels for known languages', () => {
    const facets = mapAggregationsToFacets(fullAggregations);
    const langFacet = facets.find((f) => f.key === 'language')!;

    expect(langFacet.options[0].label).toBe('DE');
    expect(langFacet.options[1].label).toBe('FR');
  });
});

// ─── Non-mapped Facets ───

describe('court_level and legal_area facets', () => {
  it('should use checkbox type for court_level', () => {
    const facets = mapAggregationsToFacets(fullAggregations);
    const courtFacet = facets.find((f) => f.key === 'court_level');
    expect(courtFacet?.type).toBe('checkbox');
  });

  it('should fall back to raw key as label when no labelMap', () => {
    const facets = mapAggregationsToFacets(fullAggregations);
    const courtFacet = facets.find((f) => f.key === 'court_level')!;
    expect(courtFacet.options[0].label).toBe('federal');
  });
});
