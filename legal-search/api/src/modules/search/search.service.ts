import { Inject, Injectable, Logger } from '@nestjs/common';
import type { WarnFn } from '../../core/types/warn';
import { mapContextAggregations } from './mappers/search-context.mapper';
import { mapAggregationsToFacets } from './mappers/search-facet.mapper';
import { mapSearchHitToView } from './mappers/search-result.mapper';
import { SEARCH_REPOSITORY, type SearchRepository } from './search.repository';

@Injectable()
export class SearchService {
  private readonly logger = new Logger(SearchService.name);
  private readonly warn: WarnFn;

  constructor(
    @Inject(SEARCH_REPOSITORY)
    private readonly repository: SearchRepository,
  ) {
    this.warn = (event, meta) => this.logger.warn(`[contract] ${event}`, meta);
  }

  async search(
    query: string,
    options?: {
      jurisdiction?: string;
      documentType?: string;
      page?: number;
      pageSize?: number;
    },
  ) {
    const result = await this.repository.search(query, {
      jurisdiction: options?.jurisdiction,
      documentType: options?.documentType,
      page: options?.page,
      pageSize: options?.pageSize,
    });

    return {
      results: result.hits.map((hit) => mapSearchHitToView(hit, this.warn)),
      facets: mapAggregationsToFacets(result.aggregations),
      totalResults: result.total,
    };
  }

  async getContext() {
    const aggs = await this.repository.getContextAggregations();
    return mapContextAggregations(aggs);
  }
}
