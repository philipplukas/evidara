/**
 * Search facet mapper.
 *
 * Maps OpenSearch aggregation buckets to FilterFacetView DTOs.
 * Uses vocabulary-loaded labels where available.
 */

import { DOCUMENT_TYPE_LABELS, JURISDICTION_META } from '../../../core/vocabularies';
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
  label: string;
  type: FilterFacetView['type'];
  labelMap?: Record<string, { label: string; iconKey?: string }>;
}

const FACET_CONFIGS: FacetConfig[] = [
  {
    key: 'jurisdiction',
    label: 'Jurisdiction',
    type: 'chip',
    labelMap: Object.fromEntries(
      Object.entries(JURISDICTION_META).map(([k, v]) => [
        k,
        { label: v.label, iconKey: v.iconKey },
      ]),
    ),
  },
  {
    key: 'document_type',
    label: 'Document type',
    type: 'chip',
    labelMap: Object.fromEntries(
      Object.entries(DOCUMENT_TYPE_LABELS).map(([k, v]) => [
        k,
        { label: `${v}s` }, // pluralize for facet labels
      ]),
    ),
  },
  {
    key: 'language',
    label: 'Language',
    type: 'chip',
    labelMap: {
      de: { label: 'DE' },
      fr: { label: 'FR' },
      it: { label: 'IT' },
      en: { label: 'EN' },
    },
  },
  {
    key: 'court_level',
    label: 'Court level',
    type: 'checkbox',
  },
  {
    key: 'legal_area',
    label: 'Legal area',
    type: 'checkbox',
  },
];

// ─── Mapper ───

function mapBucketsToOptions(
  buckets: AggregationBucket[],
  labelMap?: Record<string, { label: string; iconKey?: string }>,
): FilterOptionView[] {
  return buckets.map((bucket) => {
    const mapped = labelMap?.[bucket.key];
    return {
      value: bucket.key,
      label: mapped?.label ?? bucket.key,
      count: bucket.doc_count,
      ...(mapped?.iconKey && { iconKey: mapped.iconKey }),
    };
  });
}

export function mapAggregationsToFacets(aggregations: SearchAggregations): FilterFacetView[] {
  const facets: FilterFacetView[] = [];

  for (const config of FACET_CONFIGS) {
    const buckets = aggregations[config.key as keyof SearchAggregations];
    if (!buckets || buckets.length === 0) continue;

    facets.push({
      key: config.key,
      label: config.label,
      type: config.type,
      options: mapBucketsToOptions(buckets, config.labelMap),
    });
  }

  return facets;
}
