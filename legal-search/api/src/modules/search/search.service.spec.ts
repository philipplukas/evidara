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
    expect(result.results[0].badges[0].label).toBe('Gesetz');
    expect(result.facets.length).toBeGreaterThan(0);
  });

  it('should pass search options to repository', async () => {
    const repo = createMockRepo();
    const service = new SearchService(repo);

    await service.search('test', {
      jurisdictions: ['ch'],
      documentTypes: ['law'],
      languages: ['de'],
      officialOnly: true,
      page: 2,
      pageSize: 10,
    });

    expect(repo.search).toHaveBeenCalledWith('test', {
      jurisdictions: ['ch'],
      documentTypes: ['law'],
      languages: ['de'],
      officialOnly: true,
      page: 2,
      pageSize: 10,
    });
  });

  it('should pass canonical jurisdiction ids through to the repository', async () => {
    const repo = createMockRepo();
    const service = new SearchService(repo);

    await service.search('test', {
      canonicalJurisdictionIds: ['jur_ch_gemeinde_261'],
    });

    expect(repo.search).toHaveBeenCalledWith(
      'test',
      expect.objectContaining({
        canonicalJurisdictionIds: ['jur_ch_gemeinde_261'],
      }),
    );
  });

  it('should return context from getContext', async () => {
    const repo = createMockRepo();
    const service = new SearchService(repo);

    const ctx = await service.getContext();

    expect(ctx.jurisdictions).toHaveLength(1);
    expect(ctx.jurisdictions[0].label).toBe('Schweiz');
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

  // ─── Sprint 2 (#425): mixed-result responses ───

  it('returns mixed commentary + primary-document hits with their join fields', async () => {
    const repo = createMockRepo({
      search: vi.fn().mockResolvedValue({
        total: 2,
        hits: [
          {
            document_id: 'doc_law_1',
            title: 'Obligationenrecht',
            document_type: 'law',
            jurisdiction: 'CH',
            record_kind: 'document',
            commentary_support_count: 4,
          },
          {
            document_id: 'doc_comm_1',
            title: 'Kommentar zu Art. 41 OR',
            document_type: 'commentary',
            jurisdiction: 'CH',
            record_kind: 'commentary',
            source_document_ids: ['doc_law_1'],
          },
        ],
        aggregations: {},
      } satisfies SearchResultEntity),
    });
    const service = new SearchService(repo);

    const result = await service.search('haftung');

    expect(result.totalResults).toBe(2);
    expect(result.results).toHaveLength(2);
    expect(result.results[0]).toEqual(
      expect.objectContaining({
        id: 'doc_law_1',
        recordKind: 'document',
        commentarySupportCount: 4,
      }),
    );
    expect(result.results[0]).not.toHaveProperty('sourceDocumentIds');
    expect(result.results[1]).toEqual(
      expect.objectContaining({
        id: 'doc_comm_1',
        recordKind: 'commentary',
        sourceDocumentIds: ['doc_law_1'],
      }),
    );
    expect(result.results[1]).not.toHaveProperty('commentarySupportCount');
  });

  it('forwards record_kind filter to the repository', async () => {
    const repo = createMockRepo();
    const service = new SearchService(repo);

    await service.search('test', { recordKind: 'commentary' });

    expect(repo.search).toHaveBeenCalledWith(
      'test',
      expect.objectContaining({ recordKind: 'commentary' }),
    );
  });

  it('defaults legacy hits without record_kind to "document" and exposes no support count when zero', async () => {
    const repo = createMockRepo({
      search: vi.fn().mockResolvedValue({
        total: 1,
        hits: [
          {
            document_id: 'doc_legacy',
            title: 'Legacy law',
            document_type: 'law',
            jurisdiction: 'CH',
          },
        ],
        aggregations: {},
      } satisfies SearchResultEntity),
    });
    const service = new SearchService(repo);

    const result = await service.search('legacy');

    expect(result.results[0].recordKind).toBe('document');
    expect(result.results[0]).not.toHaveProperty('commentarySupportCount');
    expect(result.results[0]).not.toHaveProperty('sourceDocumentIds');
  });
});
