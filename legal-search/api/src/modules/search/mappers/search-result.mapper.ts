/**
 * Search result ViewModel mapper.
 *
 * Pure functions that compose SearchResultView from SearchHitEntity.
 * This is the core BFF logic — it encodes the rules for badges, actions,
 * metadata rows, subtitle composition, etc.
 *
 * Observable fallbacks (ADR-0012):
 * - Unknown vocabulary values produce a warning via WarnFn, not silent degradation.
 * - Lookup tables are derived from contracts/vocabularies/*.json.
 *
 * ADR-0011 conventions:
 * - Array fields always present (empty [])
 * - Optional scalar fields omitted when absent
 */

import type { WarnFn } from '../../../core/types/warn';
import { DOCUMENT_TYPE_LABELS, JURISDICTION_META } from '../../../core/vocabularies';
import type { SearchHitEntity } from '../entities/search.entities';

// ─── Public Types (ViewModel shapes) ───

export interface BadgeView {
  label: string;
  colorKey: string;
  iconKey?: string;
}

export interface MetadataRowView {
  label: string;
  value: string;
  iconKey?: string;
}

export interface RelatedCountView {
  label: string;
  count: number;
  href?: string;
}

export interface ActionView {
  label: string;
  icon: string;
  href?: string;
}

export interface ContentLanguageView {
  display: string;
  original: string;
  isTranslation: boolean;
  label?: string;
}

export interface SearchResultView {
  id: string;
  type: string;
  title: string;
  subtitle: string;
  snippet: string;
  structuralContext?: string;
  badges: BadgeView[];
  metadataRows: MetadataRowView[];
  relatedCounts: RelatedCountView[];
  actions: ActionView[];
  contentLanguage?: ContentLanguageView;
}

// ─── Document Type Rules (presentation config) ───

interface DocumentTypeConfig {
  badgeLabel: string;
  badgeColorKey: string;
  actions: ActionView[];
}

const DOCUMENT_TYPE_CONFIG: Record<string, DocumentTypeConfig> = {
  law: {
    badgeLabel: DOCUMENT_TYPE_LABELS['law'] ?? 'Gesetz',
    badgeColorKey: 'blue',
    actions: [
      { label: 'Artikel öffnen', icon: 'file-text' },
      { label: 'Verwandt', icon: 'link' },
    ],
  },
  decision: {
    badgeLabel: DOCUMENT_TYPE_LABELS['decision'] ?? 'Gerichtsentscheid',
    badgeColorKey: 'pink',
    actions: [
      { label: 'Entscheid öffnen', icon: 'scale' },
      { label: 'Verwandt', icon: 'link' },
    ],
  },
  commentary: {
    badgeLabel: DOCUMENT_TYPE_LABELS['commentary'] ?? 'Kommentar',
    badgeColorKey: 'green',
    actions: [
      { label: 'Kommentar öffnen', icon: 'book-open' },
      { label: 'Artikel anzeigen', icon: 'file-text' },
    ],
  },
  rechtssatz: {
    badgeLabel: DOCUMENT_TYPE_LABELS['rechtssatz'] ?? 'Rechtssatz',
    badgeColorKey: 'indigo',
    actions: [
      { label: 'Öffnen', icon: 'bookmark' },
      { label: 'Verwandter Entscheid', icon: 'scale' },
    ],
  },
};

const DEFAULT_TYPE_CONFIG: DocumentTypeConfig = {
  badgeLabel: 'Dokument',
  badgeColorKey: 'slate',
  actions: [{ label: 'Öffnen', icon: 'file-text' }],
};

// ─── Composition Functions ───

/** Compose badge views from document type and jurisdiction. Warns on unknown values. */
export function composeBadges(hit: SearchHitEntity, warn?: WarnFn): BadgeView[] {
  const docType = hit.document_type ?? '';
  const config = DOCUMENT_TYPE_CONFIG[docType];

  if (docType && !config) {
    warn?.('unknown_document_type', {
      document_id: hit.document_id,
      document_type: hit.document_type,
    });
  }

  const resolvedConfig = config ?? DEFAULT_TYPE_CONFIG;
  const jurisdiction = JURISDICTION_META[hit.jurisdiction ?? ''];

  if (hit.jurisdiction && !jurisdiction) {
    warn?.('unknown_jurisdiction', {
      document_id: hit.document_id,
      jurisdiction: hit.jurisdiction,
    });
  }

  return [
    {
      label: resolvedConfig.badgeLabel,
      colorKey: resolvedConfig.badgeColorKey,
      ...(jurisdiction && { iconKey: jurisdiction.iconKey }),
    },
  ];
}

/** Compose subtitle from jurisdiction label and document type label. */
export function composeSubtitle(hit: SearchHitEntity, warn?: WarnFn): string {
  const parts: string[] = [];
  const jurisdiction = JURISDICTION_META[hit.jurisdiction ?? ''];

  if (hit.jurisdiction && !jurisdiction) {
    warn?.('unknown_jurisdiction_subtitle', {
      document_id: hit.document_id,
      jurisdiction: hit.jurisdiction,
    });
  }

  if (jurisdiction) parts.push(jurisdiction.label);

  const config = DOCUMENT_TYPE_CONFIG[hit.document_type ?? ''];
  if (config) {
    parts.push(config.badgeLabel);
  }

  return parts.join(' · ') || (hit.document_type ?? 'Dokument');
}

/** Compose metadata rows (date label varies by document type). */
export function composeMetadata(hit: SearchHitEntity): MetadataRowView[] {
  const rows: MetadataRowView[] = [];

  if (hit.effective_date) {
    const label = hit.document_type === 'decision' ? 'Datum' : 'In Kraft';
    rows.push({ label, value: hit.effective_date });
  }

  return rows;
}

/** Compose related-count chips from hit entity counts. */
export function composeRelatedCounts(hit: SearchHitEntity): RelatedCountView[] {
  const counts: RelatedCountView[] = [];

  if (hit.related_commentary_count && hit.related_commentary_count > 0) {
    counts.push({
      label: 'Kommentare',
      count: hit.related_commentary_count,
    });
  }
  if (hit.related_decisions_count && hit.related_decisions_count > 0) {
    counts.push({
      label: 'Gerichtsentscheide',
      count: hit.related_decisions_count,
    });
  }
  if (hit.citations_count && hit.citations_count > 0) {
    counts.push({ label: 'Zitationen', count: hit.citations_count });
  }

  return counts;
}

/** Compose action buttons from document type config. Warns on unknown types. */
export function composeActions(hit: SearchHitEntity, warn?: WarnFn): ActionView[] {
  const docType = hit.document_type ?? '';
  const config = DOCUMENT_TYPE_CONFIG[docType];

  if (docType && !config) {
    warn?.('unknown_document_type_actions', {
      document_id: hit.document_id,
      document_type: hit.document_type,
    });
  }

  return [...(config ?? DEFAULT_TYPE_CONFIG).actions];
}

/** Compose content-language view from hit language field. */
export function composeLanguage(hit: { language?: string }): ContentLanguageView | undefined {
  if (!hit.language) return undefined;
  return {
    display: hit.language,
    original: hit.language,
    isTranslation: false,
  };
}

// ─── Main Mapper ───

/** Map a single SearchHitEntity to a complete SearchResultView. Threads WarnFn to all sub-composers. */
export function mapSearchHitToView(hit: SearchHitEntity, warn?: WarnFn): SearchResultView {
  return {
    id: hit.document_id,
    type: hit.document_type ?? 'unknown',
    title: hit.title,
    subtitle: composeSubtitle(hit, warn),
    snippet: hit.snippet ?? '',
    badges: composeBadges(hit, warn),
    metadataRows: composeMetadata(hit),
    relatedCounts: composeRelatedCounts(hit),
    actions: composeActions(hit, warn),
    // Optional scalars — omit when absent (ADR-0011)
    ...(hit.structural_path && { structuralContext: hit.structural_path }),
    ...(hit.language && { contentLanguage: composeLanguage(hit) }),
  };
}
