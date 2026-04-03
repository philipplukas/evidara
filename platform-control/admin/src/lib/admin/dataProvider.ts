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

export type FirecrawlAcquisitionSpec = {
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
  acquisition_spec: FirecrawlAcquisitionSpec;
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
  acquisition_spec: FirecrawlAcquisitionSpec;
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
    payload.acquisition_spec = data.acquisition_spec as FirecrawlAcquisitionSpec;
  }
  return payload;
};

const getSimpleListResult = async <TResource extends SimpleListResourceName>(
  resource: TResource,
  idField: keyof ResourceRecordMap[TResource],
): Promise<GetListResult<ResourceRecordMap[TResource] & RaRecord<Identifier>>> => {
  const items = await fetchSimpleList(resource);
  return {
    data: items.map((item) => toRecord(item, idField)),
    total: items.length,
  };
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
  const response = await requestJson<ListResponse<ResourceRecordMap[TResource]>>(
    config.path(runId),
  );
  return {
    data: response.data.map((item) => toRecord(item, config.idField)),
    total: response.data.length,
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
    return requestJson<RunPreviewSummary>(`/v1/runs/${runId}/preview-summary`);
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
};

export const controlPlaneDataProvider: DataProvider = {
  async getList(resource, params): Promise<GetListResult> {
    if (resource === "jurisdictions") {
      return getSimpleListResult("jurisdictions", "jurisdiction_id");
    }

    if (resource === "authorities") {
      return getSimpleListResult("authorities", "authority_id");
    }

    if (resource === "sources") {
      return getSimpleListResult("sources", "source_id");
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
      return {
        data: response.data.map((item) => toRecord(item, "source_version_id")),
        total: response.data.length,
      };
    }

    if (resource === "runs") {
      const response = await requestJson<ListResponse<RunListItem>>(
        `/v1/runs${toQueryString(params)}`,
      );
      return {
        data: response.data.map((item) => toRecord(item, "run_id")),
        total: response.data.length,
      };
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
      return {
        data: response.data.map((item) => toRecord(item, "run_id")),
        total: response.data.length,
      };
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
