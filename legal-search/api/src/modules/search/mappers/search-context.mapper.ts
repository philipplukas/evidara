/**
 * Search context mapper.
 *
 * Maps global aggregation data to the SearchContextView ViewModel.
 * Query-independent and cacheable. Accepts locale for label resolution (ADR-0013).
 */

import type { SupportedLocale } from '../../../core/i18n';
import { DEFAULT_LOCALE, t } from '../../../core/i18n';
import { getDocumentTypeLabel, getJurisdictionMeta } from '../../../core/vocabularies';
import type { ContextAggregations } from '../entities/search.entities';

export interface ContextChipView {
  key: string;
  label: string;
  active: boolean;
  iconKey?: string;
}

export interface SearchContextView {
  jurisdictions: ContextChipView[];
  languages: ContextChipView[];
  sourceTypes: ContextChipView[];
  exactMatches: never[]; // populated later when exact-match logic exists
}

// ─── Language Labels ───

const LANGUAGE_LABELS: Record<string, string> = {
  de: 'DE',
  fr: 'FR',
  it: 'IT',
  en: 'EN',
};

// ─── Mapper ───

/** Map raw OpenSearch aggregation buckets to the SearchContextView ViewModel. */
export function mapContextAggregations(
  aggs: ContextAggregations,
  locale: SupportedLocale = DEFAULT_LOCALE,
): SearchContextView {
  return {
    jurisdictions: aggs.jurisdictions.map((bucket) => {
      const mapped = getJurisdictionMeta(bucket.key, locale);
      return {
        key: bucket.key.toLowerCase(),
        label: mapped?.label ?? bucket.key,
        active: true, // default: all active
        ...(mapped?.iconKey && { iconKey: mapped.iconKey }),
      };
    }),
    languages: aggs.languages.map((bucket) => ({
      key: bucket.key,
      label: LANGUAGE_LABELS[bucket.key] ?? bucket.key.toUpperCase(),
      active: bucket.key === 'de', // default: DE active
    })),
    sourceTypes: [
      { key: 'all', label: t('labels.all', locale), active: true },
      ...aggs.source_types.map((bucket) => ({
        key: bucket.key,
        label: getDocumentTypeLabel(bucket.key, locale),
        active: false,
      })),
    ],
    exactMatches: [],
  };
}
