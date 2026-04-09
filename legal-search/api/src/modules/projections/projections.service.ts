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
    const preview =
      extracted.previewText ??
      this.truncateForPreview(extracted.bodyPreviewFallback) ??
      event.payload.processing_version;
    const jurisdiction =
      extracted.jurisdictionFromCanonical ?? this.inferJurisdiction(provenance.corpus_id);
    const projection: SearchProjectionDocument = {
      document_id: event.payload.document_id,
      title,
      sections_count: extracted.sectionsCount,
      citations_count: extracted.citationsCount,
      source_id: provenance.source_id,
      source_version_id: provenance.source_version_id,
      run_id: provenance.run_id,
      processing_manifest_id: event.payload.processing_manifest_id,
      document_revision: event.payload.document_revision,
      lifecycle_status: event.payload.lifecycle_status,
      processed_at: event.occurred_at,
      jurisdiction,
      language: extracted.language ?? this.inferLanguage(provenance.corpus_id),
      content_preview: preview,
    };
    if (extracted.documentType) projection.document_type = extracted.documentType;
    if (extracted.effectiveDate) projection.effective_date = extracted.effectiveDate;
    if (extracted.structuralPath) projection.structural_path = extracted.structuralPath;
    return projection;
  }

  private extractLeanDocumentFields(leanDocument: unknown): {
    title?: string;
    language?: string;
    previewText?: string;
    bodyPreviewFallback?: string;
    sectionsCount: number;
    citationsCount: number;
    documentType?: string;
    effectiveDate?: string;
    structuralPath?: string;
    jurisdictionFromCanonical?: string;
  } {
    if (!leanDocument || typeof leanDocument !== 'object') {
      return { sectionsCount: 0, citationsCount: 0 };
    }
    const doc = leanDocument as Record<string, unknown>;
    const title = typeof doc.title === 'string' && doc.title.trim() ? doc.title.trim() : undefined;
    const language =
      typeof doc.language === 'string' && doc.language.trim() ? doc.language.trim() : undefined;
    const sectionCandidates = [doc.sections, doc.document_sections, doc.body_sections];
    const citationCandidates = [doc.citations, doc.document_citations];
    const extensions = this.asRecord(doc.extensions);
    const citationExt = extensions?.citations;
    const citationCandidatesWithExtensions = [
      ...citationCandidates,
      Array.isArray(citationExt) ? citationExt : undefined,
    ];
    const textCandidates = [doc.content_text, doc.text, doc.summary];
    const sectionsCount = this.countArrayLike(sectionCandidates);
    const citationsCount = this.countArrayLike(citationCandidatesWithExtensions);
    const meta = this.asRecord(doc.metadata);
    const extractedMeta = meta ? this.asRecord(meta.extracted_metadata) : undefined;
    const llmMeta = meta ? this.asRecord(meta.llm_extraction) : undefined;

    const llmPreview =
      llmMeta?.applied === true && typeof llmMeta.summary === 'string' && llmMeta.summary.trim()
        ? (llmMeta.summary as string).trim()
        : undefined;
    const previewText =
      this.firstString(textCandidates) ??
      (llmPreview && !llmPreview.startsWith('extractor_failed:') ? llmPreview : undefined);

    const bodyPreviewFallback =
      typeof doc.body_text === 'string' && doc.body_text.trim()
        ? doc.body_text
        : typeof doc.full_text === 'string' && doc.full_text.trim()
          ? doc.full_text
          : undefined;

    const documentType =
      typeof doc.document_type === 'string' && doc.document_type.trim()
        ? doc.document_type.trim()
        : undefined;
    const effectiveDate =
      typeof doc.effective_date === 'string' && doc.effective_date.trim()
        ? doc.effective_date.trim()
        : undefined;
    const structuralPath = this.firstString([
      typeof doc.structural_path === 'string' ? doc.structural_path : undefined,
      extractedMeta && typeof extractedMeta.structural_path === 'string'
        ? extractedMeta.structural_path
        : undefined,
      extractedMeta && typeof extractedMeta.path === 'string' ? extractedMeta.path : undefined,
    ]);
    const jurisdictionFromCanonical =
      typeof doc.jurisdiction_id === 'string' && doc.jurisdiction_id.trim()
        ? this.inferJurisdictionFromCanonicalId(doc.jurisdiction_id.trim())
        : undefined;

    return {
      title,
      language,
      previewText,
      bodyPreviewFallback,
      sectionsCount,
      citationsCount,
      documentType,
      effectiveDate,
      structuralPath,
      jurisdictionFromCanonical,
    };
  }

  private truncateForPreview(text: string | undefined, maxChars = 400): string | undefined {
    if (!text) return undefined;
    const t = text.trim();
    if (!t) return undefined;
    if (t.length <= maxChars) return t;
    return `${t.slice(0, maxChars - 1)}…`;
  }

  private asRecord(value: unknown): Record<string, unknown> | undefined {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return undefined;
    return value as Record<string, unknown>;
  }

  /** Map canonical `jurisdiction_id` (e.g. ch_zh) to facet code CH|AT|DE|LI. */
  private inferJurisdictionFromCanonicalId(jurisdictionId: string): string | undefined {
    const prefix = jurisdictionId.split('_')[0]?.toUpperCase();
    if (prefix === 'CH' || prefix === 'AT' || prefix === 'DE' || prefix === 'LI') {
      return prefix;
    }
    return undefined;
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
