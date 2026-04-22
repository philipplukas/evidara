/**
 * `RunShowV2` — v2 preview of the run detail page. Largest single admin
 * page (v1's `RunShow.tsx` is 433 LoC before `RunDetailSections`). This
 * port covers header + metric band + decision-support 2×2 + 13-field
 * metadata grid + failure alert, then delegates the lifecycle stack to
 * `<RunDetailSectionsV2>` (ADR-0026 P3 — pipeline health + 5 accordion
 * sections). All primitives come from `src/ui/primitives/`.
 *
 * Deferred until follow-up increments:
 *   - `RunHandoffCard` — stateful URL-param read; ports with the shell.
 *   - `RunActionStack` (cancel button) — mutation migration.
 *
 * Pure helpers (`buildRunDecisionSupport`, `describeRunNextStep`) are
 * imported from v1's `./RunShow.tsx` rather than forked.
 */
"use client";

import { RecordContextProvider, useShowController } from "ra-core";
import { useParams } from "react-router-dom";
import type { RunRecord } from "../../lib/admin/dataProvider";
import { formatSwissDateTime } from "../../lib/format/date";
import { DetailGrid, FieldCell, Pill } from "../../ui/primitives";
import { runModeToLevel, runRecordStatusToLevel } from "../shared/StatusBadge";
import { PromoteToProductionButton } from "./RunActions";
import RunDetailSectionsV2 from "./RunDetailSectionsV2";
import { buildRunDecisionSupport } from "./RunShow";

function formatDuration(run: RunRecord): string {
  if (!run.started_at || !run.completed_at) return "—";
  const ms = new Date(run.completed_at).getTime() - new Date(run.started_at).getTime();
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.floor(ms / 60000)}m ${Math.round((ms % 60000) / 1000)}s`;
}

function describeRunNextStep(run: RunRecord): string {
  if (run.status === "failed") {
    return "Open the pipeline sections below and use the failure reason to pinpoint the blocked stage.";
  }
  if (run.status === "running") {
    return "The run is active. Watch the pipeline health and stage sections for the next operator cue.";
  }
  if (run.status === "pending") {
    return "The run is queued. Review readiness and wait for the first stage update.";
  }
  if (run.status === "completed") {
    return "The run completed successfully. Use the lifecycle sections as the audit trail.";
  }
  return "The run was cancelled. Review the detail sections if the stop was unexpected.";
}

const STATUS_LABEL: Record<RunRecord["status"], string> = {
  pending: "Pending",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
  cancelled: "Cancelled",
};

export default function RunShowV2() {
  const { id } = useParams();
  const controller = useShowController<RunRecord>({
    resource: "runs",
    id,
  });
  const run = controller.record;

  if (controller.isPending) {
    return <div className="px-4 py-10 text-center text-[rgba(29,41,61,0.6)]">Loading run…</div>;
  }
  if (controller.error || !run) {
    return <div className="px-4 py-10 text-center text-[#b71c1c]">Failed to load run.</div>;
  }

  const decision = buildRunDecisionSupport(run);
  const duration = formatDuration(run);

  return (
    <div className="px-4 py-6 sm:px-6 sm:py-8 max-w-[1600px] mx-auto space-y-6">
      {/* Header — parity with v1 `RunPageContextBar`, minus the action stack. */}
      <header className="space-y-3">
        <p className="text-[11px] uppercase tracking-[0.16em] font-semibold text-[rgba(29,41,61,0.6)]">
          Preview · Tailwind + ra-core · Run detail
        </p>
        <h1 className="font-serif text-[28px] font-semibold text-[var(--foreground)] leading-tight">
          Run <span className="font-mono text-[22px]">{run.run_id}</span>
        </h1>
        <div className="text-[13px] text-[rgba(29,41,61,0.7)] font-mono">
          {run.source_id} · {run.source_version_id}
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <Pill level={runRecordStatusToLevel(run.status)}>{STATUS_LABEL[run.status]}</Pill>
          <Pill level={runModeToLevel(run.mode)}>
            {run.mode === "production" ? "Production" : "Preview"}
          </Pill>
          <Pill variant="meta">{`Version ${run.source_version_id}`}</Pill>
        </div>
        {run.status === "completed" && run.mode === "preview" ? (
          <RecordContextProvider value={run}>
            <PromoteToProductionButton size="medium" variant="contained" />
          </RecordContextProvider>
        ) : null}
      </header>

      {/* Overview band — metric chips + next-step narrative. */}
      <section className="rounded-[18px] border border-[rgba(29,41,61,0.08)] bg-gradient-to-b from-[var(--brand-wash-4)] to-white/95 p-5 sm:p-6 shadow-[var(--shadow-card)] backdrop-blur-[12px] space-y-4">
        <div className="flex flex-wrap items-center gap-1.5">
          <Pill variant="meta">{`Captured ${run.captured_resources_count}`}</Pill>
          <Pill variant="meta">{`Artifacts ${run.artifacts_count}`}</Pill>
          <Pill variant="meta">{`Duration ${duration}`}</Pill>
        </div>
        <p className="text-[14px] text-[rgba(29,41,61,0.75)]">{describeRunNextStep(run)}</p>

        {/* Decision support — 2x2 on md+, stacked on mobile. */}
        <div className="rounded-[14px] border border-[rgba(29,41,61,0.08)] bg-[var(--brand-wash-3)] p-4 space-y-3">
          <div>
            <h2 className="text-[14px] font-semibold text-[var(--foreground)]">Decision support</h2>
            <p className="text-[12px] text-[rgba(29,41,61,0.65)]">
              The four cues below answer the operator questions we use most often on active runs.
            </p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <DecisionCell label="Why this matters" value={decision.whyItMatters} />
            <DecisionCell label="What is blocked" value={decision.whatIsBlocked} />
            <DecisionCell label="What changed recently" value={decision.whatChangedRecently} />
            <DecisionCell label="If you do nothing" value={decision.whatHappensIfIgnored} />
          </div>
        </div>

        {run.failure_reason ? (
          <div
            role="alert"
            className={`rounded-[12px] border p-3 ${
              run.status === "failed"
                ? "border-[rgba(198,40,40,0.4)] bg-[rgba(198,40,40,0.06)] text-[#b71c1c]"
                : "border-[rgba(237,108,2,0.4)] bg-[rgba(237,108,2,0.08)] text-[#e65100]"
            }`}
          >
            <p className="text-[13px] font-semibold">Failure reason</p>
            <p className="text-[13px] mt-0.5 text-[rgba(29,41,61,0.8)]">{run.failure_reason}</p>
          </div>
        ) : null}
      </section>

      {/* Metadata grid — same M-15 2-col pattern as SourceShowV2. */}
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
        <FieldCell label="Mode">{run.mode}</FieldCell>
        <FieldCell label="Status">{run.status}</FieldCell>
        <FieldCell label="Captured resources">
          <span className="tabular-nums">{run.captured_resources_count}</span>
        </FieldCell>
        <FieldCell label="Artifacts">
          <span className="tabular-nums">{run.artifacts_count}</span>
        </FieldCell>
        <FieldCell label="Failure reason">
          {run.failure_reason ?? <span className="text-[rgba(29,41,61,0.4)]">—</span>}
        </FieldCell>
        <FieldCell label="Started">
          {run.started_at ? (
            formatSwissDateTime(run.started_at)
          ) : (
            <span className="text-[rgba(29,41,61,0.4)]">—</span>
          )}
        </FieldCell>
        <FieldCell label="Completed">
          {run.completed_at ? (
            formatSwissDateTime(run.completed_at)
          ) : (
            <span className="text-[rgba(29,41,61,0.4)]">—</span>
          )}
        </FieldCell>
        <FieldCell label="Duration">{duration}</FieldCell>
        <FieldCell label="Created">{formatSwissDateTime(run.created_at)}</FieldCell>
        <FieldCell label="Updated">{formatSwissDateTime(run.updated_at)}</FieldCell>
      </DetailGrid>

      {/* Lifecycle stack — pipeline health banner + 5 collapsed accordion sections. */}
      <RecordContextProvider value={run}>
        <RunDetailSectionsV2 />
      </RecordContextProvider>

      {/* UX-12.2: softened footnote — remaining deferred items only. */}
      <aside className="rounded-[10px] border border-dashed border-[rgba(29,41,61,0.1)] px-3 py-2.5 text-[11px] text-[rgba(29,41,61,0.55)] space-y-1">
        <p className="font-semibold text-[rgba(29,41,61,0.7)] text-[11px] uppercase tracking-[0.06em]">
          Deferred in this spike
        </p>
        <p>
          The legal-search handoff card (stateful URL-param read) and the run action stack (cancel
          mutation) are intentionally absent — open{" "}
          <code className="font-mono">/runs/{run.run_id}/show</code> for the complete MUI view.
        </p>
      </aside>
    </div>
  );
}

function DecisionCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[10px] border border-[rgba(29,41,61,0.08)] bg-white/80 p-3 space-y-0.5">
      <span className="block text-[11px] font-semibold uppercase tracking-[0.08em] text-[rgba(29,41,61,0.6)] leading-[1.2]">
        {label}
      </span>
      <p className="text-[13px] text-[rgba(29,41,61,0.8)] leading-snug">{value}</p>
    </div>
  );
}
