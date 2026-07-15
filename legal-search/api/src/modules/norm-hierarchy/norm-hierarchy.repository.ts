/**
 * Norm-hierarchy repository interface (ADR-0008: OpenSearch logic lives only in
 * adapters).
 */
import type { InForceFields } from '../../core/norm-hierarchy';

/** A norm as it appears in a hierarchy walk. */
export type NormEntity = InForceFields & {
  document_id: string;
  title: string;
  level: string;
  jurisdiction_ids: string[];
  document_type?: string;
  official_citation?: string;
  effective_date?: string;
  subordinate_to?: string[];
};

export type NormsByLevel = {
  /** Norms found for each `level` bucket, capped at `perLevelLimit`. */
  documents: Map<string, NormEntity[]>;
  /** Total matching norms per level, BEFORE the cap — so the caller can say
   * "12 federal acts, showing 5" instead of implying there are only 5. */
  totals: Map<string, number>;
};

export type FindNormsOptions = {
  /** Every jurisdiction whose law governs the place being asked about. */
  jurisdictionIds: string[];
  /** ISO date. When set, norms known to be repealed by or not yet in force on
   * this date are excluded; norms with unknown dates are KEPT and reported. */
  inForceAt?: string;
  perLevelLimit: number;
};

export interface NormHierarchyRepository {
  findNormsByScopes(options: FindNormsOptions): Promise<NormsByLevel>;
}

export const NORM_HIERARCHY_REPOSITORY = Symbol('NORM_HIERARCHY_REPOSITORY');
