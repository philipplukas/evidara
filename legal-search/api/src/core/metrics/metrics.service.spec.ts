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

  // ── Citation graph (#582) ──
  // An unresolved citation is a broken edge. These counters exist so that a hollow
  // graph is loud rather than invisible — it returns 200s and empty lists otherwise.

  it('separates citations DI could key from the ones it could not', async () => {
    const metrics = new MetricsService();
    metrics.recordCitationsProjected(2, 4);

    const json = await metrics.registry.getMetricsAsJSON();
    const projected = json.find((m) => m.name === 'legal_search_citations_projected_total') as
      | { values: { value: number; labels: { keyed: string } }[] }
      | undefined;

    const keyed = projected?.values.find((v) => v.labels.keyed === 'true')?.value;
    const unkeyed = projected?.values.find((v) => v.labels.keyed === 'false')?.value;
    // A single blended "citations indexed: 6" would look perfectly healthy while
    // two-thirds of the graph's edges quietly do not exist.
    expect(keyed).toBe(2);
    expect(unkeyed).toBe(4);
  });

  it('attributes a resolution failure to its cause', async () => {
    const metrics = new MetricsService();
    metrics.recordCitationResolution(true, null);
    metrics.recordCitationResolution(false, 'not_normalizable');
    metrics.recordCitationResolution(false, 'no_target_in_corpus');

    const json = await metrics.registry.getMetricsAsJSON();
    const resolutions = json.find((m) => m.name === 'legal_search_citation_resolutions_total') as
      | { values: { value: number; labels: { outcome: string } }[] }
      | undefined;

    const byOutcome = Object.fromEntries(
      (resolutions?.values ?? []).map((v) => [v.labels.outcome, v.value]),
    );
    // An extractor gap and a coverage gap need different fixes; one number cannot
    // tell an operator which they have.
    expect(byOutcome).toEqual({
      resolved: 1,
      not_normalizable: 1,
      no_target_in_corpus: 1,
    });
  });

  it('exposes the corpus-wide resolution rate as a gauge', async () => {
    const metrics = new MetricsService();
    metrics.setCitationResolutionRate(0.3333, 6, 2);

    expect(await counter(metrics, 'legal_search_citation_resolution_rate')).toBeCloseTo(0.3333, 4);
    expect(await counter(metrics, 'legal_search_citations_indexed_count')).toBe(6);
    expect(await counter(metrics, 'legal_search_citations_resolved_count')).toBe(2);
  });

  it('counts citation targets — the graph nodes anything can be cited by', async () => {
    const metrics = new MetricsService();
    metrics.recordCitationTargetsIndexed(3);
    metrics.recordCitationTargetsIndexed(0);

    expect(await counter(metrics, 'legal_search_citation_targets_indexed_total')).toBe(3);
  });
});
