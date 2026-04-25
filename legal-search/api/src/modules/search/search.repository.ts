/**
 * Search repository interface.
 * Adapters implement this to abstract the search backend.
 */
import type {
  ContextAggregations,
  SearchRecordKind,
  SearchResultEntity,
} from './entities/search.entities';

export interface SearchRepository {
  search(query: string, options?: SearchOptions): Promise<SearchResultEntity>;
  getContextAggregations(): Promise<ContextAggregations>;
}

export interface SearchOptions {
  jurisdictions?: string[];
  languages?: string[];
  documentTypes?: string[];
  officialOnly?: boolean;
  refinements?: SearchRefinement[];
  page?: number;
  pageSize?: number;
  /**
   * Sprint 2 (#425): filter results to a specific record kind. When
   * omitted, both `document` and `commentary` hits are returned.
   */
  recordKind?: SearchRecordKind;
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
