import { Injectable, Inject } from '@nestjs/common';
import { SEARCH_REPOSITORY, type SearchRepository } from './search.repository';
import type { SearchQueryDto } from './dto/search-query.dto';
import type { SearchResponseDto } from './dto/search-response.dto';

@Injectable()
export class SearchService {
  constructor(
    @Inject(SEARCH_REPOSITORY) private readonly searchRepository: SearchRepository,
  ) {}

  async search(query: SearchQueryDto): Promise<SearchResponseDto> {
    // Orchestration layer — business logic and validation would live here,
    // not in the controller and not in the adapter.
    return this.searchRepository.search(query);
  }
}
