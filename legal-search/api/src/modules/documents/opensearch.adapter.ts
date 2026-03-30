import { Injectable, Logger } from '@nestjs/common';
import type { DocumentsRepository } from './documents.repository';
import type { CitationEntity, DocumentEntity, SectionEntity } from './entities/document.entities';

@Injectable()
export class DocumentsOpenSearchAdapter implements DocumentsRepository {
  private readonly logger = new Logger(DocumentsOpenSearchAdapter.name);
  async getById(id: string): Promise<DocumentEntity | null> {
    this.logger.debug(`Fetching document ${id}`);
    // TODO: Replace with actual OpenSearch get
    return null;
  }

  async getSections(documentId: string): Promise<SectionEntity[]> {
    this.logger.debug(`Fetching sections for ${documentId}`);
    // TODO: Replace with actual OpenSearch search
    return [];
  }

  async getCitations(documentId: string): Promise<CitationEntity[]> {
    this.logger.debug(`Fetching citations for ${documentId}`);
    // TODO: Replace with actual OpenSearch search
    return [];
  }
}
