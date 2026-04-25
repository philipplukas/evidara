import { Inject, Injectable, Logger } from '@nestjs/common';
import type { SupportedLocale } from '../../core/i18n';
import { DEFAULT_LOCALE } from '../../core/i18n';
import type { WarnFn } from '../../core/types/warn';
import { mapContextAggregations } from './mappers/search-context.mapper';
import { mapAggregationsToFacets } from './mappers/search-facet.mapper';
import { mapSearchHitToView } from './mappers/search-result.mapper';
import {
  SEARCH_REPOSITORY,
  type SearchRefinement,
  type SearchRepository,
} from './search.repository';

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
      jurisdictions?: string[];
      canonicalJurisdictionIds?: string[];
      languages?: string[];
      documentTypes?: string[];
      officialOnly?: boolean;
      refinements?: SearchRefinement[];
      page?: number;
      pageSize?: number;
      locale?: SupportedLocale;
    },
  ) {
    const locale = options?.locale ?? DEFAULT_LOCALE;
    const result = await this.repository.search(query, {
      jurisdictions: options?.jurisdictions,
      canonicalJurisdictionIds: options?.canonicalJurisdictionIds,
      languages: options?.languages,
      documentTypes: options?.documentTypes,
      officialOnly: options?.officialOnly,
      refinements: options?.refinements,
      page: options?.page,
      pageSize: options?.pageSize,
    });

    return {
      results: result.hits.map((hit) => mapSearchHitToView(hit, locale, this.warn)),
      facets: mapAggregationsToFacets(result.aggregations, locale),
      totalResults: result.total,
    };
  }

  async getContext(locale: SupportedLocale = DEFAULT_LOCALE) {
    const aggs = await this.repository.getContextAggregations();
    return mapContextAggregations(aggs, locale);
  }
}
