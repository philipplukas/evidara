import { Inject, Injectable, Logger } from '@nestjs/common';
import { normalizeDocumentType } from '../../core/vocabularies';
import {
  DOCUMENT_INTELLIGENCE_CLIENT,
  type DocumentIntelligenceClient,
} from '../../lib/document-intelligence/document-intelligence.client';
import type {
  DocumentProcessedEventDto,
  DocumentWithdrawnEventDto,
} from './dto/projection-events.dto';
import {
  type CitationProjection,
  type CitationTargetEntry,
  type CitationTargetMatch,
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
      this.truncateForPreview(extracted.bodyPreviewFallback) ??
      event.payload.processing_version;
    const jurisdiction =
      extracted.jurisdictionFromCanonical ?? this.inferJurisdiction(provenance.corpus_id);
    const projection: SearchProjectionDocument = {
      document_id: event.payload.document_id,
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
      language: extracted.language ?? this.inferLanguage(provenance.corpus_id),
      content_preview: preview,
    };
    if (extracted.documentType) projection.document_type = extracted.documentType;
    if (extracted.effectiveDate) projection.effective_date = extracted.effectiveDate;
    if (extracted.structuralPath) projection.structural_path = extracted.structuralPath;
    return projection;
  }

  private extractLeanDocumentFields(leanDocument: unknown): {
    title?: string;
    language?: string;
    officialCitation?: string;
    originalLanguage?: string;
    translationStatus?: 'original' | 'machine_translated' | 'translation_unavailable';
    previewText?: string;
    bodyPreviewFallback?: string;
    sectionsCount: number;
    citationsCount: number;
    documentType?: string;
    effectiveDate?: string;
    structuralPath?: string;
    jurisdictionFromCanonical?: string;
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

    return {
      title: fallbackTitle,
      language,
      officialCitation,
      originalLanguage,
      translationStatus,
      previewText,
      bodyPreviewFallback,
      sectionsCount,
      citationsCount,
      documentType,
      effectiveDate,
      structuralPath,
      jurisdictionFromCanonical,
    };
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

  private inferLanguage(corpusId: string): string | undefined {
    if (corpusId.includes('de')) return 'de';
    if (corpusId.includes('fr')) return 'fr';
    if (corpusId.includes('it')) return 'it';
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

    // Extract structured identifiers from the content_preview or title
    // that match deterministic patterns (SR, CELEX, ECLI).
    const text = [projection.title, projection.official_citation, projection.structural_path]
      .filter(Boolean)
      .join(' ');

    const srMatch = text.match(/\bSR\s+(\d{3}(?:\.\d+)*)\b/);
    if (srMatch) {
      targets.push({ ...base, identifier_type: 'sr', identifier_value: srMatch[1] });
    }

    const celexMatch = text.match(/\b([1-9]\d{4}[A-Z]{1,2}\d{4})\b/);
    if (celexMatch) {
      targets.push({ ...base, identifier_type: 'celex', identifier_value: celexMatch[1] });
    }

    const ecliMatch = text.match(/\bECLI:[A-Z]{2}:[A-Z0-9]+:\d{4}:[A-Z0-9.]+\b/);
    if (ecliMatch) {
      targets.push({ ...base, identifier_type: 'ecli', identifier_value: ecliMatch[0] });
    }

    const atBgblRef = this.extractAustrianBgblReference(projection, leanDocument);
    if (atBgblRef) {
      targets.push({ ...base, identifier_type: 'at_bgbl', identifier_value: atBgblRef });
    }

    return targets.filter(
      (target, index, all) =>
        all.findIndex(
          (other) =>
            other.identifier_type === target.identifier_type &&
            other.identifier_value === target.identifier_value,
        ) === index,
    );
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
