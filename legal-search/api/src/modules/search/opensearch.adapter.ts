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
  ) {
    this.indexDocuments = config.get<string>('opensearch.documentsReadAlias') ?? 'documents-read';
  }

  async search(query: string, options?: SearchOptions): Promise<SearchResultEntity> {
    const page = options?.page ?? 1;
    const pageSize = options?.pageSize ?? 20;
    const from = (page - 1) * pageSize;
    const normalizedQuery = query.trim();
    const queryShape = this.classifyQuery(normalizedQuery);

    // Build filter clauses
    const filters: Record<string, unknown>[] = [];
    const jurisdictionFilter = this.buildJurisdictionFilter(
      options?.jurisdictions,
      options?.canonicalJurisdictionIds,
    );
    if (jurisdictionFilter) {
      filters.push(jurisdictionFilter);
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
    if (options?.recordKind) {
      // Sprint 2 (#425): record_kind filter. Treat rows without an explicit
      // record_kind as `document` so backfilled data still matches the
      // default kind. TODO(#430): once the alias migration completes and
      // every row carries an explicit record_kind, this can collapse to a
      // simple `term` filter.
      if (options.recordKind === 'document') {
        filters.push({
          bool: {
            should: [
              { term: { record_kind: 'document' } },
              { bool: { must_not: { exists: { field: 'record_kind' } } } },
            ],
            minimum_should_match: 1,
          },
        });
      } else {
        filters.push({ term: { record_kind: options.recordKind } });
      }
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
      aggs: {
        jurisdiction: { terms: { field: 'jurisdiction.keyword', size: 20 } },
        document_type: { terms: { field: 'document_type.keyword', size: 20 } },
        language: { terms: { field: 'language.keyword', size: 10 } },
        // Sprint 2 (#425): commentary support join. Counts how many
        // commentary hits in this query reference each primary document
        // via `source_document_ids`. The primary-document hit picks up
        // its support count from this map in a single round-trip rather
        // than issuing a per-hit follow-up query. The `.keyword` suffix
        // is defensive — the alias-cutover script maps the field as
        // `keyword`, but legacy auto-mapped indices store it as
        // `text`+`keyword` subfield.
        commentary_support: {
          filter: { term: { record_kind: 'commentary' } },
          aggs: {
            by_source_document: {
              terms: {
                field: 'source_document_ids',
                size: pageSize * 4,
              },
            },
          },
        },
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

      // Sprint 2 (#425): build the commentary support map once and look it
      // up per primary-document hit below.
      const commentarySupportCounts = this.parseCommentarySupportCounts(result.aggregations);

      const hits: SearchHitEntity[] = (result.hits.hits as OpenSearchHit[])
        .filter((hit) => hit._source != null)
        .map((hit) => {
          const src = hit._source as Record<string, unknown>;
          const recordKind = this.normalizeRecordKind(src.record_kind);
          const sourceDocumentIds = this.toStringArray(src.source_document_ids);
          const documentId = src.document_id as string;
          const supportCount =
            recordKind === 'commentary' ? undefined : commentarySupportCounts.get(documentId);
          return {
            document_id: documentId,
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
            // Sprint 2 (#425): mixed-result fields.
            record_kind: recordKind,
            ...(sourceDocumentIds && { source_document_ids: sourceDocumentIds }),
            ...(() => {
              const ids = this.toStringArray(src.jurisdiction_ids);
              return ids ? { jurisdiction_ids: ids } : {};
            })(),
            ...(() => {
              const ids = this.toStringArray(src.authority_ids);
              return ids ? { authority_ids: ids } : {};
            })(),
            ...(supportCount !== undefined && { commentary_support_count: supportCount }),
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
            jurisdictions: { terms: { field: 'jurisdiction.keyword', size: 20 } },
            languages: { terms: { field: 'language.keyword', size: 10 } },
            source_types: { terms: { field: 'document_type.keyword', size: 20 } },
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
      },
    };
  }

  /**
   * Build the jurisdiction filter clause.
   *
   * Routing:
   *   - ISO country / subdivision tokens (`ch`, `ch-zh`) -> existing
   *     single-valued `jurisdiction` keyword field.
   *   - Canonical `jur_*` ids -> the multi-valued `jurisdiction_ids`
   *     field added by the canonical-ID projection slice (#425).
   *
   * Semantics: a mixed list is OR'd at the field level — a doc matches
   * if either field hits any of its tokens. We express this as a nested
   * `bool` with `should` clauses inside the parent's filter context, so
   * the union still narrows results without contributing to score.
   * When only one shape is supplied we return the simpler `terms`
   * clause directly (no nesting overhead).
   */
  private buildJurisdictionFilter(
    isoTokens: string[] | undefined,
    canonicalIds: string[] | undefined,
  ): Record<string, unknown> | null {
    const haveIso = !!isoTokens && isoTokens.length > 0;
    const haveCanonical = !!canonicalIds && canonicalIds.length > 0;
    if (!haveIso && !haveCanonical) return null;

    if (haveIso && !haveCanonical) {
      return { terms: { jurisdiction: isoTokens } };
    }
    if (!haveIso && haveCanonical) {
      return { terms: { 'jurisdiction_ids.keyword': canonicalIds } };
    }

    // Mixed list: OR-union the two field filters via a nested bool.
    return {
      bool: {
        should: [
          { terms: { jurisdiction: isoTokens } },
          { terms: { 'jurisdiction_ids.keyword': canonicalIds } },
        ],
        minimum_should_match: 1,
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
      // Sprint 2 (#425): commentary_support is a filter+terms sub-agg used
      // for the per-hit support count, not a facet — skip it so the facet
      // mapper does not surface it as a filter in the UI.
      if (key === 'commentary_support') continue;
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

  /**
   * Sprint 2 (#425): pull the commentary→primary-document join counts out
   * of the `commentary_support` filter aggregation. The aggregation buckets
   * each `source_document_ids` value with a `doc_count` of "how many
   * commentary records in this query mention that document". Returned as a
   * Map for O(1) per-hit lookup.
   */
  private parseCommentarySupportCounts(
    aggs: Record<string, unknown> | undefined,
  ): Map<string, number> {
    const result = new Map<string, number>();
    if (!aggs || typeof aggs !== 'object') return result;
    const support = (aggs as Record<string, unknown>).commentary_support;
    if (!support || typeof support !== 'object') return result;
    const bySource = (support as Record<string, unknown>).by_source_document;
    if (!bySource || typeof bySource !== 'object') return result;
    const buckets = (bySource as { buckets?: unknown[] }).buckets;
    if (!Array.isArray(buckets)) return result;
    for (const bucket of buckets) {
      if (!bucket || typeof bucket !== 'object') continue;
      const key = (bucket as { key?: unknown }).key;
      const docCount = (bucket as { doc_count?: unknown }).doc_count;
      if (typeof key === 'string' && typeof docCount === 'number') {
        result.set(key, docCount);
      }
    }
    return result;
  }

  private normalizeRecordKind(value: unknown): 'document' | 'commentary' {
    if (value === 'commentary') return 'commentary';
    return 'document';
  }

  private toStringArray(value: unknown): string[] | undefined {
    if (!Array.isArray(value)) {
      if (typeof value === 'string' && value.trim().length > 0) {
        return [value.trim()];
      }
      return undefined;
    }
    const cleaned = value
      .filter((entry): entry is string => typeof entry === 'string' && entry.trim().length > 0)
      .map((entry) => entry.trim());
    return cleaned.length > 0 ? cleaned : undefined;
  }
}
