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

/** A body is only a body if it carries text — an empty string is not one. */
function hasBodyText(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0;
}

/**
 * Pull the body text out of a Document Service `/lean` payload.
 *
 * Despite the name and `contracts/api/document-intelligence.openapi.yaml`, the
 * payload is NOT a DoclingDocument: `service/store.py` serialises a canonical
 * row (`full_text`/`body_text`, both `str`), and `service/lean.py` falls back
 * to returning that dict whenever `DoclingDocument.model_validate` rejects it —
 * which it always does, because a canonical row has no Docling fields.
 *
 * `ProjectionsService` reads the same two keys in the same order to build the
 * indexed `content`; keep the two in step so the fallback and the index agree
 * on what the body is.
 */
function extractLeanBodyText(lean: unknown): string | undefined {
  if (!lean || typeof lean !== 'object') return undefined;
  const doc = lean as Record<string, unknown>;
  for (const key of ['body_text', 'full_text']) {
    const value = doc[key];
    if (hasBodyText(value)) return value;
  }
  return undefined;
}

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

    // The projection already indexes the body as `content`, so the Document
    // Service is a fallback for the one case the index cannot cover: a
    // document projected without a body. Previously this asked for a lean
    // document only when `content_docling` was ALSO absent and then stored the
    // reply under `content_docling` — a field nothing indexes and nothing
    // produces — so every document that HAD a body skipped the fetch and then
    // had its body dropped by the mapper. The body never reached the client.
    if (!hasBodyText(doc.content)) {
      const lean = await this.documentIntelligence.fetchLeanDocument(id, { correlationId });
      const body = extractLeanBodyText(lean);
      if (body !== undefined) {
        doc = { ...doc, content: body };
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
