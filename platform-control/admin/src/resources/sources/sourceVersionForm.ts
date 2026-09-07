/**
 * Shared source-version form + lifecycle helpers.
 *
 * The source-version editor (create/edit dialog, lifecycle summary, and the
 * acquisition-spec preview) turns a provider-specific form into a validated
 * `acquisition_spec`, and a list of versions into an operator-facing
 * lifecycle summary. The pure, framework-agnostic pieces of that flow live
 * here — separated from the Tailwind `SourceVersionsSection.tsx` component so
 * the state machine + acquisition-spec mapping can be unit-tested in isolation:
 *
 *   - form-state model (`SourceVersionFormState`, `emptyFormState`,
 *     `toFormState`) and its round-trip into an `acquisition_spec`
 *     (`toAcquisitionSpec`, `parseIntegerField`, `listToText`/`textToList`);
 *   - lifecycle rollup (`summarizeSourceVersionLifecycle`,
 *     `describeSourceVersionStatus`, `VERSION_STATUS_META`);
 *   - the provider-specific acquisition-spec summary lines
 *     (`summarizeAcquisitionSpec`) and the overlay -> provider-template
 *     choice map (`PROVIDER_TEMPLATE_CHOICES`).
 *
 * No React, no MUI, no Tailwind — just data in, data out.
 */
import type {
  AcquisitionSpec,
  DeterministicHttpAcquisitionSpec,
  FedlexSparqlAcquisitionSpec,
  FirecrawlAcquisitionSpec,
  RisOgdAcquisitionSpec,
  SourceVersionRecord,
} from "../../lib/admin/dataProvider";

/**
 * The providers this form renders editable widgets for.
 *
 * This is deliberately NOT "the providers that exist" — the API serves eleven
 * (`AcquisitionProvider` in `platform_control/domain.py`). The list that matters
 * to the form is the one it can actually round-trip, and that is decided by the
 * branches in `toFormState`/`toAcquisitionSpec` below, not by a provider
 * registry. Anything else is preserved verbatim rather than rebuilt — see
 * `isEditableProvider` (#614).
 */
export type ProviderType = "firecrawl" | "deterministic_http" | "ris_ogd" | "fedlex_sparql";

/**
 * The provider as the record actually reports it.
 *
 * `AcquisitionSpec` models only the four providers this form edits, so its
 * `provider` is typed as those four — but the wire carries eleven. Widening to
 * `string` at the read keeps that fact in front of the type checker instead of
 * letting the union's lie justify a firecrawl fallthrough (#614).
 */
const specProvider = (spec: AcquisitionSpec): string => spec.provider;

/**
 * The `BaseAcquisitionSpec` fields every provider carries
 * (`platform_control/schemas/source.py`). The form renders none of them, so
 * they survive an edit only by being copied off the spec that was loaded.
 */
export const BASE_SPEC_FIELDS = [
  "tenant_id",
  "corpus_id",
  "scope_type",
  "source_origin_kind",
  "trust_tier",
  "language_codes",
  "document_type_hint",
  "request_timeout_seconds",
  "user_agent",
  "max_content_bytes",
] as const;

const BASE_SPEC_FIELD_SET: ReadonlySet<string> = new Set(BASE_SPEC_FIELDS);

export type SourceVersionFormState = {
  version_label: string;
  extractor_profile_id: string;
  use_blueprint: boolean;
  overlay_id: string;
  provider_template_id: string;
  /**
   * The provider whose widgets the dialog renders. Meaningless — and never sent
   * — when `spec_editable` is false.
   */
  provider: ProviderType;
  seed_url: string;
  seed_urls_text: string;
  mode: "crawl" | "batch_scrape";
  include_paths_text: string;
  exclude_paths_text: string;
  limit: string;
  max_discovery_depth: string;
  scrape_formats_text: string;
  zero_data_retention: boolean;
  base_url: string;
  applikation: string;
  preferred_formats_text: string;
  page_size: string;
  max_pages: string;
  sparql_endpoint: string;
  preferred_languages_text: string;
  query_mode: "work_to_expression";
  max_expressions: string;
  /**
   * The acquisition spec exactly as it was loaded, kept so an edit can be
   * merged over it instead of rebuilt from the handful of fields that have a
   * widget. `null` when creating a new version. See `toAcquisitionSpec`.
   */
  original_spec: AcquisitionSpec | null;
  /**
   * False when `original_spec` uses a provider this form has no widgets for.
   * The dialog then shows the spec read-only and round-trips it untouched.
   */
  spec_editable: boolean;
};

export const SOURCE_VERSION_LIST_PARAMS = {
  pagination: { page: 1, perPage: 100 },
  sort: { field: "created_at", order: "DESC" as const },
};

export const emptyFormState = (): SourceVersionFormState => ({
  version_label: "",
  extractor_profile_id: "",
  use_blueprint: true,
  overlay_id: "at",
  provider_template_id: "ris_ogd_bundesrecht",
  provider: "firecrawl",
  seed_url: "",
  seed_urls_text: "",
  mode: "crawl",
  include_paths_text: "",
  exclude_paths_text: "",
  limit: "20",
  max_discovery_depth: "2",
  scrape_formats_text: "markdown, html",
  zero_data_retention: false,
  base_url: "",
  applikation: "",
  preferred_formats_text: "Xml, Html",
  page_size: "20",
  max_pages: "50",
  sparql_endpoint: "https://fedlex.data.admin.ch/sparqlendpoint",
  preferred_languages_text: "de",
  query_mode: "work_to_expression",
  max_expressions: "1",
  original_spec: null,
  spec_editable: true,
});

export const PROVIDER_TEMPLATE_CHOICES: Record<string, Array<{ value: string; label: string }>> = {
  at: [
    { value: "ris_ogd_bundesrecht", label: "AT RIS OGD Bundesrecht" },
    { value: "ris_ogd_bundesrecht_narrow_html", label: "AT RIS Bundesrecht narrow HTML" },
    { value: "ris_ogd_bundesrecht_small_batch_html", label: "AT RIS Bundesrecht small batch HTML" },
    { value: "firecrawl_justice_portal", label: "AT Justice portal crawl" },
  ],
  de: [{ value: "deterministic_http_bundesrecht", label: "DE Bundesrecht deterministic HTTP" }],
  ch: [
    { value: "deterministic_http_fedlex_legislation", label: "CH Fedlex legislation (legacy)" },
    { value: "fedlex_sparql_constitution_de", label: "CH Fedlex constitution (SPARQL)" },
    { value: "fedlex_sparql_vwvg_de", label: "CH Fedlex VwVG (SPARQL)" },
    { value: "fedlex_sparql_federal_law_batch_de", label: "CH Fedlex small batch (SPARQL)" },
  ],
  fr: [],
  it: [],
};

export const OVERLAY_CHOICES: Array<{ value: string; label: string }> = [
  { value: "at", label: "AT" },
  { value: "de", label: "DE" },
  { value: "ch", label: "CH" },
  { value: "fr", label: "FR" },
  { value: "it", label: "IT" },
];

export const PROVIDER_CHOICES: Array<{ value: ProviderType; label: string }> = [
  { value: "firecrawl", label: "Firecrawl (website crawl)" },
  { value: "deterministic_http", label: "Deterministic HTTP" },
  { value: "fedlex_sparql", label: "Fedlex SPARQL" },
  { value: "ris_ogd", label: "RIS OGD API (Austrian law)" },
];

const EDITABLE_PROVIDERS: ReadonlySet<string> = new Set(
  PROVIDER_CHOICES.map((choice) => choice.value),
);

/**
 * Can this form edit a spec with this provider without losing anything?
 *
 * Answering from `PROVIDER_CHOICES` — the providers the dialog offers widgets
 * for — rather than from a list of every provider that exists means a provider
 * added server-side is unknown here by default, and unknown means preserved
 * rather than rewritten. There is no list to keep in sync for that to hold.
 */
export const isEditableProvider = (provider: string): provider is ProviderType =>
  EDITABLE_PROVIDERS.has(provider);

export const VERSION_STATUS_META = {
  draft: {
    label: "Draft",
    detail: "Needs review before approval.",
    attention: true,
  },
  pending_approval: {
    label: "Pending approval",
    detail: "Waiting on operator review.",
    attention: true,
  },
  approved: {
    label: "Approved",
    detail: "Ready for preview or production runs.",
    attention: false,
  },
  rejected: {
    label: "Rejected",
    detail: "Needs revision or replacement.",
    attention: true,
  },
  superseded: {
    label: "Superseded",
    detail: "Read-only history.",
    attention: false,
  },
} as const;

export const listToText = (values: string[]): string => values.join("\n");

export const textToList = (value: string): string[] =>
  value
    .split(/[\n,]/)
    .map((entry) => entry.trim())
    .filter((entry) => entry.length > 0);

export const describeSourceVersionStatus = (status: SourceVersionRecord["status"]) =>
  VERSION_STATUS_META[status];

export type SourceVersionAction = "edit" | "preview" | "production" | "approve" | "reject";

const ACTION_LABEL: Record<SourceVersionAction, string> = {
  edit: "Edit",
  preview: "Preview run",
  production: "Production run",
  approve: "Approve",
  reject: "Reject",
};

/**
 * Why is this action unavailable on a version in this status?
 *
 * The row rendered `Edit` / `Approve` / `Reject` as three greyed buttons on an
 * approved version with no `title`, no accessible description, and no adjacent
 * copy (#674). "Approval is terminal" is a rule of the lifecycle, not something
 * an operator can infer from a dimmed button — and to a screen-reader user a
 * disabled button with no stated reason carries no information at all.
 *
 * Returns `null` when the action is available, so the caller can use the same
 * value for both the `disabled` decision and the explanation.
 */
export const explainUnavailableVersionAction = (
  action: SourceVersionAction,
  status: SourceVersionRecord["status"],
): string | null => {
  const label = ACTION_LABEL[action];

  if (action === "edit") {
    if (status === "draft" || status === "rejected") return null;
    if (status === "approved") {
      return "Approved versions are immutable — create a new version to change the spec.";
    }
    if (status === "superseded") {
      return "Superseded versions are read-only history.";
    }
    return `${label} is unavailable while the version is waiting on operator review.`;
  }

  if (action === "approve" || action === "reject") {
    if (status === "draft" || status === "pending_approval") return null;
    if (status === "approved") {
      return "This version is already approved — approval is terminal.";
    }
    if (status === "rejected") {
      return "This version is already rejected — rejection is terminal.";
    }
    return "Superseded versions are read-only history.";
  }

  if (action === "preview") {
    if (status !== "rejected" && status !== "superseded") return null;
    return status === "rejected"
      ? "Rejected versions are permanently blocked from runs."
      : "Superseded versions are read-only history.";
  }

  if (status === "approved") return null;
  return "Production runs require an approved version.";
};

export type SourceVersionLifecycleSummary = {
  total: number;
  counts: Record<SourceVersionRecord["status"], number>;
  attentionCount: number;
  latestVersion: SourceVersionRecord | null;
  nextAction: string;
  nextActionDetail: string;
};

export const summarizeSourceVersionLifecycle = (
  versions: SourceVersionRecord[],
): SourceVersionLifecycleSummary => {
  const counts: SourceVersionLifecycleSummary["counts"] = {
    draft: 0,
    pending_approval: 0,
    approved: 0,
    rejected: 0,
    superseded: 0,
  };

  for (const version of versions) {
    counts[version.status] += 1;
  }

  const attentionCount = counts.draft + counts.pending_approval + counts.rejected;

  if (versions.length === 0) {
    return {
      total: 0,
      counts,
      attentionCount,
      latestVersion: null,
      nextAction: "Create the first source version.",
      nextActionDetail: "Start with a draft so the source has a reviewable lifecycle.",
    };
  }

  if (counts.draft > 0) {
    return {
      total: versions.length,
      counts,
      attentionCount,
      latestVersion: versions[0] ?? null,
      nextAction: "Finish the draft version.",
      nextActionDetail: "Draft versions need review before they can move into approval.",
    };
  }

  if (counts.pending_approval > 0) {
    return {
      total: versions.length,
      counts,
      attentionCount,
      latestVersion: versions[0] ?? null,
      nextAction: "Review pending approval versions.",
      nextActionDetail: "Pending versions are waiting on an operator decision before launch.",
    };
  }

  if (counts.rejected > 0) {
    return {
      total: versions.length,
      counts,
      attentionCount,
      latestVersion: versions[0] ?? null,
      nextAction: "Replace or revise the rejected version.",
      nextActionDetail: "Rejected versions should be corrected or superseded before new runs.",
    };
  }

  if (counts.approved > 0) {
    return {
      total: versions.length,
      counts,
      attentionCount,
      latestVersion: versions[0] ?? null,
      nextAction: "Launch preview or production from the approved version.",
      nextActionDetail: "Approved versions are ready for operator use and run creation.",
    };
  }

  return {
    total: versions.length,
    counts,
    attentionCount,
    latestVersion: versions[0] ?? null,
    nextAction: "Use the latest history as the baseline for a new version.",
    nextActionDetail:
      "Superseded versions are read-only, so new work should start from a fresh draft.",
  };
};

export const toFormState = (version?: SourceVersionRecord | null): SourceVersionFormState => {
  if (!version) {
    return emptyFormState();
  }
  const spec = version.acquisition_spec;
  const provider = specProvider(spec);
  const common = {
    version_label: version.version_label,
    extractor_profile_id: version.extractor_profile_id ?? "",
    use_blueprint: false,
    overlay_id: "at",
    provider_template_id: "ris_ogd_bundesrecht",
    original_spec: spec,
  } as const;

  // A provider this form has no widgets for (canton_http, gemeinde_http,
  // legifrance, …). Rebuilding it from form fields would rewrite it as
  // firecrawl and drop whatever identifies it — canton_code, bfs_number,
  // court. Every one of those defaults is valid, so the server accepts the
  // rewrite silently. Hand it back read-only instead (#614).
  if (!isEditableProvider(provider)) {
    return { ...emptyFormState(), ...common, spec_editable: false };
  }

  if (provider === "ris_ogd") {
    const ris = spec as RisOgdAcquisitionSpec;
    return {
      ...emptyFormState(),
      ...common,
      provider: "ris_ogd",
      base_url: ris.base_url ?? "",
      applikation: ris.applikation ?? "",
      preferred_formats_text: listToText(ris.preferred_formats ?? []),
      page_size: String(ris.page_size ?? 20),
      max_pages: String(ris.max_pages ?? 50),
    };
  }

  if (provider === "fedlex_sparql") {
    const fedlex = spec as FedlexSparqlAcquisitionSpec;
    return {
      ...emptyFormState(),
      ...common,
      provider: "fedlex_sparql",
      seed_url: fedlex.seed_url ?? "",
      // `seed_urls` only. The dialog renders `seed_url` in its own field, so
      // folding it in here as well round-tripped it into `seed_urls` too (#614).
      seed_urls_text: listToText(fedlex.seed_urls ?? []),
      sparql_endpoint: fedlex.sparql_endpoint ?? "https://fedlex.data.admin.ch/sparqlendpoint",
      preferred_languages_text: listToText(fedlex.preferred_languages ?? []),
      query_mode: fedlex.query_mode ?? "work_to_expression",
      max_expressions: String(fedlex.max_expressions ?? 1),
    };
  }

  if (provider === "deterministic_http") {
    const deterministic = spec as DeterministicHttpAcquisitionSpec;
    return {
      ...emptyFormState(),
      ...common,
      provider: "deterministic_http",
      seed_url: deterministic.seed_url ?? "",
      seed_urls_text: listToText(deterministic.seed_urls ?? []),
    };
  }

  const firecrawl = spec as FirecrawlAcquisitionSpec;
  return {
    ...emptyFormState(),
    ...common,
    provider: "firecrawl",
    seed_url: firecrawl.seed_url ?? "",
    seed_urls_text: listToText(firecrawl.seed_urls ?? []),
    mode: firecrawl.mode ?? "crawl",
    include_paths_text: listToText(firecrawl.include_paths ?? []),
    exclude_paths_text: listToText(firecrawl.exclude_paths ?? []),
    limit: String(firecrawl.limit ?? 20),
    max_discovery_depth: String(firecrawl.max_discovery_depth ?? 2),
    scrape_formats_text: listToText(firecrawl.scrape_formats ?? []),
    zero_data_retention: firecrawl.zero_data_retention ?? false,
  };
};

export const parseIntegerField = (
  value: string,
  fieldName: string,
  { min, max }: { min: number; max: number },
): number => {
  const trimmed = value.trim();
  if (trimmed.length === 0) {
    throw new Error(`${fieldName} is required.`);
  }
  if (!/^-?\d+$/.test(trimmed)) {
    throw new Error(`${fieldName} must be an integer.`);
  }
  const parsed = Number.parseInt(trimmed, 10);
  if (parsed < min || parsed > max) {
    throw new Error(`${fieldName} must be between ${min} and ${max}.`);
  }
  return parsed;
};

/** The `BaseAcquisitionSpec` fields carried by `spec`, and nothing else. */
const pickBaseSpecFields = (spec: AcquisitionSpec): Partial<AcquisitionSpec> => {
  const source = spec as Record<string, unknown>;
  const picked: Record<string, unknown> = {};
  for (const field of BASE_SPEC_FIELDS) {
    if (field in source) {
      picked[field] = source[field];
    }
  }
  return picked as Partial<AcquisitionSpec>;
};

/** The provider-specific spec described by the form's own fields. */
const toProviderSpec = (state: SourceVersionFormState): Partial<AcquisitionSpec> => {
  const base: Partial<AcquisitionSpec> = { provider: state.provider };

  if (state.provider === "ris_ogd") {
    return {
      ...base,
      base_url: state.base_url.trim(),
      applikation: state.applikation.trim() || null,
      preferred_formats: textToList(state.preferred_formats_text),
      page_size: parseIntegerField(state.page_size, "Page size", { min: 1, max: 100 }),
      max_pages: parseIntegerField(state.max_pages, "Max pages", { min: 1, max: 500 }),
    };
  }

  if (state.provider === "deterministic_http") {
    return {
      ...base,
      seed_url: state.seed_url.trim().length > 0 ? state.seed_url.trim() : null,
      seed_urls: textToList(state.seed_urls_text),
    };
  }

  if (state.provider === "fedlex_sparql") {
    return {
      ...base,
      seed_url: state.seed_url.trim().length > 0 ? state.seed_url.trim() : null,
      seed_urls: textToList(state.seed_urls_text),
      sparql_endpoint: state.sparql_endpoint.trim(),
      preferred_languages: textToList(state.preferred_languages_text),
      query_mode: state.query_mode,
      max_expressions: parseIntegerField(state.max_expressions, "Max expressions", {
        min: 1,
        max: 10,
      }),
    };
  }

  return {
    ...base,
    seed_url: state.seed_url.trim().length > 0 ? state.seed_url.trim() : null,
    seed_urls: textToList(state.seed_urls_text),
    mode: state.mode,
    include_paths: textToList(state.include_paths_text),
    exclude_paths: textToList(state.exclude_paths_text),
    limit: parseIntegerField(state.limit, "Limit", { min: 1, max: 500 }),
    max_discovery_depth: parseIntegerField(state.max_discovery_depth, "Max discovery depth", {
      min: 0,
      max: 10,
    }),
    scrape_formats: textToList(state.scrape_formats_text),
    zero_data_retention: state.zero_data_retention,
  };
};

/**
 * The complete `acquisition_spec` to send for this form state.
 *
 * The server REPLACES the spec rather than merging it
 * (`source_service.update_source_version`: `version.acquisition_spec =
 * acquisition_spec.model_dump(mode="json")`), so every field omitted here is
 * reset to its schema default. The dialog renders neither the ten
 * `BaseAcquisitionSpec` fields nor every provider field, so emitting only what
 * has a widget silently wiped the rest — renaming a label reset `corpus_id` to
 * `corpus_public_default` and emptied `language_codes` (#614).
 *
 * So: merge the form's edits over the spec that was loaded, rather than
 * rebuilding the spec from the form alone. Fixing this client-side keeps the
 * server's replace semantics — switching it to a PATCH-merge would be a
 * contract change with a much wider blast radius.
 */
export const toAcquisitionSpec = (state: SourceVersionFormState): Partial<AcquisitionSpec> => {
  const original = state.original_spec;

  // A provider the form never modelled: there is nothing to merge, and
  // rebuilding it would be the corruption. Send back exactly what we loaded.
  if (original && !state.spec_editable) {
    return original;
  }

  const edited = toProviderSpec(state);
  if (!original) {
    return edited;
  }

  // Same provider -> every field without a widget survives, base or otherwise
  // (ris_ogd's `applikation`/`page_size`, say). Provider switched -> only
  // the base fields carry over: they are provider-independent, whereas the old
  // provider's own fields are not valid on the new one and the server's spec
  // models are `extra="forbid"`.
  const preserved =
    specProvider(original) === state.provider ? original : pickBaseSpecFields(original);

  return { ...preserved, ...edited };
};

/**
 * How many entries of a list the summary names before counting the rest.
 *
 * The summary is a table *cell*. The Fedlex 50-act version printed all 50 work
 * URIs into it, producing one row several screens tall that pushed the row's
 * other columns out of view, next to a four-line ZH row (#674). Three entries
 * is enough to recognise the shape of the list; the full value stays available
 * in the edit dialog, which renders the spec verbatim.
 */
const SUMMARY_LIST_LIMIT = 3;

export const summarizeList = (values: string[]): string => {
  if (values.length === 0) return "none";
  if (values.length <= SUMMARY_LIST_LIMIT) return values.join(", ");
  return `${values.slice(0, SUMMARY_LIST_LIMIT).join(", ")} … and ${
    values.length - SUMMARY_LIST_LIMIT
  } more`;
};

const formatSpecValue = (value: unknown): string => {
  if (value === null || value === undefined) {
    return "not set";
  }
  if (Array.isArray(value)) {
    return summarizeList(value.map(String));
  }
  return String(value);
};

export const summarizeAcquisitionSpec = (spec: AcquisitionSpec): string[] => {
  const provider = specProvider(spec);

  // A provider with no renderer here. Reading it as firecrawl printed
  // "mode: undefined / limit: undefined" over a spec that has neither, and hid
  // the fields that actually define it — a real canton_http version showed no
  // canton_code at all (#614). List the spec's own fields instead.
  if (!isEditableProvider(provider)) {
    return [
      `provider: ${provider}`,
      ...Object.entries(spec as Record<string, unknown>)
        .filter(([key]) => key !== "provider" && !BASE_SPEC_FIELD_SET.has(key))
        .map(([key, value]) => `${key}: ${formatSpecValue(value)}`),
    ];
  }

  if (provider === "ris_ogd") {
    const ris = spec as RisOgdAcquisitionSpec;
    return [
      `provider: ${provider}`,
      ris.base_url ? `base URL: ${ris.base_url}` : "base URL: not set",
      ris.applikation ? `applikation: ${ris.applikation}` : "applikation: all",
      `formats: ${(ris.preferred_formats ?? []).join(", ") || "Xml, Html"}`,
      `page size: ${ris.page_size ?? 20}`,
      `max pages: ${ris.max_pages ?? 50}`,
    ];
  }

  if (provider === "deterministic_http") {
    const deterministic = spec as DeterministicHttpAcquisitionSpec;
    const seeds = deterministic.seed_url
      ? [deterministic.seed_url, ...(deterministic.seed_urls ?? [])]
      : (deterministic.seed_urls ?? []);
    return [`provider: ${provider}`, `seeds: ${summarizeList(seeds)}`];
  }

  if (provider === "fedlex_sparql") {
    const fedlex = spec as FedlexSparqlAcquisitionSpec;
    const seeds = fedlex.seed_url
      ? [fedlex.seed_url, ...(fedlex.seed_urls ?? [])]
      : (fedlex.seed_urls ?? []);
    return [
      `provider: ${provider}`,
      `work URIs: ${summarizeList(seeds)}`,
      `SPARQL endpoint: ${fedlex.sparql_endpoint ?? "n/a"}`,
      `preferred languages: ${(fedlex.preferred_languages ?? []).join(", ") || "n/a"}`,
      `query mode / max expressions: ${fedlex.query_mode ?? "n/a"} / ${fedlex.max_expressions ?? "n/a"}`,
    ];
  }

  const firecrawl = spec as FirecrawlAcquisitionSpec;
  const seeds = firecrawl.seed_url
    ? [firecrawl.seed_url, ...(firecrawl.seed_urls ?? [])]
    : (firecrawl.seed_urls ?? []);
  return [
    `provider: ${provider}`,
    `mode: ${firecrawl.mode}`,
    `seeds: ${summarizeList(seeds)}`,
    `limit: ${firecrawl.limit}`,
    `depth: ${firecrawl.max_discovery_depth}`,
    (firecrawl.include_paths ?? []).length > 0
      ? `include: ${(firecrawl.include_paths ?? []).join(", ")}`
      : "include: all",
    (firecrawl.exclude_paths ?? []).length > 0
      ? `exclude: ${(firecrawl.exclude_paths ?? []).join(", ")}`
      : "exclude: none",
    `formats: ${(firecrawl.scrape_formats ?? []).join(", ")}`,
    `zero retention: ${firecrawl.zero_data_retention ? "yes" : "no"}`,
  ];
};
