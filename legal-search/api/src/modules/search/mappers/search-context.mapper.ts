/**
 * Search context mapper.
 *
 * Maps global aggregation data to the SearchContextView ViewModel.
 * Query-independent and cacheable.
 */

import { DOCUMENT_TYPE_LABELS, JURISDICTION_META } from '../../../core/vocabularies';
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

export function mapContextAggregations(aggs: ContextAggregations): SearchContextView {
  return {
    jurisdictions: aggs.jurisdictions.map((bucket) => {
      const mapped = JURISDICTION_META[bucket.key];
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
      { key: 'all', label: 'All', active: true },
      ...aggs.source_types.map((bucket) => ({
        key: bucket.key,
        label: DOCUMENT_TYPE_LABELS[bucket.key] ?? bucket.key,
        active: false,
      })),
    ],
    exactMatches: [],
  };
}
