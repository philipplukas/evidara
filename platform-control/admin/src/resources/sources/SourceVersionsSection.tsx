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
  FirecrawlAcquisitionSpec,
  RunRecord,
  SourceRecord,
  SourceVersionRecord,
} from "../../lib/admin/dataProvider";
import { controlPlaneActions } from "../../lib/admin/dataProvider";

type SourceVersionFormState = {
  version_label: string;
  extractor_profile_id: string;
  seed_url: string;
  seed_urls_text: string;
  mode: "crawl" | "batch_scrape";
  include_paths_text: string;
  exclude_paths_text: string;
  limit: string;
  max_discovery_depth: string;
  scrape_formats_text: string;
  zero_data_retention: boolean;
};

const LIST_PARAMS = {
  pagination: { page: 1, perPage: 100 },
  sort: { field: "created_at", order: "DESC" as const },
};

const emptyFormState = (): SourceVersionFormState => ({
  version_label: "",
  extractor_profile_id: "",
  seed_url: "",
  seed_urls_text: "",
  mode: "crawl",
  include_paths_text: "",
  exclude_paths_text: "",
  limit: "20",
  max_discovery_depth: "2",
  scrape_formats_text: "markdown, html",
  zero_data_retention: false,
});

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

  return {
    version_label: version.version_label,
    extractor_profile_id: version.extractor_profile_id ?? "",
    seed_url: version.acquisition_spec.seed_url ?? "",
    seed_urls_text: listToText(version.acquisition_spec.seed_urls),
    mode: version.acquisition_spec.mode,
    include_paths_text: listToText(version.acquisition_spec.include_paths),
    exclude_paths_text: listToText(version.acquisition_spec.exclude_paths),
    limit: String(version.acquisition_spec.limit),
    max_discovery_depth: String(version.acquisition_spec.max_discovery_depth),
    scrape_formats_text: listToText(version.acquisition_spec.scrape_formats),
    zero_data_retention: version.acquisition_spec.zero_data_retention,
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

const toAcquisitionSpec = (state: SourceVersionFormState): FirecrawlAcquisitionSpec => ({
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
});

const summarizeAcquisitionSpec = (spec: FirecrawlAcquisitionSpec): string[] => {
  const seeds = spec.seed_url ? [spec.seed_url, ...spec.seed_urls] : spec.seed_urls;
  return [
    `mode: ${spec.mode}`,
    seeds.length > 0 ? `seeds: ${seeds.join(", ")}` : "seeds: none",
    `limit: ${spec.limit}`,
    `depth: ${spec.max_discovery_depth}`,
    spec.include_paths.length > 0 ? `include: ${spec.include_paths.join(", ")}` : "include: all",
    spec.exclude_paths.length > 0 ? `exclude: ${spec.exclude_paths.join(", ")}` : "exclude: none",
    `formats: ${spec.scrape_formats.join(", ")}`,
    `zero retention: ${spec.zero_data_retention ? "yes" : "no"}`,
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
          <TextField
            label="Seed URL"
            value={formState.seed_url}
            onChange={(event) => onChange({ ...formState, seed_url: event.target.value })}
            fullWidth
          />
          <TextField
            label="Additional seed URLs"
            value={formState.seed_urls_text}
            onChange={(event) => onChange({ ...formState, seed_urls_text: event.target.value })}
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
            onChange={(event) => onChange({ ...formState, include_paths_text: event.target.value })}
            fullWidth
            multiline
            minRows={2}
            helperText="Comma or newline separated."
          />
          <TextField
            label="Exclude paths"
            value={formState.exclude_paths_text}
            onChange={(event) => onChange({ ...formState, exclude_paths_text: event.target.value })}
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
            acquisition_spec: toAcquisitionSpec(formState),
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
            acquisition_spec: toAcquisitionSpec(formState),
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

        {!versions.error && (versions.data?.length ?? 0) === 0 ? (
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
