/**
 * `PreviewReviewListV2` — Tailwind + `ra-core` port of the MUI
 * `PreviewReviewList`. The preview-approval queue is the preview-mode slice of
 * the runs list: the dataProvider forces `mode: "preview"` for the
 * `PreviewReview` resource, so this page only exposes the status filter (no
 * mode presets) plus the preview-scoped launch CTA and the shared
 * `CancelRunButton` row action.
 */
"use client";

import { ListContextProvider, RecordContextProvider, useListController } from "ra-core";
import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { ResourceName } from "../../domain/resourceNames";
import type { RunListRecord } from "../../lib/admin/dataProvider";
import { formatSwissDateTime } from "../../lib/format/date";
import { DataTable, type DataTableColumn, Pill, type PillLevel } from "../../ui/primitives";
import { runRecordStatusToLevel } from "../shared/statusLevels";
import { CancelRunButton } from "./RunActions";
import { RunLaunchButton } from "./RunLaunchDialog";

type RunStatus = RunListRecord["status"];
type PreviewFilterValues = Partial<Pick<RunListRecord, "status">>;

type StatusPreset = {
  key: RunStatus;
  label: string;
  level: PillLevel;
};

const STATUS_PRESETS: StatusPreset[] = [
  { key: "pending", label: "Pending", level: "degraded" },
  { key: "running", label: "Running", level: "info" },
  { key: "completed", label: "Completed", level: "healthy" },
  { key: "failed", label: "Failed", level: "critical" },
  { key: "cancelled", label: "Cancelled", level: "neutral" },
];

interface PresetButtonProps {
  isActive: boolean;
  onClick: () => void;
  children: React.ReactNode;
  tone?: "accent" | "warning";
}

function PresetButton({ isActive, onClick, children, tone = "accent" }: PresetButtonProps) {
  const toneActive =
    tone === "warning"
      ? "bg-[var(--status-degraded-subtle)] border-[var(--status-degraded)]/40 text-[var(--status-degraded)]"
      : "bg-[var(--brand-wash-8)] border-[var(--brand)]/50 text-[var(--brand)]";
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex items-center rounded-full border px-3 h-8 text-[12px] font-semibold transition-colors ${
        isActive
          ? toneActive
          : "bg-white/60 border-[var(--border)] text-[var(--foreground-muted)] hover:border-[var(--border-strong)]"
      }`}
    >
      {children}
    </button>
  );
}

export default function PreviewReviewListV2() {
  const controller = useListController<RunListRecord>({
    resource: ResourceName.PreviewReview,
    perPage: 25,
    sort: { field: "created_at", order: "DESC" },
  });
  const navigate = useNavigate();

  const records = controller.data;
  const filterValues = controller.filterValues as PreviewFilterValues;
  const runs = useMemo(() => records ?? [], [records]);
  const hasActiveFilters = Boolean(filterValues.status);

  const statusCounts = useMemo(() => {
    const seed: Record<RunStatus, number> = {
      pending: 0,
      running: 0,
      completed: 0,
      failed: 0,
      cancelled: 0,
    };
    for (const run of runs) {
      seed[run.status] += 1;
    }
    return seed;
  }, [runs]);

  const setStatus = (status: RunStatus | undefined) =>
    controller.setFilters({ ...filterValues, status }, undefined, false);
  const clearFilters = () => controller.setFilters({}, undefined, false);

  const columns: DataTableColumn<RunListRecord>[] = [
    {
      key: "run",
      header: "Run",
      sortField: "run_id",
      render: (record) => (
        <span className="font-mono text-[12px] text-[var(--foreground)]">{record.run_id}</span>
      ),
    },
    {
      key: "source",
      header: "Source",
      render: (record) => (
        <div className="flex flex-col gap-0.5">
          <span className="font-semibold">{record.source_name}</span>
          <span className="text-[12px] text-[var(--foreground-subtle)]">
            {record.version_label}
          </span>
        </div>
      ),
    },
    {
      key: "status",
      header: "Status",
      sortField: "status",
      render: (record) => (
        <div className="flex flex-col gap-1 max-w-[32ch]">
          <Pill level={runRecordStatusToLevel(record.status)}>{record.status}</Pill>
          {record.status === "failed" && record.failure_reason ? (
            <span
              className="text-[12px] text-[var(--status-critical)] truncate"
              title={record.failure_reason}
            >
              Failure: {record.failure_reason}
            </span>
          ) : null}
        </div>
      ),
    },
    {
      key: "captured",
      header: "Captured",
      sortField: "captured_resources_count",
      className: "text-right tabular-nums",
      headerClassName: "text-right",
      render: (record) => record.captured_resources_count,
    },
    {
      key: "artifacts",
      header: "Artifacts",
      sortField: "artifacts_count",
      className: "text-right tabular-nums",
      headerClassName: "text-right",
      render: (record) => record.artifacts_count,
    },
    {
      key: "created",
      header: "Created",
      sortField: "created_at",
      render: (record) => (
        <span className="text-[var(--foreground-muted)] whitespace-nowrap">
          {formatSwissDateTime(record.created_at)}
        </span>
      ),
    },
    {
      key: "updated",
      header: "Updated",
      sortField: "updated_at",
      render: (record) => (
        <span className="text-[var(--foreground-muted)] whitespace-nowrap">
          {formatSwissDateTime(record.updated_at)}
        </span>
      ),
    },
    {
      key: "actions",
      header: "Actions",
      headerClassName: "sr-only",
      className: "text-right",
      render: (record) => (
        <RecordContextProvider value={record}>
          <CancelRunButton />
        </RecordContextProvider>
      ),
    },
  ];

  return (
    <ListContextProvider value={controller}>
      <div className="px-4 py-6 sm:px-6 sm:py-8 max-w-[var(--container-max)] mx-auto space-y-4">
        <header className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="space-y-2">
            <p className="text-[11px] uppercase tracking-[0.16em] font-semibold text-[var(--foreground-subtle)]">
              Preview approvals
            </p>
            <h1 className="font-[family:var(--font-admin-serif)] text-[28px] font-semibold text-[var(--foreground)] leading-tight">
              Preview approvals
            </h1>
            <p className="text-[14px] text-[var(--foreground-muted)] max-w-[72ch]">
              Review preview-mode acquisition runs before promoting them to production. Use the
              status presets to narrow the queue.
            </p>
          </div>
          <div className="shrink-0">
            <RunLaunchButton
              label="Create Preview Run"
              defaultMode="preview"
              allowedModes={["preview"]}
              redirectResource={ResourceName.PreviewReview}
            />
          </div>
        </header>

        <section className="rounded-[18px] border border-[var(--border-faint)] bg-[var(--admin-panel-bg)] p-4 space-y-3 shadow-[var(--shadow-card)] backdrop-blur-[12px]">
          <div className="flex flex-wrap items-center gap-1.5">
            <PresetButton isActive={!hasActiveFilters} onClick={clearFilters}>
              All preview runs
            </PresetButton>
            {STATUS_PRESETS.map((preset) => (
              <PresetButton
                key={preset.key}
                isActive={filterValues.status === preset.key}
                onClick={() => setStatus(preset.key)}
                tone={preset.key === "failed" ? "warning" : "accent"}
              >
                {preset.label} {statusCounts[preset.key]}
              </PresetButton>
            ))}
          </div>
          <p className="text-[12px] text-[var(--foreground-subtle)]">
            {hasActiveFilters
              ? `Filtering ${filterValues.status} · ${runs.length} of ${controller.total ?? runs.length}`
              : `${runs.length} preview run${runs.length === 1 ? "" : "s"} in view`}
          </p>
        </section>

        <DataTable<RunListRecord>
          records={records}
          columns={columns}
          getRowId={(r) => String(r.id)}
          isLoading={controller.isPending}
          error={controller.error}
          sort={controller.sort}
          onSort={(field, order) => controller.setSort({ field, order })}
          onRowClick={(r) => navigate(`/preview-review/${encodeURIComponent(String(r.id))}/show`)}
          total={controller.total}
          page={controller.page}
          perPage={controller.perPage}
          onPageChange={controller.setPage}
          empty={
            hasActiveFilters
              ? "No preview runs match the current filter — try clearing it."
              : "No preview runs yet."
          }
        />
      </div>
    </ListContextProvider>
  );
}
