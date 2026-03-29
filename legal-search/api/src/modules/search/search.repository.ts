import type { SearchQueryDto } from './dto/search-query.dto';
import type { SearchResponseDto } from './dto/search-response.dto';

/**
 * Repository interface for search operations.
 *
 * Services depend on this interface. The OpenSearch adapter implements it.
 * This keeps service logic decoupled from the search engine — testable with a mock,
 * and swappable if the underlying engine changes.
 */
export interface SearchRepository {
  search(query: SearchQueryDto): Promise<SearchResponseDto>;
}

export const SEARCH_REPOSITORY = Symbol('SearchRepository');
