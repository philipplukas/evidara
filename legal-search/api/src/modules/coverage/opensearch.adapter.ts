/**
 * OpenSearch adapter for corpus coverage (ADR-0042).
 *
 * One round trip, `size: 0`. The scope becomes a bool filter; the dimension
 * becomes a `terms` agg with three sub-aggs that carry the honesty fields:
 *
 *   - `last_processed`  `max(processed_at)`   — freshness, such as it is
 *   - `no_repeal_date`  `missing in_force_until` — how much in-force standing is assumed
 *   - `source_versions` `terms(source_version_id)` + `cardinality` — provenance
 *
 * Two top-level aggs sit beside it: `missing_key`, counting documents that carry
 * no value for the grouping field (sparse `authority_ids`), and the hit total.
 * Both exist so the caller is told what the grouping did not see, rather than
 * having to infer it from sums that cannot balance over multi-valued fields.
 */
import { Inject, Injectable, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import type { Client } from '@opensearch-project/opensearch';
import { inForceExclusionClauses } from '../../core/norm-hierarchy';
import { OPENSEARCH_CLIENT } from '../../core/opensearch/client';
import { COVERAGE_DIMENSION_AGG_FIELDS } from '../../core/opensearch/facet-fields';
import type {
  CoverageBucket,
  CoverageCounts,
  CoverageQueryOptions,
  CoverageRepository,
} from './coverage.repository';

/** Provenance ids returned per group. The exact count is reported separately. */
const SOURCE_VERSION_SAMPLE_SIZE = 25;

type TermsBucket = {
  key: string;
  doc_count: number;
  last_processed?: { value_as_string?: string; value?: number | null };
  no_repeal_date?: { doc_count?: number };
  source_versions?: { buckets?: { key: string }[] };
  source_version_count?: { value?: number };
};

@Injectable()
export class CoverageOpenSearchAdapter implements CoverageRepository {
  private readonly logger = new Logger(CoverageOpenSearchAdapter.name);
  private readonly indexDocuments: string;

  constructor(
    @Inject(OPENSEARCH_CLIENT)
    private readonly client: Client,
    @Inject(ConfigService)
    config: ConfigService,
  ) {
    this.indexDocuments = config.get<string>('opensearch.documentsReadAlias') ?? 'documents-read';
  }

  async countCoverage(options: CoverageQueryOptions): Promise<CoverageCounts> {
    const aggField = COVERAGE_DIMENSION_AGG_FIELDS[options.dimension];

    const filter: Record<string, unknown>[] = [
      // Commentary is not a norm. Counting it as coverage would report the
      // corpus as holding law it does not hold — the same rule norm-hierarchy
      // applies, for the same reason.
      { term: { record_kind: 'legal_document' } },
    ];
    // `undefined` means "no filter asked for"; an EMPTY ARRAY means "a filter
    // was asked for and nothing survived validation" — which must match nothing,
    // not everything. Guarding on `.length` here instead conflates the two and
    // silently widens the scope to the whole corpus, so a caller asking about
    // one unrecognized jurisdiction would get corpus-wide totals back under a
    // response echoing their narrow scope. An empty `terms` matches nothing,
    // which is the honest answer.
    if (options.jurisdictionIds !== undefined) {
      filter.push({ terms: { 'jurisdiction_ids.keyword': options.jurisdictionIds } });
    }
    if (options.authorityIds !== undefined) {
      filter.push({ terms: { 'authority_ids.keyword': options.authorityIds } });
    }
    if (options.documentTypes !== undefined) {
      filter.push({ terms: { 'document_type.keyword': options.documentTypes } });
    }
    if (options.levels !== undefined) {
      filter.push({ terms: { 'level.keyword': options.levels } });
    }

    // `must_not` rather than a positive range: documents with unknown dates are
    // KEPT. Dropping them would hide law from the caller and make silence
    // indistinguishable from absence (ADR-0033 §2).
    const mustNot = options.inForceAt ? inForceExclusionClauses(options.inForceAt) : [];

    const response = await this.client.search({
      index: this.indexDocuments,
      body: {
        size: 0,
        track_total_hits: true,
        query: { bool: { filter, must_not: mustNot } },
        aggs: {
          by_dimension: {
            terms: { field: aggField, size: options.limit },
            aggs: {
              last_processed: { max: { field: 'processed_at' } },
              no_repeal_date: { missing: { field: 'in_force_until' } },
              source_versions: {
                terms: { field: 'source_version_id', size: SOURCE_VERSION_SAMPLE_SIZE },
              },
              source_version_count: { cardinality: { field: 'source_version_id' } },
            },
          },
          missing_key: { missing: { field: aggField } },
        },
      },
    });

    const aggregations = response.body.aggregations as
      | {
          by_dimension?: { buckets?: TermsBucket[] };
          missing_key?: { doc_count?: number };
        }
      | undefined;

    const buckets: CoverageBucket[] = (aggregations?.by_dimension?.buckets ?? []).map((bucket) => ({
      key: bucket.key,
      documents: bucket.doc_count,
      lastProcessedAt: bucket.last_processed?.value_as_string,
      documentsWithoutRepealDate: bucket.no_repeal_date?.doc_count ?? 0,
      sourceVersionIds: (bucket.source_versions?.buckets ?? []).map((entry) => entry.key),
      sourceVersionCount: bucket.source_version_count?.value ?? 0,
    }));

    const total = response.body.hits?.total;
    const totalDocuments = typeof total === 'number' ? total : (total?.value ?? 0);

    this.logger.debug(
      `coverage: dimension=${options.dimension} -> ${buckets.length} groups of ${totalDocuments}`,
    );

    return {
      totalDocuments,
      documentsWithoutGroupKey: aggregations?.missing_key?.doc_count ?? 0,
      buckets,
    };
  }
}
