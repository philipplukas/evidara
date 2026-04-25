import type { ConfigService } from '@nestjs/config';
import { describe, expect, it, vi } from 'vitest';
import { SearchOpenSearchAdapter } from './opensearch.adapter';

describe('SearchOpenSearchAdapter', () => {
  it('translates multi-filter options into OpenSearch bool filters', async () => {
    const search = vi.fn().mockResolvedValue({
      body: {
        hits: { total: { value: 0 }, hits: [] },
        aggregations: {},
      },
    });

    const adapter = new SearchOpenSearchAdapter(
      { search } as never,
      {
        get: (key: string) =>
          key === 'opensearch.documentsReadAlias' ? 'documents-read-test' : null,
      } as ConfigService,
    );

    await adapter.search('verantwortlichkeit', {
      jurisdictions: ['ch', 'at'],
      documentTypes: ['law', 'decision'],
      languages: ['de'],
      officialOnly: true,
      refinements: [{ field: 'court_level', type: 'terms', values: ['supreme'] }],
    });

    const firstCall = search.mock.calls[0][0] as {
      body: {
        query: {
          bool: {
            filter: unknown[];
            must?: [{ multi_match: { fields: string[] } }];
            should?: unknown[];
          };
        };
      };
    };
    expect(firstCall.body.query.bool.filter).toEqual([
      { terms: { jurisdiction: ['ch', 'at'] } },
      { terms: { document_type: ['law', 'decision'] } },
      { terms: { language: ['de'] } },
      { term: { is_official: true } },
      { terms: { court_level: ['supreme'] } },
    ]);

    const must = firstCall.body.query.bool.must;
    expect(must).toBeDefined();
    expect(must![0].multi_match.fields).toEqual([
      'title^4',
      'authority_name^3',
      'official_citation^3',
      'structural_path^2',
      'regeste^2',
      'content',
      'content_preview',
      'docket_number^2',
    ]);
    expect(firstCall.body.query.bool.should).toEqual([
      { match_phrase: { title: { query: 'verantwortlichkeit', boost: 8 } } },
      { match_phrase: { official_citation: { query: 'verantwortlichkeit', boost: 6 } } },
      { match_phrase: { authority_name: { query: 'verantwortlichkeit', boost: 5 } } },
      { match_phrase: { structural_path: { query: 'verantwortlichkeit', boost: 4 } } },
      { match_phrase: { docket_number: { query: 'verantwortlichkeit', boost: 4 } } },
    ]);
    expect(firstCall.body.query.bool.must).toEqual([
      {
        multi_match: {
          query: 'verantwortlichkeit',
          fields: [
            'title^4',
            'authority_name^3',
            'official_citation^3',
            'structural_path^2',
            'regeste^2',
            'content',
            'content_preview',
            'docket_number^2',
          ],
          type: 'best_fields',
          operator: 'and',
        },
      },
    ]);
  });

  it('maps toggle, range, date_range, and text refinements', async () => {
    const search = vi.fn().mockResolvedValue({
      body: {
        hits: { total: { value: 0 }, hits: [] },
        aggregations: {},
      },
    });

    const adapter = new SearchOpenSearchAdapter(
      { search } as never,
      {
        get: (key: string) =>
          key === 'opensearch.documentsReadAlias' ? 'documents-read-test' : null,
      } as ConfigService,
    );

    await adapter.search('verantwortlichkeit', {
      refinements: [
        { field: 'has_commentary', type: 'toggle', values: ['true'], value: true },
        { field: 'citations_count', type: 'range', values: ['10+'], from: '10' },
        { field: 'effective_date', type: 'date_range', values: ['since-2020'], from: '2020-01-01' },
        { field: 'content', type: 'text', values: ['haftung', 'verwaltungsrat'] },
      ],
    });

    const firstCall = search.mock.calls[0][0] as {
      body: { query: { bool: { filter: unknown[] } } };
    };
    expect(firstCall.body.query.bool.filter).toEqual([
      { term: { has_commentary: true } },
      { range: { citations_count: { gte: '10' } } },
      { range: { effective_date: { gte: '2020-01-01' } } },
      { match: { content: 'haftung verwaltungsrat' } },
    ]);
  });

  it('ignores invalid refinement payloads that cannot map to filters', async () => {
    const search = vi.fn().mockResolvedValue({
      body: {
        hits: { total: { value: 0 }, hits: [] },
        aggregations: {},
      },
    });

    const adapter = new SearchOpenSearchAdapter(
      { search } as never,
      {
        get: (key: string) =>
          key === 'opensearch.documentsReadAlias' ? 'documents-read-test' : null,
      } as ConfigService,
    );

    await adapter.search('verantwortlichkeit', {
      refinements: [
        { field: 'has_commentary', type: 'toggle', values: ['true'], value: 'true' },
        { field: 'effective_date', type: 'date_range', values: ['missing-bounds'] },
      ],
    });

    const firstCall = search.mock.calls[0][0] as {
      body: { query: { bool: { filter: unknown[] } } };
    };
    expect(firstCall.body.query.bool.filter).toEqual([]);
  });

  it('maps lifecycle_status from OpenSearch hits', async () => {
    const search = vi.fn().mockResolvedValue({
      body: {
        hits: {
          total: { value: 1 },
          hits: [
            {
              _source: {
                document_id: 'doc_001',
                title: 'Obligationenrecht',
                lifecycle_status: 'repealed',
              },
            },
          ],
        },
        aggregations: {},
      },
    });

    const adapter = new SearchOpenSearchAdapter(
      { search } as never,
      {
        get: (key: string) =>
          key === 'opensearch.documentsReadAlias' ? 'documents-read-test' : null,
      } as ConfigService,
    );

    const result = await adapter.search('obligationenrecht');

    expect(result.hits[0]).toEqual(
      expect.objectContaining({
        document_id: 'doc_001',
        lifecycle_status: 'repealed',
      }),
    );
  });

  it('maps authority_name from OpenSearch hits', async () => {
    const search = vi.fn().mockResolvedValue({
      body: {
        hits: {
          total: { value: 1 },
          hits: [
            {
              _source: {
                document_id: 'doc_001',
                title: 'Obligationenrecht',
                authority_name: 'Fedlex',
                official_citation: 'SR 101',
                is_official: true,
              },
            },
          ],
        },
        aggregations: {},
      },
    });

    const adapter = new SearchOpenSearchAdapter(
      { search } as never,
      {
        get: (key: string) =>
          key === 'opensearch.documentsReadAlias' ? 'documents-read-test' : null,
      } as ConfigService,
    );

    const result = await adapter.search('obligationenrecht');

    expect(result.hits[0]).toEqual(
      expect.objectContaining({
        document_id: 'doc_001',
        authority_name: 'Fedlex',
        official_citation: 'SR 101',
        is_official: true,
      }),
    );
  });

  it('does not fall back to match_all when a non-wildcard query returns zero hits', async () => {
    const search = vi.fn().mockResolvedValue({
      body: {
        hits: { total: { value: 0 }, hits: [] },
        aggregations: {},
      },
    });

    const adapter = new SearchOpenSearchAdapter(
      { search } as never,
      {
        get: (key: string) =>
          key === 'opensearch.documentsReadAlias' ? 'documents-read-test' : null,
      } as ConfigService,
    );

    const result = await adapter.search('Bundesgericht');

    expect(search).toHaveBeenCalledTimes(1);
    expect(result.total).toBe(0);
    expect(result.hits).toEqual([]);
  });

  it('uses phrase-heavy non-fuzzy matching for short legal queries', async () => {
    const search = vi.fn().mockResolvedValue({
      body: {
        hits: { total: { value: 0 }, hits: [] },
        aggregations: {},
      },
    });

    const adapter = new SearchOpenSearchAdapter(
      { search } as never,
      {
        get: (key: string) =>
          key === 'opensearch.documentsReadAlias' ? 'documents-read-test' : null,
      } as ConfigService,
    );

    await adapter.search('Art. 8 EMRK');

    const firstCall = search.mock.calls[0][0] as {
      body: { query: { bool: { must: [{ multi_match: Record<string, unknown> }] } } };
    };
    expect(firstCall.body.query.bool.must[0].multi_match).toEqual(
      expect.objectContaining({
        query: 'Art. 8 EMRK',
        operator: 'and',
      }),
    );
    expect(firstCall.body.query.bool.must[0].multi_match.fuzziness).toBeUndefined();
  });

  describe('jurisdiction filter routing', () => {
    function makeAdapter(searchFn = vi.fn()) {
      searchFn.mockResolvedValue({
        body: { hits: { total: { value: 0 }, hits: [] }, aggregations: {} },
      });
      const adapter = new SearchOpenSearchAdapter({ search: searchFn } as never, {
        get: (key: string) =>
          key === 'opensearch.documentsReadAlias' ? 'documents-read-test' : null,
      } as ConfigService);
      return { adapter, searchFn };
    }

    function getFilters(searchFn: ReturnType<typeof vi.fn>): unknown[] {
      const firstCall = searchFn.mock.calls[0][0] as {
        body: { query: { bool: { filter: unknown[] } } };
      };
      return firstCall.body.query.bool.filter;
    }

    it('routes ISO country tokens to the legacy jurisdiction keyword', async () => {
      const { adapter, searchFn } = makeAdapter();
      await adapter.search('q', { jurisdictions: ['ch', 'de'] });

      expect(getFilters(searchFn)).toEqual([{ terms: { jurisdiction: ['ch', 'de'] } }]);
    });

    it('routes ISO subdivision tokens to the legacy jurisdiction keyword', async () => {
      const { adapter, searchFn } = makeAdapter();
      await adapter.search('q', { jurisdictions: ['ch-zh'] });

      expect(getFilters(searchFn)).toEqual([{ terms: { jurisdiction: ['ch-zh'] } }]);
    });

    it('routes canonical jur_* ids to jurisdiction_ids.keyword (the field added by #425)', async () => {
      const { adapter, searchFn } = makeAdapter();
      await adapter.search('q', {
        canonicalJurisdictionIds: ['jur_ch_federal', 'jur_ch_gemeinde_261'],
      });

      expect(getFilters(searchFn)).toEqual([
        {
          terms: {
            'jurisdiction_ids.keyword': ['jur_ch_federal', 'jur_ch_gemeinde_261'],
          },
        },
      ]);
    });

    it('OR-unions a mixed ISO + canonical list with minimum_should_match=1', async () => {
      const { adapter, searchFn } = makeAdapter();
      await adapter.search('q', {
        jurisdictions: ['ch-zh'],
        canonicalJurisdictionIds: ['jur_ch_gemeinde_261'],
      });

      expect(getFilters(searchFn)).toEqual([
        {
          bool: {
            should: [
              { terms: { jurisdiction: ['ch-zh'] } },
              { terms: { 'jurisdiction_ids.keyword': ['jur_ch_gemeinde_261'] } },
            ],
            minimum_should_match: 1,
          },
        },
      ]);
    });

    it('emits no jurisdiction filter when neither token list is supplied', async () => {
      const { adapter, searchFn } = makeAdapter();
      await adapter.search('q');

      expect(getFilters(searchFn)).toEqual([]);
    });

    it('emits no jurisdiction filter when both lists are empty', async () => {
      const { adapter, searchFn } = makeAdapter();
      await adapter.search('q', { jurisdictions: [], canonicalJurisdictionIds: [] });

      expect(getFilters(searchFn)).toEqual([]);
    });
  });

  it('keeps fuzzy broad matching for longer free-text queries', async () => {
    const search = vi.fn().mockResolvedValue({
      body: {
        hits: { total: { value: 0 }, hits: [] },
        aggregations: {},
      },
    });

    const adapter = new SearchOpenSearchAdapter(
      { search } as never,
      {
        get: (key: string) =>
          key === 'opensearch.documentsReadAlias' ? 'documents-read-test' : null,
      } as ConfigService,
    );

    await adapter.search('verwaltungsrat haftung gesellschaftsrecht');

    const firstCall = search.mock.calls[0][0] as {
      body: { query: { bool: { must: [{ multi_match: Record<string, unknown> }] } } };
    };
    expect(firstCall.body.query.bool.must[0].multi_match).toEqual(
      expect.objectContaining({
        query: 'verwaltungsrat haftung gesellschaftsrecht',
        fuzziness: 'AUTO',
      }),
    );
    expect(firstCall.body.query.bool.must[0].multi_match.operator).toBeUndefined();
  });
});
