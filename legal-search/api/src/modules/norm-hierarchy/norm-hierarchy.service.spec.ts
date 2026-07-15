import { NotFoundException } from '@nestjs/common';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type {
  FindNormsOptions,
  NormEntity,
  NormHierarchyRepository,
  NormsByLevel,
} from './norm-hierarchy.repository';
import { NormHierarchyService } from './norm-hierarchy.service';

const ZURICH_CITY = 'jur_ch_gemeinde_261';
const ZURICH_CANTON = 'jur_ch_zh';
const CH_FEDERAL = 'jur_ch_federal';

function norm(overrides: Partial<NormEntity>): NormEntity {
  return {
    document_id: 'doc_1',
    title: 'Untitled',
    level: 'federal',
    jurisdiction_ids: [CH_FEDERAL],
    ...overrides,
  };
}

function repositoryReturning(byLevel: Record<string, NormEntity[]>): {
  repository: NormHierarchyRepository;
  lastOptions: () => FindNormsOptions | undefined;
} {
  let captured: FindNormsOptions | undefined;
  const findNormsByScopes = vi.fn(async (options: FindNormsOptions): Promise<NormsByLevel> => {
    captured = options;
    return {
      documents: new Map(Object.entries(byLevel)),
      totals: new Map(Object.entries(byLevel).map(([level, docs]) => [level, docs.length])),
    };
  });
  return { repository: { findNormsByScopes }, lastOptions: () => captured };
}

describe('NormHierarchyService', () => {
  let service: NormHierarchyService;

  describe('the hierarchy for a municipality', () => {
    beforeEach(() => {
      const { repository } = repositoryReturning({});
      service = new NormHierarchyService(repository);
    });

    it('returns its canton and the federation', async () => {
      const view = await service.getHierarchy({ jurisdictionId: ZURICH_CITY });

      const cantonal = view.levels.find((l) => l.level === 'cantonal');
      const federal = view.levels.find((l) => l.level === 'federal');
      expect(cantonal?.jurisdiction_ids).toEqual([ZURICH_CANTON]);
      expect(federal?.jurisdiction_ids).toContain(CH_FEDERAL);
    });

    it('orders the levels most authoritative first', async () => {
      const view = await service.getHierarchy({ jurisdictionId: ZURICH_CITY });
      expect(view.levels.map((l) => l.level)).toEqual([
        'constitutional',
        'federal',
        'cantonal',
        'municipal',
      ]);
    });

    it('queries every governing scope in one walk', async () => {
      const { repository, lastOptions } = repositoryReturning({});
      service = new NormHierarchyService(repository);
      await service.getHierarchy({ jurisdictionId: ZURICH_CITY });

      const scopes = lastOptions()?.jurisdictionIds ?? [];
      expect(scopes).toEqual(expect.arrayContaining([ZURICH_CITY, ZURICH_CANTON, CH_FEDERAL]));
      expect(scopes).not.toContain('jur_ch_be');
    });
  });

  it('refuses an unknown jurisdiction rather than returning an empty hierarchy', async () => {
    const { repository } = repositoryReturning({});
    service = new NormHierarchyService(repository);
    await expect(service.getHierarchy({ jurisdictionId: 'jur_atlantis' })).rejects.toBeInstanceOf(
      NotFoundException,
    );
  });

  describe('coverage', () => {
    it('reports the levels the corpus does not hold, so an agent can refuse', async () => {
      // ADR-0033 §2: "I do not have the Hundereglement for this commune" is a
      // correct answer. Omitting the empty level silently is not.
      const { repository } = repositoryReturning({
        federal: [norm({ document_id: 'doc_tschg', title: 'Tierschutzgesetz' })],
      });
      service = new NormHierarchyService(repository);

      const view = await service.getHierarchy({ jurisdictionId: ZURICH_CITY });
      expect(view.coverage.covered_levels).toEqual(['federal']);
      expect(view.coverage.missing_levels).toContain('municipal');
      expect(view.coverage.missing_levels).toContain('cantonal');
      // The empty level is still present in the response, not dropped.
      expect(view.levels.find((l) => l.level === 'municipal')?.total).toBe(0);
    });
  });

  describe('temporal validity', () => {
    it('marks a norm repealed before the asked-about date', async () => {
      const { repository } = repositoryReturning({
        cantonal: [
          norm({
            document_id: 'doc_old_hundegesetz',
            level: 'cantonal',
            jurisdiction_ids: [ZURICH_CANTON],
            in_force_from: '2005-01-01',
            in_force_until: '2018-12-31',
          }),
        ],
      });
      service = new NormHierarchyService(repository);

      const view = await service.getHierarchy({
        jurisdictionId: ZURICH_CITY,
        inForceAt: '2019-06-01',
      });
      const cantonal = view.levels.find((l) => l.level === 'cantonal');
      expect(cantonal?.documents[0]?.in_force_state).toBe('repealed');
    });

    it('passes the as-of date down to the repository', async () => {
      const { repository, lastOptions } = repositoryReturning({});
      service = new NormHierarchyService(repository);
      await service.getHierarchy({ jurisdictionId: ZURICH_CITY, inForceAt: '2019-06-01' });
      expect(lastOptions()?.inForceAt).toBe('2019-06-01');
    });

    it('leaves in_force_state unresolved when no date was asked about', async () => {
      const { repository } = repositoryReturning({
        federal: [norm({ in_force_from: '2005-01-01' })],
      });
      service = new NormHierarchyService(repository);
      const view = await service.getHierarchy({ jurisdictionId: ZURICH_CITY });
      expect(
        view.levels.find((l) => l.level === 'federal')?.documents[0]?.in_force_state,
      ).toBeUndefined();
    });
  });
});
