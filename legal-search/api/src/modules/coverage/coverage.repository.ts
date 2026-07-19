/**
 * Port for the corpus-coverage read model (ADR-0008 repository interface).
 *
 * The port speaks in counts and buckets, not in OpenSearch. Everything the
 * service needs to answer honestly — the group counts, the freshness stamp, the
 * provenance ids, and the two "how much did we not see" numbers — is returned
 * here so the service never reasons about aggregation shape.
 */

import type { NormLevel } from '../../core/norm-hierarchy';
import type { CoverageDimension } from '../../core/opensearch/facet-fields';

export const COVERAGE_REPOSITORY = Symbol('COVERAGE_REPOSITORY');

export type CoverageQueryOptions = {
  dimension: CoverageDimension;
  jurisdictionIds?: string[];
  authorityIds?: string[];
  documentTypes?: string[];
  levels?: NormLevel[];
  inForceAt?: string;
  limit: number;
};

export type CoverageBucket = {
  key: string;
  documents: number;
  lastProcessedAt?: string;
  documentsWithoutRepealDate: number;
  sourceVersionIds: string[];
  sourceVersionCount: number;
};

export type CoverageCounts = {
  /**
   * Documents matching the scope. NOT the sum of `buckets` — the grouping
   * fields are multi-valued, so one document can appear in several buckets, and
   * a document missing the field appears in none.
   */
  totalDocuments: number;
  /**
   * Documents matching the scope that carry no value for the grouping field.
   * Surfaced because `authority_ids` is sparse on legal documents, so grouping
   * by authority can omit a large share of the corpus without saying so.
   */
  documentsWithoutGroupKey: number;
  buckets: CoverageBucket[];
};

export interface CoverageRepository {
  countCoverage(options: CoverageQueryOptions): Promise<CoverageCounts>;
}
