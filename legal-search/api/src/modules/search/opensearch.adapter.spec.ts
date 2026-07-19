import type { ConfigService } from '@nestjs/config';
import { describe, expect, it, vi } from 'vitest';
import { MetricsService } from '../../core/metrics/metrics.service';
import { SearchOpenSearchAdapter } from './opensearch.adapter';
import { SearchBackendUnavailableError } from './search.errors';

const CONFIG = {
  get: (key: string) => (key === 'opensearch.documentsReadAlias' ? 'documents-read-test' : null),
} as ConfigService;

/** The error the OpenSearch client raises when the index/alias does not exist. */
function indexNotFoundError(): Error {
  const err = new Error('index_not_found_exception');
  Object.assign(err, {
    meta: {
      statusCode: 404,
      body: {
        error: {
          type: 'index_not_found_exception',
          reason: 'no such index [documents-read-test]',
        },
      },
    },
  });
  return err;
}

describe('SearchOpenSearchAdapter', () => {
  it('asks OpenSearch for an exact hit count rather than the default 10 000 cap', async () => {
    const search = vi.fn().mockResolvedValue({
      body: { hits: { total: { value: 0 }, hits: [] }, aggregations: {} },
    });

    const adapter = new SearchOpenSearchAdapter({ search } as never, CONFIG, new MetricsService());

    await adapter.search('verantwortlichkeit');

    // `total` becomes `SearchResponseView.totalResults`. Without
    // `track_total_hits`, OpenSearch caps the count at 10 000 and the UI
    // under-reports how many documents matched (#615).
    const body = (search.mock.calls[0][0] as { body: { track_total_hits?: boolean } }).body;
    expect(body.track_total_hits).toBe(true);
  });

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
      new MetricsService(),
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
      new MetricsService(),
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

  it('routes canonical jurisdiction/authority IDs to the projection keyword fields and ANDs with ISO', async () => {
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
      new MetricsService(),
    );

    await adapter.search('arbeitsrecht', {
      jurisdictions: ['ch'],
      jurisdictionIds: ['jur_ch_federal', 'jur_ch_gemeinde_4001'],
      authorityIds: ['auth_fedlex'],
    });

    const firstCall = search.mock.calls[0][0] as {
      body: { query: { bool: { filter: unknown[] } } };
    };
    expect(firstCall.body.query.bool.filter).toEqual([
      { terms: { jurisdiction: ['ch'] } },
      {
        terms: {
          'jurisdiction_ids.keyword': ['jur_ch_federal', 'jur_ch_gemeinde_4001'],
        },
      },
      { terms: { 'authority_ids.keyword': ['auth_fedlex'] } },
    ]);
  });

  it('omits canonical filter clauses when the option arrays are absent or empty', async () => {
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
      new MetricsService(),
    );

    await adapter.search('arbeitsrecht', {
      jurisdictionIds: [],
      authorityIds: undefined,
    });

    const firstCall = search.mock.calls[0][0] as {
      body: { query: { bool: { filter: unknown[] } } };
    };
    expect(firstCall.body.query.bool.filter).toEqual([]);
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
      new MetricsService(),
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
      new MetricsService(),
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
      new MetricsService(),
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
      new MetricsService(),
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
      new MetricsService(),
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
      new MetricsService(),
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

  // ─── Failure vs. zero matches (#551) ───

  describe('failed queries are not empty result sets', () => {
    it('resolves with an empty result set when the query executes and matches nothing', async () => {
      const search = vi.fn().mockResolvedValue({
        body: { hits: { total: { value: 0 }, hits: [] }, aggregations: {} },
      });
      const adapter = new SearchOpenSearchAdapter(
        { search } as never,
        CONFIG,
        new MetricsService(),
      );

      await expect(adapter.search('nichts')).resolves.toEqual({
        total: 0,
        hits: [],
        aggregations: {},
      });
    });

    it('throws index_missing instead of returning empty when the index does not exist', async () => {
      const search = vi.fn().mockRejectedValue(indexNotFoundError());
      const adapter = new SearchOpenSearchAdapter(
        { search } as never,
        CONFIG,
        new MetricsService(),
      );

      const failure = await adapter.search('obligationenrecht').catch((err: unknown) => err);

      expect(failure).toBeInstanceOf(SearchBackendUnavailableError);
      expect((failure as SearchBackendUnavailableError).reason).toBe('index_missing');
      expect((failure as SearchBackendUnavailableError).index).toBe('documents-read-test');
      expect((failure as SearchBackendUnavailableError).message).toContain(
        'index_not_found_exception',
      );
    });

    it('throws unavailable when the cluster cannot be reached', async () => {
      const search = vi.fn().mockRejectedValue(new Error('connect ECONNREFUSED 127.0.0.1:9200'));
      const adapter = new SearchOpenSearchAdapter(
        { search } as never,
        CONFIG,
        new MetricsService(),
      );

      const failure = await adapter.search('obligationenrecht').catch((err: unknown) => err);

      expect(failure).toBeInstanceOf(SearchBackendUnavailableError);
      expect((failure as SearchBackendUnavailableError).reason).toBe('unavailable');
    });

    it('throws rather than returning empty context aggregations when the index is missing', async () => {
      const search = vi.fn().mockRejectedValue(indexNotFoundError());
      const adapter = new SearchOpenSearchAdapter(
        { search } as never,
        CONFIG,
        new MetricsService(),
      );

      await expect(adapter.getContextAggregations()).rejects.toBeInstanceOf(
        SearchBackendUnavailableError,
      );
    });
  });

  // ─── Read-alias readiness probe (#551) ───

  describe('checkReadAlias', () => {
    it('reports ok with the resolved indices', async () => {
      const getAlias = vi.fn().mockResolvedValue({ body: { 'documents-000001': { aliases: {} } } });
      const adapter = new SearchOpenSearchAdapter(
        { indices: { getAlias } } as never,
        CONFIG,
        new MetricsService(),
      );

      await expect(adapter.checkReadAlias()).resolves.toEqual({
        status: 'ok',
        alias: 'documents-read-test',
        indices: ['documents-000001'],
      });
      expect(getAlias).toHaveBeenCalledWith({ name: 'documents-read-test' });
    });

    it('reports error when the alias does not resolve', async () => {
      const getAlias = vi.fn().mockRejectedValue(indexNotFoundError());
      const adapter = new SearchOpenSearchAdapter(
        { indices: { getAlias } } as never,
        CONFIG,
        new MetricsService(),
      );

      const result = await adapter.checkReadAlias();

      expect(result.status).toBe('error');
      expect(result).toMatchObject({ alias: 'documents-read-test' });
    });

    it('reports error when the alias resolves to no index', async () => {
      const getAlias = vi.fn().mockResolvedValue({ body: {} });
      const adapter = new SearchOpenSearchAdapter(
        { indices: { getAlias } } as never,
        CONFIG,
        new MetricsService(),
      );

      const result = await adapter.checkReadAlias();

      expect(result.status).toBe('error');
    });
  });
});
