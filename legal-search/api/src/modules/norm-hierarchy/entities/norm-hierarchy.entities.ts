/**
 * ViewModel shapes for `GET /v1/norm-hierarchy/{jurisdiction_id}`.
 * Mirrors `NormHierarchyView` in contracts/api/legal-search.openapi.yaml.
 */
import type { InForceState, NormLevel } from '../../../core/norm-hierarchy';

export type NormHierarchyJurisdiction = {
  jurisdiction_id: string;
  name: string;
  slug: string;
  level: string;
};

export type NormHierarchyDocumentView = {
  document_id: string;
  title: string;
  document_type?: string;
  official_citation?: string;
  jurisdiction_ids: string[];
  effective_date?: string;
  in_force_from?: string;
  in_force_until?: string;
  /** Only resolved when the caller asked `in_force_at`. */
  in_force_state?: InForceState;
};

export type NormHierarchyLevelView = {
  level: NormLevel;
  /** Lower rank = higher authority. */
  rank: number;
  label: string;
  /** The jurisdictions whose law sits at this level for this place. */
  jurisdiction_ids: string[];
  /** Total norms held at this level, before `documents` was capped. */
  total: number;
  documents: NormHierarchyDocumentView[];
};

export type NormHierarchyView = {
  jurisdiction: NormHierarchyJurisdiction;
  in_force_at?: string;
  /** Ordered most authoritative first. */
  levels: NormHierarchyLevelView[];
  coverage: {
    covered_levels: NormLevel[];
    /** Levels that bind this place but for which the corpus holds nothing. */
    missing_levels: NormLevel[];
  };
};
