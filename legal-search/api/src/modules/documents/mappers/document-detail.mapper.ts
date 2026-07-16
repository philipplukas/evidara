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
  formatLanguageDisplay,
  formatLifecycleStatus,
  formatMessage,
  t,
} from '../../../core/i18n';
import {
  iconKeyForDocumentType,
  METADATA_ROW_ICONS,
} from '../../../core/presentation/metadata-icons';
import type { WarnFn } from '../../../core/types/warn';
import { getDocumentTypeLabel, getJurisdictionMeta } from '../../../core/vocabularies';
import type { CitationEntity, DocumentEntity, SectionEntity } from '../entities/document.entities';

/**
 * A body is only a body if it carries text. Whitespace-only `content` would
 * otherwise advertise an "Inhalt" tab over an empty document.
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
  metadata: {
    label: string;
    value: string;
    iconKey?: string;
    visibility?: 'always' | 'default' | 'expanded';
  }[];
  /** The document body text — plain text, paragraphs split by blank lines. */
  content?: string;
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
    }[];
  }[];
  annotations: { id: string; label: string; text: string; type?: string }[];
  localStructure?: {
    items: { id: string; label: string; depth?: number; active?: boolean }[];
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

type MetadataRowView = {
  label: string;
  value: string;
  iconKey?: string;
  visibility?: 'always' | 'default' | 'expanded';
};

function composeMetadata(doc: DocumentEntity, locale: SupportedLocale): MetadataRowView[] {
  const rows: MetadataRowView[] = [];
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
    const label = isDecision ? t('metadata.date', locale) : t('metadata.inForce', locale);
    rows.push({
      label,
      value: doc.effective_date,
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
  if (citationsCount > 0) {
    tabs.push({
      key: 'citations',
      label: t('tabs.citations', locale),
      count: citationsCount,
    });
  }

  tabs.push({ key: 'details', label: t('tabs.details', locale) });

  return tabs;
}

function composeReferences(
  citations: CitationEntity[],
  locale: SupportedLocale,
): DetailView['references'] {
  if (citations.length === 0) return [];

  // Group by citation type
  const groups = new Map<string, DetailView['references'][0]>();
  for (const cit of citations) {
    const groupLabel = cit.citation_type ?? t('labels.references', locale);
    if (!groups.has(groupLabel)) {
      groups.set(groupLabel, { label: groupLabel, items: [] });
    }
    groups.get(groupLabel)!.items.push({
      id: cit.citation_id,
      title: cit.target_title ?? cit.citation_text,
      citation: cit.citation_text,
      ...(cit.target_document_id && {
        href: `/documents/${cit.target_document_id}`,
      }),
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

  return {
    id: doc.document_id,
    type: doc.document_type ?? 'unknown',
    title: doc.title,
    subtitle: composeSubtitle(doc, locale, warn),
    metadata: composeMetadata(doc, locale),
    tabs: composeTabs(doc, sectionsCount, citationsCount, locale),
    relatedGroups: [],
    references: composeReferences(citations, locale),
    annotations: [],
    // Optional fields — omit when absent (ADR-0011)
    ...(doc.structural_path && {
      breadcrumbs: doc.structural_path.split(' › '),
    }),
    ...(hasBodyText(doc.content) && { content: doc.content }),
    ...(composeContentLanguage(doc, locale) && {
      contentLanguage: composeContentLanguage(doc, locale),
    }),
    ...(sections.length > 0 && {
      localStructure: composeLocalStructure(sections, locale),
    }),
  };
}
