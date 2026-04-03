/**
 * OpenSearch adapter for document operations.
 * Implements DocumentsRepository using the real OpenSearch client.
 *
 * Strategy:
 * - getById: direct get by document_id (term query)
 * - getSections: search sections index by document_id
 * - getCitations: search citations index by source_document_id
 */
import { Inject, Injectable, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import type { Client } from '@opensearch-project/opensearch';
import { OPENSEARCH_CLIENT } from '../../core/opensearch/client';
import type { DocumentsRepository } from './documents.repository';
import type { CitationEntity, DocumentEntity, SectionEntity } from './entities/document.entities';

type OpenSearchHit = {
  _source?: Record<string, unknown>;
};

@Injectable()
export class DocumentsOpenSearchAdapter implements DocumentsRepository {
  private readonly logger = new Logger(DocumentsOpenSearchAdapter.name);
  private readonly indexDocuments: string;
  private readonly indexSections: string;
  private readonly indexCitations: string;

  constructor(
    @Inject(OPENSEARCH_CLIENT)
    private readonly client: Client,
    @Inject(ConfigService)
    config: ConfigService,
  ) {
    this.indexDocuments = config.get<string>('opensearch.indexDocuments') ?? 'documents';
    this.indexSections = config.get<string>('opensearch.indexSections') ?? 'sections';
    this.indexCitations = config.get<string>('opensearch.indexCitations') ?? 'citations';
  }

  async getById(id: string): Promise<DocumentEntity | null> {
    this.logger.debug(`Fetching document ${id}`);

    try {
      const response = await this.client.search({
        index: this.indexDocuments,
        body: {
          size: 1,
          query: { term: { document_id: id } },
        },
      });

      const hit = response.body.hits.hits[0];
      if (!hit) return null;

      const src = hit._source as Record<string, unknown>;
      return {
        document_id: src.document_id as string,
        title: src.title as string,
        content: src.content as string | undefined,
        content_docling: src.content_docling as unknown,
        jurisdiction: src.jurisdiction as string | undefined,
        document_type: src.document_type as string | undefined,
        effective_date: src.effective_date as string | undefined,
        source_id: src.source_id as string | undefined,
        processed_at: src.processed_at as string | undefined,
        structural_path: src.structural_path as string | undefined,
        language: src.language as string | undefined,
        sections_count: src.sections_count as number | undefined,
        citations_count: src.citations_count as number | undefined,
      };
    } catch (err) {
      this.logger.error(`Failed to fetch document ${id}`, err);
      return null;
    }
  }

  async getSections(documentId: string): Promise<SectionEntity[]> {
    this.logger.debug(`Fetching sections for ${documentId}`);

    try {
      const response = await this.client.search({
        index: this.indexSections,
        body: {
          size: 200,
          query: { term: { document_id: documentId } },
          sort: [{ ordinal: { order: 'asc' } }],
        },
      });

      return (response.body.hits.hits as OpenSearchHit[])
        .filter((hit) => hit._source != null)
        .map((hit) => {
          const src = hit._source as Record<string, unknown>;
          return {
            section_id: src.section_id as string,
            document_id: src.document_id as string,
            title: src.title as string | undefined,
            ordinal: src.ordinal as number | undefined,
            depth: src.depth as number | undefined,
            content_preview: src.content_preview as string | undefined,
            parent_section_id: src.parent_section_id as string | undefined,
          };
        });
    } catch (err) {
      this.logger.error(`Failed to fetch sections for ${documentId}`, err);
      return [];
    }
  }

  async getCitations(documentId: string): Promise<CitationEntity[]> {
    this.logger.debug(`Fetching citations for ${documentId}`);

    try {
      const response = await this.client.search({
        index: this.indexCitations,
        body: {
          size: 100,
          query: { term: { source_document_id: documentId } },
        },
      });

      return (response.body.hits.hits as OpenSearchHit[])
        .filter((hit) => hit._source != null)
        .map((hit) => {
          const src = hit._source as Record<string, unknown>;
          return {
            citation_id: src.citation_id as string,
            source_document_id: src.source_document_id as string,
            source_section_id: src.source_section_id as string | undefined,
            target_document_id: src.target_document_id as string | undefined,
            target_title: src.target_title as string | undefined,
            target_subtitle: src.target_subtitle as string | undefined,
            target_document_type: src.target_document_type as string | undefined,
            citation_text: src.citation_text as string,
            citation_type: src.citation_type as string | undefined,
            resolved: (src.resolved as boolean) ?? false,
          };
        });
    } catch (err) {
      this.logger.error(`Failed to fetch citations for ${documentId}`, err);
      return [];
    }
  }
}
