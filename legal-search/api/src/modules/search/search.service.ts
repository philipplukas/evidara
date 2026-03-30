import { Inject, Injectable } from '@nestjs/common';
import type { SearchQueryDto } from './dto/search-query.dto';
import type { SearchResponseDto } from './dto/search-response.dto';
import { SEARCH_REPOSITORY, type SearchRepository } from './search.repository';

@Injectable()
export class SearchService {
  constructor(
    @Inject(SEARCH_REPOSITORY) private readonly _searchRepository: SearchRepository,
  ) {}

  async search(query: SearchQueryDto): Promise<SearchResponseDto> {
    // Orchestration layer — business logic and validation would live here,
    // not in the controller and not in the adapter.
    return this.searchRepository.search(query);
  }
}
