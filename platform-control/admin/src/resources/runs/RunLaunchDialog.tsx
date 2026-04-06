"use client";

import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Stack,
  TextField,
} from "@mui/material";
import { useEffect, useMemo, useState } from "react";
import { useDataProvider, useGetList, useNotify, useRedirect } from "react-admin";
import type {
  RunCreateInput,
  RunReadiness,
  RunRecord,
  SourceRecord,
  SourceVersionRecord,
} from "../../lib/admin/dataProvider";
import { controlPlaneActions } from "../../lib/admin/dataProvider";

const LIST_PARAMS = {
  pagination: { page: 1, perPage: 250 },
  sort: { field: "name", order: "ASC" as const },
};

type RunLaunchButtonProps = {
  label: string;
  buttonVariant?: "contained" | "outlined" | "text";
  buttonColor?: "primary" | "secondary";
  defaultMode?: "preview" | "production";
  allowedModes?: Array<"preview" | "production">;
  redirectResource?: "runs" | "preview-review";
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

export function RunLaunchButton({
  label,
  buttonVariant = "contained",
  buttonColor = "primary",
  defaultMode = "production",
  allowedModes = ["preview", "production"],
  redirectResource = "runs",
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

  const sources = useGetList<SourceRecord>("sources", {
    ...LIST_PARAMS,
    filter: {},
  });

  const sourceVersions = useGetList<SourceVersionRecord>("source-versions", {
    pagination: { page: 1, perPage: 100 },
    sort: { field: "created_at", order: "DESC" as const },
    filter: { source_id: formState.source_id || "__none__" },
  });

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
      const result = await dataProvider.create<RunRecord>("runs", {
        data: formState as RunCreateInput,
      });
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

  useEffect(() => {
    const canCheck = Boolean(formState.source_id && formState.source_version_id);
    if (!canCheck) {
      setReadiness(null);
      setReadinessError(null);
      setIsCheckingReadiness(false);
      return;
    }

    let active = true;
    setIsCheckingReadiness(true);
    setReadinessError(null);

    void controlPlaneActions
      .getRunReadiness(formState)
      .then((result) => {
        if (!active) return;
        setReadiness(result);
      })
      .catch((error: unknown) => {
        if (!active) return;
        setReadiness(null);
        setReadinessError(error instanceof Error ? error.message : "Unable to run preflight checks.");
      })
      .finally(() => {
        if (!active) return;
        setIsCheckingReadiness(false);
      });

    return () => {
      active = false;
    };
  }, [formState]);

  const failingChecks = useMemo(
    () => readiness?.checks.filter((check) => !check.ok) ?? [],
    [readiness],
  );
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
        <DialogTitle>Create Run</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            {sources.error ? <Alert severity="error">Unable to load sources.</Alert> : null}

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
                  {mode}
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

            {isCheckingReadiness ? <Alert severity="info">Running run preflight checks...</Alert> : null}
            {readinessError ? <Alert severity="error">{readinessError}</Alert> : null}
            {readiness && !readiness.ready ? (
              <Alert severity="warning">
                Run is blocked until preflight checks pass:
                <ul style={{ margin: "8px 0 0", paddingInlineStart: "20px" }}>
                  {failingChecks.map((check) => (
                    <li key={check.code}>{check.detail}</li>
                  ))}
                </ul>
              </Alert>
            ) : null}
            {readiness?.ready ? <Alert severity="success">Preflight checks passed.</Alert> : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={closeDialog} disabled={isSubmitting}>
            Cancel
          </Button>
          <Button
            variant="contained"
            onClick={submit}
            disabled={!isReadyToCreate}
          >
            {isSubmitting ? "Creating..." : "Create Run"}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
