import type { CitationUnresolvedReason } from '../citations/citation-resolution';
import type { CitationTarget } from '../citations/citations.repository';
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
  /**
   * The official headnote of a decision, verbatim — the Swiss `Regeste`, the
   * Austrian `Rechtssatz`/`Leitsatz`. Copied from the canonical document's
   * `metadata.regeste`, which document-intelligence promotes only from a headnote
   * the source itself published (#836). Absent for statutes and ordinances, which
   * legitimately have none.
   */
  regeste?: string;
  /** Derived: the head of `content`, for display without loading the body. */
  content_preview?: string;
  /** Normalized document type from canonical DI row (law, decision, …). */
  document_type?: string;
  /** ISO date from canonical document when present. */
  effective_date?: string;
  /** Breadcrumb-style path when present in canonical metadata. */
  structural_path?: string;
  /**
   * Rank in the hierarchy of norms (ADR-0033), derived from the row's
   * jurisdiction — see `core/norm-hierarchy`. Absent when the jurisdiction is
   * unknown to the hierarchy vocabulary; the row is then simply not reachable
   * through `norm_hierarchy()`, which is the honest outcome.
   */
  level?: string;
  /**
   * Jurisdictions whose law outranks this row, most authoritative first.
   * Derived from the jurisdiction tree.
   */
  subordinate_to?: string[];
  /**
   * Competence this norm delegates downward. UNPOPULATED — it is an assertion
   * made by the norm's text, not a fact derivable from the tree. See the
   * `delegates_to` note in `documents-index.mapping.ts`.
   */
  delegates_to?: NormDelegation[];
  /** First date the norm was in force; falls back to `effective_date`. */
  in_force_from?: string;
  /** Last date the norm WAS in force (inclusive). Absent = not known to be repealed. */
  in_force_until?: string;
};

/** One `delegates_to` edge. Declared, not yet produced. */
export type NormDelegation = {
  target_level?: string;
  target_jurisdiction_id?: string;
  section_id?: string;
  scope?: string;
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
  /**
   * Whether resolution was ATTEMPTED and what it concluded. Absent means never
   * attempted (a row written before this field existed, or one that never went
   * through `resolveCitations`) — which is a different state from "attempted
   * and found nothing", and the index must be able to tell them apart
   * (ADR-0052, #958).
   */
  resolution_status?: 'resolved' | 'unresolved';
  /** Why `resolution_status: 'unresolved'`. Absent when resolved. */
  unresolved_reason?: CitationUnresolvedReason;
  metadata?: Record<string, unknown>;
};

export type CitationTargetEntry = {
  document_id: string;
  identifier_type: string;
  identifier_value: string;
  title?: string;
  document_type?: string;
  jurisdiction?: string;
  /** Set on PROVISION-level targets (`abbrev_art:BV/36`); absent otherwise. */
  section_id?: string;
  /** In-document anchor for `section_id`, e.g. `art_36`. */
  section_anchor?: string;
};

/**
 * The `citation-targets` rows a canonical key matched — ALL of them.
 *
 * Deliberately not narrowed to one match: choosing among several documents IS
 * the resolution decision, and it belongs to `resolveAgainstTargets`
 * (`modules/citations/citation-resolution.ts`), not to a repository adapter.
 * The previous `Map<string, CitationTargetMatch>` shape made the adapter pick
 * silently (last hit wins), which persisted an arbitrary `target_document_id`
 * with `resolved: true` for every ambiguous key.
 */
export type CitationTargetCandidates = Map<string, CitationTarget[]>;

/**
 * One indexed projection row, reduced to the identity a reconcile pass needs.
 *
 * ADR-0005 makes the index a derived view of canonical Delta, but nothing could
 * previously *enumerate* the derived side — so an index row whose canonical row no
 * longer exists (an orphan from an earlier run) stayed user-visible forever. This is
 * the index-side enumeration that makes the diff possible.
 *
 * The provenance fields are carried because a de-index goes through the
 * `document.withdrawn` path, whose payload contract requires them. They are read back
 * off the projection rather than invented: the row was written from a validated
 * `document.processed` event, so the ids it carries are the real ones.
 */
export type IndexedDocumentEntry = {
  document_id: string;
  document_revision?: number;
  processing_manifest_id?: string;
  source_id?: string;
  source_version_id?: string;
  run_id?: string;
  title?: string;
};

export type IndexedDocumentQuery = {
  /** Exclusive cursor — the last `document_id` of the previous page. */
  after?: string;
  limit?: number;
};

export type IndexedDocumentPage = {
  data: IndexedDocumentEntry[];
  limit: number;
  /** Cursor for the next page; absent when the walk is complete. */
  next_after?: string;
};

export interface ProjectionRepository {
  hasHistoryEvent(eventId: string): Promise<boolean>;
  listIndexedDocuments(query: IndexedDocumentQuery): Promise<IndexedDocumentPage>;
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
  /** Every `citation-targets` row matching each key — unnarrowed. */
  resolveCitationTargets(normalizedRefs: string[]): Promise<CitationTargetCandidates>;
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
