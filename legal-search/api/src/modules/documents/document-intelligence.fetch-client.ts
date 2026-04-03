import { Injectable, Logger } from '@nestjs/common';
// biome-ignore lint/style/useImportType: ConfigService is injected by Nest at runtime
import { ConfigService } from '@nestjs/config';
import type { DocumentContentPort } from './ports/document-content.port';

@Injectable()
export class NoOpDocumentContentClient implements DocumentContentPort {
  async fetchLeanContent(): Promise<unknown | undefined> {
    return undefined;
  }
}

/** Calls document-intelligence Document Service `GET /v1/documents/{id}/lean`. */
@Injectable()
export class FetchDocumentIntelligenceClient implements DocumentContentPort {
  private readonly logger = new Logger(FetchDocumentIntelligenceClient.name);

  constructor(private readonly config: ConfigService) {}

  async fetchLeanContent(
    documentId: string,
    processingManifestId?: string,
  ): Promise<unknown | undefined> {
    const base = this.config.get<string>('documentIntelligence.baseUrl', '');
    if (!base) return undefined;

    const url = new URL(
      `/v1/documents/${encodeURIComponent(documentId)}/lean`,
      `${base.replace(/\/$/, '')}/`,
    );
    if (processingManifestId) {
      url.searchParams.set('processing_manifest_id', processingManifestId);
    }

    const token = this.config.get<string>('documentIntelligence.bearerToken', '');
    const headers: Record<string, string> = { Accept: 'application/json' };
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }

    try {
      const res = await fetch(url, { headers, signal: AbortSignal.timeout(30_000) });
      if (res.status === 404) {
        return undefined;
      }
      if (!res.ok) {
        this.logger.warn(`Document Service lean fetch failed: ${res.status} ${res.statusText}`, {
          url: url.toString(),
        });
        return undefined;
      }
      return (await res.json()) as unknown;
    } catch (err) {
      this.logger.warn(`Document Service lean fetch error: ${String(err)}`, {
        url: url.toString(),
      });
      return undefined;
    }
  }
}
