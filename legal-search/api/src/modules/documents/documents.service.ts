import {
  Inject,
  Injectable,
  Logger,
  NotFoundException,
  ServiceUnavailableException,
} from '@nestjs/common';
import type { SupportedLocale } from '../../core/i18n';
import { DEFAULT_LOCALE } from '../../core/i18n';
import type { WarnFn } from '../../core/types/warn';
import {
  DOCUMENT_INTELLIGENCE_CLIENT,
  type DocumentIntelligenceClient,
  LeanDocumentUnavailableError,
} from '../../lib/document-intelligence/document-intelligence.client';
import { resolveAgainstTargets } from '../citations/citation-resolution';
import {
  CITATIONS_REPOSITORY,
  type CitationsRepository,
  type CitationTarget,
} from '../citations/citations.repository';
import { DOCUMENTS_REPOSITORY, type DocumentsRepository } from './documents.repository';
import type { CitationEntity } from './entities/document.entities';
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
    @Inject(CITATIONS_REPOSITORY)
    private readonly citations: CitationsRepository,
  ) {
    this.warn = (event, meta) => this.logger.warn(`[contract] ${event}`, meta);
  }

  async getDetail(id: string, locale: SupportedLocale = DEFAULT_LOCALE, correlationId?: string) {
    let doc = await this.repository.getById(id);
    if (!doc) throw new NotFoundException(`Document ${id} not found`);

    const [sections, indexedCitations] = await Promise.all([
      this.repository.getSections(id),
      this.repository.getCitations(id),
    ]);
    const citations = await this.joinUnresolvedCitations(indexedCitations);

    // The projection already indexes the body as `content`, so the Document
    // Service is a fallback for the one case the index cannot cover: a
    // document projected without a body. Previously this asked for a lean
    // document only when `content_docling` was ALSO absent and then stored the
    // reply under `content_docling` — a field nothing indexes and nothing
    // produces — so every document that HAD a body skipped the fetch and then
    // had its body dropped by the mapper. The body never reached the client.
    if (!hasBodyText(doc.content)) {
      const lean = await this.readLeanBodySource(id, correlationId);
      const body = extractLeanBodyText(lean);
      if (body !== undefined) {
        doc = { ...doc, content: body };
      }
    }

    return mapDocumentToDetailView(doc, sections, citations, locale, this.warn);
  }

  /**
   * Read the body fallback, and refuse rather than answer "no body" on a guess.
   *
   * `null` is the upstream saying the document has no canonical row, or the
   * integration being switched off. Either way the detail view renders without
   * a body and omits the content tab — an honest "we hold no text for this".
   *
   * A *failed* read is not that. Returning the document anyway would publish
   * the same page and make the failure indistinguishable from the absence,
   * which is what #984 is: the 503 #983 introduced to say "do not believe this
   * absence" arrived here and became `undefined`. So it becomes a 503 of our
   * own — `use-detail.ts` already branches 404 (not found) from any other
   * non-200 (failed to load), so the distinction has a consumer at the surface.
   *
   * The narrower answer — serve the page with the body marked unavailable —
   * needs a field on the detail view and therefore `document-detail.mapper.ts`,
   * which is #1039's lane. Until then a refusal is the only channel that does
   * not lie, and it fires only for a document the index has no body for AND
   * whose upstream read actually broke.
   */
  private async readLeanBodySource(id: string, correlationId?: string): Promise<unknown | null> {
    try {
      return await this.documentIntelligence.fetchLeanDocument(id, { correlationId });
    } catch (err) {
      if (err instanceof LeanDocumentUnavailableError) {
        this.logger.warn('document_body_read_unavailable', {
          document_id: id,
          upstream_status: err.status,
          correlation_id: correlationId,
        });
        throw new ServiceUnavailableException(
          `Document ${id} has no indexed body and its canonical text could not be read ` +
            '(document-intelligence did not answer). This is a failed read, not an empty ' +
            'document — retry rather than concluding the document has no text.',
        );
      }
      throw err;
    }
  }

  async getSections(documentId: string) {
    return this.repository.getSections(documentId);
  }

  /**
   * Join citations that carry a canonical key but no `target_document_id`.
   *
   * `target_document_id` is a WRITE-time denormalization: it is null whenever
   * the cited norm had not yet been projected when the citing document was.
   * Project the BV after a law that cites it and that edge is missing forever,
   * with no error anywhere — which is why `citation-graph-index.mapping.ts`
   * calls `normalized_reference` the only order-independent way to traverse.
   *
   * Document detail nonetheless built its reference links from
   * `target_document_id` alone (`document-detail.mapper.ts`), so every
   * out-of-order pair rendered as an unlinked string. This closes that at read
   * time, using the SAME rule the write path and `/v1/citations/resolve` use —
   * so an ambiguous key stays unlinked here too rather than acquiring an href
   * to an arbitrary norm.
   *
   * A failed lookup leaves the rows exactly as indexed: unknown is not an
   * empty corpus.
   */
  private async joinUnresolvedCitations(citations: CitationEntity[]): Promise<CitationEntity[]> {
    const pending = citations.filter((c) => !c.target_document_id && c.normalized_reference);
    if (pending.length === 0) return citations;

    let candidates: Map<string, CitationTarget[]>;
    try {
      candidates = await this.citations.findTargetsByKeys([
        ...new Set(pending.map((c) => c.normalized_reference as string)),
      ]);
    } catch (err) {
      this.logger.warn('citation_read_join_failed', err as Error);
      return citations;
    }

    return citations.map((c) => {
      if (c.target_document_id || !c.normalized_reference) return c;
      const resolution = resolveAgainstTargets(
        c.normalized_reference,
        candidates.get(c.normalized_reference) ?? [],
      );
      if (resolution.status === 'unresolved') return c;
      return {
        ...c,
        target_document_id: resolution.target.document_id,
        target_title: c.target_title ?? resolution.target.title,
        target_document_type: c.target_document_type ?? resolution.target.document_type,
        resolved: true,
      };
    });
  }

  async getCitedBy(documentId: string) {
    return this.repository.getCitedBy(documentId);
  }
}
