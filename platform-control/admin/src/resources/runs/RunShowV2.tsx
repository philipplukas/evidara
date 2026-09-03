/**
 * `RunShowV2` — v2 preview of the run detail page. Largest single admin
 * page (v1's `RunShow.tsx` is 433 LoC before `RunDetailSections`). This
 * port covers header + metric band + decision-support (primary + 3) + 13-field
 * metadata grid + failure alert, then delegates the lifecycle stack to
 * `<RunDetailSectionsV2>` (ADR-0026 P3 — pipeline health + 5 accordion
 * sections). All primitives come from `src/ui/primitives/`.
 *
 * The operator-action stack (`RunActionStack`, cancel + promote) and the
 * legal-search `RunHandoffCard` reuse the now-Tailwind action components; the
 * handoff card reads the stateful URL-param context via `readLegalSearchHandoff`.
 *
 * Pure helpers (`buildRunDecisionSupport`, `describeRunNextStep`,
 * `buildRunHandoffGuidance`) are imported from v1's `./RunShow.tsx` rather
 * than forked.
 */
"use client";

import { RecordContextProvider, useShowController } from "ra-core";
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { runModeLabel } from "../../domain/runMode";
import type { RunRecord } from "../../lib/admin/dataProvider";
import { type LegalSearchHandoff, readLegalSearchHandoff } from "../../lib/admin/navigationContext";
import { formatSwissDateTime } from "../../lib/format/date";
import { DetailGrid, FieldCell, Panel, Pill } from "../../ui/primitives";
import { runModeToLevel, runRecordStatusToLevel } from "../shared/statusLevels";
import { PrimaryDecisionCell } from "./PrimaryDecisionCell";
import { RunActionStack } from "./RunActions";
import RunDetailSectionsV2 from "./RunDetailSectionsV2";
import {
  RunAcceptanceEvidencePanel,
  RunCaptureLedgerPanel,
  RunRefusalBanner,
  RunStallPanel,
} from "./RunEvidencePanels";
import {
  buildRunDecisionSupport,
  buildRunHandoffGuidance,
  describeRunReplay,
  describeRunScope,
} from "./RunShow";
import { useRunPipelineHealth } from "./useRunPipelineHealth";

export function formatDuration(run: RunRecord): string {
  if (!run.started_at || !run.completed_at) return "—";
  const ms = new Date(run.completed_at).getTime() - new Date(run.started_at).getTime();
  // See the sibling guard in `Dashboard.tsx`: a run whose `completed_at`
  // precedes its `started_at` has no duration we can state. Rendering the raw
  // difference produced "Duration -1ms" on the failed ZH repro run.
  if (!Number.isFinite(ms) || ms < 0) return "—";
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.floor(ms / 60000)}m ${Math.round((ms % 60000) / 1000)}s`;
}

function describeRunNextStep(run: RunRecord): string {
  // A refusal is not a failure and must not be triaged as one: nothing was
  // dispatched, so there is no blocked stage to pinpoint (ADR-0035, #634).
  if (run.refused) {
    return "This run was refused before dispatch. Read the refusal banner above; the remedy is a key on the blueprint template, not the pipeline sections.";
  }
  if (run.status === "failed") {
    return "Open the pipeline sections below and use the failure reason to pinpoint the blocked stage.";
  }
  if (run.status === "running") {
    return "The run is active. Watch the pipeline health and stage sections for the next operator cue.";
  }
  if (run.status === "pending") {
    // "Wait for the first stage update" was one sentence for six causes, and the
    // most common one — no worker picked the run up — is not something waiting
    // fixes. The named cause is in the stall panel below.
    return "The run is queued and nothing has dispatched it yet. See the named cause below rather than waiting on it.";
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
  // One fetch of pipeline health for the whole page: the stall diagnosis and the
  // stage list must not derive from two snapshots that can disagree.
  const pipelineHealth = useRunPipelineHealth(run?.run_id);

  if (controller.isPending) {
    return (
      <div className="px-4 py-10 text-center text-[var(--foreground-subtle)]">Loading run…</div>
    );
  }
  if (controller.error || !run) {
    return (
      <div className="px-4 py-10 text-center text-[var(--status-critical)]">
        Failed to load run.
      </div>
    );
  }

  const decision = buildRunDecisionSupport(run);
  const duration = formatDuration(run);
  const scope = describeRunScope(run);
  const replay = describeRunReplay(run);

  return (
    <div className="px-4 py-6 sm:px-6 sm:py-8 max-w-[var(--container-max)] mx-auto space-y-6">
      <RunHandoffCard run={run} />

      {/* Leads the page: a refused run was never dispatched, and every other
          panel below reads differently once that is known. */}
      <RunRefusalBanner run={run} />

      {/* Header — parity with v1 `RunPageContextBar`, incl. the action stack. */}
      <header className="space-y-3">
        <p className="text-[11px] uppercase tracking-[0.16em] font-semibold text-[var(--foreground-subtle)]">
          Run detail
        </p>
        <h1 className="font-[family:var(--font-admin-serif)] text-[28px] font-semibold text-[var(--foreground)] leading-tight">
          Run <span className="font-mono text-[22px]">{run.run_id}</span>
        </h1>
        <div className="text-[13px] text-[var(--foreground-muted)] font-mono">
          {run.source_id} · {run.source_version_id}
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <Pill level={runRecordStatusToLevel(run.status)}>{STATUS_LABEL[run.status]}</Pill>
          <Pill variant="tag" level={runModeToLevel(run.mode)}>
            {runModeLabel(run.mode)}
          </Pill>
          {run.refused ? <Pill level="degraded">Refused</Pill> : null}
          {run.replay ? <Pill variant="meta">{`Replay · ${run.replay.mode}`}</Pill> : null}
          {/*
           * `scope` may genuinely be absent here even though `RunResponse`
           * declares it: react-admin seeds `useShowController` from the list
           * cache, whose rows are `RunListItemResponse` — which carries neither
           * `scope` nor `replay`. So this renders over the list row for one frame
           * before the `getOne` lands, and `run.scope.kind` threw on it.
           */}
          {scope.known ? <Pill variant="meta">{`Scope ${scope.value}`}</Pill> : null}
          <Pill variant="meta">{`Version ${run.source_version_id}`}</Pill>
        </div>
        <RecordContextProvider value={run}>
          <RunActionStack />
        </RecordContextProvider>
      </header>

      {/* Overview band — metric chips + next-step narrative. */}
      <section className="rounded-[18px] border border-[var(--border-faint)] bg-gradient-to-b from-[var(--brand-wash-4)] to-[var(--admin-panel-bg)] p-5 sm:p-6 shadow-[var(--shadow-card)] backdrop-blur-[12px] space-y-4">
        <div className="flex flex-wrap items-center gap-1.5">
          <Pill variant="meta">{`Captured ${run.captured_resources_count}`}</Pill>
          <Pill variant="meta">{`Artifacts ${run.artifacts_count}`}</Pill>
          <Pill variant="meta">{`Duration ${duration}`}</Pill>
        </div>
        <p className="text-[14px] text-[var(--foreground-muted)]">{describeRunNextStep(run)}</p>

        {/* Decision support — primary cue on top (full-width), three subordinate cues inline below on md+, all stacked on mobile. */}
        <div className="rounded-[14px] border border-[var(--border-faint)] bg-[var(--brand-wash-3)] p-4 space-y-3">
          <div>
            <h2 className="text-[14px] font-semibold text-[var(--foreground)]">Decision support</h2>
            <p className="text-[12px] text-[var(--foreground-subtle)]">
              The primary cue leads with why this run matters; the three subordinate cues add
              operational context.
            </p>
          </div>
          <div className="space-y-3">
            <PrimaryDecisionCell label="Why this matters" value={decision.whyItMatters} />
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <DecisionCell label="What is blocked" value={decision.whatIsBlocked} />
              <DecisionCell label="What changed recently" value={decision.whatChangedRecently} />
              <DecisionCell label="If you do nothing" value={decision.whatHappensIfIgnored} />
            </div>
          </div>
        </div>

        {run.failure_reason ? (
          <div
            role="alert"
            className={`rounded-[12px] border p-3 ${
              run.status === "failed"
                ? "border-[var(--status-critical)]/40 bg-[var(--status-critical-subtle)] text-[var(--status-critical)]"
                : "border-[var(--status-degraded)]/40 bg-[var(--status-degraded-subtle)] text-[var(--status-degraded)]"
            }`}
          >
            <p className="text-[13px] font-semibold">Failure reason</p>
            <p className="text-[13px] mt-0.5 text-[var(--foreground-muted)]">
              {run.failure_reason}
            </p>
          </div>
        ) : null}
      </section>

      {/* Metadata grid — same M-15 2-col pattern as SourceShow. */}
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
        {/*
         * Already on the wire and dropped by this grid until now: `refused`
         * (ADR-0035), and `scope`/`replay`, without which a replay run is
         * indistinguishable from a fresh one.
         */}
        <FieldCell label="Refused by the two-key lock">{run.refused ? "yes" : "no"}</FieldCell>
        <FieldCell label="Scope">
          <span
            className={scope.known ? "font-mono text-[13px]" : "text-[var(--foreground-faint)]"}
          >
            {scope.value}
          </span>
        </FieldCell>
        <FieldCell label="Replay">
          {/*
           * Three states, and "not a replay" is a claim: it must not be printed
           * off a list-cache record that never carried the field. See
           * `describeRunReplay`.
           */}
          <span
            className={
              replay.known && run.replay
                ? "font-mono text-[13px]"
                : "text-[var(--foreground-faint)]"
            }
          >
            {replay.value}
          </span>
        </FieldCell>
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
        <FieldCell label="Duration">{duration}</FieldCell>
        <FieldCell label="Created">{formatSwissDateTime(run.created_at)}</FieldCell>
        <FieldCell label="Updated">{formatSwissDateTime(run.updated_at)}</FieldCell>
      </DetailGrid>

      {/*
       * M15 read surfaces. Ordered by the question an operator arrives with:
       * why did nothing happen → does this justify the flip → what did it
       * actually capture, publish and refuse.
       */}
      <RunStallPanel
        run={run}
        health={pipelineHealth.health}
        healthIsPending={pipelineHealth.isPending}
        healthError={pipelineHealth.error}
      />
      <RunAcceptanceEvidencePanel run={run} />
      <RunCaptureLedgerPanel run={run} />

      {/* Lifecycle stack — pipeline health banner + 5 collapsed accordion sections. */}
      <RecordContextProvider value={run}>
        <RunDetailSectionsV2
          health={pipelineHealth.health}
          healthIsPending={pipelineHealth.isPending}
          healthError={pipelineHealth.error}
        />
      </RecordContextProvider>
    </div>
  );
}

function DecisionCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[10px] border border-[var(--border-faint)] bg-[var(--surface-panel)]/80 p-3 space-y-0.5">
      <span className="block text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--foreground-subtle)] leading-[1.2]">
        {label}
      </span>
      <p className="text-[13px] text-[var(--foreground-muted)] leading-snug">{value}</p>
    </div>
  );
}

// Legal-search handoff banner — reads the URL-param context once on mount so
// operators who arrive from a search result get "why you are here / what to
// check next" guidance. Renders nothing outside the handoff flow.
function RunHandoffCard({ run }: { run: RunRecord }) {
  const [handoff, setHandoff] = useState<LegalSearchHandoff | null>(null);

  useEffect(() => {
    setHandoff(readLegalSearchHandoff());
  }, []);

  if (!handoff) {
    return null;
  }

  const guidance = buildRunHandoffGuidance(run, handoff);
  if (!guidance) {
    return null;
  }

  return (
    <Panel className="p-4 space-y-3">
      <div>
        <h2 className="text-[14px] font-semibold text-[var(--foreground)]">Legal search handoff</h2>
        <p className="text-[12px] text-[var(--foreground-subtle)]">
          Why you are here and what to check next before acting on this run.
        </p>
      </div>
      <p className="text-[13px] text-[var(--foreground-muted)]">{guidance.whyYouAreHere}</p>
      <div className="flex flex-wrap items-center gap-1.5">
        {handoff.query ? <Pill variant="meta">{handoff.query}</Pill> : null}
        {handoff.scopeLabel ? <Pill variant="meta">{handoff.scopeLabel}</Pill> : null}
        {handoff.selectedId ? (
          <Pill variant="meta">{`Selected item: ${handoff.selectedId}`}</Pill>
        ) : null}
      </div>
      <p className="text-[13px] text-[var(--foreground-muted)]">{guidance.whatToCheckNext}</p>
    </Panel>
  );
}
