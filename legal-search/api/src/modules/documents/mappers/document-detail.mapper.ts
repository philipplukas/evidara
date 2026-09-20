/**
 * Document detail ViewModel mapper.
 *
 * Composes DetailView from DocumentEntity + sections + citations.
 * Accepts locale parameter for all composed labels (ADR-0013).
 * Observable fallbacks via WarnFn (ADR-0012).
 */

import type { SupportedLocale } from '../../../core/i18n';
import {
  DEFAULT_LOCALE,
  formatIsoDateDisplay,
  formatLanguageDisplay,
  formatLifecycleStatus,
  formatMessage,
  t,
} from '../../../core/i18n';
import { effectiveDateLabel } from '../../../core/presentation/effective-date';
import {
  iconKeyForDocumentType,
  METADATA_ROW_ICONS,
} from '../../../core/presentation/metadata-icons';
import type { WarnFn } from '../../../core/types/warn';
import { getDocumentTypeLabel, getJurisdictionMeta } from '../../../core/vocabularies';
import type { CitationUnresolvedReason } from '../../citations/citation-resolution';
import type { CitationEntity, DocumentEntity, SectionEntity } from '../entities/document.entities';

/**
 * A body is only a body if it carries text. Whitespace-only `content` would
 * otherwise advertise an "Inhalt" tab over an empty document.
 *
 * The same rule governs `regeste`: the index stores whatever the seed wrote,
 * including `''`, and an empty headnote must be omitted rather than shipped —
 * the client cannot distinguish "no Regeste" from "a Regeste that is blank"
 * once the key is present.
 */
function hasBodyText(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0;
}

// ─── ViewModel Types ───

export interface DetailView {
  id: string;
  type: string;
  title: string;
  subtitle: string;
  breadcrumbs?: string[];
  metadata: DetailMetadataRowView[];
  /** The document body text — plain text, paragraphs split by blank lines. */
  content?: string;
  /**
   * The official headnote (Regeste) of a court decision, as prose. Omitted
   * when the document carries none or carries only whitespace — an empty
   * string here would have the client draw a labelled box around nothing.
   */
  regeste?: string;
  contentLanguage?: {
    display: string;
    original: string;
    isTranslation: boolean;
    label?: string;
  };
  tabs: { key: string; label: string; count?: number }[];
  relatedGroups: {
    label: string;
    items: {
      id: string;
      title: string;
      subtitle?: string;
      badge?: { label: string; colorKey: string };
      href?: string;
    }[];
  }[];
  references: {
    label: string;
    items: {
      id: string;
      title: string;
      citation: string;
      href?: string;
      /**
       * The document the citation resolves to, present exactly when `href` is.
       * The reader navigates by document id (`?item=`), not by URL path, so it
       * gets the id rather than re-parsing a display href.
       */
      targetDocumentId?: string;
      /**
       * Whether the corpus holds the cited norm. Required, and `false` is a
       * real answer the client must render differently — see
       * `composeReferences`.
       */
      resolved: boolean;
      /** Why not, when the index recorded a reason. */
      unresolvedReason?: CitationUnresolvedReason;
    }[];
  }[];
  annotations: { id: string; label: string; text: string; type?: string }[];
  localStructure?: {
    items: { id: string; label: string; depth?: number; active?: boolean; text?: string }[];
  };
}

// ─── Composition ───

function composeSubtitle(doc: DocumentEntity, locale: SupportedLocale, warn?: WarnFn): string {
  const parts: string[] = [];
  const jurisdictionMeta = getJurisdictionMeta(doc.jurisdiction ?? '', locale);

  if (doc.jurisdiction && !jurisdictionMeta) {
    warn?.('unknown_jurisdiction_detail', {
      document_id: doc.document_id,
      jurisdiction: doc.jurisdiction,
    });
  }

  if (jurisdictionMeta) parts.push(jurisdictionMeta.label);

  if (doc.document_type) {
    const typeLabel = getDocumentTypeLabel(doc.document_type, locale);
    if (typeLabel !== doc.document_type) {
      // Only push if we have a real label, not just the raw code
      parts.push(typeLabel);
    } else {
      warn?.('unknown_document_type_detail', {
        document_id: doc.document_id,
        document_type: doc.document_type,
      });
    }
  }
  if (doc.authority_name) {
    parts.push(doc.authority_name);
  }

  return parts.join(' · ') || t('labels.document', locale);
}

/**
 * A detail metadata row. `visibility` is REQUIRED — the BFF owns the density
 * decision because `label` is localized ("Rechtsordnung", "In Kraft") and the
 * frontend cannot key a rule off it across locales (#787). Making it required
 * here is what stops a new `rows.push` from silently reaching the reader with
 * no visibility, which `filterByDensity` would then hide at default density.
 */
export type DetailMetadataRowView = {
  label: string;
  value: string;
  iconKey?: string;
  visibility: 'always' | 'default' | 'expanded';
};

function composeMetadata(doc: DocumentEntity, locale: SupportedLocale): DetailMetadataRowView[] {
  const rows: DetailMetadataRowView[] = [];
  const documentTypeLabel = doc.document_type
    ? getDocumentTypeLabel(doc.document_type, locale)
    : undefined;
  const isDecision = doc.document_type === 'decision';

  if (doc.lifecycle_status && doc.lifecycle_status !== 'active') {
    rows.push({
      label: t('metadata.status', locale),
      value: formatLifecycleStatus(doc.lifecycle_status, locale),
      iconKey: METADATA_ROW_ICONS.status,
      visibility: 'always',
    });
  }
  if (doc.document_type && documentTypeLabel && documentTypeLabel !== doc.document_type) {
    rows.push({
      label: t('facets.documentType', locale),
      value: documentTypeLabel,
      iconKey: iconKeyForDocumentType(doc.document_type),
      visibility: 'default',
    });
  }
  if (doc.effective_date) {
    rows.push({
      label: effectiveDateLabel(doc.document_type, locale),
      value: formatIsoDateDisplay(doc.effective_date),
      iconKey: METADATA_ROW_ICONS.calendar,
      visibility: 'always',
    });
  }
  if (doc.authority_name) {
    rows.push({
      label: t('metadata.authority', locale),
      value: doc.authority_name,
      iconKey: METADATA_ROW_ICONS.authority,
      visibility: isDecision ? 'always' : 'default',
    });
  }
  if (doc.official_citation) {
    rows.push({
      label: t('metadata.citation', locale),
      value: doc.official_citation,
      iconKey: METADATA_ROW_ICONS.citation,
      visibility: 'always',
    });
  }
  if (doc.is_official) {
    rows.push({
      label: t('metadata.source', locale),
      value: t('metadata.officialSource', locale),
      iconKey: METADATA_ROW_ICONS.official,
      visibility: 'expanded',
    });
  }
  if (doc.jurisdiction) {
    const meta = getJurisdictionMeta(doc.jurisdiction, locale);
    rows.push({
      label: t('metadata.jurisdiction', locale),
      value: meta?.label ?? doc.jurisdiction,
      ...(meta?.iconKey && { iconKey: meta.iconKey }),
      visibility: 'always',
    });
  }
  if (doc.language) {
    rows.push({
      label: t('metadata.language', locale),
      value: formatLanguageDisplay(doc.language),
      iconKey: METADATA_ROW_ICONS.language,
      visibility: 'default',
    });
  }

  return rows;
}

function composeTabs(
  doc: DocumentEntity,
  sectionsCount: number,
  citationsCount: number,
  hasReferences: boolean,
  locale: SupportedLocale,
): { key: string; label: string; count?: number }[] {
  const tabs: { key: string; label: string; count?: number }[] = [];

  // Only advertise "Inhalt" when the response actually carries a body.
  // This tab used to be unconditional, which promised a document text that
  // the response never included.
  if (hasBodyText(doc.content)) {
    tabs.push({ key: 'content', label: t('tabs.content', locale) });
  }

  if (sectionsCount > 0) {
    tabs.push({ key: 'sections', label: t('tabs.sections', locale), count: sectionsCount });
  }
  // Same honesty rule as "Inhalt" above: only advertise the citations tab when
  // the response actually carries the reference groups that render it.
  // `citations_count` comes from the documents index while the citations
  // themselves come from a separate query, so the two can disagree — a lagging
  // or empty citations index otherwise produced a confident "Zitate (15)" tab
  // over an empty payload (#622).
  if (hasReferences) {
    tabs.push({
      key: 'citations',
      label: t('tabs.citations', locale),
      count: citationsCount,
    });
  }

  tabs.push({ key: 'details', label: t('tabs.details', locale) });

  return tabs;
}

/**
 * German (or French) name for a citation type code.
 *
 * `citation_type` is a machine code — production carries `sr`, `article`,
 * `ch_paragraph`, `de_paragraph`, `eu_directive` and `eu_regulation` across
 * the 8,234 rows of the `citations` index. This function used not to exist:
 * the group heading was the raw code, so a German-language legal UI printed
 * headings reading "sr" and "article" over the reference groups, and
 * `labels.references` — the only translated string in the path — fired only
 * for the rare row with no type at all.
 *
 * An unmapped code falls back to the code itself rather than to a generic
 * word. A new upstream type must be *visible* as untranslated, not quietly
 * absorbed into "Verweise": the guard in `terminology.spec.ts` asserts the
 * mapped set, and a code that slips through should look wrong on screen.
 */
function citationTypeLabel(citationType: string, locale: SupportedLocale): string {
  const key = `citationTypes.${citationType.trim().toLowerCase()}`;
  const label = t(key, locale);
  return label === key ? citationType : label;
}

function composeReferences(
  citations: CitationEntity[],
  locale: SupportedLocale,
): DetailView['references'] {
  if (citations.length === 0) return [];

  // Group by citation type
  const groups = new Map<string, DetailView['references'][0]>();
  for (const cit of citations) {
    const groupLabel = cit.citation_type
      ? citationTypeLabel(cit.citation_type, locale)
      : t('labels.references', locale);
    if (!groups.has(groupLabel)) {
      groups.set(groupLabel, { label: groupLabel, items: [] });
    }
    // Resolution is decided by `target_document_id` and nothing else.
    //
    // That field is what `href` is built from, and `DocumentsService.
    // joinUnresolvedCitations` fills it in at read time for edges the index
    // wrote before their target was projected. The index's own `resolved`
    // flag is a write-time denormalization that goes stale in BOTH
    // directions, so keying the link off it would either hide a link the
    // corpus can now serve or advertise one it cannot.
    //
    // `resolved: false` is the answer, not the absence of one: the four
    // citations on the ZH Hundegesetz all carry `no_target_in_corpus`, and
    // rendering them as rows identical to resolvable ones is the reader
    // claiming a norm is reachable when the corpus says it is not (ADR-0052,
    // #1040).
    const resolved = Boolean(cit.target_document_id);
    groups.get(groupLabel)!.items.push({
      id: cit.citation_id,
      title: cit.target_title ?? cit.citation_text,
      citation: cit.citation_text,
      resolved,
      ...(cit.target_document_id && {
        targetDocumentId: cit.target_document_id,
        href: `/documents/${cit.target_document_id}`,
      }),
      // Only when it is both unresolved AND the index said why. An
      // unresolved row with no recorded reason still reports unresolved; it
      // does not acquire an invented cause.
      ...(!resolved && cit.unresolved_reason && { unresolvedReason: cit.unresolved_reason }),
    });
  }

  return Array.from(groups.values());
}

function composeLocalStructure(
  sections: SectionEntity[],
  locale: SupportedLocale,
): DetailView['localStructure'] | undefined {
  if (sections.length === 0) return undefined;

  return {
    items: sections
      .sort((a, b) => (a.ordinal ?? 0) - (b.ordinal ?? 0))
      .map((s) => ({
        id: s.section_id,
        label: s.title ?? `${t('labels.section', locale)} ${s.ordinal ?? 0}`,
        depth: s.depth,
        // The section's own text. The `sections` index carries it on all
        // 50,389 rows and this mapper used to drop it, so the outline
        // reached the reader as labels with nothing under them — a list, not
        // a structure (#1040). Same honesty rule as `content` and `regeste`
        // above: a whitespace-only preview is omitted rather than shipped, so
        // the client can tell "no text" from "blank text".
        ...(hasBodyText(s.content_preview) && { text: s.content_preview.trim() }),
      })),
  };
}

function composeContentLanguage(
  doc: DocumentEntity,
  locale: SupportedLocale,
): DetailView['contentLanguage'] | undefined {
  const display = doc.language;
  const original = doc.original_language ?? doc.language;
  if (!display || !original) return undefined;
  const status = doc.translation_status ?? 'original';
  return {
    display,
    original,
    isTranslation: status === 'machine_translated',
    label:
      status === 'machine_translated'
        ? formatMessage('contentLanguage.machineTranslatedFrom', { language: original }, locale)
        : status === 'translation_unavailable'
          ? t('contentLanguage.unavailable', locale)
          : t('contentLanguage.original', locale),
  };
}

// ─── Main Mapper ───

/** Map a DocumentEntity with its sections and citations to a complete DetailView. */
export function mapDocumentToDetailView(
  doc: DocumentEntity,
  sections: SectionEntity[],
  citations: CitationEntity[],
  locale: SupportedLocale = DEFAULT_LOCALE,
  warn?: WarnFn,
): DetailView {
  const sectionsCount = doc.sections_count ?? sections.length;
  const citationsCount = doc.citations_count ?? citations.length;
  const references = composeReferences(citations, locale);

  return {
    id: doc.document_id,
    type: doc.document_type ?? 'unknown',
    title: doc.title,
    subtitle: composeSubtitle(doc, locale, warn),
    metadata: composeMetadata(doc, locale),
    tabs: composeTabs(doc, sectionsCount, citationsCount, references.length > 0, locale),
    relatedGroups: [],
    references,
    annotations: [],
    // Optional fields — omit when absent (ADR-0011)
    ...(doc.structural_path && {
      breadcrumbs: doc.structural_path.split(' › '),
    }),
    ...(hasBodyText(doc.content) && { content: doc.content }),
    ...(hasBodyText(doc.regeste) && { regeste: doc.regeste.trim() }),
    ...(composeContentLanguage(doc, locale) && {
      contentLanguage: composeContentLanguage(doc, locale),
    }),
    ...(sections.length > 0 && {
      localStructure: composeLocalStructure(sections, locale),
    }),
  };
}
