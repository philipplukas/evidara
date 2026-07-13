import type { Client } from '@opensearch-project/opensearch';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MetricsService } from './metrics.service';
import { SearchIndexProbe } from './search-index.probe';

const config = {
  get: (key: string) =>
    key === 'opensearch.documentsReadAlias' ? 'documents-read' : 'documents-write',
} as never;

function buildProbe(client: Partial<Client>) {
  const metrics = new MetricsService();
  const probe = new SearchIndexProbe(client as Client, config, metrics);
  return { metrics, probe };
}

async function gauge(
  metrics: MetricsService,
  name: string,
  labels: Record<string, string> = {},
): Promise<number | undefined> {
  const metric = (await metrics.registry.getMetricsAsJSON()).find((m) => m.name === name) as
    | { values: { value: number; labels: Record<string, string> }[] }
    | undefined;
  return metric?.values.find((sample) =>
    Object.entries(labels).every(([key, value]) => sample.labels[key] === value),
  )?.value;
}

describe('SearchIndexProbe', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('reports a healthy index when both aliases resolve to the same physical index', async () => {
    const { metrics, probe } = buildProbe({
      indices: {
        getAlias: vi.fn().mockResolvedValue({ body: { 'documents-000001': {} } }),
      } as never,
      count: vi.fn().mockResolvedValue({ body: { count: 42 } }),
    });

    await probe.refresh();

    expect(await gauge(metrics, 'legal_search_alias_resolved', { alias: 'documents-read' })).toBe(
      1,
    );
    expect(await gauge(metrics, 'legal_search_alias_resolved', { alias: 'documents-write' })).toBe(
      1,
    );
    expect(await gauge(metrics, 'legal_search_aliases_consistent')).toBe(1);
    expect(await gauge(metrics, 'legal_search_indexed_documents')).toBe(42);
    expect(await gauge(metrics, 'legal_search_index_probe_up')).toBe(1);
  });

  // The #549 outage, exactly: no index, so `documents-read` 404s. Every pod stayed
  // Ready. This gauge is what the page fires on.
  it('reports the read alias as unresolved when OpenSearch 404s it', async () => {
    const notFound = Object.assign(new Error('index_not_found_exception'), { statusCode: 404 });
    const { metrics, probe } = buildProbe({
      indices: { getAlias: vi.fn().mockRejectedValue(notFound) } as never,
      count: vi.fn(),
    });

    await probe.refresh();

    expect(await gauge(metrics, 'legal_search_alias_resolved', { alias: 'documents-read' })).toBe(
      0,
    );
    expect(await gauge(metrics, 'legal_search_aliases_consistent')).toBe(0);
    expect(await gauge(metrics, 'legal_search_indexed_documents')).toBe(0);
    // The cluster answered — it is the index that is missing, not OpenSearch.
    expect(await gauge(metrics, 'legal_search_index_probe_up')).toBe(1);
  });

  // The divergence #551 was about: projections write to one index, search reads another.
  it('reports aliases as inconsistent when they point at different physical indices', async () => {
    const getAlias = vi
      .fn()
      .mockResolvedValueOnce({ body: { 'documents-000001': {} } })
      .mockResolvedValueOnce({ body: { 'documents-000002': {} } });
    const { metrics, probe } = buildProbe({
      indices: { getAlias } as never,
      count: vi.fn().mockResolvedValue({ body: { count: 0 } }),
    });

    await probe.refresh();

    expect(await gauge(metrics, 'legal_search_aliases_consistent')).toBe(0);
    expect(await gauge(metrics, 'legal_search_alias_resolved', { alias: 'documents-read' })).toBe(
      1,
    );
  });

  it('never throws and marks the probe down when the cluster is unreachable', async () => {
    const { metrics, probe } = buildProbe({
      indices: { getAlias: vi.fn().mockRejectedValue(new Error('ECONNREFUSED')) } as never,
      count: vi.fn(),
    });

    await expect(probe.refresh()).resolves.toBeUndefined();

    expect(await gauge(metrics, 'legal_search_index_probe_up')).toBe(0);
    expect(await gauge(metrics, 'legal_search_alias_resolved', { alias: 'documents-read' })).toBe(
      0,
    );
  });
});
