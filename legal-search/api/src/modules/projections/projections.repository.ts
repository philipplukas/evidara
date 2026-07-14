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

/**
 * Discriminator separating primary legal documents from commentary
 * insight projection rows. Mirrors `record_kind` in
 * `contracts/schemas/search-projection.schema.json` (PR #434).
 */
export type RecordKind = 'legal_document' | 'commentary_insight';

export type SearchProjectionDocument = {
  document_id: string;
  /**
   * Polymorphic discriminator for projection rows. `legal_document` is
   * the historical default (one row per canonical DI document);
   * `commentary_insight` rows are produced from DI commentary insights
   * via `ProjectionsService.applyCommentaryInsight`.
   */
  record_kind: RecordKind;
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
  /**
   * Canonical jurisdiction IDs the row belongs to. Required by the
   * frozen contract; legal_document rows derive from the row's primary
   * jurisdiction, commentary_insight rows copy from the upstream
   * commentary insight.
   */
  jurisdiction_ids: string[];
  /**
   * Canonical authority IDs attached to the row. Optional for
   * `legal_document` rows; required and non-empty for
   * `commentary_insight` rows per the freeze.
   */
  authority_ids?: string[];
  /**
   * Canonical primary documents this row references. Empty for
   * `legal_document` rows; required and non-empty for
   * `commentary_insight` rows so the UI can resolve back to source.
   */
  source_document_ids?: string[];
  language?: string;
  /**
   * Full document text. Indexed as `content` (analyzer `legal_text`) and
   * is what the search highlighter reads to build a query-relevant snippet.
   * Without it, `SearchResult.snippet` degrades to `content_preview`, which
   * is the head of the document and identical for every query.
   */
  content?: string;
  /** Derived: the head of `content`, for display without loading the body. */
  content_preview?: string;
  /** Normalized document type from canonical DI row (law, decision, …). */
  document_type?: string;
  /** ISO date from canonical document when present. */
  effective_date?: string;
  /** Breadcrumb-style path when present in canonical metadata. */
  structural_path?: string;
};

/**
 * Commentary-insight payload accepted by
 * `ProjectionsService.applyCommentaryInsight`. Mirrors the subset of
 * `contracts/schemas/commentary-insight.schema.json` (PR #434) needed
 * to produce a search projection row.
 */
export type CommentaryInsightInput = {
  insight_id: string;
  document_id: string;
  document_revision: number;
  processing_manifest_id: string;
  insight_type: string;
  claim: string;
  display_text: string;
  language?: string | null;
  jurisdiction_id?: string | null;
  jurisdiction_ids: string[];
  authority_ids: string[];
  source_document_ids: string[];
  confidence: number;
  review_state: string;
  occurred_at?: string;
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

export type CitationTargetMatch = {
  document_id: string;
  title?: string;
  document_type?: string;
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
  resolveCitationTargets(normalizedRefs: string[]): Promise<Map<string, CitationTargetMatch>>;
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
