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

  // ─── Sprint 2 (#425): commentary records + primary-document joins ───

  it('adds a record_kind=commentary filter when recordKind option is set', async () => {
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

    await adapter.search('Kommentar', { recordKind: 'commentary' });

    const firstCall = search.mock.calls[0][0] as {
      body: { query: { bool: { filter: unknown[] } } };
    };
    expect(firstCall.body.query.bool.filter).toEqual([{ term: { record_kind: 'commentary' } }]);
  });

  it('treats record_kind=document as "document or missing" so backfilled rows still match', async () => {
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

    await adapter.search('Gesetz', { recordKind: 'document' });

    const firstCall = search.mock.calls[0][0] as {
      body: { query: { bool: { filter: unknown[] } } };
    };
    expect(firstCall.body.query.bool.filter).toEqual([
      {
        bool: {
          should: [
            { term: { record_kind: 'document' } },
            { bool: { must_not: { exists: { field: 'record_kind' } } } },
          ],
          minimum_should_match: 1,
        },
      },
    ]);
  });

  it('issues a single commentary_support sub-aggregation for the support count', async () => {
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

    await adapter.search('Haftung');

    const firstCall = search.mock.calls[0][0] as { body: { aggs: Record<string, unknown> } };
    expect(firstCall.body.aggs.commentary_support).toEqual({
      filter: { term: { record_kind: 'commentary' } },
      aggs: {
        by_source_document: {
          terms: { field: 'source_document_ids', size: 80 },
        },
      },
    });
    // Only ONE search call — no per-hit follow-up.
    expect(search).toHaveBeenCalledTimes(1);
  });

  it('returns mixed results with commentary support count on document hits and source_document_ids on commentary hits', async () => {
    const search = vi.fn().mockResolvedValue({
      body: {
        hits: {
          total: { value: 2 },
          hits: [
            {
              _source: {
                document_id: 'doc_law_1',
                title: 'Obligationenrecht',
                document_type: 'law',
                record_kind: 'document',
              },
            },
            {
              _source: {
                document_id: 'doc_comm_1',
                title: 'Kommentar zu Art. 41 OR',
                document_type: 'commentary',
                record_kind: 'commentary',
                source_document_ids: ['doc_law_1'],
                jurisdiction_ids: ['jur_ch_federal'],
                authority_ids: ['auth_swisslex'],
              },
            },
          ],
        },
        aggregations: {
          commentary_support: {
            doc_count: 1,
            by_source_document: {
              buckets: [{ key: 'doc_law_1', doc_count: 3 }],
            },
          },
        },
      },
    });

    const adapter = new SearchOpenSearchAdapter(
      { search } as never,
      {
        get: (key: string) =>
          key === 'opensearch.documentsReadAlias' ? 'documents-read-test' : null,
      } as ConfigService,
    );

    const result = await adapter.search('haftung');

    expect(result.hits).toHaveLength(2);
    expect(result.hits[0]).toEqual(
      expect.objectContaining({
        document_id: 'doc_law_1',
        record_kind: 'document',
        commentary_support_count: 3,
      }),
    );
    expect(result.hits[0].source_document_ids).toBeUndefined();
    expect(result.hits[1]).toEqual(
      expect.objectContaining({
        document_id: 'doc_comm_1',
        record_kind: 'commentary',
        source_document_ids: ['doc_law_1'],
        jurisdiction_ids: ['jur_ch_federal'],
        authority_ids: ['auth_swisslex'],
      }),
    );
    // Commentary hits don't carry a support count (it's a primary-document concept).
    expect(result.hits[1].commentary_support_count).toBeUndefined();
  });

  it('defaults record_kind to "document" for legacy rows without the field', async () => {
    const search = vi.fn().mockResolvedValue({
      body: {
        hits: {
          total: { value: 1 },
          hits: [
            {
              _source: {
                document_id: 'doc_legacy',
                title: 'Legacy law',
                document_type: 'law',
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

    const result = await adapter.search('legacy');

    expect(result.hits[0]).toEqual(
      expect.objectContaining({
        document_id: 'doc_legacy',
        record_kind: 'document',
      }),
    );
  });

  it('omits the commentary_support sub-aggregation from the parsed facet aggregations', async () => {
    const search = vi.fn().mockResolvedValue({
      body: {
        hits: { total: { value: 0 }, hits: [] },
        aggregations: {
          commentary_support: {
            doc_count: 1,
            by_source_document: { buckets: [{ key: 'doc_a', doc_count: 1 }] },
          },
          jurisdiction: { buckets: [{ key: 'CH', doc_count: 5 }] },
        },
      },
    });

    const adapter = new SearchOpenSearchAdapter(
      { search } as never,
      {
        get: (key: string) =>
          key === 'opensearch.documentsReadAlias' ? 'documents-read-test' : null,
      } as ConfigService,
    );

    const result = await adapter.search('test');

    expect((result.aggregations as Record<string, unknown>).commentary_support).toBeUndefined();
    expect(result.aggregations.jurisdiction).toEqual([{ key: 'CH', doc_count: 5 }]);
  });

  describe('jurisdiction filter routing', () => {
    function makeAdapter(searchFn = vi.fn()) {
      searchFn.mockResolvedValue({
        body: { hits: { total: { value: 0 }, hits: [] }, aggregations: {} },
      });
      const adapter = new SearchOpenSearchAdapter(
        { search: searchFn } as never,
        {
          get: (key: string) =>
            key === 'opensearch.documentsReadAlias' ? 'documents-read-test' : null,
        } as ConfigService,
      );
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
