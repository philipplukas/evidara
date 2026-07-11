/**
 * `RunList` — Tailwind + `ra-core` run queue. Richer than the sources list:
 *
 *   - 5-level status cascade (pending/running/completed/failed/cancelled)
 *     exercises every `Pill` level, not just 3 like sources.
 *   - Numeric columns (M-8 density) render via `DataTable` column config.
 *   - `useListController.setFilters` drives a preset bar built from
 *     Tailwind buttons instead of MUI `SelectInput` — proves the filter-
 *     controller surface works without MUI.
 *
 * The operator-action stack (`RunLaunchButton` "Create Run" CTA,
 * `CancelRunButton` row action) and the `/`+`o` keyboard shortcuts reuse the
 * now-Tailwind action components and the pure helpers in `./RunList.tsx`.
 */
"use client";

import { ListContextProvider, RecordContextProvider, useListController } from "ra-core";
import { useEffect, useMemo, useRef } from "react";
import { useNavigate } from "react-router-dom";
import type { RunListRecord } from "../../lib/admin/dataProvider";
import { formatSwissDateTime } from "../../lib/format/date";
import { DataTable, type DataTableColumn, Pill, type PillLevel } from "../../ui/primitives";
import { runModeToLevel, runRecordStatusToLevel } from "../shared/statusLevels";
import { CancelRunButton } from "./RunActions";
import { RunLaunchButton } from "./RunLaunchDialog";
import {
  describeRunState,
  getRunQueueKeyboardShortcutAction,
  summarizeRunFilters,
} from "./runQueueHelpers";

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

export default function RunList() {
  const controller = useListController<RunListRecord>({
    resource: "runs",
    perPage: 25,
    sort: { field: "created_at", order: "DESC" },
  });
  const navigate = useNavigate();
  const attentionButtonRef = useRef<HTMLButtonElement | null>(null);

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

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const shortcut = getRunQueueKeyboardShortcutAction(event, event.target, attentionRun);
      if (!shortcut) {
        return;
      }
      event.preventDefault();
      if (shortcut.type === "focus-attention") {
        attentionButtonRef.current?.focus();
        return;
      }
      navigate(`/runs/${encodeURIComponent(shortcut.runId)}/show`);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [attentionRun, navigate]);

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
          <span className="text-[12px] text-[var(--foreground-subtle)]">
            {record.version_label}
          </span>
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
          <span className="text-[12px] text-[var(--foreground-subtle)]">
            {describeRunState(record)}
          </span>
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
      // Renders only for pending/running runs; the ConfirmButton inside
      // CancelRunButton stops click propagation so the row-click navigation
      // does not fire when the operator opens the cancel confirmation.
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
              Run queue
            </p>
            <h1 className="font-[family:var(--font-admin-serif)] text-[28px] font-semibold text-[var(--foreground)] leading-tight">
              Runs
            </h1>
            <p className="text-[14px] text-[var(--foreground-muted)] max-w-[72ch]">
              Triage active, failed, and completed acquisition runs. Use presets to narrow the
              operator queue without leaving the list.
            </p>
            <p className="text-[12px] text-[var(--foreground-subtle)]">
              Press <kbd className="font-mono">/</kbd> to focus the attention run. Press{" "}
              <kbd className="font-mono">O</kbd> to open it.
            </p>
          </div>
          <div className="shrink-0">
            <RunLaunchButton label="Create Run" defaultMode="production" />
          </div>
        </header>

        {/* Preset bar (replaces the MUI RunQueueHeader presets). */}
        <section className="rounded-[18px] border border-[var(--border-faint)] bg-[var(--admin-panel-bg)] p-4 space-y-3 shadow-[var(--shadow-card)] backdrop-blur-[12px]">
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
                ref={attentionButtonRef}
                type="button"
                onClick={() => navigate(`/runs/${encodeURIComponent(attentionRun.run_id)}/show`)}
                className="inline-flex items-center rounded-full border border-[var(--status-degraded)]/40 bg-[var(--status-degraded-subtle)] px-3 h-9 text-[12px] font-semibold text-[var(--status-degraded)] hover:bg-[var(--status-degraded-subtle)]/80"
              >
                Open attention run · {attentionRun.source_name}
              </button>
            ) : null}
          </div>
          <p className="text-[12px] text-[var(--foreground-subtle)]">
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
          onRowClick={(r) => navigate(`/runs/${encodeURIComponent(String(r.id))}/show`)}
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
