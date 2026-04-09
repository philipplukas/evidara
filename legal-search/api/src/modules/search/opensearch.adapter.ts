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
import type { SearchOptions, SearchRefinement, SearchRepository } from './search.repository';

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
    this.indexDocuments = config.get<string>('opensearch.indexDocumentsRead') ?? 'documents-read';
  }

  async search(query: string, options?: SearchOptions): Promise<SearchResultEntity> {
    const page = options?.page ?? 1;
    const pageSize = options?.pageSize ?? 20;
    const from = (page - 1) * pageSize;
    const normalizedQuery = query.trim();

    // Build filter clauses
    const filters: Record<string, unknown>[] = [];
    if (options?.jurisdictions && options.jurisdictions.length > 0) {
      filters.push({ terms: { jurisdiction: options.jurisdictions } });
    }
    if (options?.documentTypes && options.documentTypes.length > 0) {
      filters.push({ terms: { document_type: options.documentTypes } });
    }
    if (options?.languages && options.languages.length > 0) {
      filters.push({ terms: { language: options.languages } });
    }
    if (options?.officialOnly) {
      filters.push({ term: { is_official: true } });
    }
    if (options?.refinements && options.refinements.length > 0) {
      filters.push(...this.mapRefinementsToFilters(options.refinements));
    }

    const body = {
      from,
      size: pageSize,
      query: {
        bool: {
          must:
            normalizedQuery === '*' || normalizedQuery.length === 0
              ? [{ match_all: {} }]
              : [
                  {
                    multi_match: {
                      query: normalizedQuery,
                      fields: [
                        'title^3',
                        'regeste^2',
                        'content',
                        'content_preview',
                        'docket_number^2',
                      ],
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
      let response = await this.client.search({
        index: this.indexDocuments,
        body,
      });

      let result = response.body;
      let total =
        typeof result.hits.total === 'number' ? result.hits.total : (result.hits.total?.value ?? 0);
      if (total === 0 && normalizedQuery !== '*' && normalizedQuery.length > 0) {
        // Fallback keeps search usable when indexed docs have sparse text fields.
        response = await this.client.search({
          index: this.indexDocuments,
          body: {
            ...body,
            query: {
              bool: {
                must: [{ match_all: {} }],
                filter: filters,
              },
            },
          },
        });
        result = response.body;
        total =
          typeof result.hits.total === 'number'
            ? result.hits.total
            : (result.hits.total?.value ?? 0);
      }

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
            authority_name: src.authority_name as string | undefined,
            official_citation: src.official_citation as string | undefined,
            original_language: src.original_language as string | undefined,
            translation_status: src.translation_status as
              | 'original'
              | 'machine_translated'
              | 'translation_unavailable'
              | undefined,
            is_official: src.is_official as boolean | undefined,
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

  private mapRefinementsToFilters(refinements: SearchRefinement[]): Record<string, unknown>[] {
    const mapped: Record<string, unknown>[] = [];
    for (const refinement of refinements) {
      if (refinement.values.length === 0) continue;
      switch (refinement.type) {
        case 'terms':
          mapped.push({ terms: { [refinement.field]: refinement.values } });
          break;
        case 'toggle':
          if (typeof refinement.value === 'boolean') {
            mapped.push({ term: { [refinement.field]: refinement.value } });
          }
          break;
        case 'range':
        case 'date_range':
          if (refinement.from || refinement.to) {
            mapped.push({
              range: {
                [refinement.field]: {
                  ...(refinement.from ? { gte: refinement.from } : {}),
                  ...(refinement.to ? { lte: refinement.to } : {}),
                },
              },
            });
          }
          break;
        case 'text':
          mapped.push({ match: { [refinement.field]: refinement.values.join(' ') } });
          break;
        default:
          break;
      }
    }
    return mapped;
  }

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
