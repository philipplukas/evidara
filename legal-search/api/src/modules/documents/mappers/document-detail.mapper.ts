/**
 * Document detail ViewModel mapper.
 *
 * Composes DetailView from DocumentEntity + sections + citations.
 * Observable fallbacks via WarnFn (ADR-0012).
 */

import type { WarnFn } from '../../../core/types/warn';
import { DOCUMENT_TYPE_LABELS, JURISDICTION_META } from '../../../core/vocabularies';
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

// Badge colors are resolved via DOCUMENT_TYPE_LABELS + per-type config in search-result.mapper.

// ─── Composition ───

function composeSubtitle(doc: DocumentEntity, warn?: WarnFn): string {
  const parts: string[] = [];
  const jurisdiction = JURISDICTION_META[doc.jurisdiction ?? ''];

  if (doc.jurisdiction && !jurisdiction) {
    warn?.('unknown_jurisdiction_detail', {
      document_id: doc.document_id,
      jurisdiction: doc.jurisdiction,
    });
  }

  if (jurisdiction) parts.push(jurisdiction.label);

  const typeLabel = DOCUMENT_TYPE_LABELS[doc.document_type ?? ''];
  if (doc.document_type && !typeLabel) {
    warn?.('unknown_document_type_detail', {
      document_id: doc.document_id,
      document_type: doc.document_type,
    });
  }
  if (typeLabel) parts.push(typeLabel);

  return parts.join(' · ') || (doc.document_type ?? 'Dokument');
}

function composeMetadata(
  doc: DocumentEntity,
): { label: string; value: string; iconKey?: string }[] {
  const rows: { label: string; value: string; iconKey?: string }[] = [];

  if (doc.effective_date) {
    const label = doc.document_type === 'decision' ? 'Datum' : 'In Kraft';
    rows.push({ label, value: doc.effective_date });
  }
  if (doc.jurisdiction) {
    const meta = JURISDICTION_META[doc.jurisdiction];
    rows.push({
      label: 'Zuständigkeit',
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
): { key: string; label: string; count?: number }[] {
  const tabs: { key: string; label: string; count?: number }[] = [
    { key: 'content', label: 'Inhalt' },
  ];

  if (sectionsCount > 0) {
    tabs.push({ key: 'sections', label: 'Abschnitte', count: sectionsCount });
  }
  if (citationsCount > 0) {
    tabs.push({
      key: 'citations',
      label: 'Zitationen',
      count: citationsCount,
    });
  }

  tabs.push({ key: 'details', label: 'Details' });

  return tabs;
}

function composeReferences(citations: CitationEntity[]): DetailView['references'] {
  if (citations.length === 0) return [];

  // Group by citation type
  const groups = new Map<string, DetailView['references'][0]>();
  for (const cit of citations) {
    const groupLabel = cit.citation_type ?? 'Referenzen';
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
): DetailView['localStructure'] | undefined {
  if (sections.length === 0) return undefined;

  return {
    items: sections
      .sort((a, b) => (a.ordinal ?? 0) - (b.ordinal ?? 0))
      .map((s) => ({
        id: s.section_id,
        label: s.title ?? `Abschnitt ${s.ordinal ?? 0}`,
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
  warn?: WarnFn,
): DetailView {
  const sectionsCount = doc.sections_count ?? sections.length;
  const citationsCount = doc.citations_count ?? citations.length;

  return {
    id: doc.document_id,
    type: doc.document_type ?? 'unknown',
    title: doc.title,
    subtitle: composeSubtitle(doc, warn),
    metadata: composeMetadata(doc),
    tabs: composeTabs(doc, sectionsCount, citationsCount),
    relatedGroups: [],
    references: composeReferences(citations),
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
      localStructure: composeLocalStructure(sections),
    }),
  };
}
