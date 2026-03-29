import { Injectable, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { Client } from '@opensearch-project/opensearch';
import type { SearchRepository } from './search.repository';
import type { SearchQueryDto } from './dto/search-query.dto';
import type { SearchResponseDto } from './dto/search-response.dto';

/**
 * OpenSearch implementation of SearchRepository.
 *
 * All OpenSearch query DSL lives here — never in controllers or services.
 * Index names come from config (versioned for clean reindex support).
 */
@Injectable()
export class OpenSearchSearchAdapter implements SearchRepository {
  private readonly logger = new Logger(OpenSearchSearchAdapter.name);
  private readonly client: Client;
  private readonly indexDocuments: string;

  constructor(private readonly config: ConfigService) {
    this.client = new Client({
      node: config.get<string>('opensearch.url', 'http://localhost:9200'),
    });
    this.indexDocuments = config.get<string>(
      'opensearch.indexDocuments',
      'evidara-documents-v1',
    );
  }

  async search(query: SearchQueryDto): Promise<SearchResponseDto> {
    const { q, jurisdiction, document_type, page = 1, page_size = 20 } = query;
    const from = (page - 1) * page_size;

    const must: object[] = [{ multi_match: { query: q, fields: ['title^2', 'content'] } }];
    const filter: object[] = [];

    if (jurisdiction) filter.push({ term: { jurisdiction } });
    if (document_type) filter.push({ term: { document_type } });

    const response = await this.client.search({
      index: this.indexDocuments,
      body: {
        from,
        size: page_size,
        query: { bool: { must, filter } },
        highlight: { fields: { content: { fragment_size: 200, number_of_fragments: 1 } } },
      },
    });

    const hits = response.body.hits;
    const results = (hits.hits as Array<Record<string, unknown>>).map((hit) => {
      const source = hit['_source'] as Record<string, unknown>;
      const highlight = hit['highlight'] as Record<string, string[]> | undefined;
      return {
        document_id: hit['_id'] as string,
        title: source['title'] as string,
        snippet: highlight?.['content']?.[0],
        jurisdiction: source['jurisdiction'] as string | undefined,
        document_type: source['document_type'] as string | undefined,
        effective_date: source['effective_date'] as string | undefined,
        relevance_score: hit['_score'] as number | undefined,
      };
    });

    return {
      query: q,
      total_results: typeof hits.total === 'number' ? hits.total : (hits.total as { value: number }).value,
      page,
      page_size,
      results,
    };
  }
}
