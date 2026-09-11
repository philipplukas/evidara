/**
 * The #986 calibration set, run against the service.
 *
 * Production holds `jur_ch_zh` (889 documents) plus three federal documents and
 * nothing else, so that is the corpus these tests stand in. The set is fixed by
 * the issue and is deliberately half "must ANSWER": a mechanism that refuses
 * everything would sail through a suite that only checked the refusals, and
 * that is the vacuous-test trap AGENTS.md names.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CorpusJurisdictionsService } from './corpus-jurisdictions.service';
import type { ContextAggregations, SearchResultEntity } from './entities/search.entities';
import type { SearchRepository } from './search.repository';
import { SearchService } from './search.service';

/** What the production index actually holds, per #986. */
const PRODUCTION_HOLDINGS = ['jur_ch_zh', 'jur_ch_federal'];

const RESULTS: SearchResultEntity = {
  total: 3,
  hits: [
    {
      document_id: 'doc_hug',
      title: 'Hundegesetz (HuG) 554.5',
      document_type: 'law',
      jurisdiction: 'CH',
      snippet: 'Hundehaltung im Kanton Zürich',
    },
  ],
  aggregations: { jurisdiction: [{ key: 'CH', doc_count: 3 }] },
};

function createRepo(holdings: string[] = PRODUCTION_HOLDINGS): SearchRepository {
  return {
    search: vi.fn().mockResolvedValue(RESULTS),
    getContextAggregations: vi.fn().mockResolvedValue({
      jurisdictions: [],
      languages: [],
      source_types: [],
    } satisfies ContextAggregations),
    getHeldJurisdictionIds: vi.fn().mockResolvedValue(holdings),
    checkReadAlias: vi
      .fn()
      .mockResolvedValue({ status: 'ok', alias: 'documents-read', indices: ['documents-000001'] }),
  };
}

function createService(repo: SearchRepository): SearchService {
  return new SearchService(repo, new CorpusJurisdictionsService(repo));
}

describe('jurisdiction-aware refusal (#986)', () => {
  let repo: SearchRepository;
  let service: SearchService;

  beforeEach(() => {
    repo = createRepo();
    service = createService(repo);
  });

  describe('must ANSWER — the corpus holds ZH', () => {
    it.each([
      ['Statistikgesetz Kanton Zürich', 'names ZH, which IS held'],
      ['Darf ich meinen Hund in Zürich ohne Leine laufen lassen', 'names ZH without a marker'],
      ['Anrechnung ausländischer Quellensteuern', 'names no jurisdiction'],
      ['recipe for chocolate cake', 'names no jurisdiction — out of scope for this mechanism'],
    ])('answers %j (%s)', async (query) => {
      const result = await service.search(query);

      expect(result.refusal).toBeUndefined();
      expect(result.totalResults).toBe(3);
      expect(result.results).toHaveLength(1);
      // The query must actually have reached the index — a mechanism that
      // short-circuits every query would otherwise pass the line above.
      expect(repo.search).toHaveBeenCalledWith(query, expect.anything());
    });
  });

  describe('must REFUSE — the query names a canton the corpus lacks', () => {
    it.each([
      ['Hundegesetz Kanton Bern', 'jur_ch_be', 'CH-BE'],
      ['Mietrecht Kanton Aargau', 'jur_ch_ag', 'CH-AG'],
    ])('refuses %j', async (query, jurisdictionId, isoCode) => {
      const result = await service.search(query);

      expect(result.refusal).toBeDefined();
      expect(result.refusal?.code).toBe('jurisdiction_not_held');
      expect(result.refusal?.jurisdictions).toEqual([
        expect.objectContaining({ jurisdiction_id: jurisdictionId, iso_code: isoCode }),
      ]);
      // The refusal must be legible, not an empty list: it names the
      // jurisdiction in prose a caller can relay.
      expect(result.refusal?.message).toContain(isoCode);
      expect(result.results).toEqual([]);
      expect(result.totalResults).toBe(0);
      // No confident results from another canton are fetched at all.
      expect(repo.search).not.toHaveBeenCalled();
    });

    it('is distinguishable from a query that ran and matched nothing', async () => {
      // #984: the whole point is that these two are different answers. A caller
      // must be able to tell them apart from the payload alone.
      const empty = createRepo();
      (empty.search as ReturnType<typeof vi.fn>).mockResolvedValue({
        total: 0,
        hits: [],
        aggregations: {},
      } satisfies SearchResultEntity);

      const zeroMatches = await createService(empty).search('Statistikgesetz Kanton Zürich');
      const refused = await service.search('Hundegesetz Kanton Bern');

      expect(zeroMatches.totalResults).toBe(0);
      expect(zeroMatches.refusal).toBeUndefined();
      expect(refused.totalResults).toBe(0);
      expect(refused.refusal).toBeDefined();
    });
  });

  describe('what it refuses to refuse', () => {
    it('answers when one named canton is held and another is not', async () => {
      const result = await service.search('Hundegesetz Kanton Bern und Kanton Zürich');

      expect(result.refusal).toBeUndefined();
      expect(repo.search).toHaveBeenCalled();
    });

    it('answers when corpus holdings cannot be established', async () => {
      // A refusal built on a failed lookup would be a lie the caller cannot
      // detect. Search itself still works, so it must still answer.
      const broken = createRepo();
      (broken.getHeldJurisdictionIds as ReturnType<typeof vi.fn>).mockRejectedValue(
        new Error('connection refused'),
      );

      const result = await createService(broken).search('Hundegesetz Kanton Bern');

      expect(result.refusal).toBeUndefined();
      expect(broken.search).toHaveBeenCalled();
    });

    it('answers when the holdings aggregation returns no buckets at all', async () => {
      // Empty buckets are what a DRIFTED MAPPING produces (#675), not evidence
      // of an empty corpus. Refusing here would refuse every jurisdictional
      // query in production the moment `jurisdiction_ids` stopped aggregating.
      const result = await createService(createRepo([])).search('Hundegesetz Kanton Bern');

      expect(result.refusal).toBeUndefined();
    });
  });

  describe('cost', () => {
    it('does not re-aggregate holdings on every request', async () => {
      await service.search('Statistikgesetz Kanton Zürich');
      await service.search('Hundegesetz Kanton Bern');
      await service.search('Mietrecht Kanton Aargau');

      expect(repo.getHeldJurisdictionIds).toHaveBeenCalledTimes(1);
    });

    it('does not aggregate at all for a query that names no jurisdiction', async () => {
      await service.search('Anrechnung ausländischer Quellensteuern');

      expect(repo.getHeldJurisdictionIds).not.toHaveBeenCalled();
    });
  });
});
