import { Inject, Injectable, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import type { Client } from '@opensearch-project/opensearch';
import { OPENSEARCH_CLIENT } from '../../core/opensearch/client';
import type {
  ProjectionHistoryEntry,
  ProjectionHistoryPage,
  ProjectionHistoryQuery,
  ProjectionHistoryStats,
  ProjectionRepository,
  SearchProjectionDocument,
} from './projections.repository';

@Injectable()
export class ProjectionOpenSearchAdapter implements ProjectionRepository {
  private readonly logger = new Logger(ProjectionOpenSearchAdapter.name);
  private readonly indexDocumentsWrite: string;
  private readonly indexProjectionHistory: string;

  constructor(
    @Inject(OPENSEARCH_CLIENT)
    private readonly client: Client,
    @Inject(ConfigService)
    config: ConfigService,
  ) {
    this.indexDocumentsWrite =
      config.get<string>('opensearch.documentsWriteAlias') ?? 'documents-write';
    this.indexProjectionHistory =
      config.get<string>('opensearch.projectionHistoryIndex') ?? 'projection-history';
  }

  async hasHistoryEvent(eventId: string): Promise<boolean> {
    try {
      const result = await this.client.exists({
        index: this.indexProjectionHistory,
        id: eventId,
      });
      return Boolean(result.body);
    } catch {
      return false;
    }
  }

  async getLatestRevision(documentId: string): Promise<number | null> {
    try {
      const response = await this.client.search({
        index: this.indexProjectionHistory,
        body: {
          size: 1,
          query: {
            term: { 'document_id.keyword': documentId },
          },
          sort: [{ document_revision: { order: 'desc' } }],
        },
      });
      const hit = response.body.hits?.hits?.[0]?._source as
        | { document_revision?: number }
        | undefined;
      return typeof hit?.document_revision === 'number' ? hit.document_revision : null;
    } catch (err) {
      this.logger.warn(`Failed to read latest revision for ${documentId}`, err as Error);
      return null;
    }
  }

  async upsertProjection(document: SearchProjectionDocument): Promise<void> {
    await this.client.index({
      index: this.indexDocumentsWrite,
      id: document.document_id,
      body: document,
      refresh: 'wait_for',
    });
  }

  async deleteProjection(documentId: string): Promise<void> {
    try {
      await this.client.delete({
        index: this.indexDocumentsWrite,
        id: documentId,
        refresh: 'wait_for',
      });
    } catch (err) {
      // Ignore missing index/document errors to keep event handling idempotent.
      const message = String((err as { message?: string }).message ?? '');
      if (message.includes('index_not_found_exception') || message.includes('not_found')) {
        return;
      }
      throw err;
    }
  }

  async appendHistory(entry: ProjectionHistoryEntry): Promise<void> {
    try {
      await this.client.create({
        index: this.indexProjectionHistory,
        id: entry.eventId,
        body: {
          event_id: entry.eventId,
          event_type: entry.eventType,
          document_id: entry.documentId,
          document_revision: entry.documentRevision,
          processing_manifest_id: entry.processingManifestId,
          run_id: entry.runId,
          occurred_at: entry.occurredAt,
          status: entry.status,
          notes: entry.notes,
        },
        refresh: 'wait_for',
      });
    } catch (err) {
      const message = String((err as { message?: string }).message ?? '');
      if (message.includes('version_conflict_engine_exception')) {
        return;
      }
      throw err;
    }
  }

  async queryHistory(query: ProjectionHistoryQuery): Promise<ProjectionHistoryPage> {
    const limit = query.limit ?? 50;
    const offset = query.offset ?? 0;
    const filters: Array<Record<string, unknown>> = [];

    if (query.documentId) {
      filters.push({ term: { 'document_id.keyword': query.documentId } });
    }
    if (query.runId) {
      filters.push({ term: { 'run_id.keyword': query.runId } });
    }
    if (query.status) {
      filters.push({ term: { 'status.keyword': query.status } });
    }

    const body: Record<string, unknown> = {
      size: limit,
      from: offset,
      sort: [{ occurred_at: { order: 'desc' } }],
      track_total_hits: true,
    };

    if (filters.length > 0) {
      body.query = { bool: { filter: filters } };
    } else {
      body.query = { match_all: {} };
    }

    try {
      const response = await this.client.search({
        index: this.indexProjectionHistory,
        body,
      });

      const hits = response.body.hits?.hits ?? [];
      const total =
        typeof response.body.hits?.total === 'object'
          ? (response.body.hits.total as { value: number }).value
          : ((response.body.hits?.total as number) ?? 0);

      const data: ProjectionHistoryEntry[] = (
        hits as Array<{ _source: Record<string, unknown> }>
      ).map((hit) => ({
        eventId: hit._source.event_id as string,
        eventType: hit._source.event_type as ProjectionHistoryEntry['eventType'],
        documentId: hit._source.document_id as string,
        documentRevision: hit._source.document_revision as number,
        processingManifestId: hit._source.processing_manifest_id as string,
        runId: hit._source.run_id as string,
        occurredAt: hit._source.occurred_at as string,
        status: hit._source.status as ProjectionHistoryEntry['status'],
        notes: hit._source.notes as string | undefined,
      }));

      return { data, total, limit, offset };
    } catch (err) {
      this.logger.warn('Failed to query projection history', err as Error);
      return { data: [], total: 0, limit, offset };
    }
  }

  async getHistoryStats(): Promise<ProjectionHistoryStats> {
    try {
      const response = await this.client.search({
        index: this.indexProjectionHistory,
        body: {
          size: 0,
          track_total_hits: true,
          aggs: {
            by_status: {
              terms: { field: 'status.keyword', size: 10 },
            },
            unique_documents: {
              cardinality: { field: 'document_id.keyword' },
            },
          },
        },
      });

      const totalEvents =
        typeof response.body.hits?.total === 'object'
          ? (response.body.hits.total as { value: number }).value
          : ((response.body.hits?.total as number) ?? 0);

      // biome-ignore lint/suspicious/noExplicitAny: OpenSearch agg types are loose
      const aggs = response.body.aggregations as Record<string, any> | undefined;

      const statusBuckets = (aggs?.by_status?.buckets ?? []) as Array<{
        key: string;
        doc_count: number;
      }>;

      const statusCounts: Record<string, number> = {};
      for (const bucket of statusBuckets) {
        statusCounts[bucket.key] = bucket.doc_count;
      }

      const uniqueDocuments = (aggs?.unique_documents?.value as number) ?? 0;

      return {
        totalEvents,
        applied: statusCounts.applied ?? 0,
        stale: statusCounts.stale ?? 0,
        ignoredDuplicate: statusCounts.ignored_duplicate ?? 0,
        uniqueDocuments,
      };
    } catch (err) {
      this.logger.warn('Failed to get projection history stats', err as Error);
      return {
        totalEvents: 0,
        applied: 0,
        stale: 0,
        ignoredDuplicate: 0,
        uniqueDocuments: 0,
      };
    }
  }
}
