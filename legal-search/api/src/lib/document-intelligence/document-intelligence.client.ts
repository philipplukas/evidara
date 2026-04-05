import { Injectable, Logger } from '@nestjs/common';
// biome-ignore lint/style/useImportType: ConfigService is injected by Nest at runtime
import { ConfigService } from '@nestjs/config';
import { DocumentIntelligenceHttpError } from './document-intelligence-mutator';
import { getDocumentLean } from './generated/api';

export const DOCUMENT_INTELLIGENCE_CLIENT = Symbol('DOCUMENT_INTELLIGENCE_CLIENT');

export interface DocumentIntelligenceClient {
  /**
   * Fetches lean Docling JSON for the document when the service is configured.
   * Returns null when not configured, on 404, or on recoverable upstream failure.
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

    try {
      const res = await getDocumentLean(
        documentId,
        options?.documentRevision !== undefined
          ? { document_revision: options.documentRevision }
          : undefined,
        { headers },
      );

      if (res.status === 200) {
        return res.data;
      }

      return null;
    } catch (err) {
      if (err instanceof DocumentIntelligenceHttpError) {
        this.logger.warn('document_intelligence_lean_http_error', {
          documentId,
          status: err.status,
          message: err.message,
        });
        return null;
      }
      if (err instanceof Error && err.message === 'DOCUMENT_INTELLIGENCE_BASE_URL is not set') {
        return null;
      }
      this.logger.warn('document_intelligence_lean_failed', {
        documentId,
        error: err instanceof Error ? err.message : String(err),
      });
      return null;
    }
  }
}
