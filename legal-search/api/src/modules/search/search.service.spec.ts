import { describe, expect, it, vi } from 'vitest';
import { CorpusJurisdictionsService } from './corpus-jurisdictions.service';
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
    getHeldJurisdictionIds: vi.fn().mockResolvedValue(['jur_ch_zh']),
    checkReadAlias: vi
      .fn()
      .mockResolvedValue({ status: 'ok', alias: 'documents-read', indices: ['documents-000001'] }),
    ...overrides,
  };
}

// ─── Tests ───

describe('SearchService', () => {
  it('should return ViewModel results from search', async () => {
    const repo = createMockRepo();
    const service = new SearchService(repo, new CorpusJurisdictionsService(repo));

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
    const service = new SearchService(repo, new CorpusJurisdictionsService(repo));

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

  it('should return context from getContext', async () => {
    const repo = createMockRepo();
    const service = new SearchService(repo, new CorpusJurisdictionsService(repo));

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
    const service = new SearchService(repo, new CorpusJurisdictionsService(repo));

    const result = await service.search('nothing');

    expect(result.totalResults).toBe(0);
    expect(result.results).toEqual([]);
    expect(result.facets).toEqual([]);
  });

  // ─── #975 gap A: the query names a place, and that must reach the ranker ───

  describe('jurisdiction mentions as a ranking signal (#975 gap A)', () => {
    it('prefers the named canton AND the federal tier above it, never one alone', async () => {
      // Both halves are load-bearing and were measured against production:
      // without the canton, "Kanton Bern" returned a ZURICH document whose
      // title merely contains the word Bern; without the federal tier, the
      // Tierschutzgesetz fell out of the top 20 of the dog question entirely.
      const repo = createMockRepo({
        getHeldJurisdictionIds: vi.fn().mockResolvedValue(['jur_ch_be', 'jur_ch_zh']),
      });
      const service = new SearchService(repo, new CorpusJurisdictionsService(repo));

      await service.search('Hundehaltung Kanton Bern Vorschriften');

      const [, options] = (repo.search as ReturnType<typeof vi.fn>).mock.calls[0];
      expect(options.boostJurisdictionIds).toEqual(
        expect.arrayContaining(['jur_ch_be', 'jur_ch_federal']),
      );
    });

    it('passes it as a ranking signal, never as a filter', async () => {
      // `jurisdictionIds` REMOVES everything else; this must not. A query naming
      // Zürich that silently filtered to Zürich would hide the federal act.
      const repo = createMockRepo();
      const service = new SearchService(repo, new CorpusJurisdictionsService(repo));

      await service.search('Hundegesetz Kanton Zuerich');

      const [, options] = (repo.search as ReturnType<typeof vi.fn>).mock.calls[0];
      expect(options.boostJurisdictionIds).toEqual(expect.arrayContaining(['jur_ch_zh']));
      expect(options.jurisdictionIds).toBeUndefined();
    });

    it('sends no signal at all when the query names nowhere', async () => {
      // The overwhelming majority of queries. They must be scored exactly as
      // they are today — an empty array here would be a clause that matches
      // nothing and still changes the query.
      const repo = createMockRepo();
      const service = new SearchService(repo, new CorpusJurisdictionsService(repo));

      await service.search('Anrechnung auslaendischer Quellensteuern');

      const [, options] = (repo.search as ReturnType<typeof vi.fn>).mock.calls[0];
      expect(options.boostJurisdictionIds).toBeUndefined();
    });

    it('does not reach the repository at all when the corpus refuses', async () => {
      // Refusal wins over ranking: there is nothing to rank.
      const repo = createMockRepo({
        getHeldJurisdictionIds: vi.fn().mockResolvedValue(['jur_ch_zh']),
      });
      const service = new SearchService(repo, new CorpusJurisdictionsService(repo));

      const result = await service.search('Hundegesetz Kanton Aargau');

      expect(result.refusal?.code).toBe('jurisdiction_not_held');
      expect(repo.search).not.toHaveBeenCalled();
    });
  });
});
