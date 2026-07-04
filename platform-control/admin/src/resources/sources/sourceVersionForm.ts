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

export type ProviderType = "firecrawl" | "deterministic_http" | "ris_ogd" | "fedlex_sparql";

export type SourceVersionFormState = {
  version_label: string;
  extractor_profile_id: string;
  use_blueprint: boolean;
  overlay_id: string;
  provider_template_id: string;
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
  const common = {
    version_label: version.version_label,
    extractor_profile_id: version.extractor_profile_id ?? "",
    use_blueprint: false,
    overlay_id: "at",
    provider_template_id: "ris_ogd_bundesrecht",
    provider: spec.provider ?? "firecrawl",
  } as const;

  if (spec.provider === "ris_ogd") {
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

  if (spec.provider === "fedlex_sparql") {
    const fedlex = spec as FedlexSparqlAcquisitionSpec;
    const seedUrls = fedlex.seed_url
      ? [fedlex.seed_url, ...(fedlex.seed_urls ?? [])]
      : (fedlex.seed_urls ?? []);
    return {
      ...emptyFormState(),
      ...common,
      provider: "fedlex_sparql",
      seed_url: fedlex.seed_url ?? "",
      seed_urls_text: listToText(seedUrls),
      sparql_endpoint: fedlex.sparql_endpoint ?? "https://fedlex.data.admin.ch/sparqlendpoint",
      preferred_languages_text: listToText(fedlex.preferred_languages ?? []),
      query_mode: fedlex.query_mode ?? "work_to_expression",
      max_expressions: String(fedlex.max_expressions ?? 1),
    };
  }

  if (spec.provider === "deterministic_http") {
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

export const toAcquisitionSpec = (state: SourceVersionFormState): Partial<AcquisitionSpec> => {
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

export const summarizeAcquisitionSpec = (spec: AcquisitionSpec): string[] => {
  const provider = spec.provider ?? "firecrawl";

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
    return [
      `provider: ${provider}`,
      seeds.length > 0 ? `seeds: ${seeds.join(", ")}` : "seeds: none",
    ];
  }

  if (provider === "fedlex_sparql") {
    const fedlex = spec as FedlexSparqlAcquisitionSpec;
    const seeds = fedlex.seed_url
      ? [fedlex.seed_url, ...(fedlex.seed_urls ?? [])]
      : (fedlex.seed_urls ?? []);
    return [
      `provider: ${provider}`,
      `work URIs: ${seeds.join(", ") || "none"}`,
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
    seeds.length > 0 ? `seeds: ${seeds.join(", ")}` : "seeds: none",
    `limit: ${firecrawl.limit}`,
    `depth: ${firecrawl.max_discovery_depth}`,
    (firecrawl.include_paths ?? []).length > 0
      ? `include: ${firecrawl.include_paths.join(", ")}`
      : "include: all",
    (firecrawl.exclude_paths ?? []).length > 0
      ? `exclude: ${firecrawl.exclude_paths.join(", ")}`
      : "exclude: none",
    `formats: ${(firecrawl.scrape_formats ?? []).join(", ")}`,
    `zero retention: ${firecrawl.zero_data_retention ? "yes" : "no"}`,
  ];
};
