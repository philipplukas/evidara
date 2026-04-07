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

type ListResponse<T> = {
  data: T[];
};

type RunScopedPaginatedList<T> = {
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

export type AcquisitionSpec =
  | FirecrawlAcquisitionSpec
  | DeterministicHttpAcquisitionSpec
  | RisOgdAcquisitionSpec;

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

export type SourceBlueprintPreview = SourceBlueprintPreviewInput & {
  acquisition_spec: AcquisitionSpec;
};

export type SourceBlueprintTemplate = {
  overlay_id: string;
  provider_template_id: string;
  provider: "firecrawl" | "deterministic_http" | "ris_ogd";
};

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

type SimpleListResourceName = "jurisdictions" | "authorities" | "sources";
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
  method?: "GET" | "POST" | "PATCH";
  body?: unknown;
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
  sources: "/v1/sources",
};

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

const toQueryString = (params: GetListParams): string => {
  const query = new URLSearchParams();
  const { filter } = params;

  if (typeof filter.mode === "string" && filter.mode.length > 0) {
    query.set("mode", filter.mode);
  }
  if (typeof filter.status === "string" && filter.status.length > 0) {
    query.set("status", filter.status);
  }

  const queryString = query.toString();
  return queryString.length > 0 ? `?${queryString}` : "";
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

/** Sort + page full list responses when the API returns an unbounded array. */
const applyClientListWindow = <T extends Record<string, unknown>>(
  records: T[],
  params: GetListParams,
): { data: T[]; total: number } => {
  const sortField = params.sort?.field ?? "id";
  const sortOrder = params.sort?.order ?? "ASC";
  const page = params.pagination?.page ?? 1;
  const perPage = params.pagination?.perPage ?? 25;

  const sorted = [...records].sort((left, right) => {
    const cmp = compareSortValues(left[sortField as keyof T], right[sortField as keyof T]);
    return sortOrder === "DESC" ? -cmp : cmp;
  });

  const total = sorted.length;
  const limit = Math.min(Math.max(perPage, 1), 500);
  const start = Math.max((page - 1) * limit, 0);
  const data = sorted.slice(start, start + limit);
  return { data, total };
};

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
  const page = params.pagination?.page ?? 1;
  const perPage = params.pagination?.perPage ?? 100;
  const limit = Math.min(Math.max(perPage, 1), 500);
  const offset = Math.max((page - 1) * limit, 0);
  const query = new URLSearchParams();
  query.set("limit", String(limit));
  query.set("offset", String(offset));
  return `?${query.toString()}`;
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
  const response = await requestJson<RunScopedPaginatedList<ResourceRecordMap[TResource]>>(
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
};

export const controlPlaneDataProvider: DataProvider = {
  async getList(resource, params): Promise<GetListResult> {
    if (resource === "jurisdictions") {
      return getSimpleListResult("jurisdictions", "jurisdiction_id", params);
    }

    if (resource === "authorities") {
      return getSimpleListResult("authorities", "authority_id", params);
    }

    if (resource === "sources") {
      return getSimpleListResult("sources", "source_id", params);
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

    if (resource === "runs") {
      const response = await requestJson<ListResponse<RunListItem>>(
        `/v1/runs${toQueryString(params)}`,
      );
      const records = response.data.map((item) => toRecord(item, "run_id"));
      return applyClientListWindow(records, params);
    }

    if (resource === "preview-review") {
      const previewParams: GetListParams = {
        ...params,
        filter: {
          ...params.filter,
          mode: "preview",
        },
      };
      const response = await requestJson<ListResponse<RunListItem>>(
        `/v1/runs${toQueryString(previewParams)}`,
      );
      const records = response.data.map((item) => toRecord(item, "run_id"));
      return applyClientListWindow(records, params);
    }

    if (isRunDetailResource(resource)) {
      return getRunDetailList(resource, params);
    }

    throw new Error(`Unsupported resource "${resource}".`);
  },

  async getOne(resource, params): Promise<GetOneResult> {
    if (resource === "jurisdictions") {
      return {
        data: toRecord(
          await findInSimpleList("jurisdictions", "jurisdiction_id", params.id),
          "jurisdiction_id",
        ),
      };
    }

    if (resource === "authorities") {
      return {
        data: toRecord(
          await findInSimpleList("authorities", "authority_id", params.id),
          "authority_id",
        ),
      };
    }

    if (resource === "sources") {
      const response = await requestJson<Source>(`/v1/sources/${params.id}`);
      return {
        data: toRecord(response, "source_id"),
      };
    }

    if (resource === "runs") {
      const response = await requestJson<RunResponse>(`/v1/runs/${params.id}`);
      return {
        data: toRecord(response, "run_id"),
      };
    }

    if (resource === "preview-review") {
      const response = await requestJson<RunResponse>(`/v1/runs/${params.id}`);
      if (response.mode !== "preview") {
        throw new HttpError("Preview review run not found", 404);
      }
      return {
        data: toRecord(response, "run_id"),
      };
    }

    return unsupported(resource, "getOne");
  },

  async getMany(resource, params): Promise<GetManyResult> {
    if (resource === "jurisdictions") {
      const items = await fetchSimpleList("jurisdictions");
      return {
        data: items
          .filter((item) => params.ids.includes(item.jurisdiction_id))
          .map((item) => toRecord(item, "jurisdiction_id")),
      };
    }

    if (resource === "authorities") {
      const items = await fetchSimpleList("authorities");
      return {
        data: items
          .filter((item) => params.ids.includes(item.authority_id))
          .map((item) => toRecord(item, "authority_id")),
      };
    }

    if (resource === "sources") {
      const items = await fetchSimpleList("sources");
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
    if (resource === "jurisdictions") {
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

    if (resource === "authorities") {
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

    return unsupported(resource, "update");
  },

  async updateMany(resource, _params: UpdateManyParams): Promise<UpdateManyResult> {
    return unsupported(resource, "updateMany");
  },

  async create(resource, params): Promise<CreateResult> {
    if (resource === "jurisdictions") {
      const response = await requestJson<Jurisdiction>("/v1/reference-data/jurisdictions", {
        method: "POST",
        body: toJurisdictionPayload(params.data),
      });
      return {
        data: toRecord(response, "jurisdiction_id"),
      };
    }

    if (resource === "authorities") {
      const response = await requestJson<Authority>("/v1/reference-data/authorities", {
        method: "POST",
        body: toAuthorityPayload(params.data),
      });
      return {
        data: toRecord(response, "authority_id"),
      };
    }

    if (resource === "sources") {
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

    if (resource === "runs") {
      const response = await requestJson<RunResponse>("/v1/runs", {
        method: "POST",
        body: params.data as RunCreateInput,
      });
      return {
        data: toRecord(response, "run_id"),
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
