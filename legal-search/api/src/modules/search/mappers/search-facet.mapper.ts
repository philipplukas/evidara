/**
 * Search facet mapper.
 *
 * Maps OpenSearch aggregation buckets to FilterFacetView DTOs.
 * Uses locale-aware vocabulary labels and t() for group labels (ADR-0013).
 */

import type { SupportedLocale } from '../../../core/i18n';
import { DEFAULT_LOCALE, t } from '../../../core/i18n';
import { getDocumentTypeLabel, getJurisdictionMeta } from '../../../core/vocabularies';
import type { AggregationBucket, SearchAggregations } from '../entities/search.entities';

export interface FilterOptionView {
  value: string;
  label: string;
  count?: number;
  iconKey?: string;
}

export interface FilterFacetView {
  key: string;
  label: string;
  type: 'checkbox' | 'chip' | 'dropdown' | 'date' | 'toggle';
  options: FilterOptionView[];
}

// ─── Facet Configuration ───

interface FacetConfig {
  key: string;
  labelKey: string;
  type: FilterFacetView['type'];
  resolveOption?: (
    bucketKey: string,
    locale: SupportedLocale,
  ) => { label: string; iconKey?: string } | undefined;
}

const FACET_CONFIGS: FacetConfig[] = [
  {
    key: 'jurisdiction',
    labelKey: 'facets.jurisdiction',
    type: 'chip',
    resolveOption: (bucketKey, locale) => {
      const meta = getJurisdictionMeta(bucketKey, locale);
      return meta ? { label: meta.label, iconKey: meta.iconKey } : undefined;
    },
  },
  {
    key: 'document_type',
    labelKey: 'facets.documentType',
    type: 'chip',
    resolveOption: (bucketKey, locale) => {
      const label = getDocumentTypeLabel(bucketKey, locale);
      // Use plural forms from translation file
      const pluralKey = `plurals.${bucketKey}`;
      const pluralLabel = t(pluralKey, locale);
      return { label: pluralLabel !== pluralKey ? pluralLabel : label };
    },
  },
  {
    key: 'language',
    labelKey: 'facets.language',
    type: 'chip',
    resolveOption: (bucketKey, _locale) => {
      const labels: Record<string, string> = { de: 'DE', fr: 'FR', it: 'IT', en: 'EN' };
      return labels[bucketKey] ? { label: labels[bucketKey] } : undefined;
    },
  },
  {
    key: 'court_level',
    labelKey: 'facets.courtLevel',
    type: 'checkbox',
  },
  {
    key: 'legal_area',
    labelKey: 'facets.legalArea',
    type: 'checkbox',
  },
];

// ─── Mapper ───

function mapBucketsToOptions(
  buckets: AggregationBucket[],
  resolveOption?: (
    key: string,
    locale: SupportedLocale,
  ) => { label: string; iconKey?: string } | undefined,
  locale: SupportedLocale = DEFAULT_LOCALE,
): FilterOptionView[] {
  return buckets.map((bucket) => {
    const resolved = resolveOption?.(bucket.key, locale);
    return {
      value: bucket.key,
      label: resolved?.label ?? bucket.key,
      count: bucket.doc_count,
      ...(resolved?.iconKey && { iconKey: resolved.iconKey }),
    };
  });
}

export function mapAggregationsToFacets(
  aggregations: SearchAggregations,
  locale: SupportedLocale = DEFAULT_LOCALE,
): FilterFacetView[] {
  const facets: FilterFacetView[] = [];

  for (const config of FACET_CONFIGS) {
    const buckets = aggregations[config.key as keyof SearchAggregations];
    if (!buckets || buckets.length === 0) continue;

    facets.push({
      key: config.key,
      label: t(config.labelKey, locale),
      type: config.type,
      options: mapBucketsToOptions(buckets, config.resolveOption, locale),
    });
  }

  return facets;
}
