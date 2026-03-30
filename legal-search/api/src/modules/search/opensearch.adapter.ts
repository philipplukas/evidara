/**
 * OpenSearch adapter for search operations.
 * Implements SearchRepository using the OpenSearch client.
 */
import { Injectable, Logger } from '@nestjs/common';
import type { ConfigService } from '@nestjs/config';
import type { ContextAggregations, SearchResultEntity } from './entities/search.entities';
import type { SearchOptions, SearchRepository } from './search.repository';

@Injectable()
export class SearchOpenSearchAdapter implements SearchRepository {
  private readonly logger = new Logger(SearchOpenSearchAdapter.name);
  private readonly indexDocuments: string;

  constructor(private readonly config: ConfigService) {
    this.indexDocuments = this.config.get<string>('opensearch.indexDocuments') ?? 'documents';
  }

  async search(query: string, _options?: SearchOptions): Promise<SearchResultEntity> {
    this.logger.debug(`Searching "${query}" in ${this.indexDocuments}`);

    // TODO: Replace with actual OpenSearch client call
    // For now, return empty results
    return { total: 0, hits: [], aggregations: {} };
  }

  async getContextAggregations(): Promise<ContextAggregations> {
    // TODO: Replace with actual OpenSearch aggs query
    return { jurisdictions: [], languages: [], source_types: [] };
  }
}
