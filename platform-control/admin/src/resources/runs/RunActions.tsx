"use client";

import { useState } from "react";
import { useDataProvider, useNotify, useRecordContext, useRedirect, useRefresh } from "react-admin";
import { ResourceName } from "../../domain/resourceNames";
import type { RunRecord } from "../../lib/admin/dataProvider";
import { controlPlaneActions } from "../../lib/admin/dataProvider";
import { Panel, Pill } from "../../ui/primitives";
import { ConfirmButton } from "../shared/ConfirmButton";
import { runRecordStatusToLevel } from "../shared/statusLevels";

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

type PromoteButtonProps = {
  size?: "small" | "medium" | "large";
  variant?: "contained" | "outlined" | "text";
  fullWidth?: boolean;
};

export function PromoteToProductionButton({
  size = "small",
  variant = "outlined",
  fullWidth = false,
}: PromoteButtonProps) {
  const run = useRecordContext<RunRecord>();
  const dataProvider = useDataProvider();
  const notify = useNotify();
  const redirect = useRedirect();
  const [isSubmitting, setIsSubmitting] = useState(false);

  if (!run || !canPromoteRunToProduction(run)) {
    return null;
  }

  const promoteRun = async () => {
    try {
      setIsSubmitting(true);
      const result = await dataProvider.create<RunRecord>(ResourceName.Runs, {
        data: {
          source_id: run.source_id,
          source_version_id: run.source_version_id,
          mode: "production",
        },
      });
      notify("Production run created from preview.", { type: "success" });
      redirect("show", ResourceName.Runs, result.data.id, result.data);
    } catch (error) {
      notify(error instanceof Error ? error.message : "Unable to promote run.", {
        type: "error",
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <ConfirmButton
      tier="notable"
      color="success"
      size={size}
      variant={variant}
      fullWidth={fullWidth}
      confirmTitle="Promote to production?"
      confirmDescription="This will create a new production run using the same source version. The original preview run remains unchanged."
      confirmLabel="Create production run"
      onConfirm={promoteRun}
      disabled={isSubmitting}
    >
      {isSubmitting ? "Promoting..." : "Promote to Production"}
    </ConfirmButton>
  );
}

export function canPromoteRunToProduction(run: RunRecord): boolean {
  return run.status === "completed" && run.mode === "preview";
}

export function RunActionStack() {
  const run = useRecordContext<RunRecord>();

  if (!run) {
    return null;
  }

  const canCancel = ["pending", "running"].includes(run.status);
  const canPromote = canPromoteRunToProduction(run);
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
        : canPromote
          ? {
              summary:
                "This preview run completed successfully. You can promote it to a production run.",
              followUp:
                "If you do nothing, the preview stays as an audit trail. Promote when you are ready to go live.",
            }
          : {
              summary: "This run is read-only now. Use the detail sections to review the outcome.",
              followUp:
                "If you do nothing, the run stays as an audit trail and no more work is scheduled.",
            };

  return (
    <Panel className="w-full p-4 sm:min-w-[260px]">
      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between gap-2">
          <p className="text-sm font-semibold text-[var(--foreground)] m-0">Operator actions</p>
          <Pill level={runRecordStatusToLevel(run.status)}>{run.status}</Pill>
        </div>
        <p className="text-sm text-[var(--text-meta)] m-0">{actionCopy.summary}</p>
        <p className="text-xs text-[var(--text-meta)] m-0">{actionCopy.followUp}</p>
        {canCancel ? <CancelRunButton size="medium" variant="contained" fullWidth /> : null}
        {canPromote ? (
          <PromoteToProductionButton size="medium" variant="contained" fullWidth />
        ) : null}
      </div>
    </Panel>
  );
}
