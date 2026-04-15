"use client";

import { Chip, Paper, Stack, Typography } from "@mui/material";
import { useState } from "react";
import { useNotify, useRecordContext, useRefresh } from "react-admin";
import type { RunRecord } from "../../lib/admin/dataProvider";
import { controlPlaneActions } from "../../lib/admin/dataProvider";
import { ConfirmButton } from "../shared/ConfirmButton";

type CancelRunButtonProps = {
  size?: "small" | "medium" | "large";
  variant?: "contained" | "outlined" | "text";
  fullWidth?: boolean;
};

export function CancelRunButton({
  size = "small",
  variant = "outlined",
  fullWidth = false,
}: CancelRunButtonProps) {
  const run = useRecordContext<RunRecord>();
  const notify = useNotify();
  const refresh = useRefresh();
  const [isSubmitting, setIsSubmitting] = useState(false);

  if (!run || !["pending", "running"].includes(run.status)) {
    return null;
  }

  const cancelRun = async () => {
    try {
      setIsSubmitting(true);
      await controlPlaneActions.cancelRun(run.run_id);
      notify("Run cancelled.", { type: "success" });
      refresh();
    } catch (error) {
      notify(error instanceof Error ? error.message : "Unable to cancel run.", {
        type: "error",
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <ConfirmButton
      tier="destructive"
      color="error"
      size={size}
      variant={variant}
      fullWidth={fullWidth}
      confirmTitle="Cancel this run?"
      confirmDescription="Cancelling will stop all in-progress pipeline work. Any incomplete artifacts may be lost."
      confirmLabel="Cancel run"
      onConfirm={cancelRun}
      disabled={isSubmitting}
    >
      {isSubmitting ? "Cancelling..." : "Cancel"}
    </ConfirmButton>
  );
}

export function RunActionStack() {
  const run = useRecordContext<RunRecord>();

  if (!run) {
    return null;
  }

  const canCancel = ["pending", "running"].includes(run.status);
  const actionCopy =
    run.status === "pending"
      ? {
          summary:
            "The run is still queued. Cancel it only if you need to stop work before it starts.",
          followUp:
            "If you do nothing, it stays in queue until the platform starts it or an operator cancels it.",
        }
      : run.status === "running"
        ? {
            summary:
              "The run is active. Cancel it only if you need to stop downstream work immediately.",
            followUp:
              "If you do nothing, it continues to progress and may complete or fail without intervention.",
          }
        : {
            summary: "This run is read-only now. Use the detail sections to review the outcome.",
            followUp:
              "If you do nothing, the run stays as an audit trail and no more work is scheduled.",
          };

  return (
    <Paper
      variant="outlined"
      sx={{
        p: 1.5,
        minWidth: { xs: "100%", sm: 260 },
        background: "linear-gradient(180deg, rgba(255, 250, 238, 0.98), rgba(255, 255, 255, 0.96))",
      }}
    >
      <Stack spacing={1}>
        <Stack direction="row" spacing={1} alignItems="center" justifyContent="space-between">
          <Typography variant="subtitle2">Operator actions</Typography>
          <Chip
            size="small"
            label={run.status}
            color={
              run.status === "failed"
                ? "error"
                : run.status === "running"
                  ? "info"
                  : run.status === "pending"
                    ? "warning"
                    : "default"
            }
            variant="outlined"
          />
        </Stack>
        <Typography variant="body2" color="text.secondary">
          {actionCopy.summary}
        </Typography>
        <Typography variant="caption" color="text.secondary">
          {actionCopy.followUp}
        </Typography>
        {canCancel ? <CancelRunButton size="medium" variant="contained" fullWidth /> : null}
      </Stack>
    </Paper>
  );
}
