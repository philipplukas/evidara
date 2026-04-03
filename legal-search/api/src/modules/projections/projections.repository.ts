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
};

export interface ProjectionRepository {
  hasHistoryEvent(eventId: string): Promise<boolean>;
  getLatestRevision(documentId: string): Promise<number | null>;
  upsertProjection(document: SearchProjectionDocument): Promise<void>;
  deleteProjection(documentId: string): Promise<void>;
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
