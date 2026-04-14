"use client";

import {
  Alert,
  Box,
  Button,
  Checkbox,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  MenuItem,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from "@mui/material";
import { useState } from "react";
import {
  useDataProvider,
  useGetList,
  useNotify,
  useRecordContext,
  useRedirect,
  useRefresh,
} from "react-admin";
import type {
  AcquisitionSpec,
  DeterministicHttpAcquisitionSpec,
  FedlexSparqlAcquisitionSpec,
  FirecrawlAcquisitionSpec,
  RisOgdAcquisitionSpec,
  RunRecord,
  SourceRecord,
  SourceVersionRecord,
} from "../../lib/admin/dataProvider";
import { controlPlaneActions } from "../../lib/admin/dataProvider";

type ProviderType = "firecrawl" | "deterministic_http" | "ris_ogd" | "fedlex_sparql";

type SourceVersionFormState = {
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

const LIST_PARAMS = {
  pagination: { page: 1, perPage: 100 },
  sort: { field: "created_at", order: "DESC" as const },
};

const emptyFormState = (): SourceVersionFormState => ({
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

const PROVIDER_TEMPLATE_CHOICES: Record<string, Array<{ value: string; label: string }>> = {
  at: [
    { value: "ris_ogd_bundesrecht", label: "AT RIS OGD Bundesrecht" },
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

const listToText = (values: string[]): string => values.join("\n");

const textToList = (value: string): string[] =>
  value
    .split(/[\n,]/)
    .map((entry) => entry.trim())
    .filter((entry) => entry.length > 0);

const formatDateTime = (value: string): string =>
  new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));

const toFormState = (version?: SourceVersionRecord | null): SourceVersionFormState => {
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

const parseIntegerField = (
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

const toAcquisitionSpec = (state: SourceVersionFormState): Partial<AcquisitionSpec> => {
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

const summarizeAcquisitionSpec = (spec: AcquisitionSpec): string[] => {
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

function SourceVersionDialog({
  open,
  title,
  formState,
  isSaving,
  onClose,
  onChange,
  onSubmit,
}: {
  open: boolean;
  title: string;
  formState: SourceVersionFormState;
  isSaving: boolean;
  onClose: () => void;
  onChange: (next: SourceVersionFormState) => void;
  onSubmit: () => void;
}) {
  return (
    <Dialog open={open} onClose={isSaving ? undefined : onClose} maxWidth="md" fullWidth>
      <DialogTitle>{title}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          <TextField
            label="Version label"
            value={formState.version_label}
            onChange={(event) => onChange({ ...formState, version_label: event.target.value })}
            fullWidth
          />
          <TextField
            label="Extractor profile ID"
            value={formState.extractor_profile_id}
            onChange={(event) =>
              onChange({ ...formState, extractor_profile_id: event.target.value })
            }
            fullWidth
          />
          <FormControlLabel
            control={
              <Checkbox
                checked={formState.use_blueprint}
                onChange={(event) =>
                  onChange({ ...formState, use_blueprint: event.target.checked })
                }
              />
            }
            label="Use country overlay + provider template"
          />
          {formState.use_blueprint ? (
            <>
              <TextField
                select
                label="Country overlay"
                value={formState.overlay_id}
                onChange={(event) =>
                  onChange({
                    ...formState,
                    overlay_id: event.target.value,
                    provider_template_id:
                      PROVIDER_TEMPLATE_CHOICES[event.target.value]?.[0]?.value ?? "",
                  })
                }
                fullWidth
              >
                <MenuItem value="at">AT</MenuItem>
                <MenuItem value="de">DE</MenuItem>
                <MenuItem value="ch">CH</MenuItem>
                <MenuItem value="fr">FR</MenuItem>
                <MenuItem value="it">IT</MenuItem>
              </TextField>
              <TextField
                select
                label="Provider template"
                value={formState.provider_template_id}
                onChange={(event) =>
                  onChange({ ...formState, provider_template_id: event.target.value })
                }
                fullWidth
              >
                {(PROVIDER_TEMPLATE_CHOICES[formState.overlay_id] ?? []).map((choice) => (
                  <MenuItem key={choice.value} value={choice.value}>
                    {choice.label}
                  </MenuItem>
                ))}
              </TextField>
            </>
          ) : null}
          {!formState.use_blueprint ? (
            <Typography variant="body2" color="text.secondary">
              Manual mode: provider-specific fields are sent directly as acquisition_spec.
            </Typography>
          ) : (
            <Alert severity="info">
              Wizard preview: source version will be created from overlay{" "}
              <strong>{formState.overlay_id}</strong> and template{" "}
              <strong>{formState.provider_template_id || "not selected"}</strong>.
            </Alert>
          )}
          {!formState.use_blueprint ? (
            <>
              <TextField
                select
                label="Provider"
                value={formState.provider}
                onChange={(event) =>
                  onChange({
                    ...formState,
                    provider: event.target.value as ProviderType,
                  })
                }
                fullWidth
              >
                <MenuItem value="firecrawl">Firecrawl (website crawl)</MenuItem>
                <MenuItem value="deterministic_http">Deterministic HTTP</MenuItem>
                <MenuItem value="fedlex_sparql">Fedlex SPARQL</MenuItem>
                <MenuItem value="ris_ogd">RIS OGD API (Austrian law)</MenuItem>
              </TextField>

              {formState.provider === "ris_ogd" ? (
                <>
                  <TextField
                    label="Base URL"
                    value={formState.base_url}
                    onChange={(event) => onChange({ ...formState, base_url: event.target.value })}
                    fullWidth
                    helperText="OGD-RIS API endpoint, e.g. https://data.bka.gv.at/ris/api/v2.6/Bundesrecht"
                  />
                  <TextField
                    label="Applikation"
                    value={formState.applikation}
                    onChange={(event) =>
                      onChange({ ...formState, applikation: event.target.value })
                    }
                    fullWidth
                    helperText="Optional filter: Vfgh, Vwgh, Bvwg, Justiz, BrKons, BgblAuth"
                  />
                  <TextField
                    label="Preferred formats"
                    value={formState.preferred_formats_text}
                    onChange={(event) =>
                      onChange({ ...formState, preferred_formats_text: event.target.value })
                    }
                    fullWidth
                    helperText="Comma separated. E.g. Xml, Html"
                  />
                  <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                    <TextField
                      label="Page size"
                      type="number"
                      value={formState.page_size}
                      onChange={(event) =>
                        onChange({ ...formState, page_size: event.target.value })
                      }
                      fullWidth
                    />
                    <TextField
                      label="Max pages"
                      type="number"
                      value={formState.max_pages}
                      onChange={(event) =>
                        onChange({ ...formState, max_pages: event.target.value })
                      }
                      fullWidth
                    />
                  </Stack>
                </>
              ) : formState.provider === "fedlex_sparql" ? (
                <>
                  <TextField
                    label="Seed work URI"
                    value={formState.seed_url}
                    onChange={(event) => onChange({ ...formState, seed_url: event.target.value })}
                    fullWidth
                    helperText="Canonical Fedlex work URI, e.g. https://fedlex.data.admin.ch/eli/cc/1999/404"
                  />
                  <TextField
                    label="Additional seed work URIs"
                    value={formState.seed_urls_text}
                    onChange={(event) =>
                      onChange({ ...formState, seed_urls_text: event.target.value })
                    }
                    fullWidth
                    multiline
                    minRows={2}
                    helperText="Optional comma or newline separated additional Fedlex work URIs."
                  />
                  <TextField
                    label="SPARQL endpoint"
                    value={formState.sparql_endpoint}
                    onChange={(event) =>
                      onChange({ ...formState, sparql_endpoint: event.target.value })
                    }
                    fullWidth
                    helperText="Defaults to the public Fedlex SPARQL endpoint."
                  />
                  <TextField
                    label="Preferred languages"
                    value={formState.preferred_languages_text}
                    onChange={(event) =>
                      onChange({ ...formState, preferred_languages_text: event.target.value })
                    }
                    fullWidth
                    helperText="Comma or newline separated language codes."
                  />
                  <TextField
                    select
                    label="Query mode"
                    value={formState.query_mode}
                    onChange={(event) =>
                      onChange({
                        ...formState,
                        query_mode: event.target.value as SourceVersionFormState["query_mode"],
                      })
                    }
                    fullWidth
                  >
                    <MenuItem value="work_to_expression">work_to_expression</MenuItem>
                  </TextField>
                  <TextField
                    label="Max expressions"
                    type="number"
                    value={formState.max_expressions}
                    onChange={(event) =>
                      onChange({ ...formState, max_expressions: event.target.value })
                    }
                    fullWidth
                    helperText="How many expressions to resolve per work URI."
                  />
                </>
              ) : (
                <>
                  <TextField
                    label="Seed URL"
                    value={formState.seed_url}
                    onChange={(event) => onChange({ ...formState, seed_url: event.target.value })}
                    fullWidth
                  />
                  <TextField
                    label="Additional seed URLs"
                    value={formState.seed_urls_text}
                    onChange={(event) =>
                      onChange({ ...formState, seed_urls_text: event.target.value })
                    }
                    fullWidth
                    multiline
                    minRows={2}
                    helperText="Comma or newline separated."
                  />
                  <TextField
                    select
                    label="Mode"
                    value={formState.mode}
                    onChange={(event) =>
                      onChange({
                        ...formState,
                        mode: event.target.value as SourceVersionFormState["mode"],
                      })
                    }
                    fullWidth
                  >
                    <MenuItem value="crawl">crawl</MenuItem>
                    <MenuItem value="batch_scrape">batch_scrape</MenuItem>
                  </TextField>
                  <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                    <TextField
                      label="Limit"
                      type="number"
                      value={formState.limit}
                      onChange={(event) => onChange({ ...formState, limit: event.target.value })}
                      fullWidth
                    />
                    <TextField
                      label="Max discovery depth"
                      type="number"
                      value={formState.max_discovery_depth}
                      onChange={(event) =>
                        onChange({ ...formState, max_discovery_depth: event.target.value })
                      }
                      fullWidth
                    />
                  </Stack>
                  <TextField
                    label="Include paths"
                    value={formState.include_paths_text}
                    onChange={(event) =>
                      onChange({ ...formState, include_paths_text: event.target.value })
                    }
                    fullWidth
                    multiline
                    minRows={2}
                    helperText="Comma or newline separated."
                  />
                  <TextField
                    label="Exclude paths"
                    value={formState.exclude_paths_text}
                    onChange={(event) =>
                      onChange({ ...formState, exclude_paths_text: event.target.value })
                    }
                    fullWidth
                    multiline
                    minRows={2}
                    helperText="Comma or newline separated."
                  />
                  <TextField
                    label="Scrape formats"
                    value={formState.scrape_formats_text}
                    onChange={(event) =>
                      onChange({ ...formState, scrape_formats_text: event.target.value })
                    }
                    fullWidth
                    helperText="Comma or newline separated."
                  />
                  <FormControlLabel
                    control={
                      <Checkbox
                        checked={formState.zero_data_retention}
                        onChange={(event) =>
                          onChange({ ...formState, zero_data_retention: event.target.checked })
                        }
                      />
                    }
                    label="Zero data retention"
                  />
                </>
              )}
            </>
          ) : null}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={isSaving}>
          Cancel
        </Button>
        <Button onClick={onSubmit} variant="contained" disabled={isSaving}>
          {isSaving ? "Saving..." : "Save"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

export function SourceVersionsSection() {
  const source = useRecordContext<SourceRecord>();
  const dataProvider = useDataProvider();
  const notify = useNotify();
  const redirect = useRedirect();
  const refresh = useRefresh();

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingVersion, setEditingVersion] = useState<SourceVersionRecord | null>(null);
  const [formState, setFormState] = useState<SourceVersionFormState>(emptyFormState());
  const [isSaving, setIsSaving] = useState(false);
  const [actionVersionId, setActionVersionId] = useState<string | null>(null);

  const versions = useGetList<SourceVersionRecord>("source-versions", {
    pagination: LIST_PARAMS.pagination,
    sort: LIST_PARAMS.sort,
    filter: { source_id: source?.source_id },
  });

  if (!source) {
    return null;
  }

  const openCreateDialog = () => {
    setEditingVersion(null);
    setFormState(emptyFormState());
    setDialogOpen(true);
  };

  const openEditDialog = (version: SourceVersionRecord) => {
    setEditingVersion(version);
    setFormState(toFormState(version));
    setDialogOpen(true);
  };

  const closeDialog = () => {
    if (isSaving) {
      return;
    }
    setDialogOpen(false);
    setEditingVersion(null);
    setFormState(emptyFormState());
  };

  const submitDialog = async () => {
    try {
      setIsSaving(true);
      if (editingVersion) {
        await dataProvider.update("source-versions", {
          id: editingVersion.source_version_id,
          data: {
            version_label: formState.version_label,
            extractor_profile_id: formState.extractor_profile_id,
            ...(formState.use_blueprint
              ? {
                  overlay_id: formState.overlay_id,
                  provider_template_id: formState.provider_template_id,
                }
              : {
                  acquisition_spec: toAcquisitionSpec(formState),
                }),
          },
          previousData: editingVersion,
        });
        notify("Source version updated.", { type: "success" });
      } else {
        await dataProvider.create("source-versions", {
          data: {
            source_id: source.source_id,
            version_label: formState.version_label,
            extractor_profile_id: formState.extractor_profile_id,
            ...(formState.use_blueprint
              ? {
                  overlay_id: formState.overlay_id,
                  provider_template_id: formState.provider_template_id,
                }
              : {
                  acquisition_spec: toAcquisitionSpec(formState),
                }),
          },
        });
        notify("Source version created.", { type: "success" });
      }
      closeDialog();
      refresh();
    } catch (error) {
      notify(error instanceof Error ? error.message : "Unable to save source version.", {
        type: "error",
      });
    } finally {
      setIsSaving(false);
    }
  };

  const runVersionAction = async (action: "approve" | "reject", version: SourceVersionRecord) => {
    try {
      setActionVersionId(version.source_version_id);
      if (action === "approve") {
        await controlPlaneActions.approveSourceVersion(version.source_version_id);
        notify("Source version approved.", { type: "success" });
      } else {
        await controlPlaneActions.rejectSourceVersion(version.source_version_id);
        notify("Source version rejected.", { type: "success" });
      }
      refresh();
    } catch (error) {
      notify(error instanceof Error ? error.message : "Unable to update source version state.", {
        type: "error",
      });
    } finally {
      setActionVersionId(null);
    }
  };

  const createRun = async (mode: "preview" | "production", version: SourceVersionRecord) => {
    try {
      setActionVersionId(version.source_version_id);
      const result = await dataProvider.create<RunRecord>("runs", {
        data: {
          source_id: source.source_id,
          source_version_id: version.source_version_id,
          mode,
        },
      });
      notify(`${mode === "preview" ? "Preview" : "Production"} run created.`, {
        type: "success",
      });
      redirect("show", "runs", result.data.id, result.data);
    } catch (error) {
      notify(error instanceof Error ? error.message : "Unable to create run.", {
        type: "error",
      });
    } finally {
      setActionVersionId(null);
    }
  };

  return (
    <Paper sx={{ p: 3, mt: 2 }}>
      <Stack spacing={2}>
        <Stack
          direction={{ xs: "column", md: "row" }}
          justifyContent="space-between"
          alignItems={{ xs: "flex-start", md: "center" }}
          spacing={2}
        >
          <Box>
            <Typography variant="h6">Source Versions</Typography>
            <Typography variant="body2" color="text.secondary">
              Create, review, and transition source versions for this source.
            </Typography>
          </Box>
          <Button variant="contained" onClick={openCreateDialog}>
            Create Version
          </Button>
        </Stack>

        {versions.error ? <Alert severity="error">Unable to load source versions.</Alert> : null}

        {!versions.isPending && !versions.error && (versions.data?.length ?? 0) === 0 ? (
          <Typography variant="body2" color="text.secondary">
            No source versions exist for this source yet.
          </Typography>
        ) : null}

        {versions.data && versions.data.length > 0 ? (
          <Box sx={{ overflowX: "auto" }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Version</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell>Extractor profile</TableCell>
                  <TableCell>Acquisition config</TableCell>
                  <TableCell>Updated</TableCell>
                  <TableCell>Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {versions.data.map((version) => {
                  const canEdit = version.status === "draft" || version.status === "rejected";
                  const canReview =
                    version.status === "draft" || version.status === "pending_approval";
                  const canPreview =
                    version.status !== "rejected" && version.status !== "superseded";
                  const canProduction = version.status === "approved";
                  const isActing = actionVersionId === version.source_version_id;
                  return (
                    <TableRow key={version.id}>
                      <TableCell>
                        <Typography variant="body2" sx={{ fontWeight: 600 }}>
                          {version.version_label}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          {version.source_version_id}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        <Chip size="small" label={version.status} />
                      </TableCell>
                      <TableCell>{version.extractor_profile_id ?? "—"}</TableCell>
                      <TableCell>
                        <Stack spacing={0.5}>
                          {summarizeAcquisitionSpec(version.acquisition_spec).map((line) => (
                            <Typography key={line} variant="caption" color="text.secondary">
                              {line}
                            </Typography>
                          ))}
                        </Stack>
                      </TableCell>
                      <TableCell>{formatDateTime(version.updated_at)}</TableCell>
                      <TableCell>
                        <Stack direction="row" spacing={1} flexWrap="wrap">
                          <Button
                            size="small"
                            variant="outlined"
                            onClick={() => openEditDialog(version)}
                            disabled={!canEdit || isActing}
                          >
                            Edit
                          </Button>
                          <Button
                            size="small"
                            variant="contained"
                            onClick={() => createRun("preview", version)}
                            disabled={!canPreview || isActing}
                          >
                            Preview Run
                          </Button>
                          <Button
                            size="small"
                            variant="contained"
                            color="secondary"
                            onClick={() => createRun("production", version)}
                            disabled={!canProduction || isActing}
                          >
                            Production Run
                          </Button>
                          <Button
                            size="small"
                            variant="outlined"
                            onClick={() => runVersionAction("approve", version)}
                            disabled={!canReview || isActing}
                          >
                            Approve
                          </Button>
                          <Button
                            size="small"
                            variant="outlined"
                            color="warning"
                            onClick={() => runVersionAction("reject", version)}
                            disabled={!canReview || isActing}
                          >
                            Reject
                          </Button>
                        </Stack>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </Box>
        ) : null}
      </Stack>

      <SourceVersionDialog
        open={dialogOpen}
        title={editingVersion ? "Edit Source Version" : "Create Source Version"}
        formState={formState}
        isSaving={isSaving}
        onClose={closeDialog}
        onChange={setFormState}
        onSubmit={submitDialog}
      />
    </Paper>
  );
}
