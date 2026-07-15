/**
 * OpenSearch adapter for the norm-hierarchy walk.
 *
 * One round trip: filter the documents index to the jurisdictions that govern
 * the place, then bucket by `level`. The hierarchy is an aggregation, not N
 * queries, because `level` is a keyword on the projection — which is the whole
 * point of deriving it at projection time (ADR-0033).
 */
import { Inject, Injectable, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import type { Client } from '@opensearch-project/opensearch';
import { inForceExclusionClauses, NORM_LEVELS_BY_RANK } from '../../core/norm-hierarchy';
import { OPENSEARCH_CLIENT } from '../../core/opensearch/client';
import type {
  FindNormsOptions,
  NormEntity,
  NormHierarchyRepository,
  NormsByLevel,
} from './norm-hierarchy.repository';

const SOURCE_FIELDS = [
  'document_id',
  'title',
  'level',
  'jurisdiction_ids',
  'document_type',
  'official_citation',
  'effective_date',
  'in_force_from',
  'in_force_until',
  'lifecycle_status',
  'subordinate_to',
];

type LevelBucket = {
  key: string;
  doc_count: number;
  top?: { hits?: { hits?: { _source?: Record<string, unknown> }[] } };
};

@Injectable()
export class NormHierarchyOpenSearchAdapter implements NormHierarchyRepository {
  private readonly logger = new Logger(NormHierarchyOpenSearchAdapter.name);
  private readonly indexDocuments: string;

  constructor(
    @Inject(OPENSEARCH_CLIENT)
    private readonly client: Client,
    @Inject(ConfigService)
    config: ConfigService,
  ) {
    this.indexDocuments = config.get<string>('opensearch.documentsReadAlias') ?? 'documents-read';
  }

  async findNormsByScopes(options: FindNormsOptions): Promise<NormsByLevel> {
    const filter: Record<string, unknown>[] = [
      { terms: { 'jurisdiction_ids.keyword': options.jurisdictionIds } },
      // Commentary is not a norm. It has no rank in the hierarchy and must not
      // appear as something that governs a place.
      { term: { record_kind: 'legal_document' } },
    ];
    const mustNot = options.inForceAt ? inForceExclusionClauses(options.inForceAt) : [];

    const response = await this.client.search({
      index: this.indexDocuments,
      body: {
        size: 0,
        query: { bool: { filter, must_not: mustNot } },
        aggs: {
          by_level: {
            terms: {
              field: 'level.keyword',
              size: NORM_LEVELS_BY_RANK.length,
            },
            aggs: {
              top: {
                top_hits: {
                  size: options.perLevelLimit,
                  _source: { includes: SOURCE_FIELDS },
                  // Newest first within a level: the current act is the one an
                  // agent wants at the top, and `effective_date` is the only
                  // recency signal a norm carries.
                  sort: [{ effective_date: { order: 'desc' as const, missing: '_last' } }],
                },
              },
            },
          },
        },
      },
    });
    const aggregations = response.body.aggregations as
      | { by_level?: { buckets?: LevelBucket[] } }
      | undefined;
    const buckets = aggregations?.by_level?.buckets;

    const documents = new Map<string, NormEntity[]>();
    const totals = new Map<string, number>();

    for (const bucket of buckets ?? []) {
      totals.set(bucket.key, bucket.doc_count);
      const hits = bucket.top?.hits?.hits ?? [];
      documents.set(
        bucket.key,
        hits.map((hit) => this.toNorm(hit._source ?? {})),
      );
    }

    this.logger.debug(
      `norm hierarchy: ${options.jurisdictionIds.length} scopes -> ${totals.size} levels`,
    );
    return { documents, totals };
  }

  private toNorm(source: Record<string, unknown>): NormEntity {
    const str = (value: unknown): string | undefined =>
      typeof value === 'string' && value.trim() ? value : undefined;
    const strList = (value: unknown): string[] =>
      Array.isArray(value)
        ? value.filter((entry): entry is string => typeof entry === 'string')
        : [];

    return {
      document_id: str(source.document_id) ?? '',
      title: str(source.title) ?? '',
      level: str(source.level) ?? '',
      jurisdiction_ids: strList(source.jurisdiction_ids),
      document_type: str(source.document_type),
      official_citation: str(source.official_citation),
      effective_date: str(source.effective_date),
      in_force_from: str(source.in_force_from),
      in_force_until: str(source.in_force_until),
      lifecycle_status: str(source.lifecycle_status),
      subordinate_to: strList(source.subordinate_to),
    };
  }
}
