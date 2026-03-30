import { Injectable, Logger } from '@nestjs/common';
import type { ConfigService } from '@nestjs/config';
import { Client } from '@opensearch-project/opensearch';
import type { DocumentsRepository } from './documents.repository';
import type { DocumentDetailDto, SectionsResponseDto } from './dto/document-detail.dto';

/** Check multiple error shapes the OpenSearch client may produce for 404s. */
function isNotFoundError(err: unknown): boolean {
  const asAny = err as Record<string, unknown>;
  if (asAny?.statusCode === 404) return true;
  if ((asAny?.meta as Record<string, unknown>)?.statusCode === 404) return true;
  if (asAny?.status === 404) return true;
  return false;
}

@Injectable()
export class OpenSearchDocumentsAdapter implements DocumentsRepository {
  private readonly logger = new Logger(OpenSearchDocumentsAdapter.name);
  private readonly client: Client;
  private readonly indexDocuments: string;
  private readonly indexSections: string;

  constructor(readonly config: ConfigService) {
    this.client = new Client({
      node: config.get<string>('opensearch.url', 'http://localhost:9200'),
    });
    this.indexDocuments = config.get<string>('opensearch.indexDocuments', 'evidara-documents-v1');
    this.indexSections = config.get<string>('opensearch.indexSections', 'evidara-sections-v1');
  }

  async getById(documentId: string): Promise<DocumentDetailDto | null> {
    try {
      const response = await this.client.get({ index: this.indexDocuments, id: documentId });
      const source = response.body._source as Record<string, unknown>;
      const title = source.title;
      if (typeof title !== 'string' || !title) {
        this.logger.warn(`Document '${documentId}' has missing or invalid title`);
      }
      return {
        document_id: documentId,
        title: typeof title === 'string' ? title : '',
        content: source.content as string | undefined,
        jurisdiction: source.jurisdiction as string | undefined,
        document_type: source.document_type as string | undefined,
        effective_date: source.effective_date as string | undefined,
        source_id: source.source_id as string | undefined,
        processed_at: source.processed_at as string | undefined,
        sections_count: source.sections_count as number | undefined,
        citations_count: source.citations_count as number | undefined,
      };
    } catch (err: unknown) {
      if (isNotFoundError(err)) return null;
      throw err;
    }
  }

  async getSections(documentId: string): Promise<SectionsResponseDto> {
    const PAGE_SIZE = 100;
    const response = await this.client.search({
      index: this.indexSections,
      body: {
        size: PAGE_SIZE,
        query: { term: { document_id: documentId } },
        sort: [{ ordinal: { order: 'asc' } }],
      },
    });

    const total =
      typeof response.body.hits.total === 'number'
        ? response.body.hits.total
        : ((response.body.hits.total as { value: number })?.value ?? 0);
    const hits = response.body.hits.hits as Array<Record<string, unknown>>;

    if (hits.length === PAGE_SIZE && total > PAGE_SIZE) {
      this.logger.warn(
        `Sections for document '${documentId}' truncated: returned ${hits.length} of ${total}`,
      );
    }

    const data = hits.map((hit) => {
      const source = hit._source as Record<string, unknown>;
      return {
        section_id: hit._id as string,
        title: source.title as string | undefined,
        ordinal: source.ordinal as number | undefined,
        depth: source.depth as number | undefined,
        content_preview: source.content_preview as string | undefined,
      };
    });

    return { data, total_count: total };
  }
}
