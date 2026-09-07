/**
 * Pipeline Health — the expanded banner above the stage accordions.
 *
 * `PrimaryDecisionCell` is imported rather than redefined. Before this split,
 * `RunDetailSectionsV2.tsx` carried its own copy while `RunShowV2.tsx` imported
 * the extracted one — two definitions of the same component, semantically
 * identical and differing only in biome class ordering, which a 978-line file
 * made invisible.
 */
"use client";

import { publicConfig } from "../../config/publicConfig";
import type { RunPipelineHealth } from "../../lib/admin/dataProvider";
import { Pill } from "../../ui/primitives";
import { pipelineHealthToLevel } from "../shared/statusLevels";
import { PrimaryDecisionCell } from "./PrimaryDecisionCell";
import { stageActionTarget } from "./run-decision-support";
import { formatDateTime } from "./runCells";

export function PipelineHealthBanner({
  health,
  isPending,
  error,
  onJumpToSection,
}: {
  // The run itself is no longer a prop: the decision support that needed it —
  // "why this run matters", which is mode-dependent — is computed server-side and
  // arrives on `health.decision_support` (#908). Keeping the prop would invite
  // someone to derive from it again.
  //
  // Fetched once by `RunShowV2` via `useRunPipelineHealth` and handed down. This
  // banner used to own the fetch, which was fine while it was the only reader;
  // the stall diagnosis on the overview is a second one, and two fetches of one
  // endpoint can render two different answers about the same run.
  health: RunPipelineHealth | null;
  isPending: boolean;
  error: unknown;
  onJumpToSection: (href: string) => void;
}) {
  // publicConfig, not `process.env` — see SidebarMenu.tsx. `OrUndefined` keeps
  // the existing "hide when unconfigured" behaviour of this call site rather
  // than substituting the localhost default.
  const legalSearchUrl = publicConfig.legalSearchBaseUrlOrUndefined;
  const evidenceRunbookPath =
    "https://github.com/philipplukas/evidara/blob/main/docs/runbooks/interaction-flow-validation.md";

  return (
    <section className="space-y-4 rounded-[18px] border border-[var(--border-faint)] bg-[var(--admin-panel-bg)] p-5 shadow-[var(--shadow-card)] backdrop-blur-[12px] sm:p-6">
      <header className="space-y-1">
        <h2 className="text-[16px] font-semibold text-[var(--foreground)]">Pipeline Health</h2>
        <p className="text-[13px] text-[var(--foreground-subtle)]">
          Expanded by default so the overall signal is visible without a click; drill into the stage
          sections below for row-level detail.
        </p>
      </header>

      {isPending ? (
        <p className="text-[13px] text-[var(--foreground-subtle)]">Loading pipeline health…</p>
      ) : null}

      {!isPending && error ? (
        <div
          role="alert"
          className="rounded-[12px] border border-[var(--status-critical)]/40 bg-[var(--status-critical-subtle)] p-3 text-[13px] text-[var(--status-critical)]"
        >
          {error instanceof Error ? error.message : "Unable to load pipeline health."}
        </div>
      ) : null}

      {!isPending && !error && health ? (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-1.5">
            <Pill level={pipelineHealthToLevel(health.overall_status)}>
              {`Overall ${health.overall_status.replaceAll("_", " ")}`}
            </Pill>
            <Pill variant="meta">{`Run ${health.run_status}`}</Pill>
            <Pill variant="meta">
              {`${health.processing_status_event_count} processing / ${health.document_lifecycle_event_count} lifecycle events`}
            </Pill>
          </div>

          <p className="text-[13px] font-semibold text-[var(--foreground)]">
            {health.decision_support.overall_summary.text}
          </p>

          <div className="rounded-[14px] border border-[var(--border-faint)] bg-[var(--brand-wash-3)] p-4">
            <div className="mb-3">
              <h3 className="text-[14px] font-semibold text-[var(--foreground)]">
                Pipeline decision support
              </h3>
              <p className="text-[12px] text-[var(--foreground-subtle)]">
                The cues below translate the health snapshot into operator decisions.
              </p>
            </div>
            <div className="space-y-3">
              <PrimaryDecisionCell
                label="Why this matters"
                value={health.decision_support.why_it_matters.text}
              />
              <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                <DecisionCell
                  label="What is blocked"
                  value={health.decision_support.what_is_blocked.text}
                />
                <DecisionCell
                  label="What changed recently"
                  value={health.decision_support.what_changed_recently.text}
                />
                <DecisionCell
                  label="If you do nothing"
                  value={health.decision_support.what_happens_if_ignored.text}
                />
              </div>
            </div>
          </div>

          <div className="space-y-2">
            {health.stages.map((stage) => {
              // `not_applicable` arrives from the API now (#908). This component used
              // to re-label it here, which meant every other consumer of
              // pipeline-health kept seeing a dead run's stages as `pending`.
              const nextAction = health.decision_support.next_actions.find(
                (candidate) => candidate.stage === stage.stage,
              );
              const level = pipelineHealthToLevel(stage.status);
              const action = stageActionTarget(stage, {
                legalSearchUrl,
                evidenceRunbookPath,
              });
              const isInPageAnchor = action.href.startsWith("#");
              // The server decides whether a stage needs attention: it answers
              // `none_required` / `stage_will_not_run` when it does not. Re-deriving
              // that from the status here is the second implementation #908 removes.
              const needsAction =
                nextAction !== undefined &&
                nextAction.code !== "none_required" &&
                nextAction.code !== "stage_will_not_run";
              return (
                <div
                  key={stage.stage}
                  className="rounded-[12px] border border-[var(--border-faint)] bg-[var(--surface-panel)]/70 p-3"
                >
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="text-[13px] font-semibold capitalize text-[var(--foreground)]">
                        {stage.stage.replaceAll("_", " ")}
                      </p>
                      <p className="text-[11px] text-[var(--foreground-subtle)]">
                        {formatDateTime(stage.updated_at)}
                      </p>
                    </div>
                    <Pill level={level}>{stage.status.replaceAll("_", " ")}</Pill>
                  </div>
                  <p className="mt-1.5 text-[13px] text-[var(--foreground-muted)]">
                    {stage.detail}
                  </p>
                  {needsAction ? (
                    <div className="mt-2 flex flex-wrap items-center justify-between gap-2 rounded-[10px] border border-[var(--status-degraded)]/20 bg-[var(--status-degraded-subtle)] p-2.5">
                      <p className="text-[12px] font-semibold text-[var(--foreground)]">
                        Next action: {nextAction?.text}
                      </p>
                      {isInPageAnchor ? (
                        // A raw `<a href="#...">` would drive the HashRouter to
                        // a bad route and eject the operator to Not Found; use a
                        // button that reveals + scrolls to the target instead.
                        <button
                          type="button"
                          onClick={() => onJumpToSection(action.href)}
                          className="inline-flex h-8 items-center rounded-full border border-[var(--border)] bg-[var(--surface-panel)]/80 px-3 text-[12px] font-semibold text-[var(--brand)] hover:bg-[var(--surface-panel)]"
                        >
                          {action.label}
                        </button>
                      ) : (
                        <a
                          href={action.href}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex h-8 items-center rounded-full border border-[var(--border)] bg-[var(--surface-panel)]/80 px-3 text-[12px] font-semibold text-[var(--brand)] hover:bg-[var(--surface-panel)]"
                        >
                          {action.label}
                        </a>
                      )}
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
        </div>
      ) : null}
    </section>
  );
}

function DecisionCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="space-y-0.5 rounded-[10px] border border-[var(--border-faint)] bg-[var(--surface-panel)]/80 p-3">
      <span className="block text-[11px] font-semibold uppercase tracking-[0.08em] leading-[1.2] text-[var(--foreground-subtle)]">
        {label}
      </span>
      <p className="text-[13px] leading-snug text-[var(--foreground-muted)]">{value}</p>
    </div>
  );
}
