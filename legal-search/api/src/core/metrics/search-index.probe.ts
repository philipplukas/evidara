/**
 * Scrape-time gauges for the state of the search index (ADR-0031).
 *
 * These are the metrics that would have caught #549/#551 on the day they broke:
 * `documents-read` resolving to nothing, or resolving to a physical index that holds
 * zero documents, while every pod stayed `Running` and `1/1 Ready`.
 *
 * Refreshed on scrape (`MetricsController` awaits `refresh()`), not on a timer: at a
 * 30s scrape interval that is two cheap OpenSearch calls per minute, and there is no
 * background loop to leak on shutdown. Failures are absorbed — a probe must never be
 * the reason `/metrics` returns 500, or the alert on it goes blind at exactly the
 * moment it matters.
 */
import { Inject, Injectable, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import type { Client } from '@opensearch-project/opensearch';
import { Gauge } from 'prom-client';
import { OPENSEARCH_CLIENT } from '../opensearch/client';
import { MetricsService } from './metrics.service';

@Injectable()
export class SearchIndexProbe {
  private readonly logger = new Logger(SearchIndexProbe.name);
  private readonly readAlias: string;
  private readonly writeAlias: string;

  private readonly aliasResolved: Gauge<'alias'>;
  private readonly aliasesConsistent: Gauge;
  private readonly documentCount: Gauge;
  private readonly probeUp: Gauge;

  constructor(
    @Inject(OPENSEARCH_CLIENT) private readonly client: Client,
    @Inject(ConfigService) config: ConfigService,
    @Inject(MetricsService) metrics: MetricsService,
  ) {
    this.readAlias = config.get<string>('opensearch.documentsReadAlias') ?? 'documents-read';
    this.writeAlias = config.get<string>('opensearch.documentsWriteAlias') ?? 'documents-write';

    const registers = [metrics.registry];
    this.aliasResolved = new Gauge({
      name: 'legal_search_alias_resolved',
      help: '1 when the alias resolves to at least one physical index, 0 otherwise.',
      labelNames: ['alias'] as const,
      registers,
    });
    this.aliasesConsistent = new Gauge({
      name: 'legal_search_aliases_consistent',
      help: '1 when the documents read and write aliases resolve to the same physical index(es).',
      registers,
    });
    this.documentCount = new Gauge({
      name: 'legal_search_indexed_documents',
      help: 'Documents currently searchable behind the documents read alias.',
      registers,
    });
    this.probeUp = new Gauge({
      name: 'legal_search_index_probe_up',
      help: '1 when the last index probe reached OpenSearch, 0 when it failed.',
      registers,
    });
  }

  /** Refresh every index gauge. Never throws. */
  async refresh(): Promise<void> {
    try {
      const [readTargets, writeTargets] = await Promise.all([
        this.resolveAlias(this.readAlias),
        this.resolveAlias(this.writeAlias),
      ]);

      this.aliasResolved.set({ alias: this.readAlias }, readTargets.length > 0 ? 1 : 0);
      this.aliasResolved.set({ alias: this.writeAlias }, writeTargets.length > 0 ? 1 : 0);
      this.aliasesConsistent.set(sameTargets(readTargets, writeTargets) ? 1 : 0);
      this.documentCount.set(readTargets.length > 0 ? await this.countDocuments() : 0);
      this.probeUp.set(1);
    } catch (error) {
      // Cluster unreachable: report the probe as down and leave the alias gauges at 0
      // rather than reporting a stale "everything is fine".
      this.logger.warn(
        `Search index probe failed: ${error instanceof Error ? error.message : String(error)}`,
      );
      this.aliasResolved.set({ alias: this.readAlias }, 0);
      this.aliasResolved.set({ alias: this.writeAlias }, 0);
      this.aliasesConsistent.set(0);
      this.documentCount.set(0);
      this.probeUp.set(0);
    }
  }

  /** Physical indices an alias points at; `[]` when it does not resolve (404). */
  private async resolveAlias(alias: string): Promise<string[]> {
    try {
      const response = await this.client.indices.getAlias({ name: alias });
      return Object.keys(response.body ?? {});
    } catch (error) {
      if (statusCodeOf(error) === 404) {
        return [];
      }
      throw error;
    }
  }

  private async countDocuments(): Promise<number> {
    const response = await this.client.count({ index: this.readAlias });
    return typeof response.body?.count === 'number' ? response.body.count : 0;
  }
}

function sameTargets(read: string[], write: string[]): boolean {
  if (read.length === 0 || write.length === 0) {
    return false;
  }
  const readSet = new Set(read);
  return read.length === write.length && write.every((index) => readSet.has(index));
}

function statusCodeOf(error: unknown): number | undefined {
  const status = (error as { statusCode?: unknown; meta?: { statusCode?: unknown } } | null)
    ?.statusCode;
  if (typeof status === 'number') {
    return status;
  }
  const metaStatus = (error as { meta?: { statusCode?: unknown } } | null)?.meta?.statusCode;
  return typeof metaStatus === 'number' ? metaStatus : undefined;
}
