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
import { classifyTemplate } from "../../domain/blueprintLock";
import { ResourceName } from "../../domain/resourceNames";
import type { RunMode } from "../../domain/runMode";
import type { Schemas } from "../api/schemas";

type ListResponse<T> = {
  data: T[];
};

/**
 * The `{data, limit, offset, total}` envelope every server-paginated
 * platform-control list returns (`/v1/sources`, `/v1/runs`, and the run-scoped
 * detail lists). `total` is the hit count, not the page length — see #616,
 * where the client re-derived it from the page and capped every list at the
 * server's default `limit=100`.
 *
 * `total`/`limit`/`offset` are optional and nullable because the contract says
 * so: `Schemas["RunListResponse"]` requires only `data` and types the rest
 * `number | null`. This type used to declare all three as required `number`,
 * which is strictly narrower than what the server may send — the divergence
 * #695 was filed over, and the same class of assumption that caused #616. The
 * `?? records.length` fallback in `toServerPagedResult` is the branch that
 * narrowing hid; it is now reachable in the type system and covered by a test.
 */
type PaginatedListResponse<T> = {
  data: T[];
  total?: number | null;
  limit?: number | null;
  offset?: number | null;
};

type Jurisdiction = Schemas["JurisdictionResponse"];
// Aliased from the generated contract, never hand-written: a hand-rolled shape here
// is a divergence nothing can detect (AGENTS.md rule 4).
type AcquisitionCoverageEntry = Schemas["AcquisitionCoverageEntry"];
type AcquisitionCoverageListResponse = Schemas["AcquisitionCoverageListResponse"];
export type AcquisitionCoverageSummary = Schemas["AcquisitionCoverageSummary"];
export type CoverageWorkQueueResponse = Schemas["CoverageWorkQueueResponse"];
export type CoverageWorkItem = Schemas["CoverageWorkItem"];

type Authority = Schemas["AuthorityResponse"];

export type FirecrawlAcquisitionSpec = Schemas["FirecrawlAcquisitionSpec"];

export type DeterministicHttpAcquisitionSpec = Schemas["DeterministicHttpAcquisitionSpec"];

export type RisOgdAcquisitionSpec = Schemas["RisOgdAcquisitionSpec"];

export type FedlexSparqlAcquisitionSpec = Schemas["FedlexSparqlAcquisitionSpec"];

/**
 * Every acquisition spec the API can serve — all eleven providers, straight
 * from the contract.
 *
 * This union used to list the **four** providers the version dialog renders
 * widgets for, which conflated "what the form can edit" with "what the wire
 * carries". That conflation is #614: the admin coerced the other seven into
 * `firecrawl` and persisted the corruption with an HTTP 200. The tests papered
 * over it with `as unknown as AcquisitionSpec` casts on genuine `canton_http`
 * payloads.
 *
 * The editable subset is a separate, explicit concept and stays that way —
 * `EDITABLE_PROVIDERS` / `isEditableProvider` in `sourceVersionForm.ts`. A
 * provider this form cannot edit must be *unrenderable*, never *unrepresentable*.
 */
export type AcquisitionSpec = Schemas["SourceVersionResponse"]["acquisition_spec"];

type Source = Schemas["SourceResponse"];

export type SourceVersion = Schemas["SourceVersionResponse"];

/**
 * The full run, as `GET /v1/runs/{id}` serves it.
 *
 * Distinct from `RunListItem` on purpose: only the detail response carries
 * `scope`, `replay` and `replay_checkpoint`, and only the list row carries
 * `source_name`/`version_label`. Both used to alias one hand-written `RunBase`,
 * which typed neither honestly and left the admin unable to describe a refused
 * run at all — `refused` is the ADR-0030 two-key-lock flag from #634.
 */
type RunResponse = Schemas["RunResponse"];

/** One row of `GET /v1/runs` — the run plus its denormalised source labels. */
export type RunListItem = Schemas["RunListItemResponse"];

export type RunCreateInput = {
  source_id: string;
  source_version_id: string;
  mode: RunMode;
};

export type RunReadinessCheck = Schemas["RunReadinessCheck"];

export type RunReadiness = Schemas["RunReadinessResponse"];

export type RunPipelineHealthStage = Schemas["RunPipelineHealthStage"];

export type RunPipelineHealth = Schemas["RunPipelineHealthResponse"];

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
export type AcquisitionReadiness = Schemas["AcquisitionReadiness"];

export type BlueprintTwoKeyLock = {
  enabled: boolean;
  /**
   * Boolean projection of `acquisition_readiness`, true only for `"live"`.
   * Retained for compatibility; branch on `acquisition_readiness` instead, or a
   * built-but-unproven provider reads as a scaffold (#743).
   */
  live_ready: boolean;
  acquisition_readiness?: AcquisitionReadiness;
  launchable: boolean;
  notes: string[];
};

/** One machine-readable reason platform-control refused to move the config key (#854). */
export type BlueprintEnablementRefusal = {
  code: string;
  detail: string;
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
  /**
   * The server re-read the write and confirmed it — the effective key AND an
   * `override` provenance. A 200 alone cannot tell a flip from a write that silently
   * did nothing (#631, #713), so the dialog reports on this, not on the status code.
   */
  applied: boolean;
  /** The flip happened, but something was not decided for you. */
  needs_human: boolean;
  needs_human_reasons: string[];
  evidence_run_id: string | null;
  /** `"template"` is exact; anything weaker wants a human to confirm it (#846). */
  evidence_binding: string | null;
};

/** What the operator has to supply to arm the ADR-0030 config key (#854). */
export type BlueprintTemplateEnablementInput = {
  enabled: boolean;
  note?: string | null;
  evidence_run_id?: string | null;
  reopen_operator_kill_switch?: boolean;
  acknowledge_provider_below_live?: boolean;
};

/**
 * Read the ADR-0030 refusal codes off a rejected enablement `PUT`.
 *
 * The refusals arrive as a 409 body, which `requestJson` attaches to the thrown
 * `HttpError`. Returning `[]` for a body this cannot parse would render a refusal as
 * "nothing was wrong", so an unparseable 409 still yields one refusal.
 */
export function blueprintEnablementRefusals(error: unknown): BlueprintEnablementRefusal[] {
  const body = error instanceof HttpError ? (error.body as unknown) : undefined;
  const raw =
    typeof body === "object" && body !== null && "refusals" in body
      ? (body as { refusals?: unknown }).refusals
      : undefined;
  const refusals = Array.isArray(raw)
    ? raw.flatMap((item): BlueprintEnablementRefusal[] => {
        if (typeof item !== "object" || item === null) return [];
        const { code, detail } = item as { code?: unknown; detail?: unknown };
        if (typeof code !== "string" || code.length === 0) return [];
        return [{ code, detail: typeof detail === "string" ? detail : "" }];
      })
    : [];
  if (refusals.length > 0) return refusals;
  if (error instanceof HttpError && error.status === 409) {
    return [
      {
        code: "refused_by_server",
        detail:
          error.message || "platform-control refused the flip and did not say which rule it broke.",
      },
    ];
  }
  return [];
}

export type SourceBlueprintPreview = SourceBlueprintPreviewInput & {
  acquisition_spec: AcquisitionSpec;
} & BlueprintTwoKeyLock;

/**
 * One row of the operator's coverage inventory (#668).
 *
 * `provider` is a plain `string`, not a union: eleven providers exist and a
 * four-member union was how the contract drifted in the first place (#618).
 * Narrowing it here would make `gemeinde_http` — the municipal path the whole
 * ADR-0033 dog axis runs on — a type error in the panel that lists it.
 *
 * The provenance fields say where the config key's current value came from:
 * `source: "default"` means nobody has ever touched it (the shipped
 * `source_blueprints.yaml` value is in force), `"override"` means an operator
 * deliberately flipped it and `note`/`updated_by`/`updated_at` carry the audit
 * trail. `updated_by` is **key-shaped, not person-shaped** — every human
 * sharing an operator API key resolves to the same identity.
 */
export type SourceBlueprintTemplate = {
  overlay_id: string;
  provider_template_id: string;
  provider: string;
  default_enabled: boolean;
  source: "override" | "default";
  note: string | null;
  updated_by: string | null;
  updated_at: string | null;
} & BlueprintTwoKeyLock;

type CapturedResource = Schemas["CapturedResourceResponse"];

type RawArtifact = Schemas["RawArtifactResponse"];

type ProviderJob = Schemas["ProviderJobResponse"];

type ProcessingStatusUpdate = Schemas["ProcessingStatusUpdateResponse"];

type DocumentLifecycleEvent = Schemas["DocumentLifecycleEventResponse"];

export type RunPreviewSummarySample = Schemas["RunPreviewSummarySample"];

export type RunPreviewSummaryBreakdownEntry = Schemas["RunPreviewSummaryBreakdownEntry"];

export type RunPreviewSummaryDriftCheck = Schemas["RunPreviewSummaryDriftCheck"];

export type RunPreviewSummary = Schemas["RunPreviewSummaryResponse"];

/**
 * The reference-data collections, at `/v1/reference-data/*`.
 *
 * These are **server-paginated** as of #616 — they return the same
 * `{data, limit, offset, total}` envelope as `/v1/sources` and `/v1/runs`. They
 * are grouped separately only because they have no by-id endpoint, so `getOne`
 * and `getMany` resolve records by paging the collection out
 * (`fetchAllSimpleList`).
 *
 * `sources` used to be listed here on the false premise that it was unbounded,
 * which is #616 itself; jurisdictions and authorities were the remaining half of
 * that same mistake, at 2,169 rows per list render.
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
export type AcquisitionCoverageRecord = AcquisitionCoverageEntry & RaRecord<Identifier>;
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

/** One server page of a reference-data list. */
const fetchSimpleListPage = async <TResource extends SimpleListResourceName>(
  resource: TResource,
  { limit, offset, q }: { limit: number; offset: number; q?: string },
): Promise<PaginatedListResponse<ResourceRecordMap[TResource]>> => {
  const query = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  /*
   * `/v1/reference-data/{jurisdictions,authorities}` have taken a `q` name
   * filter since they were paginated (`reference_data.py`), and the admin never
   * sent it. So the jurisdictions list — 2,169 rows, 44 pages, alphabetical —
   * had no way to find a row at all, while the create-source wizard's picker
   * over the same registry searched fine (client-side, over the fully paged-out
   * list). Filtering server-side means the pager and the caption keep reporting
   * the real total for the search, rather than for the page in hand.
   */
  if (q) {
    query.set("q", q);
  }
  return requestJson<PaginatedListResponse<ResourceRecordMap[TResource]>>(
    `${SIMPLE_LIST_PATHS[resource]}?${query}`,
  );
};

/**
 * Every record in a reference-data collection, by paging the endpoint out.
 *
 * `/v1/reference-data/{jurisdictions,authorities}` are server-paginated since
 * #616 — before that they returned all 2,169 jurisdictions on every list render.
 * Three callers genuinely need the whole table and cannot work from a page:
 * `getOne` and `getMany` resolve records by id (there is no by-id endpoint), and
 * the reference pickers must offer every jurisdiction or Zürich becomes
 * unselectable again (#666).
 *
 * Requesting `limit=25000` would not serve them: the server clamps to 500 and
 * says nothing, which is how #666 happened. Loop instead.
 */
const fetchAllSimpleList = async <TResource extends SimpleListResourceName>(
  resource: TResource,
): Promise<ResourceRecordMap[TResource][]> => {
  const collected: ResourceRecordMap[TResource][] = [];
  let offset = 0;
  for (;;) {
    const response = await fetchSimpleListPage(resource, {
      limit: MAX_SERVER_PAGE_SIZE,
      offset,
    });
    collected.push(...response.data);
    offset += MAX_SERVER_PAGE_SIZE;
    // Continue only on an exactly-full page. A short page is the last one; an
    // over-full page means the server ignored `limit`, in which case it has
    // already given us everything and asking again would loop forever. Neither
    // case may consult `total`, which the contract permits to be null.
    if (response.data.length !== MAX_SERVER_PAGE_SIZE) {
      return collected;
    }
    if (response.total != null && collected.length >= response.total) {
      return collected;
    }
  }
};

const findInSimpleList = async <TResource extends SimpleListResourceName>(
  resource: TResource,
  idField: keyof ResourceRecordMap[TResource],
  id: Identifier,
): Promise<ResourceRecordMap[TResource]> => {
  const items = await fetchAllSimpleList(resource);
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
  // ADR-0030 two-key-lock refusals (#634). `GET /v1/runs?refused=true` was built
  // specifically so refusals can be audited "without them polluting failure
  // triage" — and then no client ever sent the parameter, so the record ADR-0035
  // built reached no screen. Only an explicit boolean is forwarded: an absent
  // filter must keep meaning "both", not "false".
  if (typeof filter.refused === "boolean") {
    query.set("refused", String(filter.refused));
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
 * Sort + page an array the client already holds **in full**.
 *
 * Two callers qualify: `/v1/sources/{id}/versions` and
 * `/v1/sources/blueprint-templates`, which genuinely return whole collections,
 * and the reference-data pickers, which have paged the collection out
 * themselves via `fetchAllSimpleList`.
 *
 * A single server *page* must never come through here — windowing one re-derives
 * `total` from the page length and silently caps the list at the server default,
 * which is exactly #616.
 */
/**
 * Window an in-memory array the way `getList` promises to.
 *
 * This deliberately does **not** reuse `toLimitOffset`. That helper clamps to
 * `MAX_SERVER_PAGE_SIZE` because the API clamps `limit` the same way — a
 * server-request concern that has no business capping a slice of an array the
 * browser already holds in full. Applying it here meant a caller asking for
 * "all 2,169 jurisdictions" got 500 and no way to tell (#666): the picker fix is
 * not just "raise `perPage`", because any `perPage` above 500 was silently
 * ignored. `total` stays the true array length either way.
 */
const applyClientListWindow = <T extends Record<string, unknown>>(
  records: T[],
  params: GetListParams,
): { data: T[]; total: number } => {
  const sorted = applyClientSort(records, params);
  const perPage = Math.max(params.pagination?.perPage ?? 25, 1);
  const page = Math.max(params.pagination?.page ?? 1, 1);
  const offset = (page - 1) * perPage;
  return { data: sorted.slice(offset, offset + perPage), total: sorted.length };
};

/**
 * Sort the records the server already selected for this page. Ordering is
 * page-local by design: `/v1/sources` and `/v1/runs` order by `created_at DESC`
 * server-side and accept no sort parameter, so a column sort can only reorder
 * the rows in hand. `total` comes from the server.
 */
const toServerPagedResult = <T extends Record<string, unknown>>(
  records: T[],
  total: number | null | undefined,
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

/**
 * Coalesce every field of the coverage summary before it reaches React.
 *
 * #623: a raw `res.json()` whose shape had drifted took down the whole SPA. The summary
 * is rendered above a 2110-row table, so a single missing counter would blank the page
 * an operator opened precisely to find out what is missing.
 *
 * Returns null rather than a zeroed object when the block is absent — zeros here would
 * read as "measured, found nothing", which is the ledger's own cardinal sin.
 */
const normalizeAcquisitionCoverageSummary = (
  raw: AcquisitionCoverageSummary | undefined | null,
): AcquisitionCoverageSummary | null => {
  if (!raw || typeof raw !== "object") {
    return null;
  }
  const count = (value: unknown): number => (typeof value === "number" ? value : 0);
  return {
    ...raw,
    jurisdictions_total: count(raw.jurisdictions_total),
    jurisdictions_with_any_acquired: count(raw.jurisdictions_with_any_acquired),
    jurisdictions_with_any_processed: count(raw.jurisdictions_with_any_processed),
    jurisdictions_with_published_denominator: count(raw.jurisdictions_with_published_denominator),
    jurisdictions_with_registry_denominator: count(raw.jurisdictions_with_registry_denominator),
    reconciliations_unattributed: count(raw.reconciliations_unattributed),
    processed_documents_unattributable: count(raw.processed_documents_unattributable),
    unmeasured_stages: Array.isArray(raw.unmeasured_stages) ? raw.unmeasured_stages : [],
  };
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

/**
 * `getList` for the reference-data collections, which have two kinds of caller.
 *
 * The list views ask for a page (`perPage: 50`) and want the true hit count so
 * their pager is honest — that is a server page, read straight through. The
 * reference pickers ask for everything (`REFERENCE_PICKER_LIST_PARAMS`, 25,000)
 * because a combobox over jurisdictions has to offer all of them (#666); that
 * cannot be one request, since the server clamps `limit` to 500.
 *
 * Deciding on `perPage` keeps the distinction where the caller already states
 * it, rather than adding a flag. Anything above the server ceiling means "the
 * whole collection", and is served by paging out and then windowing in memory.
 */
const getSimpleListResult = async <TResource extends SimpleListResourceName>(
  resource: TResource,
  idField: keyof ResourceRecordMap[TResource],
  params: GetListParams,
): Promise<GetListResult<ResourceRecordMap[TResource] & RaRecord<Identifier>>> => {
  const perPage = Math.max(params.pagination?.perPage ?? 25, 1);

  if (perPage > MAX_SERVER_PAGE_SIZE) {
    const items = await fetchAllSimpleList(resource);
    const records = items.map((item) => toRecord(item, idField));
    return applyClientListWindow(records, params);
  }

  const { limit, offset } = toLimitOffset(params);
  // `q` is the only filter these endpoints accept; anything else in
  // `params.filter` is not silently dropped into the query string, because a
  // filter the server ignores is a filter the operator believes is applied.
  const rawQuery = params.filter?.q;
  const q =
    typeof rawQuery === "string" && rawQuery.trim().length > 0 ? rawQuery.trim() : undefined;
  const response = await fetchSimpleListPage(resource, { limit, offset, q });
  const records = response.data.map((item) => toRecord(item, idField));
  return toServerPagedResult(records, response.total, params);
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
    // Continue only on an exactly-full page — see `fetchAllSimpleList` for why
    // an over-full page must terminate too. The contract permits `total: null`,
    // so neither check may depend on it.
    if (response.data.length !== MAX_SERVER_PAGE_SIZE) {
      return collected;
    }
    if (response.total != null && collected.length >= response.total) {
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
    total: response.total ?? response.data.length,
  };
};

/**
 * Wizard wire types, mirroring `platform_control.schemas.wizard`.
 *
 * `WizardRunState` repeats `platform_control.domain.WizardRunState`. The
 * terminal member matters: `GateExpired` is what an un-actioned human gate
 * becomes, and it is terminal *on purpose* — the fallback is always to refuse to
 * scale, never to auto-approve a fan-out of crawls against live government
 * portals. Anything rendering these states must not present it as a transient
 * error with a retry.
 */
export type WizardRunState =
  | "DraftScope"
  | "DiscoveryPlan"
  | "PilotRun"
  | "HumanGateApproval"
  | "ScaledRun"
  | "ReviewRouting"
  | "FinalizePublish"
  | "MonitorAndDrift"
  | "GateExpired";

export interface WizardProject {
  wizard_project_id: string;
  name: string;
  status: "draft" | "active" | "archived";
  scope: Record<string, unknown>;
  discovery_plan: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface WizardRunStatus {
  wizard_run_id: string;
  wizard_project_id: string;
  workflow_id: string | null;
  state: WizardRunState;
  state_entered_at: string;
  progress: {
    total_nodes: number;
    processed_nodes: number;
    routed_to_review: number;
    accepted_records: number;
  };
  quality: {
    confidence_distribution: Record<string, unknown>;
    conflict_count: number;
    review_backlog: number;
  };
  health: {
    retry_counters: Record<string, unknown>;
    last_errors: string[];
    next_retry_window: string | null;
  };
  failure_reason: string | null;
  created_at: string;
  updated_at: string;
}

export const controlPlaneActions = {
  async cancelRun(runId: string): Promise<RunRecord> {
    const response = await requestJson<RunResponse>(`/v1/runs/${runId}/cancel`, {
      method: "POST",
    });
    return toRecord(response, "run_id");
  },

  /**
   * `POST /v1/runs/{id}/retry` — the one recovery action for the one state that
   * needs recovering.
   *
   * The endpoint has existed since runs did (`routers/runs.py:203`); nothing in
   * the admin called it. A failed run's detail page offered "Jump to…" anchors
   * and nothing else, so the only lever on the only state that needs a lever was
   * an operator's own `curl`. The server resets the run to PENDING, drops its
   * provider jobs, and re-dispatches — so this is a real dispatch, not a
   * bookkeeping flip, and the caller must confirm it.
   */
  async retryRun(runId: string): Promise<RunRecord> {
    const response = await requestJson<RunResponse>(`/v1/runs/${runId}/retry`, {
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
    input: BlueprintTemplateEnablementInput,
  ): Promise<BlueprintTemplateEnablement> {
    return requestJson<BlueprintTemplateEnablement>(
      `/v1/sources/blueprint-templates/${encodeURIComponent(overlayId)}/${encodeURIComponent(
        providerTemplateId,
      )}/enablement`,
      { method: "PUT", body: input },
    );
  },

  /**
   * Fetch the acquisition-coverage summary (#816).
   *
   * Separate from `getList` because a react-admin list result has nowhere to carry a
   * summary block, and the summary is the headline: it is what makes "1 mapped commune
   * of 2110" legible instead of leaving it to be inferred from 2110 mostly-empty rows.
   */
  async getAcquisitionCoverageSummary(): Promise<AcquisitionCoverageSummary | null> {
    // limit=1 — we want the envelope's summary, not the page.
    const response = await requestJson<AcquisitionCoverageListResponse>(
      "/v1/acquisition-coverage?limit=1",
    );
    return normalizeAcquisitionCoverageSummary(response?.summary);
  },

  /**
   * Fetch the coverage work queue — the ledger, as a worklist (#907, #930).
   *
   * Separate from `getList` for the same reason as the summary above: the
   * response carries `jurisdictions_without_a_source` and `ordering` alongside
   * the rows, and a react-admin list result has nowhere to put them.
   *
   * The ordering is the SERVER'S and is echoed back in the payload. Do not
   * re-sort it here — a second ranking in a client is how one rule ends up
   * enforced twice with the weaker copy winning.
   */
  async getCoverageWorkQueue(limit = 50): Promise<CoverageWorkQueueResponse | null> {
    const response = await requestJson<CoverageWorkQueueResponse>(
      `/v1/acquisition-coverage/queue?limit=${encodeURIComponent(String(limit))}`,
    );
    return response ?? null;
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

  /* ---------------------------------------------------------------------- *
   * Wizard (ADR-0021). Nine endpoints under /v1/wizard that no UI called.
   *
   * NOTE: there is deliberately no `listWizardProjects` here, because the API
   * has no such route — `GET /v1/wizard/projects` answers 405 (verified
   * 2026-09-06). Only `GET /projects/{id}` exists, so the onboarding surface
   * carries the project id in its URL and cannot render an index. Adding the
   * list route is a contract change (regenerate + manifest bump); until then,
   * do not fake an index client-side.
   * ---------------------------------------------------------------------- */

  async createWizardProject(name: string): Promise<WizardProject> {
    return requestJson<WizardProject>("/v1/wizard/projects", {
      method: "POST",
      body: { name },
    });
  },

  async getWizardProject(projectId: string): Promise<WizardProject> {
    return requestJson<WizardProject>(`/v1/wizard/projects/${encodeURIComponent(projectId)}`);
  },

  async saveWizardScope(projectId: string, scope: Record<string, unknown>): Promise<WizardProject> {
    return requestJson<WizardProject>(
      `/v1/wizard/projects/${encodeURIComponent(projectId)}/scope`,
      { method: "POST", body: { scope } },
    );
  },

  async saveWizardDiscoveryPlan(
    projectId: string,
    discoveryPlan: Record<string, unknown>,
  ): Promise<WizardProject> {
    return requestJson<WizardProject>(
      `/v1/wizard/projects/${encodeURIComponent(projectId)}/discovery-plan`,
      { method: "POST", body: { discovery_plan: discoveryPlan } },
    );
  },

  async startWizardPilotRun(projectId: string, sampleLimit?: number): Promise<WizardRunStatus> {
    return requestJson<WizardRunStatus>(
      `/v1/wizard/projects/${encodeURIComponent(projectId)}/pilot-run`,
      { method: "POST", body: { sample_limit: sampleLimit ?? null } },
    );
  },

  async getWizardRun(runId: string): Promise<WizardRunStatus> {
    return requestJson<WizardRunStatus>(`/v1/wizard/runs/${encodeURIComponent(runId)}`);
  },

  async approveWizardRun(runId: string, reason?: string): Promise<WizardRunStatus> {
    return requestJson<WizardRunStatus>(`/v1/wizard/runs/${encodeURIComponent(runId)}/approve`, {
      method: "POST",
      body: { reason: reason ?? null },
    });
  },

  async rejectWizardRun(runId: string, reason?: string): Promise<WizardRunStatus> {
    return requestJson<WizardRunStatus>(`/v1/wizard/runs/${encodeURIComponent(runId)}/reject`, {
      method: "POST",
      body: { reason: reason ?? null },
    });
  },

  /**
   * `POST /v1/wizard/runs/{id}/restart` — the ONLY exit from `GateExpired`.
   *
   * That state is terminal by design: an un-actioned human gate must never
   * auto-approve a fan-out of crawls against live government portals. Restart
   * starts a *fresh* run on the same project (keeping scope and discovery plan)
   * and returns the NEW run, so the caller must re-point at the returned id.
   */
  async restartWizardRun(runId: string): Promise<WizardRunStatus> {
    return requestJson<WizardRunStatus>(`/v1/wizard/runs/${encodeURIComponent(runId)}/restart`, {
      method: "POST",
    });
  },
};

export const controlPlaneDataProvider: DataProvider = {
  async getList(resource, params): Promise<GetListResult> {
    if (resource === ResourceName.AcquisitionCoverage) {
      const page = params.pagination?.page ?? 1;
      const perPage = Math.min(params.pagination?.perPage ?? 50, MAX_SERVER_PAGE_SIZE);
      const query = new URLSearchParams({
        limit: String(perPage),
        offset: String((page - 1) * perPage),
      });
      const level = params.filter?.level;
      if (typeof level === "string" && level.length > 0) {
        query.set("level", level);
      }
      const response = await requestJson<AcquisitionCoverageListResponse>(
        `/v1/acquisition-coverage?${query.toString()}`,
      );
      const records = (response.data ?? []).map((item) => toRecord(item, "jurisdiction_id"));
      return toServerPagedResult(records, response.total ?? undefined, params);
    }

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

    if (resource === ResourceName.BlueprintTemplates) {
      // `/v1/sources/blueprint-templates` returns the whole collection (31 rows
      // today) in one unbounded array and takes no query parameters, so filter
      // and page client-side. `applyClientListWindow` is the sanctioned helper
      // for genuinely-unbounded endpoints; it derives `total` from the full
      // list, not from a server page, which is exactly right here.
      const templates = await controlPlaneActions.listSourceBlueprintTemplates();
      const overlay = params.filter?.overlay_id;
      const lockClass = params.filter?.lock_class;
      const filtered = templates.filter((template) => {
        if (typeof overlay === "string" && !isMissingFilterValue(overlay)) {
          if (template.overlay_id !== overlay) return false;
        }
        if (typeof lockClass === "string" && !isMissingFilterValue(lockClass)) {
          if (classifyTemplate(template).id !== lockClass) return false;
        }
        return true;
      });
      // Composite id: the API keys a template on (overlay, template), and
      // react-admin needs a single scalar identifier per row.
      const records = filtered.map((template) => ({
        ...template,
        id: `${template.overlay_id}/${template.provider_template_id}`,
      }));
      return applyClientListWindow(records, params);
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
      const items = await fetchAllSimpleList(ResourceName.Jurisdictions);
      return {
        data: items
          .filter((item) => params.ids.includes(item.jurisdiction_id))
          .map((item) => toRecord(item, "jurisdiction_id")),
      };
    }

    if (resource === ResourceName.Authorities) {
      const items = await fetchAllSimpleList(ResourceName.Authorities);
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
