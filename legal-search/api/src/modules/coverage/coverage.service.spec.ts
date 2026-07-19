/**
 * The honesty rules of `/v1/coverage` (ADR-0042), asserted directly.
 *
 * These are not shape tests. Each one pins a property that, if it regressed,
 * would turn a coverage answer into a claim the platform cannot substantiate —
 * which is the specific failure #709 exists to prevent.
 */
import { BadRequestException } from '@nestjs/common';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { CoverageCounts, CoverageQueryOptions } from './coverage.repository';
import { CoverageService } from './coverage.service';

const EMPTY: CoverageCounts = { totalDocuments: 0, documentsWithoutGroupKey: 0, buckets: [] };

function makeService(counts: CoverageCounts = EMPTY) {
  const countCoverage = vi.fn(async (_options: CoverageQueryOptions) => counts);
  return { service: new CoverageService({ countCoverage }), countCoverage };
}

describe('CoverageService', () => {
  let federalJurisdiction: string;

  beforeEach(() => {
    federalJurisdiction = 'jur_ch_federal';
  });

  describe('rule 1 — absence is reported, never inferred', () => {
    it('returns a not_held group for a named jurisdiction the corpus holds nothing for', async () => {
      // The whole point of #709: an aggregation produces no bucket for a value
      // that is not in the index, so without this the caller gets an empty list
      // and is back to inferring absence from emptiness.
      const { service } = makeService();

      const view = await service.getCoverage({ jurisdictionId: 'jur_ch_zh' });

      expect(view.groups).toHaveLength(1);
      expect(view.groups[0]).toMatchObject({
        key: 'jur_ch_zh',
        documents: 0,
        holding: 'not_held',
      });
    });

    it('reports held and not_held side by side when several jurisdictions are named', async () => {
      const { service } = makeService({
        totalDocuments: 73,
        documentsWithoutGroupKey: 0,
        buckets: [
          {
            key: 'jur_ch_federal',
            documents: 73,
            lastProcessedAt: '2026-07-18T09:12:00.000Z',
            documentsWithoutRepealDate: 70,
            sourceVersionIds: ['sv_1'],
            sourceVersionCount: 1,
          },
        ],
      });

      const view = await service.getCoverage({
        jurisdictionId: 'jur_ch_federal,jur_ch_zh',
      });

      const byKey = Object.fromEntries(view.groups.map((g) => [g.key, g]));
      expect(byKey.jur_ch_federal.holding).toBe('held');
      expect(byKey.jur_ch_zh.holding).toBe('not_held');
      expect(byKey.jur_ch_zh.documents).toBe(0);
    });
  });

  describe('rule 2 — a coverage answer is about the corpus, never about the law', () => {
    it('never emits a holding value that could be read as "no such law exists"', async () => {
      const { service } = makeService();

      const view = await service.getCoverage({ jurisdictionId: 'jur_ch_zh' });

      // If this ever admits a third value, ADR-0042's central guarantee is gone:
      // a caller could read a coverage response as evidence about the law.
      for (const group of view.groups) {
        expect(['held', 'not_held']).toContain(group.holding);
      }
    });

    it('declares its evidentiary basis as the index', async () => {
      const { service } = makeService();

      const view = await service.getCoverage({});

      // Machine-readable, so a caller can check the basis without reading prose.
      // `index` = what we hold; it says nothing about acquisition intent, which
      // is platform-control's (ADR-0042 §4).
      expect(view.basis).toBe('index');
    });
  });

  describe('rule 3 — an unrecognized id is not a coverage answer', () => {
    it('reports an unknown jurisdiction id as unrecognized and emits no group for it', async () => {
      const { service } = makeService();

      const view = await service.getCoverage({ jurisdictionId: 'jur_ch_zurich' });

      // `jur_ch_zurich` is a typo for `jur_ch_zh`. Answering "we hold nothing
      // for it" would read as a coverage fact when the truth is that the id is
      // unknown.
      expect(view.unrecognized_jurisdiction_ids).toEqual(['jur_ch_zurich']);
      expect(view.groups).toHaveLength(0);
    });

    it('separates unrecognized ids from recognized-but-empty ones', async () => {
      const { service } = makeService();

      const view = await service.getCoverage({
        jurisdictionId: 'jur_ch_zh,jur_ch_zurich',
      });

      expect(view.unrecognized_jurisdiction_ids).toEqual(['jur_ch_zurich']);
      expect(view.groups.map((g) => g.key)).toEqual(['jur_ch_zh']);
    });

    it('does not widen the scope to the whole corpus when every named id is unknown', async () => {
      // A filter dropped because nothing survived validation would return
      // corpus-wide totals under a response that echoes the caller's narrow
      // scope — the answer would be right about a question nobody asked.
      const { service, countCoverage } = makeService();

      await service.getCoverage({ jurisdictionId: 'jur_nowhere' });

      expect(countCoverage.mock.calls[0][0].jurisdictionIds).toEqual([]);
    });
  });

  describe('what it refuses to guess', () => {
    it('rejects an unknown group_by rather than falling back to the default', async () => {
      const { service } = makeService();

      await expect(service.getCoverage({ groupBy: 'topic' })).rejects.toBeInstanceOf(
        BadRequestException,
      );
    });

    it('rejects an unknown norm level rather than silently ignoring the filter', async () => {
      // An ignored filter widens the scope, and the caller reads the wider
      // answer as the narrower one they asked for.
      const { service } = makeService();

      await expect(service.getCoverage({ level: 'federal,galactic' })).rejects.toBeInstanceOf(
        BadRequestException,
      );
    });

    it('rejects a malformed in_force_at rather than ignoring the temporal scope', async () => {
      const { service } = makeService();

      await expect(service.getCoverage({ inForceAt: 'last year' })).rejects.toBeInstanceOf(
        BadRequestException,
      );
    });

    it('omits a label rather than echoing an id back as a name', async () => {
      const { service } = makeService({
        totalDocuments: 3,
        documentsWithoutGroupKey: 0,
        buckets: [
          {
            key: 'ordinance',
            documents: 3,
            documentsWithoutRepealDate: 3,
            sourceVersionIds: [],
            sourceVersionCount: 0,
          },
        ],
      });

      const view = await service.getCoverage({ groupBy: 'document_type' });

      // Document types have no vocabulary behind them. `undefined` says "no
      // label is known"; `'ordinance'` as a label would dress an id up as a name.
      expect(view.groups[0].label).toBeUndefined();
    });

    it('labels a jurisdiction from the vocabulary when one exists', async () => {
      const { service } = makeService();

      const view = await service.getCoverage({ jurisdictionId: federalJurisdiction });

      expect(view.groups[0].label).toBeTruthy();
    });
  });

  describe('what the numbers do and do not add up to', () => {
    it('reports documents that carry no value for the grouping field', async () => {
      // `authority_ids` is sparse on legal documents, so grouping by authority
      // can omit a large share of the corpus. Reported, not dropped — otherwise
      // a caller summing groups under-counts without being told.
      const { service } = makeService({
        totalDocuments: 73,
        documentsWithoutGroupKey: 40,
        buckets: [
          {
            key: 'auth_fedlex',
            documents: 33,
            documentsWithoutRepealDate: 30,
            sourceVersionIds: ['sv_1'],
            sourceVersionCount: 1,
          },
        ],
      });

      const view = await service.getCoverage({ groupBy: 'authority' });

      expect(view.total_documents).toBe(73);
      expect(view.documents_without_group_key).toBe(40);
    });

    it('carries the assumed-in-force count so an in-force claim can be weighed', async () => {
      // Absence of `in_force_until` means "not known to be repealed", which is
      // not "never repealed". This number is the size of that benefit of the doubt.
      const { service } = makeService({
        totalDocuments: 73,
        documentsWithoutGroupKey: 0,
        buckets: [
          {
            key: 'jur_ch_federal',
            documents: 73,
            documentsWithoutRepealDate: 70,
            sourceVersionIds: ['sv_1'],
            sourceVersionCount: 1,
          },
        ],
      });

      const view = await service.getCoverage({ inForceAt: '2019-06-01' });

      expect(view.groups[0].documents_without_repeal_date).toBe(70);
      expect(view.scope.in_force_at).toBe('2019-06-01');
    });

    it('passes the as-of date to the repository so unknown-dated norms are kept', async () => {
      const { service, countCoverage } = makeService();

      await service.getCoverage({ inForceAt: '2019-06-01' });

      expect(countCoverage.mock.calls[0][0].inForceAt).toBe('2019-06-01');
    });

    it('reports provenance — which source versions produced the group', async () => {
      const { service } = makeService({
        totalDocuments: 5,
        documentsWithoutGroupKey: 0,
        buckets: [
          {
            key: 'jur_ch_federal',
            documents: 5,
            lastProcessedAt: '2026-07-18T09:12:00.000Z',
            documentsWithoutRepealDate: 5,
            sourceVersionIds: ['sv_a', 'sv_b'],
            sourceVersionCount: 2,
          },
        ],
      });

      const view = await service.getCoverage({});

      expect(view.groups[0].source_version_ids).toEqual(['sv_a', 'sv_b']);
      expect(view.groups[0].source_version_count).toBe(2);
      expect(view.groups[0].last_processed_at).toBe('2026-07-18T09:12:00.000Z');
    });

    it('omits freshness and provenance for a group holding nothing', async () => {
      // There is no honest timestamp for documents that do not exist.
      const { service } = makeService();

      const view = await service.getCoverage({ jurisdictionId: 'jur_ch_zh' });

      expect(view.groups[0].last_processed_at).toBeUndefined();
      expect(view.groups[0].source_version_ids).toBeUndefined();
      expect(view.groups[0].source_version_count).toBeUndefined();
    });
  });

  describe('defaults and ordering', () => {
    it('groups by jurisdiction and echoes the dimension back', async () => {
      const { service, countCoverage } = makeService();

      const view = await service.getCoverage({});

      expect(view.group_by).toBe('jurisdiction');
      expect(countCoverage.mock.calls[0][0].dimension).toBe('jurisdiction');
    });

    it('orders groups by holdings descending, then by key', async () => {
      const { service } = makeService({
        totalDocuments: 9,
        documentsWithoutGroupKey: 0,
        buckets: [
          {
            key: 'jur_ch_federal',
            documents: 4,
            documentsWithoutRepealDate: 0,
            sourceVersionIds: [],
            sourceVersionCount: 0,
          },
          {
            key: 'jur_at_federal',
            documents: 5,
            documentsWithoutRepealDate: 0,
            sourceVersionIds: [],
            sourceVersionCount: 0,
          },
        ],
      });

      const view = await service.getCoverage({});

      expect(view.groups.map((g) => g.key)).toEqual(['jur_at_federal', 'jur_ch_federal']);
    });

    it('clamps limit into the contract range', async () => {
      const { service, countCoverage } = makeService();

      await service.getCoverage({ limit: 99999 });

      expect(countCoverage.mock.calls[0][0].limit).toBe(1000);
    });
  });
});
