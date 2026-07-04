"use client";

import {
  Alert,
  AlertTitle,
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
import React, { useState } from "react";
import {
  useDataProvider,
  useGetList,
  useNotify,
  useRecordContext,
  useRedirect,
  useRefresh,
} from "react-admin";
import { ResourceName } from "../../domain/resourceNames";
import type { RunRecord, SourceRecord, SourceVersionRecord } from "../../lib/admin/dataProvider";
import { controlPlaneActions } from "../../lib/admin/dataProvider";
import { formatSwissDateTime } from "../../lib/format/date";
import { ConfirmButton } from "../shared/ConfirmButton";
import { StatusBadge, sourceVersionStatusToLevel } from "../shared/StatusBadge";
import { SourceVersionDiffPanel } from "./SourceVersionDiffPanel";
import {
  describeSourceVersionStatus,
  emptyFormState,
  SOURCE_VERSION_LIST_PARAMS as LIST_PARAMS,
  PROVIDER_TEMPLATE_CHOICES,
  type ProviderType,
  type SourceVersionFormState,
  summarizeAcquisitionSpec,
  summarizeSourceVersionLifecycle,
  toAcquisitionSpec,
  toFormState,
} from "./sourceVersionForm";

const formatDateTime = (value: string): string => formatSwissDateTime(value);

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
  const [diffVersionId, setDiffVersionId] = useState<string | null>(null);

  const versions = useGetList<SourceVersionRecord>("source-versions", {
    pagination: LIST_PARAMS.pagination,
    sort: LIST_PARAMS.sort,
    filter: { source_id: source?.source_id },
  });
  const lifecycleSummary = summarizeSourceVersionLifecycle(versions.data ?? []);
  const lifecycleAttentionColor =
    lifecycleSummary.total === 0
      ? ("info" as const)
      : lifecycleSummary.attentionCount > 0
        ? ("warning" as const)
        : ("success" as const);
  const lifecycleAttentionLabel =
    lifecycleSummary.total === 0
      ? "Awaiting first version"
      : lifecycleSummary.attentionCount > 0
        ? `${lifecycleSummary.attentionCount} need attention`
        : "No attention needed";
  const lifecycleAlertSeverity =
    lifecycleSummary.total === 0
      ? ("info" as const)
      : lifecycleSummary.attentionCount > 0
        ? ("warning" as const)
        : ("success" as const);

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
      const result = await dataProvider.create<RunRecord>(ResourceName.Runs, {
        data: {
          source_id: source.source_id,
          source_version_id: version.source_version_id,
          mode,
        },
      });
      notify(`${mode === "preview" ? "Preview" : "Production"} run created.`, {
        type: "success",
      });
      redirect("show", ResourceName.Runs, result.data.id, result.data);
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

        {!versions.isPending && !versions.error ? (
          <Paper variant="outlined" sx={{ p: 1.5 }}>
            <Stack spacing={1.25}>
              <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                <Chip size="small" variant="outlined" label={`${lifecycleSummary.total} total`} />
                <Chip
                  size="small"
                  color="warning"
                  label={`${lifecycleSummary.counts.draft} draft`}
                />
                <Chip
                  size="small"
                  color="info"
                  label={`${lifecycleSummary.counts.pending_approval} pending`}
                />
                <Chip
                  size="small"
                  color="success"
                  label={`${lifecycleSummary.counts.approved} approved`}
                />
                <Chip
                  size="small"
                  color="error"
                  label={`${lifecycleSummary.counts.rejected} rejected`}
                />
                <Chip
                  size="small"
                  variant="outlined"
                  label={`${lifecycleSummary.counts.superseded} superseded`}
                />
                <Chip
                  size="small"
                  color={lifecycleAttentionColor}
                  label={lifecycleAttentionLabel}
                />
              </Stack>

              <Alert severity={lifecycleAlertSeverity} icon={false}>
                <Stack spacing={0.75}>
                  <AlertTitle>{lifecycleSummary.nextAction}</AlertTitle>
                  <Typography variant="body2">{lifecycleSummary.nextActionDetail}</Typography>
                  {lifecycleSummary.latestVersion ? (
                    <Typography variant="caption" color="text.secondary">
                      Latest version: {lifecycleSummary.latestVersion.version_label} (
                      {describeSourceVersionStatus(lifecycleSummary.latestVersion.status).label}) ·
                      updated {formatDateTime(lifecycleSummary.latestVersion.updated_at)}
                    </Typography>
                  ) : null}
                </Stack>
              </Alert>
            </Stack>
          </Paper>
        ) : null}

        {versions.isPending && !versions.error ? (
          <Alert severity="info">Loading source versions...</Alert>
        ) : null}

        {!versions.isPending && !versions.error && lifecycleSummary.total === 0 ? (
          <Paper variant="outlined" sx={{ p: 2 }}>
            <Stack spacing={1}>
              <Typography variant="subtitle2">No source versions yet</Typography>
              <Typography variant="body2" color="text.secondary">
                Create the first draft version to establish the lifecycle for this source.
              </Typography>
              <Box>
                <Button variant="contained" onClick={openCreateDialog}>
                  Create Version
                </Button>
              </Box>
            </Stack>
          </Paper>
        ) : null}

        {versions.data && versions.data.length > 0 ? (
          <Box sx={{ overflowX: "auto" }}>
            <Table size="small" stickyHeader>
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
                {versions.data.map((version, versionIndex) => {
                  const canEdit = version.status === "draft" || version.status === "rejected";
                  const canReview =
                    version.status === "draft" || version.status === "pending_approval";
                  const canPreview =
                    version.status !== "rejected" && version.status !== "superseded";
                  const canProduction = version.status === "approved";
                  const isActing = actionVersionId === version.source_version_id;
                  const statusMeta = describeSourceVersionStatus(version.status);
                  const previousVersion =
                    versions.data && versionIndex < versions.data.length - 1
                      ? versions.data[versionIndex + 1]
                      : null;
                  const isDiffOpen = diffVersionId === version.source_version_id;
                  return (
                    <React.Fragment key={version.id}>
                      <TableRow>
                        <TableCell>
                          <Typography variant="body2" sx={{ fontWeight: 600 }}>
                            {version.version_label}
                          </Typography>
                          <Typography variant="caption" color="text.secondary">
                            {version.source_version_id}
                          </Typography>
                        </TableCell>
                        <TableCell>
                          <Stack spacing={0.5} alignItems="flex-start">
                            <StatusBadge
                              level={sourceVersionStatusToLevel(version.status)}
                              label={statusMeta.label}
                            />
                            <Typography variant="caption" color="text.secondary">
                              {statusMeta.detail}
                            </Typography>
                          </Stack>
                        </TableCell>
                        <TableCell>{version.extractor_profile_id ?? "—"}</TableCell>
                        <TableCell>
                          <Box
                            component="pre"
                            sx={{
                              m: 0,
                              p: 1,
                              borderRadius: 1,
                              bgcolor: "grey.50",
                              border: "1px solid",
                              borderColor: "grey.200",
                              fontSize: "0.7rem",
                              lineHeight: 1.6,
                              fontFamily: "monospace",
                              whiteSpace: "pre-wrap",
                              maxWidth: 260,
                              overflow: "hidden",
                            }}
                          >
                            {summarizeAcquisitionSpec(version.acquisition_spec).join("\n")}
                          </Box>
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
                            {previousVersion ? (
                              <Button
                                size="small"
                                variant="outlined"
                                color={isDiffOpen ? "secondary" : "inherit"}
                                onClick={() =>
                                  setDiffVersionId(isDiffOpen ? null : version.source_version_id)
                                }
                              >
                                {isDiffOpen ? "Hide diff" : "Compare"}
                              </Button>
                            ) : null}
                            <Button
                              size="small"
                              variant="contained"
                              color="primary"
                              onClick={() => createRun("preview", version)}
                              disabled={!canPreview || isActing}
                            >
                              Preview Run
                            </Button>
                            <Box
                              component="span"
                              sx={{
                                alignSelf: "center",
                                display: { xs: "none", sm: "inline-block" },
                                width: "1px",
                                height: 24,
                                mx: 0.75,
                                bgcolor: "divider",
                              }}
                              aria-hidden
                            />
                            <ConfirmButton
                              tier="notable"
                              size="small"
                              variant="contained"
                              color="warning"
                              confirmTitle="Launch production run?"
                              confirmDescription={`This will start a production pipeline for ${version.version_label}. Production runs create real artifacts.`}
                              confirmLabel="Launch production"
                              onConfirm={() => createRun("production", version)}
                              disabled={!canProduction || isActing}
                            >
                              Production Run
                            </ConfirmButton>
                            <ConfirmButton
                              tier="notable"
                              size="small"
                              variant="outlined"
                              confirmTitle="Approve this version?"
                              confirmDescription={`Approving ${version.version_label} makes it eligible for production runs. Ensure the version has been reviewed.`}
                              confirmLabel="Approve"
                              onConfirm={() => runVersionAction("approve", version)}
                              disabled={!canReview || isActing}
                            >
                              Approve
                            </ConfirmButton>
                            <ConfirmButton
                              tier="destructive"
                              size="small"
                              variant="outlined"
                              color="error"
                              confirmTitle="Reject this version?"
                              confirmDescription={`Rejecting ${version.version_label} will permanently block it from production use. This cannot be undone.`}
                              confirmLabel="Reject version"
                              onConfirm={() => runVersionAction("reject", version)}
                              disabled={!canReview || isActing}
                            >
                              Reject
                            </ConfirmButton>
                          </Stack>
                        </TableCell>
                      </TableRow>
                      {isDiffOpen && previousVersion ? (
                        <TableRow>
                          <TableCell colSpan={6} sx={{ p: 2, bgcolor: "grey.50" }}>
                            <SourceVersionDiffPanel
                              previous={previousVersion}
                              current={version}
                              defaultOpen
                            />
                          </TableCell>
                        </TableRow>
                      ) : null}
                    </React.Fragment>
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
