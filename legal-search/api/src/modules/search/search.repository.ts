/**
 * Search repository interface.
 * Adapters implement this to abstract the search backend.
 */
import type { ContextAggregations, SearchResultEntity } from './entities/search.entities';

export interface SearchRepository {
  search(query: string, options?: SearchOptions): Promise<SearchResultEntity>;
  getContextAggregations(): Promise<ContextAggregations>;
}

export interface SearchOptions {
  /**
   * ISO 3166-1 country codes and ISO 3166-2 subdivision codes,
   * lowercased to match the `jurisdiction` keyword index. Example:
   * `["ch", "ch-zh"]`. Routed by the adapter to the existing
   * `jurisdiction` field.
   */
  jurisdictions?: string[];
  /**
   * Canonical platform-control jurisdiction ids (`jur_*`), lowercased.
   * Example: `["jur_ch_federal", "jur_ch_gemeinde_261"]`. Routed by the
   * adapter to the multi-valued `jurisdiction_ids.keyword` projection
   * field added by the canonical-ID slice (#425). When both this and
   * `jurisdictions` are supplied, both filters apply and OR together
   * (terms-on-different-fields semantics within the same array).
   */
  canonicalJurisdictionIds?: string[];
  languages?: string[];
  documentTypes?: string[];
  officialOnly?: boolean;
  refinements?: SearchRefinement[];
  page?: number;
  pageSize?: number;
}

export interface SearchRefinement {
  field: string;
  type: 'terms' | 'date_range' | 'range' | 'toggle' | 'text';
  values: string[];
  from?: string;
  to?: string;
  value?: boolean | string;
}

export const SEARCH_REPOSITORY = Symbol('SEARCH_REPOSITORY');
