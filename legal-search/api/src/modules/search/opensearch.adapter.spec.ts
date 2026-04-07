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
          key === 'opensearch.indexDocumentsRead' ? 'documents-read-test' : null,
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
      body: { query: { bool: { filter: unknown[] } } };
    };
    expect(firstCall.body.query.bool.filter).toEqual([
      { terms: { jurisdiction: ['ch', 'at'] } },
      { terms: { document_type: ['law', 'decision'] } },
      { terms: { language: ['de'] } },
      { term: { is_official: true } },
      { terms: { court_level: ['supreme'] } },
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
          key === 'opensearch.indexDocumentsRead' ? 'documents-read-test' : null,
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
});
