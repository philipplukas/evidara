/**
 * Document detail ViewModel mapper.
 *
 * Composes DetailView from DocumentEntity + sections + citations.
 * Accepts locale parameter for all composed labels (ADR-0013).
 * Observable fallbacks via WarnFn (ADR-0012).
 */

import type { SupportedLocale } from '../../../core/i18n';
import { DEFAULT_LOCALE, t } from '../../../core/i18n';
import type { WarnFn } from '../../../core/types/warn';
import { getDocumentTypeLabel, getJurisdictionMeta } from '../../../core/vocabularies';
import type { CitationEntity, DocumentEntity, SectionEntity } from '../entities/document.entities';

// ─── ViewModel Types ───

export interface DetailView {
  id: string;
  type: string;
  title: string;
  subtitle: string;
  breadcrumbs?: string[];
  metadata: { label: string; value: string; iconKey?: string }[];
  content?: unknown;
  contentLanguage?: {
    display: string;
    original: string;
    isTranslation: boolean;
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

  return parts.join(' · ') || (doc.document_type ?? t('labels.document', locale));
}

function composeMetadata(
  doc: DocumentEntity,
  locale: SupportedLocale,
): { label: string; value: string; iconKey?: string }[] {
  const rows: { label: string; value: string; iconKey?: string }[] = [];

  if (doc.effective_date) {
    const label =
      doc.document_type === 'decision' ? t('metadata.date', locale) : t('metadata.inForce', locale);
    rows.push({ label, value: doc.effective_date });
  }
  if (doc.jurisdiction) {
    const meta = getJurisdictionMeta(doc.jurisdiction, locale);
    rows.push({
      label: t('metadata.jurisdiction', locale),
      value: meta?.label ?? doc.jurisdiction,
      ...(meta?.iconKey && { iconKey: meta.iconKey }),
    });
  }

  return rows;
}

function composeTabs(
  _doc: DocumentEntity,
  sectionsCount: number,
  citationsCount: number,
  locale: SupportedLocale,
): { key: string; label: string; count?: number }[] {
  const tabs: { key: string; label: string; count?: number }[] = [
    { key: 'content', label: t('tabs.content', locale) },
  ];

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
    ...(doc.content_docling !== undefined &&
      doc.content_docling !== null && { content: doc.content_docling }),
    ...(doc.language && {
      contentLanguage: {
        display: doc.language,
        original: doc.language,
        isTranslation: false,
      },
    }),
    ...(sections.length > 0 && {
      localStructure: composeLocalStructure(sections, locale),
    }),
  };
}
