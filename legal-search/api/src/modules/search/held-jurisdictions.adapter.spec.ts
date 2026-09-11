/**
 * The holdings aggregation behind jurisdiction-aware refusal (#986).
 *
 * Kept in its own file rather than appended to `opensearch.adapter.spec.ts`
 * because it is the only test in this surface whose subject is *coverage*
 * rather than retrieval.
 */
import type { ConfigService } from '@nestjs/config';
import { describe, expect, it, vi } from 'vitest';
import { MetricsService } from '../../core/metrics/metrics.service';
import { SearchOpenSearchAdapter } from './opensearch.adapter';
import { SearchBackendUnavailableError } from './search.errors';

const CONFIG = {
  get: (key: string) => (key === 'opensearch.documentsReadAlias' ? 'documents-read-test' : null),
} as ConfigService;

describe('SearchOpenSearchAdapter.getHeldJurisdictionIds (#986)', () => {
  it('aggregates the jurisdictions the index holds, over the `.keyword` sub-field', async () => {
    const search = vi.fn().mockResolvedValue({
      body: {
        hits: { total: { value: 0 }, hits: [] },
        aggregations: {
          held_jurisdictions: {
            buckets: [
              { key: 'jur_ch_zh', doc_count: 889 },
              { key: 'jur_ch_federal', doc_count: 3 },
            ],
          },
        },
      },
    });

    const adapter = new SearchOpenSearchAdapter({ search } as never, CONFIG, new MetricsService());

    expect(await adapter.getHeldJurisdictionIds()).toEqual(['jur_ch_zh', 'jur_ch_federal']);

    const body = (
      search.mock.calls[0][0] as {
        body: {
          size: number;
          aggs: { held_jurisdictions: { terms: { field: string; size: number } } };
        };
      }
    ).body;
    expect(body.size).toBe(0);
    // Same field and sub-field `search()` filters on, so the ids compared
    // against the query cannot come from a different field than the ids
    // filtered with.
    expect(body.aggs.held_jurisdictions.terms.field).toBe('jurisdiction_ids.keyword');
    // The seed carries 2,169 jurisdictions. A bucket ceiling below that would
    // truncate the holdings list, and everything truncated off it would read as
    // "not held" — a false refusal manufactured by a default parameter.
    expect(body.aggs.held_jurisdictions.terms.size).toBeGreaterThan(2169);
  });

  it('rejects rather than resolving empty when the aggregation cannot run', async () => {
    // Same contract as `search` (#551): resolving `[]` here would be read as
    // "the corpus holds nothing" by anything that trusted it.
    const err = new Error('index_not_found_exception');
    Object.assign(err, {
      meta: { statusCode: 404, body: { error: { type: 'index_not_found_exception' } } },
    });
    const search = vi.fn().mockRejectedValue(err);
    const adapter = new SearchOpenSearchAdapter({ search } as never, CONFIG, new MetricsService());

    await expect(adapter.getHeldJurisdictionIds()).rejects.toThrow(SearchBackendUnavailableError);
  });
});
