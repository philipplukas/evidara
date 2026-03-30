import { describe, expect, it, vi } from 'vitest';
import type { ContextAggregations, SearchResultEntity } from './entities/search.entities';
import type { SearchRepository } from './search.repository';
import { SearchService } from './search.service';

// ─── Mock Repository ───

function createMockRepo(overrides?: Partial<SearchRepository>): SearchRepository {
  return {
    search: vi.fn().mockResolvedValue({
      total: 1,
      hits: [
        {
          document_id: 'doc_001',
          title: 'Test Law',
          document_type: 'law',
          jurisdiction: 'CH',
          snippet: 'test snippet',
        },
      ],
      aggregations: {
        jurisdiction: [{ key: 'CH', doc_count: 1 }],
      },
    } satisfies SearchResultEntity),
    getContextAggregations: vi.fn().mockResolvedValue({
      jurisdictions: [{ key: 'CH', doc_count: 100 }],
      languages: [{ key: 'de', doc_count: 100 }],
      source_types: [{ key: 'law', doc_count: 50 }],
    } satisfies ContextAggregations),
    ...overrides,
  };
}

// ─── Tests ───

describe('SearchService', () => {
  it('should return ViewModel results from search', async () => {
    const repo = createMockRepo();
    const service = new SearchService(repo);

    const result = await service.search('test');

    expect(result.totalResults).toBe(1);
    expect(result.results).toHaveLength(1);
    expect(result.results[0].id).toBe('doc_001');
    expect(result.results[0].badges).toHaveLength(1);
    expect(result.results[0].badges[0].label).toBe('Law');
    expect(result.facets.length).toBeGreaterThan(0);
  });

  it('should pass search options to repository', async () => {
    const repo = createMockRepo();
    const service = new SearchService(repo);

    await service.search('test', {
      jurisdiction: 'CH',
      documentType: 'law',
      page: 2,
      pageSize: 10,
    });

    expect(repo.search).toHaveBeenCalledWith('test', {
      jurisdiction: 'CH',
      documentType: 'law',
      page: 2,
      pageSize: 10,
    });
  });

  it('should return context from getContext', async () => {
    const repo = createMockRepo();
    const service = new SearchService(repo);

    const ctx = await service.getContext();

    expect(ctx.jurisdictions).toHaveLength(1);
    expect(ctx.jurisdictions[0].label).toBe('Switzerland');
    expect(ctx.languages).toHaveLength(1);
    expect(ctx.sourceTypes.length).toBeGreaterThan(0);
  });

  it('should handle empty search results', async () => {
    const repo = createMockRepo({
      search: vi.fn().mockResolvedValue({
        total: 0,
        hits: [],
        aggregations: {},
      }),
    });
    const service = new SearchService(repo);

    const result = await service.search('nothing');

    expect(result.totalResults).toBe(0);
    expect(result.results).toEqual([]);
    expect(result.facets).toEqual([]);
  });
});
