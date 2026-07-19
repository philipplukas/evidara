/**
 * View shapes for `GET /v1/coverage` (ADR-0042).
 *
 * Contract: `contracts/api/legal-search.openapi.yaml` is the source of truth.
 */

import type { NormLevel } from '../../../core/norm-hierarchy';
import type { CoverageDimension } from '../../../core/opensearch/facet-fields';

/**
 * Whether the corpus holds anything for a group.
 *
 * Two values, deliberately. `not_held` means "the index contains no document
 * matching this scope" — a claim about our holdings. It is NOT a claim that the
 * norm does not exist. There is no third value meaning "confirmed absent in
 * law", and adding one requires revisiting ADR-0042.
 */
export type CoverageHolding = 'held' | 'not_held';

export type CoverageScope = {
  jurisdiction_ids?: string[];
  authority_ids?: string[];
  document_types?: string[];
  levels?: NormLevel[];
  in_force_at?: string;
};

export type CoverageGroup = {
  key: string;
  label?: string;
  documents: number;
  holding: CoverageHolding;
  /**
   * `max(processed_at)` — when the newest document here entered the corpus.
   * NOT when the source was last checked, and therefore not a currency
   * guarantee. See ADR-0042 §3.
   */
  last_processed_at?: string;
  /**
   * Documents with no `in_force_until`: "not known to be repealed" is not
   * "never repealed", so this is how much of the group's in-force standing is
   * assumed rather than known.
   */
  documents_without_repeal_date: number;
  source_version_ids?: string[];
  source_version_count?: number;
};

export type CorpusCoverageView = {
  /** Always `index`: derived solely from what we hold, never from acquisition intent. */
  basis: 'index';
  as_of: string;
  group_by: CoverageDimension;
  scope: CoverageScope;
  total_documents: number;
  documents_without_group_key: number;
  unrecognized_jurisdiction_ids?: string[];
  groups: CoverageGroup[];
};
