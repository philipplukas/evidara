import { Inject, Injectable, Logger, NotFoundException } from '@nestjs/common';
import type { SupportedLocale } from '../../core/i18n';
import { DEFAULT_LOCALE } from '../../core/i18n';
import type { WarnFn } from '../../core/types/warn';
import {
  DOCUMENT_INTELLIGENCE_CLIENT,
  type DocumentIntelligenceClient,
} from '../../lib/document-intelligence/document-intelligence.client';
import { DOCUMENTS_REPOSITORY, type DocumentsRepository } from './documents.repository';
import { mapDocumentToDetailView } from './mappers/document-detail.mapper';

@Injectable()
export class DocumentsService {
  private readonly logger = new Logger(DocumentsService.name);
  private readonly warn: WarnFn;

  constructor(
    @Inject(DOCUMENTS_REPOSITORY)
    private readonly repository: DocumentsRepository,
    @Inject(DOCUMENT_INTELLIGENCE_CLIENT)
    private readonly documentIntelligence: DocumentIntelligenceClient,
  ) {
    this.warn = (event, meta) => this.logger.warn(`[contract] ${event}`, meta);
  }

  async getDetail(id: string, locale: SupportedLocale = DEFAULT_LOCALE, correlationId?: string) {
    let doc = await this.repository.getById(id);
    if (!doc) throw new NotFoundException(`Document ${id} not found`);

    const [sections, citations] = await Promise.all([
      this.repository.getSections(id),
      this.repository.getCitations(id),
    ]);

    const needsLean =
      (doc.content_docling === undefined || doc.content_docling === null) &&
      (doc.content === undefined || doc.content === null);

    if (needsLean) {
      const lean = await this.documentIntelligence.fetchLeanDocument(id, { correlationId });
      if (lean !== null) {
        doc = { ...doc, content_docling: lean };
      }
    }

    return mapDocumentToDetailView(doc, sections, citations, locale, this.warn);
  }

  async getSections(documentId: string) {
    return this.repository.getSections(documentId);
  }

  async getCitedBy(documentId: string) {
    return this.repository.getCitedBy(documentId);
  }
}
