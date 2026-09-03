import { Inject, Injectable, Logger } from '@nestjs/common';
import { deriveDocumentLevel, deriveSubordinateTo } from '../../core/norm-hierarchy';
import { normalizeDocumentType } from '../../core/vocabularies';
import {
  DOCUMENT_INTELLIGENCE_CLIENT,
  type DocumentIntelligenceClient,
} from '../../lib/document-intelligence/document-intelligence.client';
// The abbreviation SHAPE test is shared with the resolver on purpose: minting
// a node the resolver's key format cannot address is the drift that silently
// loses edges.
import { isLegalAbbreviation } from '../citations/citation-key';
import type {
  DocumentProcessedEventDto,
  DocumentWithdrawnEventDto,
} from './dto/projection-events.dto';
import {
  type CitationProjection,
  type CitationTargetEntry,
  type CitationTargetMatch,
  type CommentaryInsightInput,
  type IndexedDocumentPage,
  type IndexedDocumentQuery,
  PROJECTION_REPOSITORY,
  type ProjectionHistoryEntry,
  type ProjectionHistoryPage,
  type ProjectionHistoryQuery,
  type ProjectionHistoryStats,
  type ProjectionRepository,
  type SearchProjectionDocument,
  type SectionProjection,
} from './projections.repository';

export type ProjectionApplyResult = {
  eventId: string;
  status: 'applied' | 'stale' | 'ignored_duplicate';
};

@Injectable()
export class ProjectionsService {
  private readonly logger = new Logger(ProjectionsService.name);

  /**
   * How far into the body a document may still be stating its own identifier.
   * Fedlex puts the SR number in the first line ("Vom 18. April 1999 (Stand am
   * 1. Januar 2024), SR 101."); beyond the masthead, an SR number is a citation
   * to a different norm, not a self-declaration. See `citationTargetScanText`.
   */
  private static readonly MASTHEAD_WINDOW_CHARS = 400;

  constructor(
    @Inject(PROJECTION_REPOSITORY)
    private readonly repository: ProjectionRepository,
    @Inject(DOCUMENT_INTELLIGENCE_CLIENT)
    private readonly documentIntelligence: DocumentIntelligenceClient,
  ) {}

  async applyDocumentProcessed(event: DocumentProcessedEventDto): Promise<ProjectionApplyResult> {
    if (await this.repository.hasHistoryEvent(event.event_id)) {
      return { eventId: event.event_id, status: 'ignored_duplicate' };
    }

    const latestRevision = await this.repository.getLatestRevision(event.payload.document_id);
    if (latestRevision !== null && event.payload.document_revision < latestRevision) {
      await this.appendHistory(event, 'stale', `latest revision is ${latestRevision}`);
      return { eventId: event.event_id, status: 'stale' };
    }

    const leanDocument = await this.documentIntelligence.fetchLeanDocument(
      event.payload.document_id,
      {
        correlationId: event.correlation_id,
        documentRevision: event.payload.document_revision,
      },
    );
    if (leanDocument === null) {
      // Keep projection flow non-blocking when DI read API is unavailable.
      this.logger.warn('projection_enrichment_unavailable_fallback', {
        document_id: event.payload.document_id,
        correlation_id: event.correlation_id,
      });
    }
    const projection = this.buildProjection(event, leanDocument);
    await this.repository.upsertProjection(projection);

    // Index sections and citations from the lean document into their
    // dedicated indices so document-detail views can display them and
    // citation resolution can link across documents.
    const sections = this.extractSections(event.payload.document_id, leanDocument);
    const citations = await this.resolveCitations(
      this.extractCitations(event.payload.document_id, leanDocument),
    );
    const citationTargets = this.extractCitationTargets(projection, leanDocument);

    // Forward-compatible: when DI's lean document carries a
    // `commentary_insights` array, project each entry as a first-class
    // commentary_insight record. Until DI emits these, the array is
    // absent and the loop is a no-op — no API contract change.
    const commentaryInsights = this.extractCommentaryInsights(leanDocument, event.occurred_at);

    await Promise.all([
      sections.length > 0
        ? this.repository
            .deleteSectionsForDocument(event.payload.document_id)
            .then(() => this.repository.bulkIndexSections(sections))
        : Promise.resolve(),
      citations.length > 0
        ? this.repository
            .deleteCitationsForDocument(event.payload.document_id)
            .then(() => this.repository.bulkIndexCitations(citations))
        : Promise.resolve(),
      citationTargets.length > 0
        ? this.repository.bulkIndexCitationTargets(citationTargets)
        : Promise.resolve(),
      ...commentaryInsights.map((insight) => this.applyCommentaryInsight(insight)),
    ]);

    await this.appendHistory(event, 'applied');
    return { eventId: event.event_id, status: 'applied' };
  }

  async applyDocumentWithdrawn(event: DocumentWithdrawnEventDto): Promise<ProjectionApplyResult> {
    if (await this.repository.hasHistoryEvent(event.event_id)) {
      return { eventId: event.event_id, status: 'ignored_duplicate' };
    }

    const latestRevision = await this.repository.getLatestRevision(event.payload.document_id);
    if (latestRevision !== null && event.payload.document_revision < latestRevision) {
      await this.appendWithdrawnHistory(event, 'stale', `latest revision is ${latestRevision}`);
      return { eventId: event.event_id, status: 'stale' };
    }

    // Current behavior: both `remove` and `hide` result in de-indexing from search surfaces.
    await Promise.all([
      this.repository.deleteProjection(event.payload.document_id),
      this.repository.deleteSectionsForDocument(event.payload.document_id),
      this.repository.deleteCitationsForDocument(event.payload.document_id),
    ]);
    await this.appendWithdrawnHistory(event, 'applied');
    return { eventId: event.event_id, status: 'applied' };
  }

  /**
   * Project a commentary insight as a first-class search record.
   *
   * Idempotent on `insight_id` (used as the row's `document_id` in the
   * projection index — different namespace from primary documents
   * because `ins_*` and `doc_*` ID families don't collide). The
   * resulting row carries `record_kind=commentary_insight` so the
   * search adapter and the frontend renderer can pivot on it.
   *
   * Trigger wiring is deferred: this method is currently invoked from
   * `applyDocumentProcessed` when the lean document carries a
   * `commentary_insights` array. A dedicated commentary-insight event
   * topic can call this method directly when DI starts emitting one.
   */
  async applyCommentaryInsight(
    insight: CommentaryInsightInput,
  ): Promise<{ insightId: string; status: 'applied' }> {
    const projection = this.buildCommentaryProjection(insight);
    await this.repository.upsertProjection(projection);
    return { insightId: insight.insight_id, status: 'applied' };
  }

  /**
   * Enumerate what is actually indexed, so an operator (or the DI reconcile job) can
   * diff the derived index against canonical Delta. Read-only — it deletes nothing.
   */
  async listIndexedDocuments(query: IndexedDocumentQuery): Promise<IndexedDocumentPage> {
    return this.repository.listIndexedDocuments(query);
  }

  async queryHistory(query: ProjectionHistoryQuery): Promise<ProjectionHistoryPage> {
    return this.repository.queryHistory(query);
  }

  async getHistoryStats(): Promise<ProjectionHistoryStats> {
    return this.repository.getHistoryStats();
  }

  private buildProjection(
    event: DocumentProcessedEventDto,
    leanDocument: unknown | null,
  ): SearchProjectionDocument {
    const provenance = event.payload.provenance;
    const extracted = this.extractLeanDocumentFields(leanDocument);
    const title = extracted.title ?? `Document ${event.payload.document_id}`;
    const preview =
      extracted.previewText ??
      this.truncateForPreview(extracted.fullText) ??
      event.payload.processing_version;
    const jurisdiction =
      extracted.jurisdictionFromCanonical ?? this.inferJurisdiction(provenance.corpus_id);
    const jurisdictionIds = extracted.canonicalJurisdictionIds ?? [];
    const projection: SearchProjectionDocument = {
      document_id: event.payload.document_id,
      record_kind: 'legal_document',
      title,
      authority_name: event.payload.authority_name,
      official_citation: extracted.officialCitation,
      original_language: extracted.originalLanguage,
      translation_status: extracted.translationStatus,
      is_official: event.payload.is_official,
      sections_count: extracted.sectionsCount,
      citations_count: extracted.citationsCount,
      source_id: provenance.source_id,
      source_version_id: provenance.source_version_id,
      run_id: provenance.run_id,
      processing_manifest_id: event.payload.processing_manifest_id,
      document_revision: event.payload.document_revision,
      lifecycle_status: event.payload.lifecycle_status,
      processed_at: event.occurred_at,
      jurisdiction,
      jurisdiction_ids: jurisdictionIds,
      // The searchable `language` facet must describe the expression we
      // actually acquired (#572). Order matters: the canonical document's
      // own `language`, then `metadata.original_language` (DI resolves it
      // from the source HTML `lang` attribute, falling back to the source
      // version's `language_codes`), and only then the corpus-id guess.
      // Preferring the guess over `original_language` is what indexed the
      // German Federal Constitution as Italian.
      language:
        extracted.language ??
        extracted.originalLanguage ??
        this.inferLanguage(provenance.corpus_id),
      content_preview: preview,
    };
    if (extracted.fullText) projection.content = extracted.fullText;
    if (extracted.regeste) projection.regeste = extracted.regeste;
    if (extracted.documentType) projection.document_type = extracted.documentType;
    if (extracted.effectiveDate) projection.effective_date = extracted.effectiveDate;
    if (extracted.structuralPath) projection.structural_path = extracted.structuralPath;
    if (extracted.canonicalAuthorityIds && extracted.canonicalAuthorityIds.length > 0) {
      projection.authority_ids = extracted.canonicalAuthorityIds;
    }
    this.applyNormHierarchy(projection, extracted);
    return projection;
  }

  /**
   * Stamp the hierarchy-of-norms fields onto a projection row (ADR-0033).
   *
   * `level` and `subordinate_to` are derived from the row's jurisdiction, never
   * guessed from its text — the jurisdiction already knows whether it is a
   * commune, a canton or the Confederation, so the ordering of norms falls out
   * of the tree. A document whose jurisdiction is unknown to the hierarchy
   * vocabulary gets neither field and is simply unreachable through
   * `norm_hierarchy()`; that is a coverage gap the endpoint reports, not one it
   * papers over.
   *
   * `in_force_from` coalesces `effective_date` so the index has one field to
   * range-query. `delegates_to` is NOT set here: it cannot be derived from the
   * tree.
   */
  private applyNormHierarchy(
    projection: SearchProjectionDocument,
    extracted: { declaredLevel?: string; inForceFrom?: string; inForceUntil?: string },
  ): void {
    const level = deriveDocumentLevel(projection.jurisdiction_ids, extracted.declaredLevel);
    if (level) {
      projection.level = level;
      const subordinateTo = deriveSubordinateTo(projection.jurisdiction_ids);
      if (subordinateTo.length > 0) projection.subordinate_to = subordinateTo;
    }

    const inForceFrom = extracted.inForceFrom ?? projection.effective_date;
    if (inForceFrom) projection.in_force_from = inForceFrom;
    if (extracted.inForceUntil) projection.in_force_until = extracted.inForceUntil;
  }

  /**
   * Map a commentary insight payload to a `commentary_insight`
   * projection row. The row's `document_id` is the upstream
   * `insight_id` so the search projection can be reverse-joined back
   * to the originating commentary record. `source_document_ids`
   * carries the primary documents the commentary points at — the UI
   * resolves these for "explain why" / source-doc panels.
   */
  private buildCommentaryProjection(insight: CommentaryInsightInput): SearchProjectionDocument {
    // Insight `jurisdiction_id` is the platform canonical form
    // (`jur_ch_federal`); the helper expects the DI internal form
    // (`ch_federal`) — strip the `jur_` prefix to bridge the two.
    const canonicalForInfer = insight.jurisdiction_id?.startsWith('jur_')
      ? insight.jurisdiction_id.slice('jur_'.length)
      : (insight.jurisdiction_id ?? undefined);
    const jurisdiction = canonicalForInfer
      ? this.inferJurisdictionFromCanonicalId(canonicalForInfer)
      : undefined;
    const projection: SearchProjectionDocument = {
      document_id: insight.insight_id,
      record_kind: 'commentary_insight',
      title: insight.claim,
      sections_count: 0,
      citations_count: 0,
      processing_manifest_id: insight.processing_manifest_id,
      document_revision: insight.document_revision,
      processed_at: insight.occurred_at,
      jurisdiction,
      jurisdiction_ids: insight.jurisdiction_ids,
      authority_ids: insight.authority_ids,
      source_document_ids: insight.source_document_ids,
      content_preview: insight.display_text,
      document_type: 'commentary',
    };
    if (insight.language) {
      projection.language = insight.language;
      projection.original_language = insight.language;
      projection.translation_status = 'original';
    }
    return projection;
  }

  private extractLeanDocumentFields(leanDocument: unknown): {
    title?: string;
    language?: string;
    officialCitation?: string;
    regeste?: string;
    originalLanguage?: string;
    translationStatus?: 'original' | 'machine_translated' | 'translation_unavailable';
    previewText?: string;
    bodyPreviewFallback?: string;
    fullText?: string;
    sectionsCount: number;
    citationsCount: number;
    documentType?: string;
    effectiveDate?: string;
    structuralPath?: string;
    jurisdictionFromCanonical?: string;
    canonicalJurisdictionIds?: string[];
    canonicalAuthorityIds?: string[];
    declaredLevel?: string;
    inForceFrom?: string;
    inForceUntil?: string;
  } {
    if (!leanDocument || typeof leanDocument !== 'object') {
      return { sectionsCount: 0, citationsCount: 0 };
    }
    const doc = leanDocument as Record<string, unknown>;
    const language =
      typeof doc.language === 'string' && doc.language.trim() ? doc.language.trim() : undefined;
    const officialCitation = this.firstNestedString(doc, [
      ['metadata', 'official_citation'],
      ['official_citation'],
    ]);
    // The official headnote of a decision (#836). `metadata.regeste` is the field
    // document-intelligence promotes; `extracted_metadata.headnote` is where the XML
    // normalizer parks the RIS `leitsatz`/`rechtssatz`/`strs` and is read as a fallback
    // so a document published before the promotion existed picks the headnote up on its
    // next reindex, without being reprocessed.
    const regeste = this.firstNestedString(doc, [
      ['metadata', 'regeste'],
      ['regeste'],
      ['metadata', 'extracted_metadata', 'headnote'],
    ]);
    const originalLanguage =
      this.firstNestedString(doc, [['metadata', 'original_language'], ['original_language']]) ??
      language;
    const translationStatus = this.firstTranslationStatus(doc, originalLanguage);
    const sectionCandidates = [doc.sections, doc.document_sections, doc.body_sections];
    const citationCandidates = [doc.citations, doc.document_citations];
    const extensions = this.asRecord(doc.extensions);
    const citationExt = extensions?.citations;
    const citationCandidatesWithExtensions = [
      ...citationCandidates,
      Array.isArray(citationExt) ? citationExt : undefined,
    ];
    const textCandidates = [doc.content_text, doc.text, doc.summary];
    const sectionsCount = this.countArrayLike(sectionCandidates);
    const citationsCount =
      this.countArrayLike(citationCandidatesWithExtensions) +
      this.extractSectionCitationRecords(doc).length;
    const meta = this.asRecord(doc.metadata);
    const extractedMeta = meta ? this.asRecord(meta.extracted_metadata) : undefined;
    const sourceDefaults = meta ? this.asRecord(meta.source_defaults) : undefined;
    const llmMeta = meta ? this.asRecord(meta.llm_extraction) : undefined;

    const llmPreview =
      llmMeta?.applied === true && typeof llmMeta.summary === 'string' && llmMeta.summary.trim()
        ? (llmMeta.summary as string).trim()
        : undefined;
    const previewText =
      this.firstString(textCandidates) ??
      (llmPreview && !llmPreview.startsWith('extractor_failed:') ? llmPreview : undefined);

    const bodyPreviewFallback =
      typeof doc.body_text === 'string' && doc.body_text.trim()
        ? doc.body_text
        : typeof doc.full_text === 'string' && doc.full_text.trim()
          ? doc.full_text
          : undefined;
    // The body the highlighter searches. Prefer the document body; when the
    // lean document carries only structured sections, the concatenated section
    // text is the full body.
    const fullText = bodyPreviewFallback ?? this.extractSectionsText(doc);
    const structuredTitle = this.extractStructuredTitle([
      doc.title,
      doc.body_text,
      doc.full_text,
      doc.content_text,
      doc.text,
      doc.summary,
    ]);

    const documentType = this.firstNormalizedDocumentType([
      doc.document_type,
      meta?.document_type,
      sourceDefaults?.document_type_hint,
      extractedMeta?.document_type,
    ]);
    const effectiveDate =
      typeof doc.effective_date === 'string' && doc.effective_date.trim()
        ? doc.effective_date.trim()
        : undefined;
    const structuralPath = this.firstString([
      typeof doc.structural_path === 'string' ? doc.structural_path : undefined,
      extractedMeta && typeof extractedMeta.structural_path === 'string'
        ? extractedMeta.structural_path
        : undefined,
      extractedMeta && typeof extractedMeta.path === 'string' ? extractedMeta.path : undefined,
    ]);
    const fallbackTitle = this.deriveTitle({
      title:
        typeof doc.title === 'string' && doc.title.trim()
          ? this.normalizeTitle(doc.title)
          : undefined,
      structuredTitle,
      llmTitle:
        llmMeta?.applied === true &&
        typeof llmMeta.title === 'string' &&
        llmMeta.title.trim() &&
        !llmMeta.title.startsWith('extractor_failed:')
          ? this.normalizeTitle(llmMeta.title)
          : undefined,
      structuredBodyTitle: this.extractStructuredBodyTitle(bodyPreviewFallback),
      officialCitation,
      previewText,
      bodyPreviewFallback,
      structuralPath,
    });
    const jurisdictionFromCanonical =
      typeof doc.jurisdiction_id === 'string' && doc.jurisdiction_id.trim()
        ? this.inferJurisdictionFromCanonicalId(doc.jurisdiction_id.trim())
        : undefined;

    // Canonical id-list fields per the contract freeze (#434).
    // The lean document either carries these directly (when DI extends
    // its output) or the legacy path falls back to a single-element
    // array derived from `jurisdiction_id`. Empty arrays are valid for
    // legal_document rows; the OpenAPI conditional only requires
    // non-empty for `record_kind == commentary_insight`.
    const canonicalJurisdictionIds = this.extractCanonicalIdList(
      doc.jurisdiction_ids,
      /^jur_[a-z0-9_]+$/,
    );
    let resolvedJurisdictionIds = canonicalJurisdictionIds;
    if (resolvedJurisdictionIds.length === 0 && typeof doc.jurisdiction_id === 'string') {
      const trimmed = doc.jurisdiction_id.trim();
      if (/^jur_[a-z0-9_]+$/.test(trimmed)) {
        resolvedJurisdictionIds = [trimmed];
      }
    }
    const canonicalAuthorityIds = this.extractCanonicalIdList(
      doc.authority_ids,
      /^auth_[a-z0-9_]+$/,
    );

    // The only level a document may declare for itself is one the jurisdiction
    // cannot supply — in practice `constitutional`, because the BV is enacted by
    // the same federal jurisdiction as an ordinary statute. `deriveDocumentLevel`
    // rejects a declaration that would demote the norm.
    const declaredLevel = this.firstNestedString(doc, [['level'], ['metadata', 'level']]);
    const inForceFrom = this.firstNestedString(doc, [
      ['in_force_from'],
      ['metadata', 'in_force_from'],
    ]);
    // `repealed_date` is accepted as an alias so a producer that models repeal
    // as an event date does not silently drop the only field that makes
    // temporal validity answerable.
    const inForceUntil = this.firstNestedString(doc, [
      ['in_force_until'],
      ['metadata', 'in_force_until'],
      ['repealed_date'],
      ['metadata', 'repealed_date'],
    ]);

    return {
      title: fallbackTitle,
      language,
      officialCitation,
      regeste,
      originalLanguage,
      translationStatus,
      previewText,
      bodyPreviewFallback,
      fullText,
      sectionsCount,
      citationsCount,
      documentType,
      effectiveDate,
      structuralPath,
      jurisdictionFromCanonical,
      canonicalJurisdictionIds: resolvedJurisdictionIds,
      canonicalAuthorityIds,
      declaredLevel,
      inForceFrom,
      inForceUntil,
    };
  }

  /** Best-effort parse of a canonical id-list field from the lean document. */
  private extractCanonicalIdList(value: unknown, pattern: RegExp): string[] {
    if (!Array.isArray(value)) return [];
    const ids: string[] = [];
    for (const entry of value) {
      if (typeof entry !== 'string') continue;
      const trimmed = entry.trim().toLowerCase();
      if (pattern.test(trimmed)) ids.push(trimmed);
    }
    return Array.from(new Set(ids));
  }

  private deriveTitle(args: {
    title?: string;
    structuredTitle?: string;
    llmTitle?: string;
    structuredBodyTitle?: string;
    officialCitation?: string;
    previewText?: string;
    bodyPreviewFallback?: string;
    structuralPath?: string;
  }): string | undefined {
    const structuralTail = args.structuralPath?.split('›').at(-1)?.trim();
    return this.firstString([
      args.title,
      args.structuredTitle,
      args.llmTitle,
      args.structuredBodyTitle,
      args.officialCitation,
      this.firstSubstantiveLine(args.previewText ?? args.bodyPreviewFallback),
      structuralTail,
    ]);
  }

  private extractStructuredTitle(values: unknown[]): string | undefined {
    for (const value of values) {
      const title = this.extractStructuredTitleFromValue(value);
      if (title) {
        return title;
      }
    }
    return undefined;
  }

  private extractStructuredTitleFromValue(value: unknown): string | undefined {
    if (typeof value !== 'string') return undefined;
    const trimmed = value.trim();
    if (!trimmed.startsWith('{') && !trimmed.startsWith('[')) return undefined;
    try {
      const parsed = JSON.parse(trimmed) as unknown;
      return this.extractStructuredTitleFromObject(parsed);
    } catch {
      return undefined;
    }
  }

  private extractStructuredTitleFromObject(value: unknown): string | undefined {
    const record = this.asRecord(value);
    if (!record) return undefined;

    const directTitle =
      typeof record.title === 'string' ? this.normalizeTitle(record.title) : undefined;
    if (directTitle) {
      return directTitle;
    }

    const nestedInlineTitle =
      typeof record.inline_body === 'string'
        ? this.extractStructuredTitleFromValue(record.inline_body)
        : undefined;
    if (nestedInlineTitle) {
      return nestedInlineTitle;
    }

    const providerMetadata = this.asRecord(record.provider_metadata);
    const providerTitle =
      typeof providerMetadata?.title === 'string'
        ? this.normalizeTitle(providerMetadata.title)
        : undefined;
    if (providerTitle) {
      return providerTitle;
    }

    return undefined;
  }

  private firstSubstantiveLine(value: string | undefined): string | undefined {
    if (!value) return undefined;
    const line = value
      .split('\n')
      .map((part) => part.trim())
      .find((part) => part.length >= 24);
    return line;
  }

  private normalizeTitle(value: string): string | undefined {
    const title = value.trim();
    if (!title) return undefined;
    const lower = title.toLowerCase();
    if (
      lower === 'untitled document' ||
      lower === 'ris dokument' ||
      lower.startsWith('ris -') ||
      lower.startsWith('ris —')
    ) {
      return undefined;
    }
    return title;
  }

  /**
   * Concatenate the canonical section bodies into one searchable text. Used
   * when the lean document has no `body_text` / `full_text` of its own — the
   * sections then *are* the document body.
   */
  private extractSectionsText(doc: Record<string, unknown>): string | undefined {
    const raw = doc.sections ?? doc.document_sections ?? doc.body_sections;
    if (!Array.isArray(raw)) return undefined;
    const parts = raw
      .filter((s): s is Record<string, unknown> => s != null && typeof s === 'object')
      .map((s) => {
        const title = typeof s.title === 'string' ? s.title.trim() : '';
        const content = typeof s.content === 'string' ? s.content.trim() : '';
        return [title, content].filter(Boolean).join('\n');
      })
      .filter(Boolean);
    if (parts.length === 0) return undefined;
    return parts.join('\n\n');
  }

  private truncateForPreview(text: string | undefined, maxChars = 400): string | undefined {
    if (!text) return undefined;
    const t = text.trim();
    if (!t) return undefined;
    if (t.length <= maxChars) return t;
    return `${t.slice(0, maxChars - 1)}…`;
  }

  private asRecord(value: unknown): Record<string, unknown> | undefined {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return undefined;
    return value as Record<string, unknown>;
  }

  /** Map canonical `jurisdiction_id` (e.g. ch_zh) to facet code CH|AT|DE|LI. */
  private inferJurisdictionFromCanonicalId(jurisdictionId: string): string | undefined {
    const prefix = jurisdictionId.split('_')[0]?.toUpperCase();
    if (prefix === 'CH' || prefix === 'AT' || prefix === 'DE' || prefix === 'LI') {
      return prefix;
    }
    return undefined;
  }

  private countArrayLike(values: unknown[]): number {
    for (const value of values) {
      if (Array.isArray(value)) {
        return value.length;
      }
    }
    return 0;
  }

  private firstString(values: unknown[]): string | undefined {
    for (const value of values) {
      if (typeof value === 'string' && value.trim()) {
        return value.trim();
      }
    }
    return undefined;
  }

  private firstNormalizedDocumentType(values: unknown[]): string | undefined {
    for (const value of values) {
      const normalized = normalizeDocumentType(typeof value === 'string' ? value : undefined);
      if (normalized) {
        return normalized;
      }
    }
    return undefined;
  }

  private firstNestedString(
    source: Record<string, unknown>,
    paths: string[][],
  ): string | undefined {
    for (const path of paths) {
      let current: unknown = source;
      for (const key of path) {
        if (!current || typeof current !== 'object') {
          current = undefined;
          break;
        }
        current = (current as Record<string, unknown>)[key];
      }
      if (typeof current === 'string' && current.trim()) {
        return current.trim();
      }
    }
    return undefined;
  }

  private extractStructuredBodyTitle(value: unknown): string | undefined {
    if (typeof value !== 'string') return undefined;
    try {
      const parsed = JSON.parse(value.trim()) as unknown;
      return this.findFirstStringByKey(parsed, 'title');
    } catch {
      return undefined;
    }
  }

  private findFirstStringByKey(value: unknown, key: string): string | undefined {
    if (!value || typeof value !== 'object') return undefined;
    if (Array.isArray(value)) {
      for (const item of value) {
        const nested = this.findFirstStringByKey(item, key);
        if (nested) return nested;
      }
      return undefined;
    }

    const record = value as Record<string, unknown>;
    const direct = record[key];
    if (typeof direct === 'string' && direct.trim()) {
      return this.normalizeTitle(direct);
    }

    for (const nested of Object.values(record)) {
      const found = this.findFirstStringByKey(nested, key);
      if (found) return found;
    }

    return undefined;
  }

  private firstTranslationStatus(
    source: Record<string, unknown>,
    originalLanguage?: string,
  ): 'original' | 'machine_translated' | 'translation_unavailable' | undefined {
    const explicit = this.firstNestedString(source, [
      ['metadata', 'translation_status'],
      ['translation_status'],
    ]);
    if (
      explicit === 'original' ||
      explicit === 'machine_translated' ||
      explicit === 'translation_unavailable'
    ) {
      return explicit;
    }
    if (originalLanguage) {
      return 'original';
    }
    return undefined;
  }

  private inferJurisdiction(corpusId: string): string | undefined {
    const tokens = corpusId
      .toLowerCase()
      .split(/[^a-z0-9]+/)
      .filter(Boolean);
    if (tokens.includes('ch')) return 'CH';
    if (tokens.includes('at')) return 'AT';
    if (tokens.includes('de')) return 'DE';
    if (tokens.includes('li')) return 'LI';
    this.logger.warn(`[contract] unknown_corpus_jurisdiction`, { corpusId });
    return undefined;
  }

  /**
   * Last-resort language guess from the corpus id (#572).
   *
   * Token-based on purpose: the previous substring match classified
   * `corpus_public_ch_fedlex_constitution` as Italian because the word
   * "cons-t-**it**-ution" contains the letters "it" — which is how the
   * German Federal Constitution ended up indexed with `language: it`.
   * A corpus id only carries a language when it has an explicit
   * language *token* (`..._de`), so match whole tokens and return
   * `undefined` rather than a confidently wrong facet value.
   */
  private inferLanguage(corpusId: string): string | undefined {
    const tokens = corpusId
      .toLowerCase()
      .split(/[^a-z0-9]+/)
      .filter(Boolean);
    for (const code of ['de', 'fr', 'it', 'en', 'rm']) {
      if (tokens.includes(code)) return code;
    }
    return undefined;
  }

  private extractSections(documentId: string, leanDocument: unknown): SectionProjection[] {
    if (!leanDocument || typeof leanDocument !== 'object') return [];
    const doc = leanDocument as Record<string, unknown>;
    const raw = doc.sections ?? doc.document_sections ?? doc.body_sections;
    if (!Array.isArray(raw)) return [];

    return raw
      .filter((s): s is Record<string, unknown> => s != null && typeof s === 'object')
      .map((s, index) => ({
        section_id: typeof s.section_id === 'string' ? s.section_id : `sec_${documentId}_${index}`,
        document_id: documentId,
        title: typeof s.title === 'string' ? s.title : undefined,
        ordinal: typeof s.ordinal === 'number' ? s.ordinal : index,
        depth: typeof s.depth === 'number' ? s.depth : 0,
        content_preview:
          typeof s.content === 'string'
            ? s.content.slice(0, 400)
            : typeof s.content_preview === 'string'
              ? s.content_preview
              : undefined,
        parent_section_id:
          typeof s.parent_section_id === 'string' ? s.parent_section_id : undefined,
      }));
  }

  private extractCitations(documentId: string, leanDocument: unknown): CitationProjection[] {
    if (!leanDocument || typeof leanDocument !== 'object') return [];
    const doc = leanDocument as Record<string, unknown>;
    const extensions = this.asRecord(doc.extensions);
    const raw = [
      ...this.asArrayOfRecords(doc.citations),
      ...this.asArrayOfRecords(doc.document_citations),
      ...this.asArrayOfRecords(extensions?.citations),
      ...this.extractSectionCitationRecords(doc),
    ];
    let counter = 0;
    return raw.map((c) => {
      counter++;
      return {
        citation_id:
          typeof c.citation_id === 'string' ? c.citation_id : `cit_${documentId}_${counter}`,
        source_document_id: documentId,
        source_section_id:
          typeof c.source_section_id === 'string' ? c.source_section_id : undefined,
        target_document_id:
          typeof c.target_document_id === 'string' ? c.target_document_id : undefined,
        target_title: typeof c.target_title === 'string' ? c.target_title : undefined,
        citation_text: typeof c.text === 'string' ? c.text : String(c.citation_text ?? ''),
        citation_type: typeof c.citation_type === 'string' ? c.citation_type : undefined,
        normalized_reference:
          typeof c.normalized_reference === 'string' ? c.normalized_reference : undefined,
        resolved: typeof c.resolved === 'boolean' ? c.resolved : false,
        metadata:
          typeof c.metadata === 'object' && c.metadata
            ? (c.metadata as Record<string, unknown>)
            : undefined,
      };
    });
  }

  /**
   * Extract commentary insights carried by the lean document, if present.
   *
   * Forward-compatible: if DI's lean document doesn't yet emit
   * `commentary_insights`, returns an empty list and the
   * `applyDocumentProcessed` flow runs unchanged. Each entry is
   * validated against the minimum fields needed to project — entries
   * missing `insight_id`, `jurisdiction_ids`, `authority_ids`, or
   * `source_document_ids` are skipped (the freeze requires these on
   * commentary records).
   */
  private extractCommentaryInsights(
    leanDocument: unknown,
    occurredAt: string,
  ): CommentaryInsightInput[] {
    if (!leanDocument || typeof leanDocument !== 'object') return [];
    const doc = leanDocument as Record<string, unknown>;
    const extensions = this.asRecord(doc.extensions);
    const candidates = [
      ...this.asArrayOfRecords(doc.commentary_insights),
      ...this.asArrayOfRecords(extensions?.commentary_insights),
    ];
    const insights: CommentaryInsightInput[] = [];
    for (const raw of candidates) {
      const insightId = typeof raw.insight_id === 'string' ? raw.insight_id.trim() : '';
      const documentId = typeof raw.document_id === 'string' ? raw.document_id.trim() : '';
      const documentRevision =
        typeof raw.document_revision === 'number' ? raw.document_revision : undefined;
      const processingManifestId =
        typeof raw.processing_manifest_id === 'string'
          ? raw.processing_manifest_id.trim()
          : undefined;
      const insightType = typeof raw.insight_type === 'string' ? raw.insight_type : undefined;
      const claim = typeof raw.claim === 'string' ? raw.claim : undefined;
      const displayText = typeof raw.display_text === 'string' ? raw.display_text : undefined;
      const confidence = typeof raw.confidence === 'number' ? raw.confidence : undefined;
      const reviewState = typeof raw.review_state === 'string' ? raw.review_state : undefined;
      const jurisdictionIds = this.extractCanonicalIdList(raw.jurisdiction_ids, /^jur_[a-z0-9_]+$/);
      const authorityIds = this.extractCanonicalIdList(raw.authority_ids, /^auth_[a-z0-9_]+$/);
      const sourceDocumentIds = this.extractDocumentIdList(raw.source_document_ids);

      if (
        !insightId ||
        !documentId ||
        documentRevision === undefined ||
        !processingManifestId ||
        !insightType ||
        !claim ||
        !displayText ||
        confidence === undefined ||
        !reviewState ||
        jurisdictionIds.length === 0 ||
        authorityIds.length === 0 ||
        sourceDocumentIds.length === 0
      ) {
        // Skip malformed entries silently — the freeze requires the
        // minimum field set, and a partial commentary record is worse
        // than none in the search index.
        this.logger.warn('commentary_insight_skipped_missing_fields', {
          insight_id: insightId || '<missing>',
          document_id: documentId || '<missing>',
        });
        continue;
      }

      insights.push({
        insight_id: insightId,
        document_id: documentId,
        document_revision: documentRevision,
        processing_manifest_id: processingManifestId,
        insight_type: insightType,
        claim,
        display_text: displayText,
        language: typeof raw.language === 'string' ? raw.language : null,
        jurisdiction_id:
          typeof raw.jurisdiction_id === 'string' && raw.jurisdiction_id.trim()
            ? raw.jurisdiction_id.trim()
            : null,
        jurisdiction_ids: jurisdictionIds,
        authority_ids: authorityIds,
        source_document_ids: sourceDocumentIds,
        confidence,
        review_state: reviewState,
        occurred_at: occurredAt,
      });
    }
    return insights;
  }

  private extractDocumentIdList(value: unknown): string[] {
    if (!Array.isArray(value)) return [];
    const ids: string[] = [];
    for (const entry of value) {
      if (typeof entry !== 'string') continue;
      const trimmed = entry.trim().toLowerCase();
      if (/^doc_[0-9a-hjkmnp-tv-z]{26}$/.test(trimmed)) ids.push(trimmed);
    }
    return Array.from(new Set(ids));
  }

  private extractSectionCitationRecords(doc: Record<string, unknown>): Record<string, unknown>[] {
    const rawSections = doc.sections ?? doc.document_sections ?? doc.body_sections;
    const records: Record<string, unknown>[] = [];
    for (const section of this.asArrayOfRecords(rawSections)) {
      const sectionId = typeof section.section_id === 'string' ? section.section_id : undefined;
      const metadata = this.asRecord(section.metadata);
      for (const citation of this.asArrayOfRecords(metadata?.citations)) {
        records.push({
          ...citation,
          source_section_id:
            typeof citation.source_section_id === 'string' ? citation.source_section_id : sectionId,
        });
      }
    }
    return records;
  }

  private asArrayOfRecords(value: unknown): Record<string, unknown>[] {
    return Array.isArray(value)
      ? value.filter(
          (item): item is Record<string, unknown> =>
            item != null && typeof item === 'object' && !Array.isArray(item),
        )
      : [];
  }

  /**
   * Extract identifier→document_id mappings so other documents' citations can
   * resolve against our corpus. Identifiers include official_citation,
   * jurisdiction-specific codes (SR, CELEX, ECLI), and docket numbers.
   *
   * This is the NODE half of the citation graph (#582, ADR-0033). A citation
   * only becomes an edge if the norm it names is addressable here — so every
   * identifier this method fails to find is an edge that silently never forms.
   *
   * Where the identifiers actually live (verified against
   * `document-intelligence/tests/golden/ch_fedlex_law_html/`):
   *
   *   - `official_citation` — set by DI only when the source supplies one. The
   *     Fedlex SPARQL provider does NOT: it emits title, title_short and an ELI
   *     URI, and no SR number. So for Swiss federal law this is usually absent.
   *   - the document's MASTHEAD — Fedlex publishes the SR number in the title
   *     ("Bundesverfassung ... (SR 101)") and in the opening line of the body
   *     ("Vom 18. April 1999 (Stand am 1. Januar 2024), SR 101."). That is the
   *     document stating its own identifier, and it is the only deterministic
   *     SR source available without re-scraping.
   *
   * Scanning only the projection's NORMALIZED title (as this method previously
   * did) misses both: normalization strips the "(SR 101)" suffix. Result: zero
   * targets for every Fedlex document, so `citation-targets` was never even
   * created and all 504 extracted citations stayed unresolved.
   */
  private extractCitationTargets(
    projection: SearchProjectionDocument,
    leanDocument?: unknown | null,
  ): CitationTargetEntry[] {
    const targets: CitationTargetEntry[] = [];
    const base = {
      document_id: projection.document_id,
      title: projection.title,
      document_type: projection.document_type,
      jurisdiction: projection.jurisdiction,
    };

    if (projection.official_citation) {
      targets.push({
        ...base,
        identifier_type: 'official_citation',
        identifier_value: projection.official_citation,
      });
    }

    const text = this.citationTargetScanText(projection, leanDocument);

    const srMatch = text.match(/\bSR\s+(\d{3}(?:\.\d+)*)\b/i);
    if (srMatch) {
      targets.push({ ...base, identifier_type: 'sr', identifier_value: srMatch[1] });
    }

    const celexMatch = text.match(/\b([1-9]\d{4}[A-Z]{1,2}\d{4})\b/);
    if (celexMatch) {
      targets.push({ ...base, identifier_type: 'celex', identifier_value: celexMatch[1] });
    }

    const ecliMatch = text.match(/\bECLI:[A-Z]{2}:[A-Z0-9]+:\d{4}:[A-Z0-9.]+\b/i);
    if (ecliMatch) {
      targets.push({
        ...base,
        identifier_type: 'ecli',
        identifier_value: ecliMatch[0].toUpperCase(),
      });
    }

    const atBgblRef = this.extractAustrianBgblReference(projection, leanDocument);
    if (atBgblRef) {
      targets.push({ ...base, identifier_type: 'at_bgbl', identifier_value: atBgblRef });
    }

    targets.push(...this.extractAbbreviationTargets(base, projection, leanDocument));

    return targets.filter(
      (target, index, all) =>
        all.findIndex(
          (other) =>
            other.identifier_type === target.identifier_type &&
            other.identifier_value === target.identifier_value,
        ) === index,
    );
  }

  /**
   * Mint the short-title nodes: `abbrev:BV` for the statute, and
   * `abbrev_art:BV/36` for each of its article-level sections.
   *
   * This is what makes "Art. 36 BV" resolvable WITHOUT search. The corpus
   * supplies the abbreviation itself — Fedlex's `title_short` is literally the
   * short title — so the mapping from short form to norm is a fact we hold,
   * not an inference. Nothing here consults a dictionary of what `BV` "means";
   * if a document does not publish a `title_short`, it mints no abbreviation
   * node and citations to it stay honestly unresolved.
   *
   * Only legislation mints these. A decision that merely discusses the BV must
   * never become addressable AS the BV.
   */
  private extractAbbreviationTargets(
    base: Omit<CitationTargetEntry, 'identifier_type' | 'identifier_value'>,
    projection: SearchProjectionDocument,
    leanDocument?: unknown | null,
  ): CitationTargetEntry[] {
    if (projection.document_type !== 'law') return [];

    const shortTitle = this.extractShortTitle(leanDocument);
    if (!shortTitle || !isLegalAbbreviation(shortTitle)) return [];

    const targets: CitationTargetEntry[] = [
      { ...base, identifier_type: 'abbrev', identifier_value: shortTitle },
    ];

    for (const section of this.asArrayOfRecords(
      this.asRecord(leanDocument)?.sections ??
        this.asRecord(leanDocument)?.document_sections ??
        this.asRecord(leanDocument)?.body_sections,
    )) {
      const title = typeof section.title === 'string' ? section.title : '';
      // Article-level sections announce themselves: "Art. 36 Einschränkungen
      // von Grundrechten". The number is taken from the HEAD of the section
      // title only — a number anywhere else in the heading is not the
      // article's own number.
      const match = title.match(/^\s*Art\.?\s+(\d+(?:bis|ter|quater|quinquies|sexies)?)\b/);
      if (!match) continue;

      const sectionId = typeof section.section_id === 'string' ? section.section_id : undefined;
      if (!sectionId) continue;

      const anchor = [section.anchor, section.anchor_id, section.section_anchor].find(
        (value): value is string => typeof value === 'string' && value.trim().length > 0,
      );

      targets.push({
        ...base,
        identifier_type: 'abbrev_art',
        identifier_value: `${shortTitle}/${match[1]}`,
        section_id: sectionId,
        section_anchor: anchor ?? `art_${match[1]}`,
      });
    }

    return targets;
  }

  /**
   * The document's own short title (`BV`), as published by the source.
   *
   * Fedlex delivers it inside the provider payload nested in `body_text`,
   * which is the same place `extractStructuredTitleFromValue` reads the real
   * title from.
   */
  private extractShortTitle(leanDocument?: unknown | null): string | undefined {
    const direct = this.asRecord(leanDocument)?.title_short;
    if (typeof direct === 'string' && direct.trim()) return direct.trim();

    const bodyText = this.asRecord(leanDocument)?.body_text;
    return this.extractShortTitleFromValue(bodyText);
  }

  private extractShortTitleFromValue(value: unknown): string | undefined {
    if (typeof value !== 'string') return undefined;
    const trimmed = value.trim();
    if (!trimmed.startsWith('{') && !trimmed.startsWith('[')) return undefined;
    try {
      const record = this.asRecord(JSON.parse(trimmed) as unknown);
      if (!record) return undefined;
      if (typeof record.title_short === 'string' && record.title_short.trim()) {
        return record.title_short.trim();
      }
      return this.extractShortTitleFromValue(record.inline_body);
    } catch {
      return undefined;
    }
  }

  /**
   * The text a document is allowed to declare its OWN identifier in.
   *
   * The distinction that keeps this honest: an SR number in a document's
   * masthead is that document's identity; the same SR number 40 paragraphs
   * down is a citation to a different norm. Confusing the two would make a
   * cantonal decree claim to BE the civil code and corrupt every edge that
   * points at it — a wrong edge is worse than a missing one.
   *
   * So the body is scanned only within a short masthead window, and only for
   * documents that are legislation (`document_type: 'law'`, DI's normalized
   * form of `legislation`). Case law and commentary declare no SR number of
   * their own and would only ever match a citation.
   */
  private citationTargetScanText(
    projection: SearchProjectionDocument,
    leanDocument?: unknown | null,
  ): string {
    const parts = [
      projection.title,
      projection.official_citation,
      projection.structural_path,
      // The RAW lean-document title, before `normalizeTitle` strips the
      // parenthetical: this is where Fedlex puts "(SR 101)".
      this.rawLeanTitle(leanDocument),
    ];

    if (projection.document_type === 'law') {
      parts.push(this.mastheadText(leanDocument));
    }

    return parts.filter(Boolean).join(' ');
  }

  /** The lean document's untouched `title`, if any. */
  private rawLeanTitle(leanDocument?: unknown | null): string | undefined {
    if (!leanDocument || typeof leanDocument !== 'object') return undefined;
    const doc = leanDocument as Record<string, unknown>;
    return typeof doc.title === 'string' && doc.title.trim() ? doc.title : undefined;
  }

  /**
   * The opening window of the document body, where a statute states its own
   * identifier. Bounded deliberately: a wider window starts swallowing the
   * document's citations to OTHER norms.
   */
  private mastheadText(leanDocument?: unknown | null): string | undefined {
    if (!leanDocument || typeof leanDocument !== 'object') return undefined;
    const doc = leanDocument as Record<string, unknown>;
    const body = [doc.body_text, doc.full_text, doc.content_text, doc.text].find(
      (value): value is string => typeof value === 'string' && value.trim().length > 0,
    );
    return body?.slice(0, ProjectionsService.MASTHEAD_WINDOW_CHARS);
  }

  private extractAustrianBgblReference(
    projection: SearchProjectionDocument,
    leanDocument?: unknown | null,
  ): string | undefined {
    const candidates = [
      projection.official_citation,
      this.extractPublicationOrganText(leanDocument),
    ];
    for (const candidate of candidates) {
      if (!candidate) continue;
      const match = candidate.match(/\bBGBl\.\s*(?:[IVX]+\s+)?Nr\.\s*(\d+)\/(\d{4})\b/i);
      if (match) {
        return `${match[1]}/${match[2]}`;
      }
    }
    return undefined;
  }

  private extractPublicationOrganText(leanDocument: unknown): string | undefined {
    if (!leanDocument || typeof leanDocument !== 'object') return undefined;
    const doc = leanDocument as Record<string, unknown>;
    for (const section of this.asArrayOfRecords(
      doc.sections ?? doc.document_sections ?? doc.body_sections,
    )) {
      const title = typeof section.title === 'string' ? section.title.trim().toLowerCase() : '';
      if (
        title !== 'kundmachungsorgan' &&
        title !== 'publication_organ' &&
        title !== 'kundmachungsorgan/publikationsorgan'
      ) {
        continue;
      }
      const content = typeof section.content === 'string' ? section.content.trim() : undefined;
      if (content) {
        return content;
      }
    }
    return undefined;
  }

  async resolveCitations(citations: CitationProjection[]): Promise<CitationProjection[]> {
    const resolvable = citations.filter((c) => c.normalized_reference && !c.resolved);
    if (resolvable.length === 0) return citations;

    const refs = [...new Set(resolvable.map((c) => c.normalized_reference!))];
    let resolved: Map<string, CitationTargetMatch>;
    try {
      resolved = await this.repository.resolveCitationTargets(refs);
    } catch {
      this.logger.warn('citation_resolution_failed_fallback_unresolved');
      return citations;
    }
    if (resolved.size === 0) return citations;

    return citations.map((c) => {
      if (!c.normalized_reference || c.resolved) return c;
      const match = resolved.get(c.normalized_reference);
      if (!match) return c;
      return {
        ...c,
        target_document_id: match.document_id,
        target_title: match.title,
        resolved: true,
      };
    });
  }

  private async appendHistory(
    event: DocumentProcessedEventDto,
    status: ProjectionHistoryEntry['status'],
    notes?: string,
  ): Promise<void> {
    await this.repository.appendHistory({
      eventId: event.event_id,
      eventType: event.event_type,
      documentId: event.payload.document_id,
      documentRevision: event.payload.document_revision,
      processingManifestId: event.payload.processing_manifest_id,
      runId: event.payload.provenance.run_id,
      occurredAt: event.occurred_at,
      status,
      notes,
    });
  }

  private async appendWithdrawnHistory(
    event: DocumentWithdrawnEventDto,
    status: ProjectionHistoryEntry['status'],
    notes?: string,
  ): Promise<void> {
    await this.repository.appendHistory({
      eventId: event.event_id,
      eventType: event.event_type,
      documentId: event.payload.document_id,
      documentRevision: event.payload.document_revision,
      processingManifestId: event.payload.processing_manifest_id,
      runId: event.payload.provenance.run_id,
      occurredAt: event.occurred_at,
      status,
      notes,
    });
  }
}
