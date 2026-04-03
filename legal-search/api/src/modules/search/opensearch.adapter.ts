/**
 * OpenSearch adapter for search operations.
 * Implements SearchRepository using the real OpenSearch client.
 *
 * Query strategy:
 * - multi_match across title, content, regeste with boosted title
 * - keyword filters for jurisdiction, document_type
 * - aggregations for facets (jurisdiction, document_type, language)
 * - highlight on content for snippet generation
 */
import { Inject, Injectable, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import type { Client } from '@opensearch-project/opensearch';
import { OPENSEARCH_CLIENT } from '../../core/opensearch/client';
import type {
  AggregationBucket,
  ContextAggregations,
  SearchHitEntity,
  SearchResultEntity,
} from './entities/search.entities';
import type { SearchOptions, SearchRepository } from './search.repository';

type OpenSearchHit = {
  _source?: Record<string, unknown>;
  _score?: number;
  highlight?: {
    content?: string[];
    regeste?: string[];
  };
};

@Injectable()
export class SearchOpenSearchAdapter implements SearchRepository {
  private readonly logger = new Logger(SearchOpenSearchAdapter.name);
  private readonly indexDocuments: string;

  constructor(
    @Inject(OPENSEARCH_CLIENT)
    private readonly client: Client,
    @Inject(ConfigService)
    config: ConfigService,
  ) {
    this.indexDocuments = config.get<string>('opensearch.indexDocuments') ?? 'documents';
  }

  async search(query: string, options?: SearchOptions): Promise<SearchResultEntity> {
    const page = options?.page ?? 1;
    const pageSize = options?.pageSize ?? 20;
    const from = (page - 1) * pageSize;

    // Build filter clauses
    const filters: Record<string, unknown>[] = [];
    if (options?.jurisdiction) {
      filters.push({ term: { jurisdiction: options.jurisdiction } });
    }
    if (options?.documentType) {
      filters.push({ term: { document_type: options.documentType } });
    }

    const body = {
      from,
      size: pageSize,
      query: {
        bool: {
          must: [
            {
              multi_match: {
                query,
                fields: ['title^3', 'regeste^2', 'content', 'docket_number^2'],
                type: 'best_fields' as const,
                fuzziness: 'AUTO',
              },
            },
          ],
          filter: filters,
        },
      },
      highlight: {
        fields: {
          content: {
            fragment_size: 200,
            number_of_fragments: 1,
            pre_tags: ['<mark>'],
            post_tags: ['</mark>'],
          },
          regeste: {
            fragment_size: 200,
            number_of_fragments: 1,
            pre_tags: ['<mark>'],
            post_tags: ['</mark>'],
          },
        },
      },
      aggs: {
        jurisdiction: { terms: { field: 'jurisdiction', size: 20 } },
        document_type: { terms: { field: 'document_type', size: 20 } },
        language: { terms: { field: 'language', size: 10 } },
      },
    };

    this.logger.debug(`Searching "${query}" in ${this.indexDocuments}`);

    try {
      const response = await this.client.search({
        index: this.indexDocuments,
        body,
      });

      const result = response.body;
      const total =
        typeof result.hits.total === 'number' ? result.hits.total : (result.hits.total?.value ?? 0);

      const hits: SearchHitEntity[] = (result.hits.hits as OpenSearchHit[])
        .filter((hit) => hit._source != null)
        .map((hit) => {
          const src = hit._source as Record<string, unknown>;
          return {
            document_id: src.document_id as string,
            title: src.title as string,
            snippet:
              hit.highlight?.content?.[0] ??
              hit.highlight?.regeste?.[0] ??
              (src.content_preview as string | undefined) ??
              '',
            jurisdiction: src.jurisdiction as string | undefined,
            document_type: src.document_type as string | undefined,
            effective_date: src.effective_date as string | undefined,
            relevance_score: typeof hit._score === 'number' ? hit._score : undefined,
            structural_path: src.structural_path as string | undefined,
            language: src.language as string | undefined,
            sections_count: src.sections_count as number | undefined,
            citations_count: src.citations_count as number | undefined,
            related_decisions_count: src.related_decisions_count as number | undefined,
            related_commentary_count: src.related_commentary_count as number | undefined,
          };
        });

      return {
        total,
        hits,
        aggregations: this.parseAggregations(result.aggregations),
      };
    } catch (err) {
      this.logger.error('Search failed', err);
      // Return empty results instead of crashing — observable degradation
      return { total: 0, hits: [], aggregations: {} };
    }
  }

  async getContextAggregations(): Promise<ContextAggregations> {
    try {
      const response = await this.client.search({
        index: this.indexDocuments,
        body: {
          size: 0,
          aggs: {
            jurisdictions: { terms: { field: 'jurisdiction', size: 20 } },
            languages: { terms: { field: 'language', size: 10 } },
            source_types: { terms: { field: 'document_type', size: 20 } },
          },
        },
      });

      const aggs = response.body.aggregations;
      return {
        jurisdictions: this.parseBuckets(aggs?.jurisdictions),
        languages: this.parseBuckets(aggs?.languages),
        source_types: this.parseBuckets(aggs?.source_types),
      };
    } catch (err) {
      this.logger.error('Context aggregation failed', err);
      return { jurisdictions: [], languages: [], source_types: [] };
    }
  }

  // ─── Helpers ───

  private parseAggregations(
    aggs: Record<string, unknown> | undefined,
  ): Record<string, AggregationBucket[]> {
    if (!aggs) return {};
    const result: Record<string, AggregationBucket[]> = {};
    for (const [key, val] of Object.entries(aggs)) {
      result[key] = this.parseBuckets(val);
    }
    return result;
  }

  private parseBuckets(agg: unknown): AggregationBucket[] {
    if (!agg || typeof agg !== 'object') return [];
    const buckets = (agg as { buckets?: unknown[] }).buckets;
    if (!Array.isArray(buckets)) return [];
    return buckets.map((b) => {
      const bucket = b as { key: string; doc_count: number };
      return { key: bucket.key, doc_count: bucket.doc_count };
    });
  }
}
