/**
 * OpenSearch adapter for search operations.
 * Implements SearchRepository using the real OpenSearch client.
 *
 * Query strategy:
 * - multi_match across title, content, regeste with boosted title
 * - authority_name and official_citation boosts for legal-series and court-name queries
 * - keyword filters for jurisdiction, document_type
 * - aggregations for facets (jurisdiction, document_type, language)
 * - highlight on content for snippet generation
 */
import { Inject, Injectable, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import type { Client } from '@opensearch-project/opensearch';
import { MetricsService } from '../../core/metrics/metrics.service';
import { OPENSEARCH_CLIENT } from '../../core/opensearch/client';
import { SEARCH_FACET_AGG_FIELDS } from '../../core/opensearch/facet-fields';
import type {
  AggregationBucket,
  ContextAggregations,
  SearchHitEntity,
  SearchResultEntity,
} from './entities/search.entities';
import { describeOpenSearchError, SearchBackendUnavailableError } from './search.errors';
import type {
  ReadAliasCheck,
  SearchOptions,
  SearchRefinement,
  SearchRepository,
} from './search.repository';

type OpenSearchHit = {
  _source?: Record<string, unknown>;
  _score?: number;
  highlight?: {
    content?: string[];
    regeste?: string[];
  };
};

const SEARCH_FIELD_WEIGHTS = [
  'title^4',
  'authority_name^3',
  'official_citation^3',
  'structural_path^2',
  'regeste^2',
  'content',
  'content_preview',
  'docket_number^2',
] as const;

const PHRASE_BOOST_FIELDS = [
  ['title', 8],
  ['official_citation', 6],
  ['authority_name', 5],
  ['structural_path', 4],
  ['docket_number', 4],
] as const;

/**
 * Bucket ceiling for the jurisdiction-holdings aggregation. The jurisdiction
 * seed has 2,169 entries; this must stay above it, because a truncated holdings
 * list reads as "not held" for everything it dropped.
 */
const JURISDICTION_HOLDINGS_MAX_BUCKETS = 3000;

type QueryShape = 'wildcard' | 'short_legal' | 'free_text';

@Injectable()
export class SearchOpenSearchAdapter implements SearchRepository {
  private readonly logger = new Logger(SearchOpenSearchAdapter.name);
  private readonly indexDocuments: string;

  constructor(
    @Inject(OPENSEARCH_CLIENT)
    private readonly client: Client,
    @Inject(ConfigService)
    config: ConfigService,
    @Inject(MetricsService)
    private readonly metrics: MetricsService,
  ) {
    this.indexDocuments = config.get<string>('opensearch.documentsReadAlias') ?? 'documents-read';
  }

  async search(query: string, options?: SearchOptions): Promise<SearchResultEntity> {
    const page = options?.page ?? 1;
    const pageSize = options?.pageSize ?? 20;
    const from = (page - 1) * pageSize;
    const normalizedQuery = query.trim();
    const queryShape = this.classifyQuery(normalizedQuery);

    // Build filter clauses. ISO and canonical jurisdiction/authority
    // filters are independent term clauses — they ARE ANDed by being in
    // the same `bool.filter` array, matching the AND semantics
    // documented on `GET /v1/search` in the OpenAPI spec.
    const filters: Record<string, unknown>[] = [];
    if (options?.jurisdictions && options.jurisdictions.length > 0) {
      filters.push({ terms: { jurisdiction: options.jurisdictions } });
    }
    // `jurisdiction_ids` and `authority_ids` are declared `facetKeyword` in
    // the canonical mapping — `keyword` WITH a `.keyword` sub-field — so the
    // sub-field is the correct, exact-match target. It also happens to be the
    // form that resolves on the drifted live index, where these two were
    // dynamic-mapped as `text` + `.keyword`.
    if (options?.jurisdictionIds && options.jurisdictionIds.length > 0) {
      filters.push({ terms: { 'jurisdiction_ids.keyword': options.jurisdictionIds } });
    }
    if (options?.authorityIds && options.authorityIds.length > 0) {
      filters.push({ terms: { 'authority_ids.keyword': options.authorityIds } });
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
      // Without this, OpenSearch stops counting at 10 000 and reports
      // `hits.total = {value: 10000, relation: "gte"}`. `total` feeds
      // `SearchResponseView.totalResults` — the hit count on screen — so the
      // default silently under-reports every query that matches more than
      // 10 000 documents. Under-reporting hits is a correctness problem for
      // legal research ("is there any case on X"), not a cosmetic one (#615).
      // The citations and projections adapters already set this.
      track_total_hits: true,
      query: {
        bool: {
          must:
            queryShape === 'wildcard'
              ? [{ match_all: {} }]
              : [this.buildPrimaryQuery(normalizedQuery, queryShape)],
          should:
            queryShape === 'wildcard'
              ? []
              : PHRASE_BOOST_FIELDS.map(([field, boost]) => ({
                  match_phrase: {
                    [field]: {
                      query: normalizedQuery,
                      boost,
                    },
                  },
                })),
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
      // Aggregation targets come from `SEARCH_FACET_AGG_FIELDS`, which is
      // pinned to the canonical mapping (#675). Do not inline field names here.
      aggs: {
        jurisdiction: { terms: { field: SEARCH_FACET_AGG_FIELDS.jurisdiction, size: 20 } },
        document_type: { terms: { field: SEARCH_FACET_AGG_FIELDS.document_type, size: 20 } },
        language: { terms: { field: SEARCH_FACET_AGG_FIELDS.language, size: 10 } },
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
            lifecycle_status: src.lifecycle_status as string | undefined,
            relevance_score: typeof hit._score === 'number' ? hit._score : undefined,
            structural_path: src.structural_path as string | undefined,
            language: src.language as string | undefined,
            sections_count: src.sections_count as number | undefined,
            citations_count: src.citations_count as number | undefined,
            related_decisions_count: src.related_decisions_count as number | undefined,
            related_commentary_count: src.related_commentary_count as number | undefined,
            record_kind: src.record_kind as 'legal_document' | 'commentary_insight' | undefined,
            source_document_ids: Array.isArray(src.source_document_ids)
              ? (src.source_document_ids as string[])
              : undefined,
          };
        });

      this.metrics.recordSearch(total);
      return {
        total,
        hits,
        aggregations: this.parseAggregations(result.aggregations),
      };
    } catch (err) {
      // A query that could not be executed is NOT an empty result set (#551).
      // Count it before rethrowing: `search_errors_total` is what lets the
      // zero-result alert tell a dead cluster apart from a query that simply
      // matched nothing. `failure()` already logs at ERROR.
      this.metrics.recordSearchError();
      throw this.failure('search', err);
    }
  }

  async getContextAggregations(): Promise<ContextAggregations> {
    try {
      const response = await this.client.search({
        index: this.indexDocuments,
        body: {
          size: 0,
          aggs: {
            // Same pinned targets as the search aggs (#675).
            jurisdictions: { terms: { field: SEARCH_FACET_AGG_FIELDS.jurisdiction, size: 20 } },
            languages: { terms: { field: SEARCH_FACET_AGG_FIELDS.language, size: 10 } },
            source_types: { terms: { field: SEARCH_FACET_AGG_FIELDS.document_type, size: 20 } },
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
      throw this.failure('context aggregation', err);
    }
  }

  /**
   * Terms aggregation over `jurisdiction_ids.keyword` — the index's own account
   * of which jurisdictions it holds (#986).
   *
   * `size: 0` hits, `size: 3000` buckets: the seed carries 2,169 jurisdictions,
   * so a default of 10 would silently truncate the corpus's holdings into a
   * short list and make every unlisted jurisdiction look unheld. Truncating a
   * holdings list is how a coverage check turns into a false refusal.
   *
   * `.keyword` is the sub-field, matching how `search()` filters the same field.
   */
  async getHeldJurisdictionIds(): Promise<string[]> {
    try {
      const response = await this.client.search({
        index: this.indexDocuments,
        body: {
          size: 0,
          aggs: {
            held_jurisdictions: {
              terms: { field: 'jurisdiction_ids.keyword', size: JURISDICTION_HOLDINGS_MAX_BUCKETS },
            },
          },
        },
      });
      return this.parseBuckets(response.body.aggregations?.held_jurisdictions).map(
        (bucket) => bucket.key,
      );
    } catch (err) {
      throw this.failure('jurisdiction holdings aggregation', err);
    }
  }

  async checkReadAlias(): Promise<ReadAliasCheck> {
    const alias = this.indexDocuments;
    try {
      const response = await this.client.indices.getAlias({ name: alias });
      const indices = Object.keys((response.body ?? {}) as Record<string, unknown>);
      if (indices.length === 0) {
        const detail = `read alias "${alias}" resolves to no index`;
        this.logger.error(`Readiness check failed: ${detail}`);
        return { status: 'error', alias, detail };
      }
      return { status: 'ok', alias, indices };
    } catch (err) {
      const detail = describeOpenSearchError(err);
      this.logger.error(`Readiness check failed: read alias "${alias}" unresolvable — ${detail}`);
      return { status: 'error', alias, detail };
    }
  }

  // ─── Helpers ───

  /**
   * Log loudly and build the domain error. The whole point of #551: a
   * missing index is a total outage of the core product feature, so it must
   * be the loudest failure we have, not the quietest.
   */
  private failure(operation: string, err: unknown): SearchBackendUnavailableError {
    const failure = new SearchBackendUnavailableError(operation, this.indexDocuments, err);
    this.logger.error(
      `OpenSearch ${operation} failed [${failure.reason}] on "${this.indexDocuments}": ${failure.detail}`,
      err instanceof Error ? err.stack : undefined,
    );
    return failure;
  }

  private classifyQuery(query: string): QueryShape {
    if (query === '*' || query.length === 0) return 'wildcard';

    const tokens = query.split(/\s+/).filter(Boolean);
    const looksCitationLike = /(?:\bart\.?\b|\bbge\b|\bbvge\b|\bemrk\b|\d|\/|§)/i.test(query);
    const shortLegalQuery = tokens.length <= 3 && query.length <= 32;

    if (looksCitationLike || shortLegalQuery) {
      return 'short_legal';
    }

    return 'free_text';
  }

  private buildPrimaryQuery(
    query: string,
    shape: Exclude<QueryShape, 'wildcard'>,
  ): Record<string, unknown> {
    if (shape === 'short_legal') {
      return {
        multi_match: {
          query,
          fields: [...SEARCH_FIELD_WEIGHTS],
          type: 'best_fields' as const,
          operator: 'and' as const,
        },
      };
    }

    return {
      multi_match: {
        query,
        fields: [...SEARCH_FIELD_WEIGHTS],
        type: 'best_fields' as const,
        fuzziness: 'AUTO',
        /*
         * The first two characters must match exactly (#981).
         *
         * Bare `fuzziness: 'AUTO'` does not soften matching, it destroys it.
         * Measured against the 889-document production corpus, same query,
         * same fields, same analyzer, varying only this:
         *
         *   "Darf ich meinen Hund in Zuerich ohne Leine laufen lassen"
         *     AUTO                    -> "Aufnahme in die K+S Klassen ..."
         *     AUTO + prefix_length 2  -> "Hundegesetz (HuG) 554.5"
         *
         *   "Hund Leine Zuerich"
         *     AUTO                    -> "Vetsuisse-Fakultaet der Universitaeten ..."
         *     AUTO + prefix_length 2  -> "Hundegesetz (HuG) 554.5"
         *
         * Short tokens expand to unrelated terms within edit distance and the
         * expansions outscore the exact hits. `prefix_length` keeps typo
         * tolerance — a transposed or dropped character later in a word still
         * matches — while refusing an expansion that shares no opening.
         *
         * Note the second example: this was never "questions fail, keywords
         * work". `classifyQuery` routes <=3 tokens down `short_legal`, which
         * sets no fuzziness, so short queries were only ACCIDENTALLY exempt.
         * Anything longer was fuzzy-matched into noise.
         */
        prefix_length: 2,
      },
    };
  }

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
