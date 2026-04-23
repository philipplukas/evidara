"use client";

import RefreshIcon from "@mui/icons-material/Refresh";
import {
  Alert,
  AlertTitle,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Paper,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useDataProvider, useGetList, useNotify, useRedirect } from "react-admin";
import { ResourceName } from "../../domain/resourceNames";
import type {
  RunCreateInput,
  RunReadiness,
  RunRecord,
  SourceRecord,
  SourceVersionRecord,
} from "../../lib/admin/dataProvider";
import { controlPlaneActions } from "../../lib/admin/dataProvider";
import { emitOperatorJourneyEvent } from "../../lib/admin/operatorJourneyTelemetry";
import { describeReadinessDetail } from "../../lib/admin/readiness-messages";
import { ConfirmButton } from "../shared/ConfirmButton";

const LIST_PARAMS = {
  pagination: { page: 1, perPage: 250 },
  sort: { field: "name", order: "ASC" as const },
};

type RunLaunchRedirectResource = typeof ResourceName.Runs | typeof ResourceName.PreviewReview;

type RunLaunchButtonProps = {
  label: string;
  buttonVariant?: "contained" | "outlined" | "text";
  buttonColor?: "primary" | "secondary";
  defaultMode?: "preview" | "production";
  allowedModes?: Array<"preview" | "production">;
  redirectResource?: RunLaunchRedirectResource;
};

type RunLaunchFormState = {
  source_id: string;
  source_version_id: string;
  mode: "preview" | "production";
};

const resolveInitialMode = (
  defaultMode: "preview" | "production",
  allowedModes: Array<"preview" | "production">,
): "preview" | "production" => {
  if (allowedModes.includes(defaultMode)) {
    return defaultMode;
  }
  return allowedModes[0] ?? "preview";
};

const createInitialState = (defaultMode: "preview" | "production"): RunLaunchFormState => ({
  source_id: "",
  source_version_id: "",
  mode: defaultMode,
});

const versionAllowedForMode = (
  status: SourceVersionRecord["status"],
  mode: "preview" | "production",
): boolean => {
  if (mode === "production") {
    return status === "approved";
  }
  return status !== "rejected" && status !== "superseded";
};

const RUN_READINESS_CONFIRMED_KEY_PREFIX = "evidara_run_readiness_confirmed:";
const RUN_READINESS_BLOCKED_CODES_KEY_PREFIX = "evidara_run_readiness_blocked_codes:";

const normalizeReadinessCodes = (checks: RunReadiness["checks"]): string[] =>
  Array.from(new Set(checks.filter((check) => !check.ok).map((check) => check.code))).sort();

const formatModeLabel = (mode: "preview" | "production"): string =>
  mode === "production" ? "Production" : "Preview";

const modeChipColor = (mode: "preview" | "production"): "info" | "success" =>
  mode === "production" ? "success" : "info";

export type PreflightRetryPayload = {
  source_id: string;
  source_version_id: string;
  mode: "preview" | "production";
  previous_error_message: string | null;
};

export function buildPreflightRetryPayload(
  formState: { source_id: string; source_version_id: string; mode: "preview" | "production" },
  readinessError: string | null,
): PreflightRetryPayload {
  return {
    source_id: formState.source_id,
    source_version_id: formState.source_version_id,
    mode: formState.mode,
    previous_error_message: readinessError ?? null,
  };
}

export function RunLaunchButton({
  label,
  buttonVariant = "contained",
  buttonColor = "primary",
  defaultMode = "production",
  allowedModes = ["preview", "production"],
  redirectResource = ResourceName.Runs,
}: RunLaunchButtonProps) {
  const dataProvider = useDataProvider();
  const notify = useNotify();
  const redirect = useRedirect();

  const [open, setOpen] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isCheckingReadiness, setIsCheckingReadiness] = useState(false);
  const [readiness, setReadiness] = useState<RunReadiness | null>(null);
  const [readinessError, setReadinessError] = useState<string | null>(null);
  const initialMode = resolveInitialMode(defaultMode, allowedModes);
  const [formState, setFormState] = useState<RunLaunchFormState>(createInitialState(initialMode));
  const readinessCheckStartedAtRef = useRef<number | null>(null);

  const sources = useGetList<SourceRecord>(ResourceName.Sources, {
    ...LIST_PARAMS,
    filter: {},
  });

  const sourceVersions = useGetList<SourceVersionRecord>("source-versions", {
    pagination: { page: 1, perPage: 100 },
    sort: { field: "created_at", order: "DESC" as const },
    filter: { source_id: formState.source_id || "__none__" },
  });
  const selectedSource = useMemo(
    () => (sources.data ?? []).find((source) => source.source_id === formState.source_id) ?? null,
    [formState.source_id, sources.data],
  );
  const selectedVersion = useMemo(
    () =>
      (sourceVersions.data ?? []).find(
        (version) => version.source_version_id === formState.source_version_id,
      ) ?? null,
    [formState.source_version_id, sourceVersions.data],
  );

  const versionChoices = useMemo(() => {
    const versions = sourceVersions.data ?? [];
    return versions
      .filter((version) => versionAllowedForMode(version.status, formState.mode))
      .map((version) => ({
        value: version.source_version_id,
        label: `${version.version_label} (${version.status})`,
      }));
  }, [sourceVersions.data, formState.mode]);

  useEffect(() => {
    const versions = sourceVersions.data ?? [];
    const allowedIds = new Set(
      versions
        .filter((v) => versionAllowedForMode(v.status, formState.mode))
        .map((v) => v.source_version_id),
    );
    if (formState.source_version_id && !allowedIds.has(formState.source_version_id)) {
      setFormState((prev) => ({ ...prev, source_version_id: "" }));
    }
  }, [formState.mode, formState.source_version_id, sourceVersions.data]);

  const reset = () => {
    setFormState(createInitialState(initialMode));
    setReadiness(null);
    setReadinessError(null);
  };

  const closeDialog = () => {
    if (isSubmitting) {
      return;
    }
    setOpen(false);
    reset();
  };

  const submit = async () => {
    try {
      setIsSubmitting(true);
      const result = await dataProvider.create<RunRecord>(ResourceName.Runs, {
        data: formState as RunCreateInput,
      });
      if (typeof window !== "undefined") {
        const runId = String(result.data.run_id);
        window.localStorage.setItem(`${RUN_READINESS_CONFIRMED_KEY_PREFIX}${runId}`, "true");
        window.localStorage.removeItem(`${RUN_READINESS_BLOCKED_CODES_KEY_PREFIX}${runId}`);
      }
      notify(`${formState.mode === "preview" ? "Preview" : "Production"} run created.`, {
        type: "success",
      });
      setOpen(false);
      reset();
      redirect("show", redirectResource, result.data.id, result.data);
    } catch (error) {
      notify(error instanceof Error ? error.message : "Unable to create run.", {
        type: "error",
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  const runPreflight = useCallback(
    (input: RunLaunchFormState, isActive: () => boolean = () => true) => {
      const canCheck = Boolean(input.source_id && input.source_version_id);
      if (!canCheck) {
        setReadiness(null);
        setReadinessError(null);
        setIsCheckingReadiness(false);
        return;
      }

      setIsCheckingReadiness(true);
      setReadinessError(null);
      readinessCheckStartedAtRef.current = Date.now();

      void controlPlaneActions
        .getRunReadiness(input)
        .then((result) => {
          if (!isActive()) return;
          setReadiness(result);
          const elapsedMs =
            readinessCheckStartedAtRef.current != null
              ? Date.now() - readinessCheckStartedAtRef.current
              : undefined;
          if (result.ready) {
            emitOperatorJourneyEvent("preflight_ready", {
              source_id: input.source_id,
              source_version_id: input.source_version_id,
              mode: input.mode,
              readiness_codes: [],
              duration_ms: elapsedMs,
            });
          } else {
            const readinessCodes = normalizeReadinessCodes(result.checks);
            emitOperatorJourneyEvent("preflight_blocked", {
              source_id: input.source_id,
              source_version_id: input.source_version_id,
              mode: input.mode,
              readiness_codes: readinessCodes,
              duration_ms: elapsedMs,
            });
          }
        })
        .catch((error: unknown) => {
          if (!isActive()) return;
          setReadiness(null);
          setReadinessError(
            error instanceof Error ? error.message : "Unable to run preflight checks.",
          );
        })
        .finally(() => {
          if (!isActive()) return;
          setIsCheckingReadiness(false);
        });
    },
    [],
  );

  useEffect(() => {
    let active = true;
    runPreflight(formState, () => active);
    return () => {
      active = false;
    };
  }, [formState, runPreflight]);

  const handleRetry = () => {
    const previousError = readinessError;
    setReadiness(null);
    setReadinessError(null);
    emitOperatorJourneyEvent(
      "preflight_retry",
      buildPreflightRetryPayload(formState, previousError),
    );
    runPreflight(formState);
  };

  const failingChecks = useMemo(
    () => readiness?.checks.filter((check) => !check.ok) ?? [],
    [readiness],
  );
  const readinessStatusLabel = isCheckingReadiness
    ? "Preflight checking"
    : readinessError
      ? "Preflight error"
      : readiness?.ready
        ? "Preflight ready"
        : readiness
          ? "Preflight blocked"
          : "Preflight pending";
  const isReadyToCreate =
    !!formState.source_id &&
    !!formState.source_version_id &&
    !isSubmitting &&
    !isCheckingReadiness &&
    !readinessError &&
    !!readiness?.ready;

  return (
    <>
      <Button variant={buttonVariant} color={buttonColor} onClick={() => setOpen(true)}>
        {label}
      </Button>

      <Dialog open={open} onClose={closeDialog} maxWidth="sm" fullWidth>
        <DialogTitle>
          <Stack spacing={0.5}>
            <Typography variant="h6" component="div">
              Create Run
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Pick a source/version pair, then review the preflight result before launch.
            </Typography>
          </Stack>
        </DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            {sources.error ? <Alert severity="error">Unable to load sources.</Alert> : null}

            <Paper variant="outlined" sx={{ p: 1.5 }}>
              <Stack spacing={1.25}>
                <Typography variant="subtitle2">Launch summary</Typography>
                <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                  <Chip
                    size="small"
                    color={modeChipColor(formState.mode)}
                    label={`${formatModeLabel(formState.mode)} mode`}
                  />
                  <Chip
                    size="small"
                    variant="outlined"
                    label={`Source ${selectedSource?.name ?? "not selected"}`}
                  />
                  <Chip
                    size="small"
                    variant="outlined"
                    label={
                      selectedVersion
                        ? `Version ${selectedVersion.version_label} (${selectedVersion.status})`
                        : "Version not selected"
                    }
                  />
                  <Chip size="small" label={readinessStatusLabel} variant="outlined" />
                </Stack>
                <Typography variant="body2" color="text.secondary">
                  {formState.mode === "production"
                    ? "Production runs require an approved version and should be used when the source is ready for operator verification."
                    : "Preview runs let you inspect capture quality and readiness before promotion."}
                </Typography>
              </Stack>
            </Paper>

            <Paper variant="outlined" sx={{ p: 1.5 }}>
              <Stack spacing={2}>
                <Typography variant="subtitle2">Launch inputs</Typography>

                <TextField
                  select
                  label="Run mode"
                  value={formState.mode}
                  onChange={(event) => {
                    const mode = event.target.value as RunLaunchFormState["mode"];
                    setFormState((prev) => {
                      const versions = sourceVersions.data ?? [];
                      const allowedIds = new Set(
                        versions
                          .filter((v) => versionAllowedForMode(v.status, mode))
                          .map((v) => v.source_version_id),
                      );
                      return {
                        ...prev,
                        mode,
                        source_version_id: allowedIds.has(prev.source_version_id)
                          ? prev.source_version_id
                          : "",
                      };
                    });
                  }}
                  fullWidth
                  disabled={allowedModes.length === 1}
                >
                  {allowedModes.map((mode) => (
                    <MenuItem key={mode} value={mode}>
                      {formatModeLabel(mode)}
                    </MenuItem>
                  ))}
                </TextField>

                <TextField
                  select
                  label="Source"
                  value={formState.source_id}
                  onChange={(event) =>
                    setFormState({
                      ...formState,
                      source_id: event.target.value,
                      source_version_id: "",
                    })
                  }
                  fullWidth
                >
                  {(sources.data ?? []).map((source) => (
                    <MenuItem key={source.source_id} value={source.source_id}>
                      {source.name}
                    </MenuItem>
                  ))}
                </TextField>

                <TextField
                  select
                  label="Source version"
                  value={formState.source_version_id}
                  onChange={(event) =>
                    setFormState({
                      ...formState,
                      source_version_id: event.target.value,
                    })
                  }
                  fullWidth
                  disabled={!formState.source_id}
                  helperText="Production runs require an approved version."
                >
                  {versionChoices.map((version) => (
                    <MenuItem key={version.value} value={version.value}>
                      {version.label}
                    </MenuItem>
                  ))}
                </TextField>
              </Stack>
            </Paper>

            {isCheckingReadiness ? (
              <Alert severity="info" icon={false}>
                <AlertTitle>Checking preflight readiness</AlertTitle>
                The launch dialog is validating the selected source/version pair.
              </Alert>
            ) : null}
            {readinessError ? (
              <Alert
                severity="error"
                action={
                  <Button
                    size="small"
                    color="inherit"
                    startIcon={<RefreshIcon />}
                    onClick={handleRetry}
                    disabled={isCheckingReadiness}
                  >
                    Retry
                  </Button>
                }
              >
                {readinessError}
              </Alert>
            ) : null}
            {readiness && !readiness.ready ? (
              <Alert severity="warning" icon={false}>
                <Stack spacing={1.25}>
                  <AlertTitle>Preflight blocks launch</AlertTitle>
                  <Typography variant="body2" sx={{ fontWeight: 600 }}>
                    Preflight is blocking launch. Resolve the items below to enable Create Run.
                  </Typography>
                  <Stack spacing={1}>
                    {failingChecks.map((check) => {
                      const info = describeReadinessDetail(check.code);
                      return (
                        <Paper key={check.code} variant="outlined" sx={{ p: 1.25 }}>
                          <Stack spacing={0.75}>
                            <Typography variant="body2" sx={{ fontWeight: 600 }}>
                              {info.title}
                            </Typography>
                            <Typography variant="body2" color="text.secondary">
                              {check.detail}
                            </Typography>
                            <Typography variant="caption" color="text.secondary">
                              Next action: {info.action}
                            </Typography>
                          </Stack>
                        </Paper>
                      );
                    })}
                  </Stack>
                  <Typography variant="caption" color="text.secondary">
                    {failingChecks.length} blocked check
                    {failingChecks.length === 1 ? "" : "s"} need attention before the run can be
                    created.
                  </Typography>
                  {selectedVersion ? (
                    <Typography variant="caption" color="text.secondary">
                      Selected version status: {selectedVersion.status}
                    </Typography>
                  ) : null}
                </Stack>
              </Alert>
            ) : null}
            {readiness?.ready ? (
              <Alert severity="success" icon={false}>
                <AlertTitle>Preflight ready</AlertTitle>
                The current source/version pair is ready to launch.
              </Alert>
            ) : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={closeDialog} disabled={isSubmitting}>
            Cancel
          </Button>
          {formState.mode === "production" ? (
            <ConfirmButton
              tier="notable"
              variant="contained"
              color="success"
              disabled={!isReadyToCreate || isSubmitting}
              confirmTitle="Create production run?"
              confirmDescription="Production runs schedule real pipeline work against the selected approved version. Confirm only when you intend to verify capture end-to-end."
              confirmLabel="Create run"
              cancelLabel="Go back"
              onConfirm={submit}
            >
              {isSubmitting ? "Creating..." : "Create Run"}
            </ConfirmButton>
          ) : (
            <Button variant="contained" onClick={submit} disabled={!isReadyToCreate}>
              {isSubmitting ? "Creating..." : "Create Run"}
            </Button>
          )}
        </DialogActions>
      </Dialog>
    </>
  );
}
