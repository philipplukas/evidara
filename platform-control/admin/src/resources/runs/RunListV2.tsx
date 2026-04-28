/**
 * `RunListV2` — v2 preview of the run queue. Richer than SourceListV2:
 *
 *   - 5-level status cascade (pending/running/completed/failed/cancelled)
 *     exercises every `Pill` level, not just 3 like sources.
 *   - Numeric columns (M-8 density) render via `DataTable` column config.
 *   - `useListController.setFilters` drives a preset bar built from
 *     Tailwind buttons instead of MUI `SelectInput` — proves the filter-
 *     controller surface works without MUI.
 *
 * Deferred until follow-up increments:
 *   - Keyboard shortcuts (`/` focus, `o` open attention) — domain logic,
 *     not primitive work; pure helpers stay in `./RunList.tsx`.
 *   - `CancelRunButton` row action + `RunLaunchButton` "Create Run" CTA —
 *     mutation migration (needs `<Dialog>` primitive).
 */
"use client";

import { ListContextProvider, useListController } from "ra-core";
import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import type { RunListRecord } from "../../lib/admin/dataProvider";
import { formatSwissDateTime } from "../../lib/format/date";
import { DataTable, type DataTableColumn, Pill, type PillLevel } from "../../ui/primitives";
import { runModeToLevel, runRecordStatusToLevel } from "../shared/StatusBadge";
import { describeRunState, summarizeRunFilters } from "./RunList";

type RunStatus = RunListRecord["status"];
type RunMode = RunListRecord["mode"];
type RunQueueFilterValues = Partial<Pick<RunListRecord, "mode" | "status">>;

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

const MODE_PRESETS: Array<{ key: RunMode; label: string }> = [
  { key: "production", label: "Production" },
  { key: "preview", label: "Preview" },
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
      ? "bg-[rgba(237,108,2,0.1)] border-[rgba(237,108,2,0.4)] text-[#e65100]"
      : "bg-[var(--brand-wash-8)] border-[rgba(15,76,129,0.5)] text-[var(--brand)]";
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex items-center rounded-full border px-3 h-8 text-[12px] font-semibold transition-colors ${
        isActive
          ? toneActive
          : "bg-white/60 border-[rgba(29,41,61,0.16)] text-[rgba(29,41,61,0.75)] hover:border-[rgba(29,41,61,0.3)]"
      }`}
    >
      {children}
    </button>
  );
}

export default function RunListV2() {
  const controller = useListController<RunListRecord>({
    resource: "runs",
    perPage: 25,
    sort: { field: "created_at", order: "DESC" },
  });
  const navigate = useNavigate();

  const records = controller.data;
  const filterValues = controller.filterValues as RunQueueFilterValues;

  const runs = useMemo(() => records ?? [], [records]);
  // Inlined from the v1 `selectAttentionRun` helper to preserve the richer
  // `RunListRecord` typing (v1 casts to `RunRecord` and loses `source_name`).
  const attentionRun = useMemo<RunListRecord | null>(() => {
    const actionable: RunStatus[] = ["failed", "running", "pending"];
    for (const status of actionable) {
      const match = runs.find((r) => r.status === status);
      if (match) return match;
    }
    return runs[0] ?? null;
  }, [runs]);
  const filterSummary = useMemo(() => summarizeRunFilters(filterValues), [filterValues]);
  const hasActiveFilters = filterSummary.length > 0;

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
  const setMode = (mode: RunMode | undefined) =>
    controller.setFilters({ ...filterValues, mode }, undefined, false);
  const clearFilters = () => controller.setFilters({}, undefined, false);

  const columns: DataTableColumn<RunListRecord>[] = [
    {
      key: "run",
      header: "Run",
      sortField: "run_id",
      render: (record) => (
        <div className="flex flex-col gap-1">
          <span className="font-mono text-[12px] text-[var(--foreground)]">{record.run_id}</span>
          <div>
            <Pill level={runModeToLevel(record.mode)}>{record.mode}</Pill>
          </div>
        </div>
      ),
    },
    {
      key: "source",
      header: "Source",
      render: (record) => (
        <div className="flex flex-col gap-0.5">
          <span className="font-semibold">{record.source_name}</span>
          <span className="text-[12px] text-[rgba(29,41,61,0.6)]">{record.version_label}</span>
        </div>
      ),
    },
    {
      key: "state",
      header: "State",
      sortField: "status",
      render: (record) => (
        <div className="flex flex-col gap-1 max-w-[32ch]">
          <Pill level={runRecordStatusToLevel(record.status)}>{record.status}</Pill>
          <span className="text-[12px] text-[rgba(29,41,61,0.65)]">{describeRunState(record)}</span>
          {record.status === "failed" && record.failure_reason ? (
            <span className="text-[12px] text-[#b71c1c] truncate" title={record.failure_reason}>
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
        <span className="text-[rgba(29,41,61,0.75)] whitespace-nowrap">
          {formatSwissDateTime(record.created_at)}
        </span>
      ),
    },
    {
      key: "updated",
      header: "Updated",
      sortField: "updated_at",
      render: (record) => (
        <span className="text-[rgba(29,41,61,0.75)] whitespace-nowrap">
          {formatSwissDateTime(record.updated_at)}
        </span>
      ),
    },
  ];

  return (
    <ListContextProvider value={controller}>
      <div className="px-4 py-6 sm:px-6 sm:py-8 max-w-[1600px] mx-auto space-y-4">
        <header className="space-y-2">
          <p className="text-[11px] uppercase tracking-[0.16em] font-semibold text-[rgba(29,41,61,0.6)]">
            Run queue
          </p>
          <h1 className="font-sans text-[28px] font-semibold text-[var(--foreground)] leading-tight">
            Runs
          </h1>
          <p className="text-[14px] text-[rgba(29,41,61,0.7)] max-w-[72ch]">
            Triage active, failed, and completed acquisition runs. Use presets to narrow the
            operator queue without leaving the list.
          </p>
        </header>

        {/* Preset bar (replaces the MUI RunQueueHeader presets). */}
        <section className="rounded-[18px] border border-[rgba(29,41,61,0.08)] bg-[var(--admin-panel-bg)] p-4 space-y-3 shadow-[var(--shadow-card)] backdrop-blur-[12px]">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <div className="flex flex-wrap items-center gap-1.5">
              <PresetButton isActive={!hasActiveFilters} onClick={clearFilters}>
                All queue states
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
              {MODE_PRESETS.map((preset) => (
                <PresetButton
                  key={preset.key}
                  isActive={filterValues.mode === preset.key}
                  onClick={() => setMode(preset.key)}
                >
                  {preset.label}
                </PresetButton>
              ))}
            </div>
            {attentionRun ? (
              <button
                type="button"
                onClick={() => navigate(`/runs-v2/${encodeURIComponent(attentionRun.run_id)}`)}
                className="inline-flex items-center rounded-full border border-[rgba(237,108,2,0.4)] bg-[rgba(237,108,2,0.08)] px-3 h-9 text-[12px] font-semibold text-[#e65100] hover:bg-[rgba(237,108,2,0.14)]"
              >
                Open attention run · {attentionRun.source_name}
              </button>
            ) : null}
          </div>
          <p className="text-[12px] text-[rgba(29,41,61,0.6)]">
            {hasActiveFilters
              ? `Filtering ${filterSummary} · ${runs.length} of ${controller.total ?? runs.length}`
              : `${runs.length} run${runs.length === 1 ? "" : "s"} in view`}
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
          onRowClick={(r) => navigate(`/runs-v2/${encodeURIComponent(String(r.id))}`)}
          total={controller.total}
          page={controller.page}
          perPage={controller.perPage}
          onPageChange={controller.setPage}
          empty={
            hasActiveFilters
              ? "No runs match the current filter — try clearing it."
              : "No runs yet."
          }
        />
      </div>
    </ListContextProvider>
  );
}
