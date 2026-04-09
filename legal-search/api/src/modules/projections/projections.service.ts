import { Inject, Injectable, Logger } from '@nestjs/common';
import {
  DOCUMENT_INTELLIGENCE_CLIENT,
  type DocumentIntelligenceClient,
} from '../../lib/document-intelligence/document-intelligence.client';
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
    @Inject(DOCUMENT_INTELLIGENCE_CLIENT)
    private readonly documentIntelligence: DocumentIntelligenceClient,
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

    const leanDocument = await this.documentIntelligence.fetchLeanDocument(
      event.payload.document_id,
      {
        correlationId: event.correlation_id,
        documentRevision: event.payload.document_revision,
      },
    );
    if (leanDocument === null) {
      // Keep projection flow non-blocking when DI read API is unavailable.
      this.logger.warn('projection_enrichment_unavailable_fallback', {
        document_id: event.payload.document_id,
        correlation_id: event.correlation_id,
      });
    }
    const projection = this.buildProjection(event, leanDocument);
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

  private buildProjection(
    event: DocumentProcessedEventDto,
    leanDocument: unknown | null,
  ): SearchProjectionDocument {
    const provenance = event.payload.provenance;
    const extracted = this.extractLeanDocumentFields(leanDocument);
    const title = extracted.title ?? `Document ${event.payload.document_id}`;
    const preview = extracted.previewText ?? event.payload.processing_version;
    return {
      document_id: event.payload.document_id,
      title,
      authority_name: event.payload.authority_name,
      official_citation: extracted.officialCitation,
      is_official: event.payload.is_official,
      sections_count: extracted.sectionsCount,
      citations_count: extracted.citationsCount,
      source_id: provenance.source_id,
      source_version_id: provenance.source_version_id,
      run_id: provenance.run_id,
      processing_manifest_id: event.payload.processing_manifest_id,
      document_revision: event.payload.document_revision,
      lifecycle_status: event.payload.lifecycle_status,
      processed_at: event.occurred_at,
      jurisdiction: this.inferJurisdiction(provenance.corpus_id),
      language: extracted.language ?? this.inferLanguage(provenance.corpus_id),
      content_preview: preview,
    };
  }

  private extractLeanDocumentFields(leanDocument: unknown): {
    title?: string;
    language?: string;
    officialCitation?: string;
    previewText?: string;
    sectionsCount: number;
    citationsCount: number;
  } {
    if (!leanDocument || typeof leanDocument !== 'object') {
      return { sectionsCount: 0, citationsCount: 0 };
    }
    const doc = leanDocument as Record<string, unknown>;
    const title = typeof doc.title === 'string' && doc.title.trim() ? doc.title.trim() : undefined;
    const language =
      typeof doc.language === 'string' && doc.language.trim() ? doc.language.trim() : undefined;
    const officialCitation = this.firstNestedString(doc, [
      ['metadata', 'official_citation'],
      ['official_citation'],
    ]);
    const sectionCandidates = [doc.sections, doc.document_sections, doc.body_sections];
    const citationCandidates = [doc.citations, doc.document_citations];
    const textCandidates = [doc.content_text, doc.text, doc.summary];
    const sectionsCount = this.countArrayLike(sectionCandidates);
    const citationsCount = this.countArrayLike(citationCandidates);
    const previewText = this.firstString(textCandidates);
    return { title, language, officialCitation, previewText, sectionsCount, citationsCount };
  }

  private countArrayLike(values: unknown[]): number {
    for (const value of values) {
      if (Array.isArray(value)) {
        return value.length;
      }
    }
    return 0;
  }

  private firstString(values: unknown[]): string | undefined {
    for (const value of values) {
      if (typeof value === 'string' && value.trim()) {
        return value.trim();
      }
    }
    return undefined;
  }

  private firstNestedString(
    source: Record<string, unknown>,
    paths: string[][],
  ): string | undefined {
    for (const path of paths) {
      let current: unknown = source;
      for (const key of path) {
        if (!current || typeof current !== 'object') {
          current = undefined;
          break;
        }
        current = (current as Record<string, unknown>)[key];
      }
      if (typeof current === 'string' && current.trim()) {
        return current.trim();
      }
    }
    return undefined;
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
