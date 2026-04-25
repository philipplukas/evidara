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
  jurisdictions?: string[];
  /**
   * Canonical platform jurisdiction IDs (`jur_*`). ANDed with `jurisdictions`
   * (ISO) when both are present. Routes to the projection's
   * `jurisdiction_ids.keyword` field rather than the legacy `jurisdiction` /
   * subdivision keyword fields.
   */
  jurisdictionIds?: string[];
  /**
   * Canonical platform authority IDs (`auth_*`). Routes to
   * `authority_ids.keyword`.
   */
  authorityIds?: string[];
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
