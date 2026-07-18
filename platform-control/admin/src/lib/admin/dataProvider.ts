import {
  type CreateResult,
  type DataProvider,
  type DeleteManyParams,
  type DeleteManyResult,
  type DeleteParams,
  type DeleteResult,
  type GetListParams,
  type GetListResult,
  type GetManyResult,
  type GetOneResult,
  HttpError,
  type Identifier,
  type RaRecord,
  type UpdateManyParams,
  type UpdateManyResult,
  type UpdateResult,
} from "react-admin";
import { ResourceName } from "../../domain/resourceNames";

type ListResponse<T> = {
  data: T[];
};

/**
 * The `{data, limit, offset, total}` envelope every server-paginated
 * platform-control list returns (`/v1/sources`, `/v1/runs`, and the run-scoped
 * detail lists). `total` is the hit count, not the page length — see #616,
 * where the client re-derived it from the page and capped every list at the
 * server's default `limit=100`.
 */
type PaginatedListResponse<T> = {
  data: T[];
  total: number;
  limit: number;
  offset: number;
};

type ReferenceDataBase = {
  created_at: string;
  updated_at: string;
};

type Jurisdiction = ReferenceDataBase & {
  jurisdiction_id: string;
  name: string;
  slug: string;
};

type Authority = ReferenceDataBase & {
  authority_id: string;
  jurisdiction_id: string | null;
  name: string;
  slug: string;
};

type SharedAcquisitionSpec = {
  tenant_id?: string;
  corpus_id?: string;
  scope_type?: "global_public" | "tenant_private" | "tenant_shared";
  source_origin_kind?:
    | "official_primary"
    | "official_mirror"
    | "licensed_provider"
    | "community_curated"
    | "tenant_internal";
  trust_tier?: "authoritative" | "preferred" | "supplemental" | "untrusted";
  language_codes?: string[];
  document_type_hint?: string | null;
  request_timeout_seconds?: number;
  user_agent?: string | null;
  max_content_bytes?: number;
};

export type FirecrawlAcquisitionSpec = SharedAcquisitionSpec & {
  provider: "firecrawl";
  seed_url: string | null;
  seed_urls: string[];
  mode: "crawl" | "batch_scrape";
  include_paths: string[];
  exclude_paths: string[];
  limit: number;
  max_discovery_depth: number;
  scrape_formats: string[];
  zero_data_retention: boolean;
};

export type DeterministicHttpAcquisitionSpec = SharedAcquisitionSpec & {
  provider: "deterministic_http";
  seed_url: string | null;
  seed_urls: string[];
};

export type RisOgdAcquisitionSpec = SharedAcquisitionSpec & {
  provider: "ris_ogd";
  base_url: string;
  applikation: string | null;
  preferred_formats: string[];
  page_size: number;
  max_pages: number;
};

export type FedlexSparqlAcquisitionSpec = SharedAcquisitionSpec & {
  provider: "fedlex_sparql";
  seed_url: string | null;
  seed_urls: string[];
  sparql_endpoint: string;
  preferred_languages: string[];
  query_mode: "work_to_expression";
  max_expressions: number;
};

export type AcquisitionSpec =
  | FirecrawlAcquisitionSpec
  | DeterministicHttpAcquisitionSpec
  | RisOgdAcquisitionSpec
  | FedlexSparqlAcquisitionSpec;

type Source = {
  source_id: string;
  name: string;
  description: string | null;
  jurisdiction_id: string;
  authority_id: string;
  source_type: string;
  document_family: string | null;
  status: "active" | "inactive" | "archived";
  created_at: string;
  updated_at: string;
};

type SourceVersion = {
  source_version_id: string;
  source_id: string;
  extractor_profile_id: string | null;
  version_label: string;
  status: "draft" | "pending_approval" | "approved" | "rejected" | "superseded";
  acquisition_spec: AcquisitionSpec;
  created_at: string;
  updated_at: string;
};

type RunBase = {
  run_id: string;
  source_id: string;
  source_version_id: string;
  mode: "preview" | "production";
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
  started_at: string | null;
  completed_at: string | null;
  artifacts_count: number;
  captured_resources_count: number;
  failure_reason: string | null;
  created_at: string;
  updated_at: string;
};

type RunListItem = RunBase & {
  source_name: string;
  version_label: string;
};

type RunResponse = RunBase;

export type RunCreateInput = {
  source_id: string;
  source_version_id: string;
  mode: "preview" | "production";
};

export type RunReadinessCheck = {
  code: string;
  ok: boolean;
  detail: string;
};

export type RunReadiness = {
  source_id: string;
  source_version_id: string;
  mode: "preview" | "production";
  ready: boolean;
  checks: RunReadinessCheck[];
};

export type RunPipelineHealthStage = {
  stage: "acquisition" | "document_intelligence" | "projection" | "search";
  status: "pending" | "in_progress" | "blocked" | "failed" | "ok";
  detail: string;
  updated_at: string | null;
};

export type RunPipelineHealth = {
  run_id: string;
  source_id: string;
  source_version_id: string;
  mode: "preview" | "production";
  run_status: "pending" | "running" | "completed" | "failed" | "cancelled";
  overall_status: "in_progress" | "blocked" | "failed" | "ok";
  stages: RunPipelineHealthStage[];
  processing_status_event_count: number;
  document_lifecycle_event_count: number;
};

export type SourceBlueprintPreviewInput = {
  overlay_id: string;
  provider_template_id: string;
};

/**
 * The ADR-0030 two-key lock, as the API now reports it (#634). Without these
 * fields the panel cannot tell an inert template from a live one — it would
 * render `canton_http_zh` identically to the working Fedlex entry, then let an
 * operator walk four green steps into a 400. `enabled` is the config-owner key
 * (an operator flips it via `setBlueprintTemplateEnablement`, #632); `live_ready`
 * is the code-owner key; `launchable` is both turned; `notes` explains any
 * closed key.
 */
export type BlueprintTwoKeyLock = {
  enabled: boolean;
  live_ready: boolean;
  launchable: boolean;
  notes: string[];
};

/** Result of flipping the config key (#632) — carries the audit trail. */
export type BlueprintTemplateEnablement = {
  overlay_id: string;
  provider_template_id: string;
  enabled: boolean;
  default_enabled: boolean;
  source: "override" | "default";
  note: string | null;
  updated_by: string | null;
  updated_at: string | null;
};

export type SourceBlueprintPreview = SourceBlueprintPreviewInput & {
  acquisition_spec: AcquisitionSpec;
} & BlueprintTwoKeyLock;

export type SourceBlueprintTemplate = {
  overlay_id: string;
  provider_template_id: string;
  provider: "firecrawl" | "deterministic_http" | "ris_ogd" | "fedlex_sparql";
} & BlueprintTwoKeyLock;

type CapturedResource = {
  captured_resource_id: string;
  run_id: string;
  source_url: string;
  final_url: string;
  title: string | null;
  content_type: string;
  http_status: number | null;
  discovery_depth: number | null;
  checksum: string | null;
  fetched_at: string;
  created_at: string;
  updated_at: string;
};

type RawArtifact = {
  artifact_id: string;
  run_id: string;
  source_id: string;
  source_version_id: string;
  storage_path: string;
  content_type: string;
  artifact_metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

type ProviderJob = {
  provider_job_id: string;
  run_id: string;
  provider: string;
  external_job_id: string | null;
  status: "accepted" | "running" | "completed" | "failed";
  last_event_type: string | null;
  request_payload: Record<string, unknown>;
  response_payload: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

type ProcessingStatusUpdate = {
  event_id: string;
  processing_manifest_id: string;
  processing_version: string;
  status: string;
  occurred_at: string;
  source_snapshot_id: string | null;
  bundle_manifest_id: string | null;
  document_id: string | null;
  document_revision: number | null;
  error_code: string | null;
  error_summary: string | null;
  created_at: string;
  updated_at: string;
};

type DocumentLifecycleEvent = {
  event_id: string;
  event_type: string;
  run_id: string;
  document_id: string;
  document_revision: number;
  processing_manifest_id: string;
  processing_version: string | null;
  lifecycle_status: string | null;
  reason_code: string | null;
  reason_summary: string | null;
  search_disposition: string | null;
  occurred_at: string;
  created_at: string;
  updated_at: string;
};

export type RunPreviewSummarySample = {
  captured_resource_id: string;
  title: string | null;
  final_url: string;
  content_type: string;
  http_status: number | null;
  reason: string;
};

export type RunPreviewSummaryBreakdownEntry = {
  content_type: string;
  count: number;
};

export type RunPreviewSummaryDriftCheck = {
  name: string;
  status: "ok" | "warn";
  detail: string;
};

export type RunPreviewSummary = {
  run_id: string;
  captured_url_count: number;
  artifacts_count: number;
  captured_resources_count: number;
  pdf_count: number;
  likely_decision_page_count: number;
  likely_boilerplate_page_count: number;
  likely_duplicate_page_count: number;
  content_type_breakdown: RunPreviewSummaryBreakdownEntry[];
  likely_decision_pages: RunPreviewSummarySample[];
  likely_boilerplate_pages: RunPreviewSummarySample[];
  likely_duplicate_pages: RunPreviewSummarySample[];
  drift_checks: RunPreviewSummaryDriftCheck[];
};

/**
 * Endpoints that genuinely return an unbounded array under `data` — no
 * `limit`/`offset`/`total`, the whole table every time. These are the only
 * lists the client may sort and page itself. `sources` used to be listed here
 * and is not unbounded (#616).
 */
type SimpleListResourceName = "jurisdictions" | "authorities";
type RunDetailResourceName =
  | "run-captured-resources"
  | "run-raw-artifacts"
  | "run-provider-jobs"
  | "run-processing-status"
  | "run-document-lifecycle";

type ResourceRecordMap = {
  jurisdictions: Jurisdiction;
  authorities: Authority;
  sources: Source;
  "source-versions": SourceVersion;
  runs: RunListItem;
  "run-captured-resources": CapturedResource;
  "run-raw-artifacts": RawArtifact;
  "run-provider-jobs": ProviderJob;
  "run-processing-status": ProcessingStatusUpdate;
  "run-document-lifecycle": DocumentLifecycleEvent;
};

type SourceVersionMutationData = {
  source_id: string;
  version_label: string;
  extractor_profile_id?: string | null;
  acquisition_spec?: AcquisitionSpec;
  overlay_id?: string;
  provider_template_id?: string;
};

type SourceCreateWithVersionMutationData = {
  source: Partial<Source>;
  source_version: Omit<SourceVersionMutationData, "source_id">;
};

type RequestOptions = {
  method?: "GET" | "POST" | "PATCH" | "PUT";
  body?: unknown;
  /** Additional request headers (e.g. `X-Operator-Id` for corrections). */
  headers?: Record<string, string>;
};

export type JurisdictionRecord = Jurisdiction & RaRecord<Identifier>;
export type AuthorityRecord = Authority & RaRecord<Identifier>;
export type SourceRecord = Source & RaRecord<Identifier>;
export type SourceVersionRecord = SourceVersion & RaRecord<Identifier>;
export type RunListRecord = RunListItem & RaRecord<Identifier>;
export type RunRecord = RunResponse & RaRecord<Identifier>;
export type CapturedResourceRecord = CapturedResource & RaRecord<Identifier>;
export type RawArtifactRecord = RawArtifact & RaRecord<Identifier>;
export type ProviderJobRecord = ProviderJob & RaRecord<Identifier>;
export type ProcessingStatusRecord = ProcessingStatusUpdate & RaRecord<Identifier>;
export type DocumentLifecycleRecord = DocumentLifecycleEvent & RaRecord<Identifier>;

const API_PREFIX = "/api/platform-control";
const EMPTY_FILTER_VALUE = "__none__";

const SIMPLE_LIST_PATHS: Record<SimpleListResourceName, string> = {
  jurisdictions: "/v1/reference-data/jurisdictions",
  authorities: "/v1/reference-data/authorities",
};

/** Server-side ceiling on `limit` for the paginated lists (`max(1, min(limit, 500))`). */
const MAX_SERVER_PAGE_SIZE = 500;

const RUN_DETAIL_RESOURCE_CONFIG: {
  [key in RunDetailResourceName]: {
    idField: keyof ResourceRecordMap[key];
    path: (runId: string) => string;
  };
} = {
  "run-captured-resources": {
    idField: "captured_resource_id",
    path: (runId) => `/v1/runs/${runId}/captured-resources`,
  },
  "run-raw-artifacts": {
    idField: "artifact_id",
    path: (runId) => `/v1/runs/${runId}/raw-artifacts`,
  },
  "run-provider-jobs": {
    idField: "provider_job_id",
    path: (runId) => `/v1/runs/${runId}/provider-jobs`,
  },
  "run-processing-status": {
    idField: "event_id",
    path: (runId) => `/v1/runs/${runId}/processing-status`,
  },
  "run-document-lifecycle": {
    idField: "event_id",
    path: (runId) => `/v1/runs/${runId}/document-lifecycle`,
  },
};

const unsupported = async (resource: string, method: string): Promise<never> => {
  throw new Error(`${method} is not implemented for resource "${resource}".`);
};

const parseErrorPayload = async (response: Response): Promise<unknown> => {
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    return response.json();
  }

  const text = await response.text();
  return text.length > 0 ? { detail: text } : null;
};

const requestJson = async <T>(path: string, options: RequestOptions = {}): Promise<T> => {
  const headers: Record<string, string> = {
    Accept: "application/json",
  };
  const init: RequestInit = {
    method: options.method ?? "GET",
    headers,
    cache: "no-store",
  };

  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(options.body);
  }

  if (options.headers) {
    Object.assign(headers, options.headers);
  }

  const response = await fetch(`${API_PREFIX}${path}`, init);

  if (!response.ok) {
    const errorPayload = await parseErrorPayload(response);
    const detail =
      typeof errorPayload === "object" &&
      errorPayload !== null &&
      "detail" in errorPayload &&
      typeof errorPayload.detail === "string"
        ? errorPayload.detail
        : `Platform-control request failed with status ${response.status}.`;
    throw new HttpError(detail, response.status, errorPayload);
  }

  return response.json() as Promise<T>;
};

const normalizeNullableString = (value: unknown): string | null | undefined => {
  if (value === undefined) {
    return undefined;
  }
  if (value === null) {
    return null;
  }
  if (typeof value !== "string") {
    return null;
  }
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
};

const toRecord = <TItem extends Record<string, unknown>, TIdField extends keyof TItem>(
  item: TItem,
  idField: TIdField,
): TItem & RaRecord<Identifier> => ({
  id: item[idField] as Identifier,
  ...item,
});

const isRunDetailResource = (resource: string): resource is RunDetailResourceName =>
  resource in RUN_DETAIL_RESOURCE_CONFIG;

const fetchSimpleList = async <TResource extends SimpleListResourceName>(
  resource: TResource,
): Promise<ResourceRecordMap[TResource][]> => {
  const response = await requestJson<ListResponse<ResourceRecordMap[TResource]>>(
    SIMPLE_LIST_PATHS[resource],
  );
  return response.data;
};

const findInSimpleList = async <TResource extends SimpleListResourceName>(
  resource: TResource,
  idField: keyof ResourceRecordMap[TResource],
  id: Identifier,
): Promise<ResourceRecordMap[TResource]> => {
  const items = await fetchSimpleList(resource);
  const match = items.find((item) => item[idField] === id);
  if (!match) {
    throw new HttpError(`${resource} record not found`, 404);
  }
  return match;
};

/**
 * Translate ra-core's 1-based `{page, perPage}` into the server's
 * `{limit, offset}`, clamped the same way the API clamps it.
 */
const toLimitOffset = (params: GetListParams): { limit: number; offset: number } => {
  const page = params.pagination?.page ?? 1;
  const perPage = params.pagination?.perPage ?? 25;
  const limit = Math.min(Math.max(perPage, 1), MAX_SERVER_PAGE_SIZE);
  const offset = Math.max((page - 1) * limit, 0);
  return { limit, offset };
};

const setPaginationParams = (query: URLSearchParams, params: GetListParams): void => {
  const { limit, offset } = toLimitOffset(params);
  query.set("limit", String(limit));
  query.set("offset", String(offset));
};

const toRunsQueryString = (params: GetListParams): string => {
  const query = new URLSearchParams();
  const { filter } = params;

  if (typeof filter.mode === "string" && filter.mode.length > 0) {
    query.set("mode", filter.mode);
  }
  if (typeof filter.status === "string" && filter.status.length > 0) {
    query.set("status", filter.status);
  }
  if (typeof filter.source_id === "string" && !isMissingFilterValue(filter.source_id)) {
    query.set("source_id", filter.source_id);
  }
  setPaginationParams(query, params);

  return `?${query.toString()}`;
};

const toSourcesQueryString = (params: GetListParams): string => {
  const query = new URLSearchParams();
  const search = params.filter.q;
  if (typeof search === "string" && search.trim().length > 0) {
    query.set("q", search.trim());
  }
  setPaginationParams(query, params);
  return `?${query.toString()}`;
};

const compareSortValues = (left: unknown, right: unknown): number => {
  if (left === right) {
    return 0;
  }
  if (left === undefined || left === null) {
    return -1;
  }
  if (right === undefined || right === null) {
    return 1;
  }
  if (typeof left === "number" && typeof right === "number") {
    return left - right;
  }
  if (typeof left === "boolean" && typeof right === "boolean") {
    return Number(left) - Number(right);
  }
  return String(left).localeCompare(String(right));
};

const applyClientSort = <T extends Record<string, unknown>>(
  records: T[],
  params: GetListParams,
): T[] => {
  const sortField = params.sort?.field ?? "id";
  const sortOrder = params.sort?.order ?? "ASC";
  return [...records].sort((left, right) => {
    const cmp = compareSortValues(left[sortField as keyof T], right[sortField as keyof T]);
    return sortOrder === "DESC" ? -cmp : cmp;
  });
};

/**
 * Sort + page a list response **only** for endpoints that genuinely return the
 * whole collection in one unbounded array — `SIMPLE_LIST_PATHS` (reference
 * data) and `/v1/sources/{id}/versions`. Server-paginated endpoints must not
 * come through here: windowing a page re-derives `total` from the page length
 * and silently caps the list at the server default (#616).
 */
const applyClientListWindow = <T extends Record<string, unknown>>(
  records: T[],
  params: GetListParams,
): { data: T[]; total: number } => {
  const sorted = applyClientSort(records, params);
  const { limit, offset } = toLimitOffset(params);
  return { data: sorted.slice(offset, offset + limit), total: sorted.length };
};

/**
 * Sort the records the server already selected for this page. Ordering is
 * page-local by design: `/v1/sources` and `/v1/runs` order by `created_at DESC`
 * server-side and accept no sort parameter, so a column sort can only reorder
 * the rows in hand. `total` comes from the server.
 */
const toServerPagedResult = <T extends Record<string, unknown>>(
  records: T[],
  total: number | undefined,
  params: GetListParams,
): { data: T[]; total: number } => ({
  data: applyClientSort(records, params),
  total: total ?? records.length,
});

const normalizeDriftStatus = (status: string): "ok" | "warn" => (status === "warn" ? "warn" : "ok");

const normalizeRunPreviewSummary = (raw: RunPreviewSummary): RunPreviewSummary => ({
  ...raw,
  content_type_breakdown: raw.content_type_breakdown ?? [],
  likely_decision_pages: raw.likely_decision_pages ?? [],
  likely_boilerplate_pages: raw.likely_boilerplate_pages ?? [],
  likely_duplicate_pages: raw.likely_duplicate_pages ?? [],
  drift_checks: (raw.drift_checks ?? []).map((check) => ({
    ...check,
    status: normalizeDriftStatus(check.status),
  })),
});

const isMissingFilterValue = (value: string | undefined): boolean =>
  value === undefined || value.length === 0 || value === EMPTY_FILTER_VALUE;

const toJurisdictionPayload = (data: Partial<Jurisdiction>): Partial<Jurisdiction> => ({
  name: data.name,
  slug: data.slug,
});

const toAuthorityPayload = (data: Partial<Authority>): Partial<Authority> => ({
  jurisdiction_id: normalizeNullableString(data.jurisdiction_id),
  name: data.name,
  slug: data.slug,
});

const toSourcePayload = (data: Partial<Source>): Partial<Source> => ({
  name: data.name,
  description: normalizeNullableString(data.description),
  jurisdiction_id: data.jurisdiction_id,
  authority_id: data.authority_id,
  source_type: data.source_type ?? "website",
  document_family: normalizeNullableString(data.document_family),
});

const toSourceCreateWithVersionPayload = (
  data: SourceCreateWithVersionMutationData,
): {
  source: Partial<Source>;
  source_version: Partial<Omit<SourceVersionMutationData, "source_id">>;
} => ({
  source: toSourcePayload(data.source),
  source_version: toSourceVersionPayload(data.source_version),
});

const toSourceVersionPayload = (
  data: Partial<SourceVersionMutationData>,
): Partial<Omit<SourceVersionMutationData, "source_id">> => {
  const payload: Partial<Omit<SourceVersionMutationData, "source_id">> = {};
  if (data.version_label !== undefined) {
    payload.version_label = data.version_label;
  }
  if (data.extractor_profile_id !== undefined) {
    payload.extractor_profile_id = normalizeNullableString(data.extractor_profile_id);
  }
  if (data.acquisition_spec !== undefined) {
    payload.acquisition_spec = data.acquisition_spec;
  }
  if (data.overlay_id !== undefined && data.overlay_id.trim().length > 0) {
    payload.overlay_id = data.overlay_id.trim();
  }
  if (data.provider_template_id !== undefined && data.provider_template_id.trim().length > 0) {
    payload.provider_template_id = data.provider_template_id.trim();
  }
  return payload;
};

// ─── Corrections + CommentaryInsights (M7 HITL track) ───
//
// Wire shapes mirror `contracts/schemas/corrections.json` and
// `contracts/schemas/commentary-insight.schema.json` (PR #434). The
// admin app calls these through React Admin's `dataProvider`, which
// the page-level components consume via the standard hooks
// (`useGetList`, `useGetOne`, `useCreate`, `useUpdate`).

export type CorrectionResponseRecord = {
  correction_id: string;
  target_entity_type: "source" | "document" | "commentary_insight";
  target_entity_id: string;
  correction_type: "field_edit" | "annotation" | "reject" | "rescore_request";
  payload: Record<string, unknown>;
  original_snapshot: Record<string, unknown> | null;
  operator_id: string;
  pipeline_run_id: string | null;
  rationale: string | null;
  status: "pending" | "applied" | "rejected" | "superseded";
  created_at: string;
  applied_at: string | null;
};

export type CorrectionRecord = CorrectionResponseRecord & RaRecord<Identifier>;

export type CorrectionListResponse = {
  data: CorrectionResponseRecord[];
  total?: number;
  limit?: number;
  offset?: number;
};

export type CommentaryInsightRecord = {
  insight_id: string;
  document_id: string;
  document_revision: number;
  processing_manifest_id: string;
  section_id: string | null;
  citation_id: string | null;
  record_kind: "commentary_insight";
  insight_type: string;
  claim: string;
  display_text: string;
  support: Array<Record<string, unknown>>;
  referenced_authorities: Array<Record<string, unknown>>;
  language: string | null;
  jurisdiction_id: string | null;
  jurisdiction_ids: string[];
  authority_ids: string[];
  source_document_ids: string[];
  confidence: number;
  review_state: string;
  generator: Record<string, unknown>;
  scores: Record<string, unknown>;
  metadata: Record<string, unknown> | null;
  overlay_revision: number;
  last_correction_id: string | null;
  created_at: string;
  updated_at: string;
};

/**
 * `CommentaryInsightRecord` intersected with `RaRecord` (the `id` is stamped by
 * `toRecord(item, "insight_id")` in `getList`/`getOne`). Mirrors `CorrectionRecord`
 * and is what the ra-core list/show controllers are parameterised on — the raw
 * `CommentaryInsightRecord` is the wire shape, this is the in-store shape.
 */
export type CommentaryInsightRaRecord = CommentaryInsightRecord & RaRecord<Identifier>;

export type CommentaryInsightListResponse = {
  data: CommentaryInsightRecord[];
  total?: number;
  limit?: number;
  offset?: number;
};

export type CorrectionMetricsWeeklyBucket = {
  week_start: string;
  count: number;
};

export type CorrectionMetricsGroupedSeries = {
  key: string;
  buckets: CorrectionMetricsWeeklyBucket[];
};

export type CorrectionMetricsOperatorThroughput = {
  operator_id: string;
  total: number;
  applied: number;
  rejected: number;
};

export type CorrectionMetricsRescoreOutcomes = {
  pending: number;
  applied_total: number;
  rejected: number;
  changed: number;
  unchanged: number;
  failed: number;
};

export type CorrectionMetricsResponseRecord = {
  window_weeks: number;
  operator_throughput_window_days: number;
  weekly_by_target_entity_type: CorrectionMetricsGroupedSeries[];
  weekly_by_correction_type: CorrectionMetricsGroupedSeries[];
  operator_throughput: CorrectionMetricsOperatorThroughput[];
  rescore_outcomes: CorrectionMetricsRescoreOutcomes;
};

export type CreateCorrectionMutationData = {
  target_entity_type: "source" | "document" | "commentary_insight";
  target_entity_id: string;
  correction_type: "field_edit" | "annotation" | "reject" | "rescore_request";
  payload: Record<string, unknown>;
  original_snapshot?: Record<string, unknown> | null;
  pipeline_run_id?: string | null;
  rationale?: string | null;
  /**
   * Operator identity for the request — sent as `X-Operator-Id` header,
   * not in the request body, per PR #440. Optional during scaffold;
   * the API has a documented sentinel fallback.
   */
  operator_id?: string;
};

export type UpdateCorrectionStatusMutationData = {
  status: "applied" | "rejected" | "superseded";
  rationale?: string | null;
};

const toCreateCorrectionPayload = (data: Partial<CreateCorrectionMutationData>) => {
  const payload: Record<string, unknown> = {
    target_entity_type: data.target_entity_type,
    target_entity_id: data.target_entity_id,
    correction_type: data.correction_type,
    payload: data.payload ?? {},
  };
  if (data.original_snapshot !== undefined) {
    payload.original_snapshot = data.original_snapshot;
  }
  if (data.pipeline_run_id !== undefined) {
    payload.pipeline_run_id = data.pipeline_run_id;
  }
  if (data.rationale !== undefined) {
    payload.rationale = data.rationale;
  }
  return payload;
};

const toCorrectionStatusPayload = (data: Partial<UpdateCorrectionStatusMutationData>) => {
  const payload: Record<string, unknown> = {
    status: data.status,
  };
  if (data.rationale !== undefined) {
    payload.rationale = data.rationale;
  }
  return payload;
};

const readOperatorId = (data: Partial<CreateCorrectionMutationData>): string | undefined => {
  if (typeof data.operator_id === "string" && data.operator_id.trim().length > 0) {
    return data.operator_id.trim();
  }
  return undefined;
};

const toCorrectionsQueryString = (params: GetListParams): string => {
  const query = new URLSearchParams();
  const { filter, pagination } = params;
  if (typeof filter.target_entity_type === "string" && filter.target_entity_type.length > 0) {
    query.set("target_entity_type", filter.target_entity_type);
  }
  if (typeof filter.target_entity_id === "string" && filter.target_entity_id.length > 0) {
    query.set("target_entity_id", filter.target_entity_id);
  }
  if (typeof filter.operator_id === "string" && filter.operator_id.length > 0) {
    query.set("operator_id", filter.operator_id);
  }
  if (typeof filter.status === "string" && filter.status.length > 0) {
    query.set("status", filter.status);
  }
  if (typeof filter.correction_type === "string" && filter.correction_type.length > 0) {
    query.set("correction_type", filter.correction_type);
  }
  if (pagination?.perPage) {
    query.set("limit", String(pagination.perPage));
  }
  if (pagination?.page && pagination.perPage) {
    const offset = (pagination.page - 1) * pagination.perPage;
    if (offset > 0) {
      query.set("offset", String(offset));
    }
  }
  const queryString = query.toString();
  return queryString.length > 0 ? `?${queryString}` : "";
};

const toCommentaryInsightsQueryString = (params: GetListParams): string => {
  const query = new URLSearchParams();
  const { filter, pagination } = params;
  if (typeof filter.document_id === "string" && filter.document_id.length > 0) {
    query.set("document_id", filter.document_id);
  }
  if (typeof filter.review_state === "string" && filter.review_state.length > 0) {
    query.set("review_state", filter.review_state);
  }
  if (pagination?.perPage) {
    query.set("limit", String(pagination.perPage));
  }
  if (pagination?.page && pagination.perPage) {
    const offset = (pagination.page - 1) * pagination.perPage;
    if (offset > 0) {
      query.set("offset", String(offset));
    }
  }
  const queryString = query.toString();
  return queryString.length > 0 ? `?${queryString}` : "";
};

const getSimpleListResult = async <TResource extends SimpleListResourceName>(
  resource: TResource,
  idField: keyof ResourceRecordMap[TResource],
  params: GetListParams,
): Promise<GetListResult<ResourceRecordMap[TResource] & RaRecord<Identifier>>> => {
  const items = await fetchSimpleList(resource);
  const records = items.map((item) => toRecord(item, idField));
  return applyClientListWindow(records, params);
};

const buildRunScopedListQuery = (params: GetListParams): string => {
  const query = new URLSearchParams();
  setPaginationParams(query, params);
  return `?${query.toString()}`;
};

/**
 * Walk every page of `/v1/sources` so `getMany` can resolve ids beyond the
 * server's default page. Reference lookups ask for specific ids, so silently
 * stopping at the first page would blank the label for any source past it.
 */
const fetchAllSources = async (): Promise<Source[]> => {
  const collected: Source[] = [];
  let offset = 0;
  for (;;) {
    const query = new URLSearchParams({
      limit: String(MAX_SERVER_PAGE_SIZE),
      offset: String(offset),
    });
    const response = await requestJson<PaginatedListResponse<Source>>(`/v1/sources?${query}`);
    collected.push(...response.data);
    offset += MAX_SERVER_PAGE_SIZE;
    if (response.data.length === 0 || collected.length >= response.total) {
      return collected;
    }
  }
};

const getRunDetailList = async <TResource extends RunDetailResourceName>(
  resource: TResource,
  params: GetListParams,
): Promise<GetListResult<ResourceRecordMap[TResource] & RaRecord<Identifier>>> => {
  const runId = params.filter.run_id;
  if (typeof runId !== "string" || isMissingFilterValue(runId)) {
    return {
      data: [],
      total: 0,
    };
  }
  const config = RUN_DETAIL_RESOURCE_CONFIG[resource];
  const response = await requestJson<PaginatedListResponse<ResourceRecordMap[TResource]>>(
    `${config.path(runId)}${buildRunScopedListQuery(params)}`,
  );
  return {
    data: response.data.map((item) => toRecord(item, config.idField)),
    total: response.total,
  };
};

export const controlPlaneActions = {
  async cancelRun(runId: string): Promise<RunRecord> {
    const response = await requestJson<RunResponse>(`/v1/runs/${runId}/cancel`, {
      method: "POST",
    });
    return toRecord(response, "run_id");
  },

  async getRunPreviewSummary(runId: string): Promise<RunPreviewSummary> {
    const raw = await requestJson<RunPreviewSummary>(`/v1/runs/${runId}/preview-summary`);
    return normalizeRunPreviewSummary(raw);
  },

  async getRunReadiness(input: RunCreateInput): Promise<RunReadiness> {
    const query = new URLSearchParams({
      source_id: input.source_id,
      source_version_id: input.source_version_id,
      mode: input.mode,
    });
    return requestJson<RunReadiness>(`/v1/runs/readiness?${query.toString()}`);
  },

  async getRunPipelineHealth(runId: string): Promise<RunPipelineHealth> {
    return requestJson<RunPipelineHealth>(`/v1/runs/${runId}/pipeline-health`);
  },

  async approveSourceVersion(sourceVersionId: string): Promise<SourceVersionRecord> {
    const response = await requestJson<SourceVersion>(`/v1/versions/${sourceVersionId}/approve`, {
      method: "POST",
    });
    return toRecord(response, "source_version_id");
  },

  async rejectSourceVersion(sourceVersionId: string): Promise<SourceVersionRecord> {
    const response = await requestJson<SourceVersion>(`/v1/versions/${sourceVersionId}/reject`, {
      method: "POST",
    });
    return toRecord(response, "source_version_id");
  },

  async previewSourceBlueprint(
    input: SourceBlueprintPreviewInput,
  ): Promise<SourceBlueprintPreview> {
    return requestJson<SourceBlueprintPreview>("/v1/sources/blueprint-preview", {
      method: "POST",
      body: input,
    });
  },

  async listSourceBlueprintTemplates(): Promise<SourceBlueprintTemplate[]> {
    const response = await requestJson<ListResponse<SourceBlueprintTemplate>>(
      "/v1/sources/blueprint-templates",
    );
    return response.data;
  },

  /**
   * Flip the operator-reachable ADR-0030 config key for one template (#632).
   *
   * This is the key an operator turns after capturing acceptance-run evidence —
   * over the API, with an audit trail, no repo edit and no deploy. The code key
   * (`live_ready`) is unaffected: a run at a scaffold provider still refuses.
   */
  async setBlueprintTemplateEnablement(
    overlayId: string,
    providerTemplateId: string,
    input: { enabled: boolean; note?: string | null },
  ): Promise<BlueprintTemplateEnablement> {
    return requestJson<BlueprintTemplateEnablement>(
      `/v1/sources/blueprint-templates/${encodeURIComponent(overlayId)}/${encodeURIComponent(
        providerTemplateId,
      )}/enablement`,
      { method: "PUT", body: input },
    );
  },

  /**
   * Fetch the correction metrics aggregate for the admin dashboard (#432).
   *
   * Backed by `GET /v1/corrections/metrics`. Caller controls the
   * weekly window + operator-throughput window via the optional args;
   * defaults match the server defaults (8 weeks, 30 days).
   */
  async getCorrectionMetrics(
    options: {
      windowWeeks?: number;
      operatorThroughputWindowDays?: number;
      operatorThroughputTopN?: number;
    } = {},
  ): Promise<CorrectionMetricsResponseRecord> {
    const query = new URLSearchParams();
    if (options.windowWeeks !== undefined) {
      query.set("window_weeks", String(options.windowWeeks));
    }
    if (options.operatorThroughputWindowDays !== undefined) {
      query.set("operator_throughput_window_days", String(options.operatorThroughputWindowDays));
    }
    if (options.operatorThroughputTopN !== undefined) {
      query.set("operator_throughput_top_n", String(options.operatorThroughputTopN));
    }
    const queryString = query.toString();
    const path =
      queryString.length > 0 ? `/v1/corrections/metrics?${queryString}` : "/v1/corrections/metrics";
    return requestJson<CorrectionMetricsResponseRecord>(path);
  },
};

export const controlPlaneDataProvider: DataProvider = {
  async getList(resource, params): Promise<GetListResult> {
    if (resource === ResourceName.Jurisdictions) {
      return getSimpleListResult(ResourceName.Jurisdictions, "jurisdiction_id", params);
    }

    if (resource === ResourceName.Authorities) {
      return getSimpleListResult(ResourceName.Authorities, "authority_id", params);
    }

    if (resource === ResourceName.Sources) {
      const response = await requestJson<PaginatedListResponse<Source>>(
        `/v1/sources${toSourcesQueryString(params)}`,
      );
      const records = response.data.map((item) => toRecord(item, "source_id"));
      return toServerPagedResult(records, response.total, params);
    }

    if (resource === "source-versions") {
      const sourceId = params.filter.source_id;
      if (typeof sourceId !== "string" || isMissingFilterValue(sourceId)) {
        return {
          data: [],
          total: 0,
        };
      }
      const response = await requestJson<ListResponse<SourceVersion>>(
        `/v1/sources/${sourceId}/versions`,
      );
      const records = response.data.map((item) => toRecord(item, "source_version_id"));
      return applyClientListWindow(records, params);
    }

    if (resource === ResourceName.Runs) {
      const response = await requestJson<PaginatedListResponse<RunListItem>>(
        `/v1/runs${toRunsQueryString(params)}`,
      );
      const records = response.data.map((item) => toRecord(item, "run_id"));
      return toServerPagedResult(records, response.total, params);
    }

    if (resource === ResourceName.PreviewReview) {
      const previewParams: GetListParams = {
        ...params,
        filter: {
          ...params.filter,
          mode: "preview",
        },
      };
      const response = await requestJson<PaginatedListResponse<RunListItem>>(
        `/v1/runs${toRunsQueryString(previewParams)}`,
      );
      const records = response.data.map((item) => toRecord(item, "run_id"));
      return toServerPagedResult(records, response.total, params);
    }

    if (isRunDetailResource(resource)) {
      return getRunDetailList(resource, params);
    }

    if (resource === ResourceName.Corrections) {
      const query = toCorrectionsQueryString(params);
      const response = await requestJson<CorrectionListResponse>(`/v1/corrections${query}`);
      const records = response.data.map((item) => toRecord(item, "correction_id"));
      return {
        data: records,
        total: response.total ?? records.length,
      };
    }

    if (resource === ResourceName.CommentaryInsights) {
      const query = toCommentaryInsightsQueryString(params);
      const response = await requestJson<CommentaryInsightListResponse>(
        `/v1/commentary-insights${query}`,
      );
      const records = response.data.map((item) => toRecord(item, "insight_id"));
      return {
        data: records,
        total: response.total ?? records.length,
      };
    }

    throw new Error(`Unsupported resource "${resource}".`);
  },

  async getOne(resource, params): Promise<GetOneResult> {
    if (resource === ResourceName.Jurisdictions) {
      return {
        data: toRecord(
          await findInSimpleList(ResourceName.Jurisdictions, "jurisdiction_id", params.id),
          "jurisdiction_id",
        ),
      };
    }

    if (resource === ResourceName.Authorities) {
      return {
        data: toRecord(
          await findInSimpleList(ResourceName.Authorities, "authority_id", params.id),
          "authority_id",
        ),
      };
    }

    if (resource === ResourceName.Sources) {
      const response = await requestJson<Source>(`/v1/sources/${params.id}`);
      return {
        data: toRecord(response, "source_id"),
      };
    }

    if (resource === ResourceName.Runs) {
      const response = await requestJson<RunResponse>(`/v1/runs/${params.id}`);
      return {
        data: toRecord(response, "run_id"),
      };
    }

    if (resource === ResourceName.PreviewReview) {
      const response = await requestJson<RunResponse>(`/v1/runs/${params.id}`);
      if (response.mode !== "preview") {
        throw new HttpError("Preview approval run not found", 404);
      }
      return {
        data: toRecord(response, "run_id"),
      };
    }

    if (resource === ResourceName.Corrections) {
      const response = await requestJson<CorrectionResponseRecord>(`/v1/corrections/${params.id}`);
      return { data: toRecord(response, "correction_id") };
    }

    if (resource === ResourceName.CommentaryInsights) {
      const response = await requestJson<CommentaryInsightRecord>(
        `/v1/commentary-insights/${params.id}`,
      );
      return { data: toRecord(response, "insight_id") };
    }

    return unsupported(resource, "getOne");
  },

  async getMany(resource, params): Promise<GetManyResult> {
    if (resource === ResourceName.Jurisdictions) {
      const items = await fetchSimpleList(ResourceName.Jurisdictions);
      return {
        data: items
          .filter((item) => params.ids.includes(item.jurisdiction_id))
          .map((item) => toRecord(item, "jurisdiction_id")),
      };
    }

    if (resource === ResourceName.Authorities) {
      const items = await fetchSimpleList(ResourceName.Authorities);
      return {
        data: items
          .filter((item) => params.ids.includes(item.authority_id))
          .map((item) => toRecord(item, "authority_id")),
      };
    }

    if (resource === ResourceName.Sources) {
      const items = await fetchAllSources();
      return {
        data: items
          .filter((item) => params.ids.includes(item.source_id))
          .map((item) => toRecord(item, "source_id")),
      };
    }

    return unsupported(resource, "getMany");
  },

  async getManyReference(resource): Promise<GetManyResult> {
    return unsupported(resource, "getManyReference");
  },

  async update(resource, params): Promise<UpdateResult> {
    if (resource === ResourceName.Jurisdictions) {
      const response = await requestJson<Jurisdiction>(
        `/v1/reference-data/jurisdictions/${params.id}`,
        {
          method: "PATCH",
          body: toJurisdictionPayload(params.data),
        },
      );
      return {
        data: toRecord(response, "jurisdiction_id"),
      };
    }

    if (resource === ResourceName.Authorities) {
      const response = await requestJson<Authority>(`/v1/reference-data/authorities/${params.id}`, {
        method: "PATCH",
        body: toAuthorityPayload(params.data),
      });
      return {
        data: toRecord(response, "authority_id"),
      };
    }

    if (resource === "source-versions") {
      const response = await requestJson<SourceVersion>(`/v1/versions/${params.id}`, {
        method: "PATCH",
        body: toSourceVersionPayload(params.data),
      });
      return {
        data: toRecord(response, "source_version_id"),
      };
    }

    if (resource === ResourceName.Corrections) {
      // PATCH /v1/corrections/{id} is the lifecycle-transition endpoint
      // (see PR #434). The dataProvider passes through `status` and
      // optional `rationale`; the server enforces legal transitions.
      const response = await requestJson<CorrectionResponseRecord>(`/v1/corrections/${params.id}`, {
        method: "PATCH",
        body: toCorrectionStatusPayload(params.data),
      });
      return {
        data: toRecord(response, "correction_id"),
      };
    }

    return unsupported(resource, "update");
  },

  async updateMany(resource, _params: UpdateManyParams): Promise<UpdateManyResult> {
    return unsupported(resource, "updateMany");
  },

  async create(resource, params): Promise<CreateResult> {
    if (resource === ResourceName.Jurisdictions) {
      const response = await requestJson<Jurisdiction>("/v1/reference-data/jurisdictions", {
        method: "POST",
        body: toJurisdictionPayload(params.data),
      });
      return {
        data: toRecord(response, "jurisdiction_id"),
      };
    }

    if (resource === ResourceName.Authorities) {
      const response = await requestJson<Authority>("/v1/reference-data/authorities", {
        method: "POST",
        body: toAuthorityPayload(params.data),
      });
      return {
        data: toRecord(response, "authority_id"),
      };
    }

    if (resource === ResourceName.Sources) {
      const response = await requestJson<Source>("/v1/sources", {
        method: "POST",
        body: toSourcePayload(params.data),
      });
      return {
        data: toRecord(response, "source_id"),
      };
    }

    if (resource === "source-create-wizard") {
      const mutation = params.data as SourceCreateWithVersionMutationData;
      const response = await requestJson<{ source: Source; source_version: SourceVersion }>(
        "/v1/sources/with-version",
        {
          method: "POST",
          body: toSourceCreateWithVersionPayload(mutation),
        },
      );
      return {
        data: toRecord(
          {
            ...response.source,
            source_version: response.source_version,
          },
          "source_id",
        ),
      };
    }

    if (resource === "source-versions") {
      const mutation = params.data as SourceVersionMutationData;
      const response = await requestJson<SourceVersion>(
        `/v1/sources/${mutation.source_id}/versions`,
        {
          method: "POST",
          body: toSourceVersionPayload(mutation),
        },
      );
      return {
        data: toRecord(response, "source_version_id"),
      };
    }

    if (resource === ResourceName.Runs) {
      const response = await requestJson<RunResponse>("/v1/runs", {
        method: "POST",
        body: params.data as RunCreateInput,
      });
      return {
        data: toRecord(response, "run_id"),
      };
    }

    if (resource === ResourceName.Corrections) {
      // POST /v1/corrections is the canonical write surface. The
      // CommentaryInsight editor submits a `field_edit` correction
      // through this entry point; admin code never PATCHes the insight
      // directly. See PR #440 for the design rationale.
      const operatorId = readOperatorId(params.data);
      const headers: Record<string, string> = {};
      if (operatorId) {
        headers["X-Operator-Id"] = operatorId;
      }
      const response = await requestJson<CorrectionResponseRecord>("/v1/corrections", {
        method: "POST",
        body: toCreateCorrectionPayload(params.data),
        headers,
      });
      return {
        data: toRecord(response, "correction_id"),
      };
    }

    return unsupported(resource, "create");
  },

  async delete(resource, _params: DeleteParams): Promise<DeleteResult> {
    return unsupported(resource, "delete");
  },

  async deleteMany(resource, _params: DeleteManyParams): Promise<DeleteManyResult> {
    return unsupported(resource, "deleteMany");
  },
};
