import type {
  DocumentProcessedEventDto,
  DocumentWithdrawnEventDto,
} from './dto/projection-events.dto';

export type ProjectionHistoryStatus = 'applied' | 'stale' | 'ignored_duplicate';

export type ProjectionHistoryEntry = {
  eventId: string;
  eventType: 'document.processed' | 'document.withdrawn';
  documentId: string;
  documentRevision: number;
  processingManifestId: string;
  runId: string;
  occurredAt: string;
  status: ProjectionHistoryStatus;
  notes?: string;
};

export type SearchProjectionDocument = {
  document_id: string;
  title: string;
  authority_name?: string;
  official_citation?: string;
  original_language?: string;
  translation_status?: 'original' | 'machine_translated' | 'translation_unavailable';
  is_official?: boolean;
  sections_count: number;
  citations_count: number;
  source_id?: string;
  source_version_id?: string;
  run_id?: string;
  processing_manifest_id?: string;
  document_revision?: number;
  lifecycle_status?: string;
  processed_at?: string;
  jurisdiction?: string;
  language?: string;
  content_preview?: string;
  /** Normalized document type from canonical DI row (law, decision, …). */
  document_type?: string;
  /** ISO date from canonical document when present. */
  effective_date?: string;
  /** Breadcrumb-style path when present in canonical metadata. */
  structural_path?: string;
};

export type SectionProjection = {
  section_id: string;
  document_id: string;
  title?: string;
  ordinal: number;
  depth: number;
  content_preview?: string;
  parent_section_id?: string;
};

export type CitationProjection = {
  citation_id: string;
  source_document_id: string;
  source_section_id?: string;
  target_document_id?: string;
  target_title?: string;
  citation_text: string;
  citation_type?: string;
  normalized_reference?: string;
  resolved: boolean;
  metadata?: Record<string, unknown>;
};

export type CitationTargetEntry = {
  document_id: string;
  identifier_type: string;
  identifier_value: string;
  title?: string;
  document_type?: string;
  jurisdiction?: string;
};

export interface ProjectionRepository {
  hasHistoryEvent(eventId: string): Promise<boolean>;
  getLatestRevision(documentId: string): Promise<number | null>;
  upsertProjection(document: SearchProjectionDocument): Promise<void>;
  deleteProjection(documentId: string): Promise<void>;
  bulkIndexSections(sections: SectionProjection[]): Promise<void>;
  bulkIndexCitations(citations: CitationProjection[]): Promise<void>;
  bulkIndexCitationTargets(targets: CitationTargetEntry[]): Promise<void>;
  deleteSectionsForDocument(documentId: string): Promise<void>;
  deleteCitationsForDocument(documentId: string): Promise<void>;
  appendHistory(entry: ProjectionHistoryEntry): Promise<void>;
  queryHistory(query: ProjectionHistoryQuery): Promise<ProjectionHistoryPage>;
  getHistoryStats(): Promise<ProjectionHistoryStats>;
}

export type ProjectionHistoryQuery = {
  documentId?: string;
  runId?: string;
  status?: ProjectionHistoryStatus;
  limit?: number;
  offset?: number;
};

export type ProjectionHistoryPage = {
  data: ProjectionHistoryEntry[];
  total: number;
  limit: number;
  offset: number;
};

export type ProjectionHistoryStats = {
  totalEvents: number;
  applied: number;
  stale: number;
  ignoredDuplicate: number;
  uniqueDocuments: number;
};

export const PROJECTION_REPOSITORY = Symbol('PROJECTION_REPOSITORY');

export type ProcessedEventInput = DocumentProcessedEventDto;
export type WithdrawnEventInput = DocumentWithdrawnEventDto;
