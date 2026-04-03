import { Inject, Injectable, Logger } from '@nestjs/common';
import type {
  DocumentProcessedEventDto,
  DocumentWithdrawnEventDto,
} from './dto/projection-events.dto';
import {
  PROJECTION_REPOSITORY,
  type ProjectionHistoryEntry,
  type ProjectionHistoryPage,
  type ProjectionHistoryQuery,
  type ProjectionHistoryStats,
  type ProjectionRepository,
  type SearchProjectionDocument,
} from './projections.repository';

export type ProjectionApplyResult = {
  eventId: string;
  status: 'applied' | 'stale' | 'ignored_duplicate';
};

@Injectable()
export class ProjectionsService {
  private readonly logger = new Logger(ProjectionsService.name);

  constructor(
    @Inject(PROJECTION_REPOSITORY)
    private readonly repository: ProjectionRepository,
  ) {}

  async applyDocumentProcessed(event: DocumentProcessedEventDto): Promise<ProjectionApplyResult> {
    if (await this.repository.hasHistoryEvent(event.event_id)) {
      return { eventId: event.event_id, status: 'ignored_duplicate' };
    }

    const latestRevision = await this.repository.getLatestRevision(event.payload.document_id);
    if (latestRevision !== null && event.payload.document_revision < latestRevision) {
      await this.appendHistory(event, 'stale', `latest revision is ${latestRevision}`);
      return { eventId: event.event_id, status: 'stale' };
    }

    const projection = this.buildProjection(event);
    await this.repository.upsertProjection(projection);
    await this.appendHistory(event, 'applied');
    return { eventId: event.event_id, status: 'applied' };
  }

  async applyDocumentWithdrawn(event: DocumentWithdrawnEventDto): Promise<ProjectionApplyResult> {
    if (await this.repository.hasHistoryEvent(event.event_id)) {
      return { eventId: event.event_id, status: 'ignored_duplicate' };
    }

    const latestRevision = await this.repository.getLatestRevision(event.payload.document_id);
    if (latestRevision !== null && event.payload.document_revision < latestRevision) {
      await this.appendWithdrawnHistory(event, 'stale', `latest revision is ${latestRevision}`);
      return { eventId: event.event_id, status: 'stale' };
    }

    // Current behavior: both `remove` and `hide` result in de-indexing from search surfaces.
    await this.repository.deleteProjection(event.payload.document_id);
    await this.appendWithdrawnHistory(event, 'applied');
    return { eventId: event.event_id, status: 'applied' };
  }

  async queryHistory(query: ProjectionHistoryQuery): Promise<ProjectionHistoryPage> {
    return this.repository.queryHistory(query);
  }

  async getHistoryStats(): Promise<ProjectionHistoryStats> {
    return this.repository.getHistoryStats();
  }

  private buildProjection(event: DocumentProcessedEventDto): SearchProjectionDocument {
    const provenance = event.payload.provenance;
    return {
      document_id: event.payload.document_id,
      title: `Document ${event.payload.document_id}`,
      sections_count: 0,
      citations_count: 0,
      source_id: provenance.source_id,
      source_version_id: provenance.source_version_id,
      run_id: provenance.run_id,
      processing_manifest_id: event.payload.processing_manifest_id,
      document_revision: event.payload.document_revision,
      lifecycle_status: event.payload.lifecycle_status,
      processed_at: event.occurred_at,
      jurisdiction: this.inferJurisdiction(provenance.corpus_id),
      language: this.inferLanguage(provenance.corpus_id),
      content_preview: event.payload.processing_version,
    };
  }

  private inferJurisdiction(corpusId: string): string | undefined {
    if (corpusId.includes('ch')) return 'CH';
    if (corpusId.includes('at')) return 'AT';
    if (corpusId.includes('de')) return 'DE';
    if (corpusId.includes('li')) return 'LI';
    this.logger.warn(`[contract] unknown_corpus_jurisdiction`, { corpusId });
    return undefined;
  }

  private inferLanguage(corpusId: string): string | undefined {
    if (corpusId.includes('de')) return 'de';
    if (corpusId.includes('fr')) return 'fr';
    if (corpusId.includes('it')) return 'it';
    return undefined;
  }

  private async appendHistory(
    event: DocumentProcessedEventDto,
    status: ProjectionHistoryEntry['status'],
    notes?: string,
  ): Promise<void> {
    await this.repository.appendHistory({
      eventId: event.event_id,
      eventType: event.event_type,
      documentId: event.payload.document_id,
      documentRevision: event.payload.document_revision,
      processingManifestId: event.payload.processing_manifest_id,
      runId: event.payload.provenance.run_id,
      occurredAt: event.occurred_at,
      status,
      notes,
    });
  }

  private async appendWithdrawnHistory(
    event: DocumentWithdrawnEventDto,
    status: ProjectionHistoryEntry['status'],
    notes?: string,
  ): Promise<void> {
    await this.repository.appendHistory({
      eventId: event.event_id,
      eventType: event.event_type,
      documentId: event.payload.document_id,
      documentRevision: event.payload.document_revision,
      processingManifestId: event.payload.processing_manifest_id,
      runId: event.payload.provenance.run_id,
      occurredAt: event.occurred_at,
      status,
      notes,
    });
  }
}
