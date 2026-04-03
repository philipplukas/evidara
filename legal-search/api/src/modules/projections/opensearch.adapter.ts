import { Inject, Injectable, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import type { Client } from '@opensearch-project/opensearch';
import { OPENSEARCH_CLIENT } from '../../core/opensearch/client';
import type {
  ProjectionHistoryEntry,
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
      config.get<string>('opensearch.indexDocumentsWrite') ?? 'documents-write';
    this.indexProjectionHistory =
      config.get<string>('opensearch.indexProjectionHistory') ?? 'projection-history';
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
            term: { document_id: documentId },
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
}
