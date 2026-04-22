/**
 * Documents repository interface.
 */
import type { CitationEntity, DocumentEntity, SectionEntity } from './entities/document.entities';

export interface DocumentsRepository {
  getById(id: string): Promise<DocumentEntity | null>;
  getSections(documentId: string): Promise<SectionEntity[]>;
  getCitations(documentId: string): Promise<CitationEntity[]>;
  getCitedBy(documentId: string): Promise<CitationEntity[]>;
}

export const DOCUMENTS_REPOSITORY = Symbol('DOCUMENTS_REPOSITORY');
