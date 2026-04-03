"use client";

import { Button, Stack } from "@mui/material";
import { useState } from "react";
import { useNotify, useRecordContext, useRefresh } from "react-admin";
import type { RunRecord } from "../../lib/admin/dataProvider";
import { controlPlaneActions } from "../../lib/admin/dataProvider";

type CancelRunButtonProps = {
  size?: "small" | "medium" | "large";
};

export function CancelRunButton({ size = "small" }: CancelRunButtonProps) {
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
    <Button
      size={size}
      color="warning"
      variant="outlined"
      onClick={(event) => {
        event.stopPropagation();
        event.preventDefault();
        void cancelRun();
      }}
      disabled={isSubmitting}
    >
      {isSubmitting ? "Cancelling..." : "Cancel"}
    </Button>
  );
}

export function RunActionStack() {
  return (
    <Stack direction="row" spacing={1.5}>
      <CancelRunButton size="medium" />
    </Stack>
  );
}
