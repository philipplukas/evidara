/**
 * Search result ViewModel mapper.
 *
 * Pure functions that compose SearchResultView from SearchHitEntity.
 * Accepts locale parameter for all display-label composition (ADR-0013).
 *
 * Observable fallbacks (ADR-0012):
 * - Unknown vocabulary values produce a warning via WarnFn, not silent degradation.
 * - Lookup tables are derived from contracts/vocabularies/*.json.
 *
 * ADR-0011 conventions:
 * - Array fields always present (empty [])
 * - Optional scalar fields omitted when absent
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
  /**
   * Discriminator from the search projection (PR #441). Mirrors
   * `record_kind` on the projection. The frontend keys its result-card
   * variant off this OR off `type === "commentary"`.
   */
  recordKind?: 'legal_document' | 'commentary_insight';
  /**
   * Canonical primary documents this commentary references (#425).
   * Empty / undefined for legal_document rows. The frontend renders
   * these as source-document links on commentary cards.
   */
  sourceDocumentIds?: string[];
}

// ─── Document Type Rules (presentation config) ───

interface DocumentTypeConfig {
  badgeColorKey: string;
  actionKeys: [string, string][];
}

const DOCUMENT_TYPE_CONFIG: Record<string, DocumentTypeConfig> = {
  law: {
    badgeColorKey: 'blue',
    actionKeys: [
      ['actions.openArticle', 'file-text'],
      ['actions.related', 'link'],
    ],
  },
  decision: {
    badgeColorKey: 'pink',
    actionKeys: [
      ['actions.openDecision', 'gavel'],
      ['actions.relatedDecision', 'link'],
    ],
  },
  commentary: {
    badgeColorKey: 'amber',
    actionKeys: [
      ['actions.openCommentary', 'book-open'],
      ['actions.viewArticle', 'file-text'],
    ],
  },
  rechtssatz: {
    badgeColorKey: 'green',
    actionKeys: [
      ['actions.open', 'file-text'],
      ['actions.related', 'link'],
    ],
  },
};

const DEFAULT_TYPE_CONFIG: DocumentTypeConfig = {
  badgeColorKey: 'slate',
  actionKeys: [['actions.open', 'file-text']],
};

// ─── Composition Functions ───

/** Compose badge views from document type and jurisdiction. Warns on unknown values. */
export function composeBadges(
  hit: SearchHitEntity,
  locale: SupportedLocale = DEFAULT_LOCALE,
  warn?: WarnFn,
): BadgeView[] {
  const docType = hit.document_type ?? '';
  const config = DOCUMENT_TYPE_CONFIG[docType];

  if (docType && !config) {
    warn?.('unknown_document_type', {
      document_id: hit.document_id,
      document_type: hit.document_type,
    });
  }

  const resolvedConfig = config ?? DEFAULT_TYPE_CONFIG;
  const jurisdictionMeta = getJurisdictionMeta(hit.jurisdiction ?? '', locale);

  if (hit.jurisdiction && !jurisdictionMeta) {
    warn?.('unknown_jurisdiction', {
      document_id: hit.document_id,
      jurisdiction: hit.jurisdiction,
    });
  }

  const badgeLabel =
    docType && config ? getDocumentTypeLabel(docType, locale) : t('labels.document', locale);

  return [
    {
      label: badgeLabel,
      colorKey: resolvedConfig.badgeColorKey,
      ...(jurisdictionMeta && { iconKey: jurisdictionMeta.iconKey }),
    },
  ];
}

/** Compose subtitle from jurisdiction label and document type label. */
export function composeSubtitle(
  hit: SearchHitEntity,
  locale: SupportedLocale = DEFAULT_LOCALE,
  warn?: WarnFn,
): string {
  const parts: string[] = [];
  const jurisdictionMeta = getJurisdictionMeta(hit.jurisdiction ?? '', locale);

  if (hit.jurisdiction && !jurisdictionMeta) {
    warn?.('unknown_jurisdiction_subtitle', {
      document_id: hit.document_id,
      jurisdiction: hit.jurisdiction,
    });
  }

  if (jurisdictionMeta) parts.push(jurisdictionMeta.label);

  const config = DOCUMENT_TYPE_CONFIG[hit.document_type ?? ''];
  if (config && hit.document_type) {
    parts.push(getDocumentTypeLabel(hit.document_type, locale));
  }
  if (hit.authority_name) {
    parts.push(hit.authority_name);
  }

  return parts.join(' · ') || t('labels.document', locale);
}

/** Compose metadata rows (date label varies by document type). */
export function composeMetadata(
  hit: SearchHitEntity,
  locale: SupportedLocale = DEFAULT_LOCALE,
): MetadataRowView[] {
  const rows: MetadataRowView[] = [];
  const documentTypeLabel = hit.document_type
    ? getDocumentTypeLabel(hit.document_type, locale)
    : undefined;

  if (hit.lifecycle_status && hit.lifecycle_status !== 'active') {
    rows.push({
      label: t('metadata.status', locale),
      value: formatLifecycleStatus(hit.lifecycle_status, locale),
      iconKey: METADATA_ROW_ICONS.status,
    });
  }
  if (hit.document_type && documentTypeLabel && documentTypeLabel !== hit.document_type) {
    rows.push({
      label: t('facets.documentType', locale),
      value: documentTypeLabel,
      iconKey: iconKeyForDocumentType(hit.document_type),
    });
  }
  if (hit.effective_date) {
    const label =
      hit.document_type === 'decision' ? t('metadata.date', locale) : t('metadata.inForce', locale);
    rows.push({
      label,
      value: hit.effective_date,
      iconKey: METADATA_ROW_ICONS.calendar,
    });
  }
  if (hit.official_citation) {
    rows.push({
      label: t('metadata.citation', locale),
      value: hit.official_citation,
      iconKey: METADATA_ROW_ICONS.citation,
    });
  }
  if (hit.is_official) {
    rows.push({
      label: t('metadata.source', locale),
      value: t('metadata.officialSource', locale),
      iconKey: METADATA_ROW_ICONS.official,
    });
  }

  if (hit.language) {
    rows.push({
      label: t('metadata.language', locale),
      value: formatLanguageDisplay(hit.language),
      iconKey: METADATA_ROW_ICONS.language,
    });
  }

  return rows;
}

/** Compose related-count chips from hit entity counts. */
export function composeRelatedCounts(
  hit: SearchHitEntity,
  locale: SupportedLocale = DEFAULT_LOCALE,
): RelatedCountView[] {
  const counts: RelatedCountView[] = [];

  if (hit.related_commentary_count && hit.related_commentary_count > 0) {
    counts.push({
      label: t('counts.commentary', locale),
      count: hit.related_commentary_count,
    });
  }
  if (hit.related_decisions_count && hit.related_decisions_count > 0) {
    counts.push({
      label: t('counts.courtDecisions', locale),
      count: hit.related_decisions_count,
    });
  }
  if (hit.citations_count && hit.citations_count > 0) {
    counts.push({ label: t('counts.citations', locale), count: hit.citations_count });
  }

  return counts;
}

/** Compose action buttons from document type config. Warns on unknown types. */
export function composeActions(
  hit: SearchHitEntity,
  locale: SupportedLocale = DEFAULT_LOCALE,
  warn?: WarnFn,
): ActionView[] {
  const docType = hit.document_type ?? '';
  const config = DOCUMENT_TYPE_CONFIG[docType];

  if (docType && !config) {
    warn?.('unknown_document_type_actions', {
      document_id: hit.document_id,
      document_type: hit.document_type,
    });
  }

  const actionKeys = (config ?? DEFAULT_TYPE_CONFIG).actionKeys;
  return actionKeys.map(([key, icon]) => ({ label: t(key, locale), icon }));
}

/** Compose content-language view from hit language field. */
export function composeLanguage(
  hit: {
    language?: string;
    original_language?: string;
    translation_status?: 'original' | 'machine_translated' | 'translation_unavailable';
  },
  locale: SupportedLocale = DEFAULT_LOCALE,
): ContentLanguageView | undefined {
  const display = hit.language;
  const original = hit.original_language ?? hit.language;
  if (!display || !original) return undefined;
  const status = hit.translation_status ?? 'original';
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

/** Map a single SearchHitEntity to a complete SearchResultView. Threads locale and WarnFn to all sub-composers. */
export function mapSearchHitToView(
  hit: SearchHitEntity,
  locale: SupportedLocale = DEFAULT_LOCALE,
  warn?: WarnFn,
): SearchResultView {
  return {
    id: hit.document_id,
    type: hit.document_type ?? 'unknown',
    title: hit.title,
    subtitle: composeSubtitle(hit, locale, warn),
    snippet: hit.snippet ?? '',
    badges: composeBadges(hit, locale, warn),
    metadataRows: composeMetadata(hit, locale),
    relatedCounts: composeRelatedCounts(hit, locale),
    actions: composeActions(hit, locale, warn),
    // Optional scalars — omit when absent (ADR-0011)
    ...(hit.structural_path && { structuralContext: hit.structural_path }),
    ...(composeLanguage(hit, locale) && { contentLanguage: composeLanguage(hit, locale) }),
    ...(hit.record_kind && { recordKind: hit.record_kind }),
    ...(hit.source_document_ids &&
      hit.source_document_ids.length > 0 && { sourceDocumentIds: hit.source_document_ids }),
  };
}
