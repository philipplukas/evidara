import { Injectable, Inject, NotFoundException } from '@nestjs/common';
import { DOCUMENTS_REPOSITORY, type DocumentsRepository } from './documents.repository';
import type { DocumentDetailDto, SectionsResponseDto } from './dto/document-detail.dto';

@Injectable()
export class DocumentsService {
  constructor(
    @Inject(DOCUMENTS_REPOSITORY) private readonly documentsRepository: DocumentsRepository,
  ) {}

  async getById(documentId: string): Promise<DocumentDetailDto> {
    const doc = await this.documentsRepository.getById(documentId);
    if (!doc) {
      // Domain exception thrown here — mapped to 404 at the boundary (exception filter)
      // Eventually replace NotFoundException with a typed DocumentNotFoundError
      throw new NotFoundException(`Document '${documentId}' not found`);
    }
    return doc;
  }

  async getSections(documentId: string): Promise<SectionsResponseDto> {
    return this.documentsRepository.getSections(documentId);
  }
}
