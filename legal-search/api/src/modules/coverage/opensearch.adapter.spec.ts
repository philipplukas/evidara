/**
 * These tests pin the QUERY SHAPE, not just the return values.
 *
 * The failure they exist to catch is silent, and it is the same one as #675: an
 * aggregation on a field that lacks a `.keyword` sub-field returns EMPTY BUCKETS
 * rather than an error. A coverage endpoint that does that reports the corpus as
 * holding nothing — a false refusal that looks exactly like a true one. So the
 * agg fields, the `record_kind` filter and the `must_not` temporal form are
 * asserted literally.
 */
import { ServiceUnavailableException } from '@nestjs/common';
import type { ConfigService } from '@nestjs/config';
import { describe, expect, it, vi } from 'vitest';
import { CoverageOpenSearchAdapter } from './opensearch.adapter';

function makeAdapter(search: ReturnType<typeof vi.fn>) {
  return new CoverageOpenSearchAdapter(
    { search } as never,
    {
      get: (key: string) => (key === 'opensearch.documentsReadAlias' ? 'documents-read' : null),
    } as ConfigService,
  );
}

const emptyResponse = {
  body: {
    hits: { total: { value: 0 } },
    aggregations: { by_dimension: { buckets: [] }, missing_key: { doc_count: 0 } },
  },
};

const bodyOf = (search: ReturnType<typeof vi.fn>) => search.mock.calls[0][0].body;

describe('CoverageOpenSearchAdapter', () => {
  it('aggregates on the `.keyword` sub-field for every dimension', async () => {
    const expected = {
      jurisdiction: 'jurisdiction_ids.keyword',
      authority: 'authority_ids.keyword',
      document_type: 'document_type.keyword',
      level: 'level.keyword',
    } as const;

    for (const [dimension, field] of Object.entries(expected)) {
      const search = vi.fn().mockResolvedValue(emptyResponse);
      await makeAdapter(search).countCoverage({
        dimension: dimension as keyof typeof expected,
        limit: 100,
      });

      expect(bodyOf(search).aggs.by_dimension.terms.field).toBe(field);
    }
  });

  it('counts jurisdictions by the multi-valued scope field, not the display field', async () => {
    // `jurisdiction` is a single-valued display string. Counting coverage over
    // it would disagree with search and norm-hierarchy — both filter on
    // `jurisdiction_ids` — so the same corpus would report two different
    // coverages depending on which endpoint you asked.
    const search = vi.fn().mockResolvedValue(emptyResponse);

    await makeAdapter(search).countCoverage({ dimension: 'jurisdiction', limit: 100 });

    expect(bodyOf(search).aggs.by_dimension.terms.field).toBe('jurisdiction_ids.keyword');
  });

  it('excludes commentary, which is not a norm', async () => {
    // Counting commentary as coverage would report the corpus as holding law it
    // does not hold. Same rule as norm-hierarchy, same reason.
    const search = vi.fn().mockResolvedValue(emptyResponse);

    await makeAdapter(search).countCoverage({ dimension: 'jurisdiction', limit: 100 });

    expect(bodyOf(search).query.bool.filter).toContainEqual({
      term: { record_kind: 'legal_document' },
    });
  });

  it('applies the temporal window as must_not, so unknown-dated norms are kept', async () => {
    // Dropping undated norms would hide law from the caller and make silence
    // indistinguishable from absence (ADR-0033 §2).
    const search = vi.fn().mockResolvedValue(emptyResponse);

    await makeAdapter(search).countCoverage({
      dimension: 'jurisdiction',
      inForceAt: '2019-06-01',
      limit: 100,
    });

    expect(bodyOf(search).query.bool.must_not).toEqual([
      { range: { in_force_until: { lt: '2019-06-01' } } },
      { range: { in_force_from: { gt: '2019-06-01' } } },
    ]);
  });

  it('omits the temporal clause entirely when no as-of date is given', async () => {
    const search = vi.fn().mockResolvedValue(emptyResponse);

    await makeAdapter(search).countCoverage({ dimension: 'jurisdiction', limit: 100 });

    expect(bodyOf(search).query.bool.must_not).toEqual([]);
  });

  it('filters the scope on the `.keyword` sub-fields', async () => {
    const search = vi.fn().mockResolvedValue(emptyResponse);

    await makeAdapter(search).countCoverage({
      dimension: 'jurisdiction',
      jurisdictionIds: ['jur_ch_federal'],
      authorityIds: ['auth_fedlex'],
      documentTypes: ['act'],
      levels: ['federal'],
      limit: 100,
    });

    const filter = bodyOf(search).query.bool.filter;
    expect(filter).toContainEqual({ terms: { 'jurisdiction_ids.keyword': ['jur_ch_federal'] } });
    expect(filter).toContainEqual({ terms: { 'authority_ids.keyword': ['auth_fedlex'] } });
    expect(filter).toContainEqual({ terms: { 'document_type.keyword': ['act'] } });
    expect(filter).toContainEqual({ terms: { 'level.keyword': ['federal'] } });
  });

  it('applies an EMPTY id filter rather than dropping it — caught by the integration layer', async () => {
    // Guarding on `.length` here treats "a filter was asked for and nothing
    // survived validation" as "no filter was asked for", and the scope silently
    // widens to the whole corpus. A caller asking about one unrecognized
    // jurisdiction then gets corpus-wide totals under a response that echoes
    // their narrow scope — a coverage answer to a question nobody asked.
    //
    // The service-level test for this passed while the bug was live, because it
    // asserted what the service PASSED, not what the adapter DID with it. Only
    // the real index showed it.
    const search = vi.fn().mockResolvedValue(emptyResponse);

    await makeAdapter(search).countCoverage({
      dimension: 'jurisdiction',
      jurisdictionIds: [],
      limit: 100,
    });

    expect(bodyOf(search).query.bool.filter).toContainEqual({
      terms: { 'jurisdiction_ids.keyword': [] },
    });
  });

  it('applies no id filter at all when none was requested', async () => {
    const search = vi.fn().mockResolvedValue(emptyResponse);

    await makeAdapter(search).countCoverage({ dimension: 'jurisdiction', limit: 100 });

    expect(bodyOf(search).query.bool.filter).toEqual([{ term: { record_kind: 'legal_document' } }]);
  });

  it('asks for an exact hit total, so the corpus size is not capped at 10k', async () => {
    const search = vi.fn().mockResolvedValue(emptyResponse);

    await makeAdapter(search).countCoverage({ dimension: 'jurisdiction', limit: 100 });

    expect(bodyOf(search).track_total_hits).toBe(true);
  });

  it('requests the freshness, assumed-in-force and provenance sub-aggregations', async () => {
    const search = vi.fn().mockResolvedValue(emptyResponse);

    await makeAdapter(search).countCoverage({ dimension: 'jurisdiction', limit: 100 });

    const aggs = bodyOf(search).aggs.by_dimension.aggs;
    expect(aggs.last_processed).toEqual({ max: { field: 'processed_at' } });
    expect(aggs.no_repeal_date).toEqual({ missing: { field: 'in_force_until' } });
    expect(aggs.source_versions.terms.field).toBe('source_version_id');
    expect(aggs.source_version_count).toEqual({ cardinality: { field: 'source_version_id' } });
    // Documents carrying no value for the grouping field appear in no bucket.
    expect(bodyOf(search).aggs.missing_key).toEqual({
      missing: { field: 'jurisdiction_ids.keyword' },
    });
  });

  it('maps buckets into the port shape', async () => {
    const search = vi.fn().mockResolvedValue({
      body: {
        hits: { total: { value: 73 } },
        aggregations: {
          by_dimension: {
            buckets: [
              {
                key: 'jur_ch_federal',
                doc_count: 73,
                last_processed: { value_as_string: '2026-07-18T09:12:00.000Z' },
                no_repeal_date: { doc_count: 70 },
                source_versions: { buckets: [{ key: 'sv_a' }, { key: 'sv_b' }] },
                source_version_count: { value: 2 },
              },
            ],
          },
          missing_key: { doc_count: 4 },
        },
      },
    });

    const result = await makeAdapter(search).countCoverage({
      dimension: 'jurisdiction',
      limit: 100,
    });

    expect(result.totalDocuments).toBe(73);
    expect(result.documentsWithoutGroupKey).toBe(4);
    expect(result.buckets).toEqual([
      {
        key: 'jur_ch_federal',
        documents: 73,
        lastProcessedAt: '2026-07-18T09:12:00.000Z',
        documentsWithoutRepealDate: 70,
        sourceVersionIds: ['sv_a', 'sv_b'],
        sourceVersionCount: 2,
      },
    ]);
  });

  describe('when the index has drifted from the canonical mapping', () => {
    it('fails loudly rather than reporting an empty corpus', async () => {
      // Reproduced against the local stack on 2026-07-19: `documents-read` is
      // dynamically mapped, so `source_version_id` is `text` and the
      // aggregation is rejected.
      //
      // The alternative — softening the query until the drifted index accepts
      // it — returns EMPTY BUCKETS, which this endpoint would report as "the
      // corpus holds nothing". An agent would relay that as a refusal, and a
      // false refusal is a lie the caller cannot detect. An error is one they can.
      const search = vi
        .fn()
        .mockRejectedValue(
          new Error(
            'search_phase_execution_exception: [illegal_argument_exception] Reason: Text ' +
              'fields are not optimised for operations that require per-document field data ' +
              'like aggregations and sorting, so these operations are disabled by default.',
          ),
        );

      await expect(
        makeAdapter(search).countCoverage({ dimension: 'jurisdiction', limit: 100 }),
      ).rejects.toBeInstanceOf(ServiceUnavailableException);
    });

    it('names the drift as the cause, so the operator is not left guessing', async () => {
      const search = vi
        .fn()
        .mockRejectedValue(new Error('illegal_argument_exception: fielddata is disabled'));

      await expect(
        makeAdapter(search).countCoverage({ dimension: 'jurisdiction', limit: 100 }),
      ).rejects.toThrow(/drifted from the canonical mapping/);
    });

    it('does not swallow unrelated failures', async () => {
      // A connection error is not a mapping problem and must surface as itself.
      const search = vi.fn().mockRejectedValue(new Error('connect ECONNREFUSED'));

      await expect(
        makeAdapter(search).countCoverage({ dimension: 'jurisdiction', limit: 100 }),
      ).rejects.toThrow(/ECONNREFUSED/);
    });
  });
});
