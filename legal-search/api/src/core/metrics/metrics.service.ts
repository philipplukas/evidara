/**
 * Prometheus counters for the legal-search funnel (ADR-0031).
 *
 * Deliberately dependency-free: adapters inject this and call `recordX()`. The
 * OpenSearch-derived gauges live in `SearchIndexProbe`, so instrumenting a code
 * path never drags an OpenSearch client into it.
 *
 * Counters answer "is work flowing"; the probe gauges answer "did the work land".
 * The outage this exists to catch (#553) was invisible to both liveness probes and
 * logs: every pod was Ready while `documents-read` resolved to nothing.
 */
import { Injectable } from '@nestjs/common';
import { Counter, collectDefaultMetrics, Registry } from 'prom-client';

@Injectable()
export class MetricsService {
  readonly registry: Registry;

  /** Every search request that reached the OpenSearch adapter. */
  private readonly searchQueries: Counter;
  /** Searches that came back with `total === 0` (index empty, analyzer broken, bad reindex). */
  private readonly searchZeroHits: Counter;
  /** Searches where the OpenSearch call threw. The adapter swallows these and returns
   *  an empty result, so without this counter a backend outage looks like "no matches". */
  private readonly searchErrors: Counter;
  /** Documents upserted into the write alias by the projection path. */
  private readonly documentsIndexed: Counter;
  /** Documents removed from the write alias (withdrawal projections). */
  private readonly documentsDeleted: Counter;

  constructor() {
    this.registry = new Registry();
    this.registry.setDefaultLabels({ service: 'legal-search-api' });
    collectDefaultMetrics({ register: this.registry });

    this.searchQueries = new Counter({
      name: 'legal_search_search_queries_total',
      help: 'Search queries executed against OpenSearch.',
      registers: [this.registry],
    });
    this.searchZeroHits = new Counter({
      name: 'legal_search_search_queries_zero_hits_total',
      help: 'Search queries that returned zero hits.',
      registers: [this.registry],
    });
    this.searchErrors = new Counter({
      name: 'legal_search_search_errors_total',
      help: 'Search queries where the OpenSearch call failed (degraded to an empty result).',
      registers: [this.registry],
    });
    this.documentsIndexed = new Counter({
      name: 'legal_search_documents_indexed_total',
      help: 'Documents upserted into the OpenSearch write alias by projections.',
      registers: [this.registry],
    });
    this.documentsDeleted = new Counter({
      name: 'legal_search_documents_deleted_total',
      help: 'Documents deleted from the OpenSearch write alias by withdrawal projections.',
      registers: [this.registry],
    });
  }

  recordSearch(totalHits: number): void {
    this.searchQueries.inc();
    if (totalHits === 0) {
      this.searchZeroHits.inc();
    }
  }

  recordSearchError(): void {
    this.searchQueries.inc();
    this.searchZeroHits.inc();
    this.searchErrors.inc();
  }

  recordDocumentIndexed(): void {
    this.documentsIndexed.inc();
  }

  recordDocumentDeleted(): void {
    this.documentsDeleted.inc();
  }
}
