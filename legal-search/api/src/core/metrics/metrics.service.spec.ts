import { describe, expect, it } from 'vitest';
import { MetricsService } from './metrics.service';

async function counter(metrics: MetricsService, name: string): Promise<number> {
  const json = await metrics.registry.getMetricsAsJSON();
  const metric = json.find((m) => m.name === name) as { values: { value: number }[] } | undefined;
  return metric?.values[0]?.value ?? 0;
}

describe('MetricsService', () => {
  it('counts a search with hits as a query but not as a zero-hit query', async () => {
    const metrics = new MetricsService();
    metrics.recordSearch(7);

    expect(await counter(metrics, 'legal_search_search_queries_total')).toBe(1);
    expect(await counter(metrics, 'legal_search_search_queries_zero_hits_total')).toBe(0);
  });

  it('counts a search with no hits in both the query and the zero-hit counter', async () => {
    const metrics = new MetricsService();
    metrics.recordSearch(0);

    expect(await counter(metrics, 'legal_search_search_queries_total')).toBe(1);
    expect(await counter(metrics, 'legal_search_search_queries_zero_hits_total')).toBe(1);
  });

  // A failed backend call is served to the user as an empty result page, so it must
  // count as a zero-hit query (it is one, from the user's side) *and* raise the error
  // counter that tells an operator which of the two it was.
  it('counts a backend failure as a zero-hit query and an error', async () => {
    const metrics = new MetricsService();
    metrics.recordSearchError();

    expect(await counter(metrics, 'legal_search_search_queries_total')).toBe(1);
    expect(await counter(metrics, 'legal_search_search_queries_zero_hits_total')).toBe(1);
    expect(await counter(metrics, 'legal_search_search_errors_total')).toBe(1);
  });

  it('counts indexed and deleted documents', async () => {
    const metrics = new MetricsService();
    metrics.recordDocumentIndexed();
    metrics.recordDocumentIndexed();
    metrics.recordDocumentDeleted();

    expect(await counter(metrics, 'legal_search_documents_indexed_total')).toBe(2);
    expect(await counter(metrics, 'legal_search_documents_deleted_total')).toBe(1);
  });
});
