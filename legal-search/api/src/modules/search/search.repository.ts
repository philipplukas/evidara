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
  jurisdiction?: string;
  documentType?: string;
  page?: number;
  pageSize?: number;
}

export const SEARCH_REPOSITORY = Symbol('SEARCH_REPOSITORY');
