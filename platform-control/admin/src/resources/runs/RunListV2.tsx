/**
 * `RunListV2` — v2 preview of the run queue. Richer than the sources list:
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
import {
  Button,
  DataTable,
  type DataTableColumn,
  InlineAlert,
  Pill,
  type PillLevel,
} from "../../ui/primitives";
import { runModeToLevel, runRecordStatusToLevel } from "../shared/statusLevels";
import { CancelRunButton, RetryRunButton } from "./RunActions";
import { RunLaunchButton } from "./RunLaunchDialog";
import {
  describeQueueScope,
  describeRunAge,
  describeRunState,
  formatQueueCount,
  getRunQueueKeyboardShortcutAction,
  resolveQueueCountScope,
  runLooksStalled,
  runStateNeedsExplanation,
  selectAttentionRun,
  summarizeRunFilters,
} from "./RunList";

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
          : "bg-[var(--surface-panel)]/60 border-[var(--border)] text-[var(--foreground-muted)] hover:border-[var(--border-strong)]"
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
  const attentionButtonRef = useRef<HTMLButtonElement | null>(null);

  const records = controller.data;
  const filterValues = controller.filterValues as RunQueueFilterValues;

  const runs = useMemo(() => records ?? [], [records]);
  /*
   * The shared helper, not a second copy of it. The copy that used to live here
   * (justified by `RunListRecord`'s extra fields, which the helper is now
   * generic over) is how this page came to disagree with the dashboard about
   * the same queue: it ended in a `runs[0]` fallback, so on an all-completed
   * queue it nominated the newest completed run as the "attention run" while
   * the dashboard correctly reported nothing needing attention.
   */
  const attentionRun = useMemo(() => selectAttentionRun(runs), [runs]);
  const filterSummary = useMemo(() => summarizeRunFilters(filterValues), [filterValues]);
  const hasActiveFilters = filterSummary.length > 0;

  // Whether the numbers on the preset chips mean anything, and if so what.
  // Everything below reads this instead of assuming `runs` is the whole queue.
  //
  // A server-side status filter makes the per-status counts unknowable, not zero:
  // the page holds only the filtered status, so every other chip counted 0 and —
  // because loadedCount >= total on that filtered page — `resolveQueueCountScope`
  // called it `complete` and printed a confident `0` over a non-empty queue. The
  // scope is `unknown` here so the chips render the `—` this module already has
  // for exactly this case. Zero and "I could not ask" must not look the same.
  const isStatusFiltered = Boolean(filterValues.status);
  const countScope = isStatusFiltered
    ? "unknown"
    : resolveQueueCountScope({
        hasError: Boolean(controller.error),
        isPending: controller.isPending,
        loadedCount: runs.length,
        total: controller.total,
      });

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
            <Pill variant="tag" level={runModeToLevel(record.mode)}>
              {record.mode}
            </Pill>
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
      render: (record) => {
        const age = describeRunAge(record);
        const stalled = runLooksStalled(record);
        return (
          // `items-start`: a flex column stretches its children by default, so
          // the status pill grew to the width of the sentence beside it and read
          // as a bordered banner rather than a badge. It only became visible once
          // the column got wider, but the stretch was always there.
          <div className="flex flex-col items-start gap-1 max-w-[32ch]">
            <div className="flex flex-wrap items-center gap-1.5">
              <Pill level={runRecordStatusToLevel(record.status)}>{record.status}</Pill>
              {/*
               * The staleness signal. A run queued 30 seconds ago and one stuck
               * for three days used to render identically, and CREATED — the only
               * column that would let you tell them apart — is one of the two
               * clipped off the right edge at 1440px. Sitting beside the badge,
               * this survives any horizontal scroll position.
               */}
              {age ? (
                <span
                  data-testid="run-age"
                  className={
                    stalled
                      ? "text-[11px] font-semibold text-[var(--status-degraded)]"
                      : "text-[11px] text-[var(--foreground-subtle)]"
                  }
                  title={
                    stalled
                      ? "This run has been in this state for over two hours — check whether it is stuck."
                      : undefined
                  }
                >
                  {age}
                  {stalled ? " · check it" : ""}
                </span>
              ) : null}
            </div>
            {/*
             * Prose only where the badge is not the whole message. Eight
             * identical three-line repetitions of "Finished successfully…" were
             * costing the vertical space that pushed ACTIONS off the fold.
             */}
            {runStateNeedsExplanation(record) ? (
              <span className="text-[12px] text-[var(--foreground-subtle)]">
                {describeRunState(record)}
              </span>
            ) : null}
            {record.status === "failed" && record.failure_reason ? (
              /*
               * `line-clamp-3`, not `truncate`. A single-line clip cut the
               * failure reason at "provider returned HT…" — precisely where it
               * starts being useful — which forced a click into the detail page
               * on every failed row just to read the sentence. Three lines is
               * enough for the substance; the `title` still carries the whole
               * thing.
               */
              <span
                data-testid="run-failure-reason"
                className="text-[12px] text-[var(--status-critical)] line-clamp-3"
                title={record.failure_reason}
              >
                Failure: {record.failure_reason}
              </span>
            ) : null}
          </div>
        );
      },
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
      /*
       * Pinned to the right edge, and its header made visible.
       *
       * Measured on the running app at 1440px: `scrollWidth 1160 >
       * clientWidth 1054`, so UPDATED and ACTIONS sat past the right edge of a
       * scroll container that showed no cue at all. Cancel and retry are the
       * only levers an operator has on a live run, and they were off-screen on
       * a standard laptop — at 390px the table lost everything but RUN and a
       * sliver of SOURCE. Pinning means the levers survive any horizontal
       * scroll position and any viewport width.
       *
       * The header was `sr-only`, which is `position: absolute` and cannot also
       * be `position: sticky`. Showing it is the better trade anyway: a pinned
       * column that never says what it is reads as a rendering artefact.
       */
      stickyRight: true,
      className: "text-right",
      /*
       * Cancel renders for pending/running, Retry for failed/cancelled — so
       * every non-terminal-and-fine state now offers its one lever from the
       * list, and no state offers both. The ConfirmButton inside each stops
       * click propagation, so the row-click navigation does not fire when the
       * operator opens a confirmation.
       */
      render: (record) => (
        <RecordContextProvider value={record}>
          <CancelRunButton />
          <RetryRunButton />
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
            {/* Only advertised while there is an attention run to focus. */}
            {attentionRun ? (
              <p className="text-[12px] text-[var(--foreground-subtle)]">
                Press <kbd className="font-mono">/</kbd> to focus the attention run. Press{" "}
                <kbd className="font-mono">O</kbd> to open it.
              </p>
            ) : null}
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
                  {preset.label} {formatQueueCount(statusCounts[preset.key], countScope)}
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
            ) : countScope === "unknown" ? null : (
              /*
               * Says the quiet case out loud instead of leaving a gap where the
               * amber chip was — the absence of a warning is itself information.
               *
               * The wording is scoped to what this page actually knows.
               * `complete` means every run the server reports is in hand, so the
               * dashboard's sentence is true here too. `partial` means we are
               * looking at one page, and claiming anything about the queue would
               * be the same class of error as the chip this replaces. When the
               * counts are unknown (a failed list query) nothing is said at all;
               * the error alert below is the honest surface for that.
               */
              <span
                data-testid="run-queue-no-attention"
                className="inline-flex items-center rounded-full border border-[var(--border)] bg-[var(--surface-input)] px-3 h-9 text-[12px] font-semibold text-[var(--foreground-subtle)]"
              >
                {countScope === "complete"
                  ? "No run is failing, pending, or running"
                  : "No failing, pending, or running run on this page"}
              </span>
            )}
          </div>
          <p
            className={
              countScope === "unknown"
                ? "text-[12px] font-semibold text-[var(--status-critical)]"
                : "text-[12px] text-[var(--foreground-subtle)]"
            }
          >
            {describeQueueScope({
              scope: countScope,
              loadedCount: runs.length,
              total: controller.total,
              filterSummary,
            })}
          </p>
        </section>

        {/*
         * #669: the outage used to be a footnote inside the table body while
         * five confident zeros sat above it. The failure is the primary state of
         * this panel now, and it offers the operator a way out.
         */}
        {controller.error ? (
          <InlineAlert tone="error" testId="run-queue-load-error">
            <div className="space-y-2">
              <p className="font-semibold text-[var(--foreground)]">
                Cannot reach platform-control
              </p>
              <p>
                The run queue could not be loaded, so no run counts are known — the presets above
                show “—”, not zero. Existing runs are unaffected.
              </p>
              <Button variant="secondary" size="sm" onClick={() => controller.refetch()}>
                Retry
              </Button>
            </div>
          </InlineAlert>
        ) : null}

        <DataTable<RunListRecord>
          records={records}
          columns={columns}
          getRowId={(r) => String(r.id)}
          isLoading={controller.isPending}
          error={controller.error}
          sort={controller.sort}
          onSort={(field, order) => controller.setSort({ field, order })}
          onRowClick={(r) => navigate(`/runs/${encodeURIComponent(String(r.id))}/show`)}
          getRowLabel={(r) => `Open run ${r.run_id}`}
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
