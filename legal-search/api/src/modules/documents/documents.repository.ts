import type { DocumentDetailDto, SectionsResponseDto } from './dto/document-detail.dto';

export interface DocumentsRepository {
  getById(documentId: string): Promise<DocumentDetailDto | null>;
  getSections(documentId: string): Promise<SectionsResponseDto>;
}

export const DOCUMENTS_REPOSITORY = Symbol('DocumentsRepository');
