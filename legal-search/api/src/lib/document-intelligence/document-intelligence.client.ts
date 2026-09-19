import { Injectable, Logger } from '@nestjs/common';
// biome-ignore lint/style/useImportType: ConfigService is injected by Nest at runtime
import { ConfigService } from '@nestjs/config';
import { DocumentIntelligenceHttpError } from './document-intelligence-mutator';
import { getDocumentLean } from './generated/api';

export const DOCUMENT_INTELLIGENCE_CLIENT = Symbol('DOCUMENT_INTELLIGENCE_CLIENT');

/**
 * The lean read did not happen — the upstream was asked and did not answer, or
 * answered with something that is not a document.
 *
 * This is NOT "the document has no canonical row": `fetchLeanDocument` returns
 * `null` for that, and the two must stay distinguishable. #983 made
 * document-intelligence raise `PublishedSectionsUnavailable` and answer **503**
 * rather than an empty body, specifically so a caller could tell a broken read
 * from a genuine absence. This client used to catch that 503 and return `null`,
 * which is the same value it returns for 404 — the refusal died one hop after
 * it was issued (#984).
 */
export class LeanDocumentUnavailableError extends Error {
  readonly documentId: string;
  /** Upstream HTTP status, or `null` when the request never produced one. */
  readonly status: number | null;

  constructor(documentId: string, status: number | null, message: string) {
    super(message);
    this.name = 'LeanDocumentUnavailableError';
    this.documentId = documentId;
    this.status = status;
  }
}

export interface DocumentIntelligenceClient {
  /**
   * Fetches lean canonical JSON for the document.
   *
   * Three outcomes, deliberately not two:
   * - the payload, when the upstream answered 200;
   * - `null` when the document genuinely has no canonical row (404), or the
   *   integration is switched off (`DOCUMENT_INTELLIGENCE_BASE_URL` unset) —
   *   a deployment choice, not a failed read;
   * - throws {@link LeanDocumentUnavailableError} when the read itself failed:
   *   5xx, a transport error, a timeout, or any status other than 200/404.
   *
   * Callers must branch on the two. Collapsing them back into one value is
   * #984, and it is what made a 503 render as "no such document".
   */
  fetchLeanDocument(
    documentId: string,
    options?: { correlationId?: string; documentRevision?: number },
  ): Promise<unknown | null>;
}

@Injectable()
export class NoopDocumentIntelligenceClient implements DocumentIntelligenceClient {
  fetchLeanDocument(): Promise<null> {
    return Promise.resolve(null);
  }
}

@Injectable()
export class HttpDocumentIntelligenceClient implements DocumentIntelligenceClient {
  private readonly logger = new Logger(HttpDocumentIntelligenceClient.name);

  constructor(private readonly config: ConfigService) {}

  async fetchLeanDocument(
    documentId: string,
    options?: { correlationId?: string; documentRevision?: number },
  ): Promise<unknown | null> {
    const baseUrl = this.config.get<string>('documentIntelligence.baseUrl') ?? '';
    if (!baseUrl) {
      return null;
    }

    const headers: Record<string, string> = {};
    if (options?.correlationId) {
      headers['X-Correlation-Id'] = options.correlationId;
    }

    let res: Awaited<ReturnType<typeof getDocumentLean>>;
    try {
      res = await getDocumentLean(
        documentId,
        options?.documentRevision !== undefined
          ? { document_revision: options.documentRevision }
          : undefined,
        { headers },
      );
    } catch (err) {
      if (err instanceof Error && err.message === 'DOCUMENT_INTELLIGENCE_BASE_URL is not set') {
        return null;
      }
      if (err instanceof DocumentIntelligenceHttpError) {
        this.logger.warn('document_intelligence_lean_http_error', {
          documentId,
          status: err.status,
          message: err.message,
        });
        throw new LeanDocumentUnavailableError(documentId, err.status, err.message);
      }
      const message = err instanceof Error ? err.message : String(err);
      this.logger.warn('document_intelligence_lean_failed', { documentId, error: message });
      throw new LeanDocumentUnavailableError(
        documentId,
        null,
        `Document Service lean read failed: ${message}`,
      );
    }

    if (res.status === 200) {
      return res.data;
    }
    if (res.status === 404) {
      return null;
    }

    // Anything else is an unexpected reading, not an absence. Returning `null`
    // here would assert "this document has no canonical row" on the strength of
    // a status we do not understand.
    this.logger.warn('document_intelligence_lean_unexpected_status', {
      documentId,
      status: res.status,
    });
    throw new LeanDocumentUnavailableError(
      documentId,
      res.status,
      `Document Service answered ${res.status} for a lean read`,
    );
  }
}
