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
import { useMemo, useState } from "react";
import { useDataProvider, useGetList, useNotify, useRedirect } from "react-admin";
import type {
  RunCreateInput,
  RunRecord,
  SourceRecord,
  SourceVersionRecord,
} from "../../lib/admin/dataProvider";

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

const createInitialState = (defaultMode: "preview" | "production"): RunLaunchFormState => ({
  source_id: "",
  source_version_id: "",
  mode: defaultMode,
});

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
  const [formState, setFormState] = useState<RunLaunchFormState>(createInitialState(defaultMode));

  const sources = useGetList<SourceRecord>("sources", {
    ...LIST_PARAMS,
    filter: {},
  });

  const sourceVersions = useGetList<SourceVersionRecord>("source-versions", {
    pagination: { page: 1, perPage: 100 },
    sort: { field: "created_at", order: "DESC" as const },
    filter: { source_id: formState.source_id || "__none__" },
  });

  const versionChoices = useMemo(
    () =>
      (sourceVersions.data ?? []).map((version) => ({
        value: version.source_version_id,
        label: `${version.version_label} (${version.status})`,
      })),
    [sourceVersions.data],
  );

  const reset = () => {
    setFormState(createInitialState(defaultMode));
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
              onChange={(event) =>
                setFormState({
                  ...formState,
                  mode: event.target.value as RunLaunchFormState["mode"],
                })
              }
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
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={closeDialog} disabled={isSubmitting}>
            Cancel
          </Button>
          <Button
            variant="contained"
            onClick={submit}
            disabled={!formState.source_id || !formState.source_version_id || isSubmitting}
          >
            {isSubmitting ? "Creating..." : "Create Run"}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
