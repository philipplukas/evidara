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

type RetryRunButtonProps = CancelRunButtonProps;

/**
 * `RetryRunButton` — the recovery lever for a failed or cancelled run.
 *
 * `POST /v1/runs/{id}/retry` has existed since runs did and no UI ever called
 * it. So the queue offered CANCEL on the two states that are still moving and
 * *nothing at all* on the one state that has stopped and needs a decision — the
 * failed run's detail page had only "Jump to…" anchors. An operator's only
 * recovery path was a hand-written POST.
 *
 * Deliberately mirrors `CancelRunButton`'s shape rather than inventing a second
 * pattern: same `ConfirmButton`, same `useRecordContext` status gate, same
 * notify/refresh. The gate here is the server's own
 * (`RunService.retry_run` refuses anything but FAILED / CANCELLED), so the
 * button never offers an action the API would reject.
 *
 * `tier="notable"`, not `"safe"`: retry drops the run's provider jobs and
 * **re-dispatches against the live source**. It is recovery, not a refresh, and
 * the confirmation says so.
 */
export function RetryRunButton({
  size = "small",
  variant = "outlined",
  fullWidth = false,
}: RetryRunButtonProps) {
  const run = useRecordContext<RunRecord>();
  const notify = useNotify();
  const refresh = useRefresh();
  const [isSubmitting, setIsSubmitting] = useState(false);

  if (!run || !canRetryRun(run)) {
    return null;
  }

  const retryRun = async () => {
    try {
      setIsSubmitting(true);
      await controlPlaneActions.retryRun(run.run_id);
      notify("Run re-queued.", { type: "success" });
      refresh();
    } catch (error) {
      notify(error instanceof Error ? error.message : "Unable to retry run.", {
        type: "error",
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <ConfirmButton
      tier="notable"
      color="primary"
      size={size}
      variant={variant}
      fullWidth={fullWidth}
      confirmTitle="Retry this run?"
      confirmDescription="The run is reset to pending, its provider jobs are dropped, and it is dispatched again against the live source. Fix the cause first — a retry against an unchanged failure will fail the same way."
      confirmLabel="Retry run"
      onConfirm={retryRun}
      disabled={isSubmitting}
    >
      {isSubmitting ? "Retrying..." : "Retry"}
    </ConfirmButton>
  );
}

/**
 * Mirrors `RunService.retry_run`'s guard: only a run that has stopped in a
 * recoverable way can be retried. A completed run has nothing to recover, and a
 * pending/running one is still moving.
 */
export function canRetryRun(run: Pick<RunRecord, "status">): boolean {
  return run.status === "failed" || run.status === "cancelled";
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
  const canRetry = canRetryRun(run);
  const actionCopy = canRetry
    ? {
        summary:
          run.status === "failed"
            ? "This run stopped on a failure. Read the failure reason below, fix the cause, then retry."
            : "This run was cancelled before it finished. Retry it when you are ready to run it again.",
        followUp:
          "If you do nothing, nothing further happens — a failed run is not re-attempted on its own.",
      }
    : run.status === "pending"
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
        {canRetry ? <RetryRunButton size="medium" variant="contained" fullWidth /> : null}
        {canPromote ? (
          <PromoteToProductionButton size="medium" variant="contained" fullWidth />
        ) : null}
      </div>
    </Panel>
  );
}
