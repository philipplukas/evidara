/**
 * Search repository interface.
 * Adapters implement this to abstract the search backend.
 */
import type { ContextAggregations, SearchResultEntity } from './entities/search.entities';

export interface SearchRepository {
  /**
   * Runs the query. Resolving means the query *executed*: `total: 0` is a
   * genuine "zero matches". A query that could not be executed (missing
   * index/alias, connection refused, timeout) rejects with
   * `SearchBackendUnavailableError` — it is never flattened into an empty
   * result set (#551).
   */
  search(query: string, options?: SearchOptions): Promise<SearchResultEntity>;
  /** Same contract as `search`: rejects rather than returning empty aggregations. */
  getContextAggregations(): Promise<ContextAggregations>;
  /**
   * The canonical jurisdiction ids (`jur_*`) the index holds at least one
   * document for — a `jurisdiction_ids` terms aggregation over the read alias.
   *
   * This is what lets search answer "do I hold the law of the place being asked
   * about?" instead of ranking (#986). Same contract as `search`: it rejects
   * rather than resolving empty when the query could not be executed. An empty
   * array means the aggregation ran and produced no buckets — which the caller
   * must treat as UNKNOWN rather than "holds nothing", because a drifted
   * mapping produces exactly that shape (#675).
   */
  getHeldJurisdictionIds(): Promise<string[]>;
  /**
   * Readiness probe: does the documents read alias resolve to at least one
   * index? Non-throwing by design — the caller (health endpoint) reports the
   * failure rather than propagating it.
   */
  checkReadAlias(): Promise<ReadAliasCheck>;
}

/** Result of the read-alias readiness probe. */
export type ReadAliasCheck =
  | { status: 'ok'; alias: string; indices: string[] }
  | { status: 'error'; alias: string; detail: string };

export interface SearchOptions {
  jurisdictions?: string[];
  /**
   * Canonical platform jurisdiction IDs (`jur_*`). ANDed with `jurisdictions`
   * (ISO) when both are present. Routes to the projection's
   * `jurisdiction_ids.keyword` field rather than the legacy `jurisdiction` /
   * subdivision keyword fields.
   */
  jurisdictionIds?: string[];
  /**
   * Canonical platform authority IDs (`auth_*`). Routes to
   * `authority_ids.keyword`.
   */
  authorityIds?: string[];
  languages?: string[];
  documentTypes?: string[];
  officialOnly?: boolean;
  refinements?: SearchRefinement[];
  page?: number;
  pageSize?: number;
}

export interface SearchRefinement {
  field: string;
  type: 'terms' | 'date_range' | 'range' | 'toggle' | 'text';
  values: string[];
  from?: string;
  to?: string;
  value?: boolean | string;
}

export const SEARCH_REPOSITORY = Symbol('SEARCH_REPOSITORY');
