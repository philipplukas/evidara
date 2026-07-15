/**
 * `PreviewReviewShowV2` — Tailwind + `ra-core` port of the MUI
 * `PreviewReviewShow`. Renders the preview-run header + operator action stack,
 * a metadata grid, and delegates the lifecycle stack to the shared
 * `RunDetailSectionsV2` (same component the runs v2 detail uses). The
 * dataProvider guards the `PreviewReview` getOne to preview-mode runs, so a
 * production run id resolves to a 404 here.
 */
"use client";

import { RecordContextProvider, useShowController } from "ra-core";
import { useParams } from "react-router-dom";
import { ResourceName } from "../../domain/resourceNames";
import type { RunRecord } from "../../lib/admin/dataProvider";
import { formatSwissDateTime } from "../../lib/format/date";
import { DetailGrid, FieldCell, Pill } from "../../ui/primitives";
import { runModeToLevel, runRecordStatusToLevel } from "../shared/statusLevels";
import { RunActionStack } from "./RunActions";
import RunDetailSectionsV2 from "./RunDetailSectionsV2";

const STATUS_LABEL: Record<RunRecord["status"], string> = {
  pending: "Pending",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
  cancelled: "Cancelled",
};

export default function PreviewReviewShowV2() {
  const { id } = useParams();
  const controller = useShowController<RunRecord>({
    resource: ResourceName.PreviewReview,
    id,
  });
  const run = controller.record;

  if (controller.isPending) {
    return (
      <div className="px-4 py-10 text-center text-[var(--foreground-subtle)]">
        Loading preview run…
      </div>
    );
  }
  if (controller.error || !run) {
    return (
      <div className="px-4 py-10 text-center text-[var(--status-critical)]">
        Failed to load preview run.
      </div>
    );
  }

  return (
    <div className="px-4 py-6 sm:px-6 sm:py-8 max-w-[var(--container-max)] mx-auto space-y-6">
      <header className="space-y-3">
        <p className="text-[11px] uppercase tracking-[0.16em] font-semibold text-[var(--foreground-subtle)]">
          Preview approval
        </p>
        <h1 className="font-[family:var(--font-admin-serif)] text-[28px] font-semibold text-[var(--foreground)] leading-tight">
          Run <span className="font-mono text-[22px]">{run.run_id}</span>
        </h1>
        <div className="text-[13px] text-[var(--foreground-muted)] font-mono">
          {run.source_id} · {run.source_version_id}
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <Pill level={runRecordStatusToLevel(run.status)}>{STATUS_LABEL[run.status]}</Pill>
          <Pill level={runModeToLevel(run.mode)}>
            {run.mode === "production" ? "Production" : "Preview"}
          </Pill>
          <Pill variant="meta">{`Version ${run.source_version_id}`}</Pill>
        </div>
        <RecordContextProvider value={run}>
          <RunActionStack />
        </RecordContextProvider>
      </header>

      <DetailGrid>
        <FieldCell label="Run">
          <span className="font-mono text-[13px]">{run.run_id}</span>
        </FieldCell>
        <FieldCell label="Source ID">
          <span className="font-mono text-[13px]">{run.source_id}</span>
        </FieldCell>
        <FieldCell label="Source version ID">
          <span className="font-mono text-[13px]">{run.source_version_id}</span>
        </FieldCell>
        <FieldCell label="Status">{run.status}</FieldCell>
        <FieldCell label="Captured resources">
          <span className="tabular-nums">{run.captured_resources_count}</span>
        </FieldCell>
        <FieldCell label="Artifacts">
          <span className="tabular-nums">{run.artifacts_count}</span>
        </FieldCell>
        <FieldCell label="Failure reason">
          {run.failure_reason ?? <span className="text-[var(--foreground-faint)]">—</span>}
        </FieldCell>
        <FieldCell label="Started">
          {run.started_at ? (
            formatSwissDateTime(run.started_at)
          ) : (
            <span className="text-[var(--foreground-faint)]">—</span>
          )}
        </FieldCell>
        <FieldCell label="Completed">
          {run.completed_at ? (
            formatSwissDateTime(run.completed_at)
          ) : (
            <span className="text-[var(--foreground-faint)]">—</span>
          )}
        </FieldCell>
        <FieldCell label="Created">{formatSwissDateTime(run.created_at)}</FieldCell>
        <FieldCell label="Updated">{formatSwissDateTime(run.updated_at)}</FieldCell>
      </DetailGrid>

      <RecordContextProvider value={run}>
        <RunDetailSectionsV2 />
      </RecordContextProvider>
    </div>
  );
}
