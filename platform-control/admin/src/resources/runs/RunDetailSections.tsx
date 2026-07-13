/**
 * `RunDetailSections` — Tailwind + `ra-core` run lifecycle detail stack.
 *
 * Pipeline Health renders as an expanded banner at the top. The five data
 * stages below — Provider Jobs, Captured Resources, Raw Artifacts, DI
 * Processing Status, Document Lifecycle — render as collapsed accordion items;
 * each binds a `useGetList` with the `run_id` filter and draws rows via the
 * `DataTable` primitive.
 *
 * Reuses pure helpers (`buildPipelineDecisionSupport`, `overallSummaryByStatus`,
 * `stageNextAction`, `stageActionTarget`). Renders the operator checklist
 * (`deriveOperatorChecklist`), preview summary, section navigation strip, and
 * operator-journey telemetry.
 */
"use client";

import { type Identifier, useGetList, useRecordContext } from "ra-core";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { publicConfig } from "../../config/publicConfig";
import type {
  CapturedResourceRecord,
  DocumentLifecycleRecord,
  ProcessingStatusRecord,
  ProviderJobRecord,
  RawArtifactRecord,
  RunPipelineHealth,
  RunPreviewSummary,
  RunRecord,
} from "../../lib/admin/dataProvider";
import { controlPlaneActions } from "../../lib/admin/dataProvider";
import { emitOperatorJourneyEvent } from "../../lib/admin/operatorJourneyTelemetry";
import { formatSwissDateTime } from "../../lib/format/date";
import {
  AccordionContent,
  AccordionItem,
  AccordionRoot,
  AccordionTrigger,
  DataTable,
  type DataTableColumn,
  Pill,
  type PillLevel,
} from "../../ui/primitives";
import { pipelineHealthToLevel } from "../shared/statusLevels";
import {
  type ChecklistItem,
  type ChecklistState,
  deriveOperatorChecklist,
} from "./operatorChecklist";
import {
  buildPipelineDecisionSupport,
  overallSummaryByStatus,
  stageActionTarget,
  stageNextAction,
} from "./pipelineDecisionSupport";

const RUN_READINESS_CONFIRMED_KEY_PREFIX = "evidara_run_readiness_confirmed:";
const RUN_READINESS_BLOCKED_CODES_KEY_PREFIX = "evidara_run_readiness_blocked_codes:";
const RUN_VERIFICATION_OPENED_KEY_PREFIX = "evidara_run_verification_opened:";

const EVIDENCE_RUNBOOK_PATH =
  "https://github.com/philipplukas/evidara/blob/main/docs/runbooks/interaction-flow-validation.md";

/**
 * Jump targets for the section nav and the pipeline-health remediation CTAs.
 * `sectionId` is the DOM id on the accordion item; `value` is that item's
 * radix accordion key. Jumping opens the item *and* scrolls to it — under the
 * HashRouter a plain `#sectionId` link would be read as a route, so these are
 * buttons, not anchors (see `StageActionTarget`).
 */
const RUN_JUMP_SECTIONS = [
  { sectionId: "provider-jobs-section", value: "provider-jobs", label: "Provider jobs" },
  {
    sectionId: "di-processing-status-section",
    value: "processing-status",
    label: "DI processing",
  },
  {
    sectionId: "document-lifecycle-section",
    value: "document-lifecycle",
    label: "Document lifecycle",
  },
] as const;

/** Shared chrome for the pill-shaped jump/open CTAs. */
const JUMP_BUTTON_CLASS =
  "inline-flex h-8 items-center rounded-full border border-[var(--border)] bg-white/80 px-3 text-[12px] font-semibold text-[var(--brand)] hover:bg-white";

const checklistStateToLevel = (state: ChecklistState): PillLevel => {
  if (state === "ok") return "healthy";
  if (state === "blocked") return "degraded";
  if (state === "in_progress") return "info";
  return "neutral";
};

const LIST_PARAMS = {
  pagination: { page: 1, perPage: 50 },
  sort: { field: "created_at", order: "DESC" as const },
};

const formatDateTime = (value: string | null | undefined): string =>
  formatSwissDateTime(value) || "—";

const formatJson = (value: unknown): string => JSON.stringify(value, null, 2);

const renderInlineValue = (value: string | number | null | undefined) =>
  value ?? <span className="text-[var(--foreground-faint)]">—</span>;

function rowFailureLevel(isFailed: boolean): PillLevel {
  return isFailed ? "critical" : "neutral";
}

function CodeBlock({ value }: { value: unknown }) {
  return (
    <pre className="mt-1 overflow-x-auto rounded-[8px] bg-[var(--brand-wash-6)] px-3 py-2 text-[12px] leading-[1.4] text-[var(--foreground)]">
      {formatJson(value)}
    </pre>
  );
}

// ---------------------------------------------------------------------------
// Pipeline Health (expanded banner, not inside an accordion — matches v1).
// ---------------------------------------------------------------------------

function PipelineHealthBanner({
  run,
  onJumpToSection,
}: {
  run: RunRecord;
  onJumpToSection: (sectionId: string) => void;
}) {
  const [health, setHealth] = useState<RunPipelineHealth | null>(null);
  const [isPending, setIsPending] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [readinessConfirmed, setReadinessConfirmed] = useState(false);
  const [readinessBlockedCodes, setReadinessBlockedCodes] = useState<string[]>([]);
  const [verificationOpened, setVerificationOpened] = useState(false);
  // Hide the verification button entirely when no legal-search URL is
  // configured rather than defaulting to localhost (matches v1 behavior).
  const legalSearchUrl = publicConfig.legalSearchBaseUrlOrUndefined;
  const healthLoadStartedAtRef = useRef<number | null>(null);
  const firstRemediationEventEmittedRef = useRef(false);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    const readiness = window.localStorage.getItem(
      `${RUN_READINESS_CONFIRMED_KEY_PREFIX}${run.run_id}`,
    );
    const blockedRaw = window.localStorage.getItem(
      `${RUN_READINESS_BLOCKED_CODES_KEY_PREFIX}${run.run_id}`,
    );
    const verification = window.localStorage.getItem(
      `${RUN_VERIFICATION_OPENED_KEY_PREFIX}${run.run_id}`,
    );
    setReadinessConfirmed(readiness === "true");
    setVerificationOpened(verification === "true");
    if (blockedRaw) {
      try {
        const parsed = JSON.parse(blockedRaw);
        setReadinessBlockedCodes(Array.isArray(parsed) ? parsed.map(String) : []);
      } catch {
        setReadinessBlockedCodes([]);
      }
    } else {
      setReadinessBlockedCodes([]);
    }
  }, [run.run_id]);

  useEffect(() => {
    let cancelled = false;
    setIsPending(true);
    setError(null);
    healthLoadStartedAtRef.current = Date.now();
    firstRemediationEventEmittedRef.current = false;

    void controlPlaneActions
      .getRunPipelineHealth(run.run_id)
      .then((response) => {
        if (!cancelled) {
          setHealth(response);
          emitOperatorJourneyEvent("pipeline_health_loaded", {
            run_id: run.run_id,
            source_id: run.source_id,
            source_version_id: run.source_version_id,
            mode: run.mode,
            duration_ms:
              healthLoadStartedAtRef.current != null
                ? Date.now() - healthLoadStartedAtRef.current
                : undefined,
          });
        }
      })
      .catch((reason) => {
        if (!cancelled) {
          setError(reason);
          setHealth(null);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsPending(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [run.mode, run.run_id, run.source_id, run.source_version_id]);

  const openVerification = (actionLabel: string) => {
    if (!legalSearchUrl) {
      return;
    }
    if (typeof window !== "undefined") {
      window.localStorage.setItem(`${RUN_VERIFICATION_OPENED_KEY_PREFIX}${run.run_id}`, "true");
    }
    setVerificationOpened(true);
    emitOperatorJourneyEvent("legal_search_verification_opened", {
      run_id: run.run_id,
      source_id: run.source_id,
      source_version_id: run.source_version_id,
      mode: run.mode,
      action_label: actionLabel,
      action_href: legalSearchUrl,
    });
  };

  const decisionSupport = useMemo(
    () => buildPipelineDecisionSupport({ run, health }),
    [health, run],
  );

  const checklistItems = useMemo<ChecklistItem[]>(
    () =>
      deriveOperatorChecklist({
        run,
        health,
        readinessConfirmed,
        readinessBlockedCodes,
        verificationOpened,
      }),
    [run, health, readinessConfirmed, readinessBlockedCodes, verificationOpened],
  );

  const stageSummary = useMemo(
    () =>
      health?.stages.reduce(
        (counts, stage) => {
          counts[stage.status] = (counts[stage.status] ?? 0) + 1;
          return counts;
        },
        { ok: 0, blocked: 0, failed: 0, in_progress: 0, pending: 0 } as Record<string, number>,
      ) ?? null,
    [health],
  );

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
            {overallSummaryByStatus(health.overall_status)}
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
              <PrimaryDecisionCell label="Why this matters" value={decisionSupport.whyItMatters} />
              <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                <DecisionCell label="What is blocked" value={decisionSupport.whatIsBlocked} />
                <DecisionCell
                  label="What changed recently"
                  value={decisionSupport.whatChangedRecently}
                />
                <DecisionCell
                  label="If you do nothing"
                  value={decisionSupport.whatHappensIfIgnored}
                />
              </div>
            </div>
          </div>

          {stageSummary ? (
            <div className="rounded-[12px] border border-[var(--border-faint)] bg-white/70 p-3">
              <h3 className="mb-2 text-[13px] font-semibold text-[var(--foreground)]">
                Stage summary
              </h3>
              <div className="flex flex-wrap items-center gap-1.5">
                <Pill level="healthy">{`Healthy ${stageSummary.ok ?? 0}`}</Pill>
                <Pill level="degraded">
                  {`Needs action ${(stageSummary.blocked ?? 0) + (stageSummary.failed ?? 0)}`}
                </Pill>
                <Pill level="info">{`In progress ${stageSummary.in_progress ?? 0}`}</Pill>
                <Pill level="neutral">{`Pending ${stageSummary.pending ?? 0}`}</Pill>
              </div>
            </div>
          ) : null}

          <div className="rounded-[12px] border border-[var(--border-faint)] bg-white/70 p-3">
            <h3 className="mb-2 text-[13px] font-semibold text-[var(--foreground)]">
              Operator Checklist
            </h3>
            <ul className="space-y-2">
              {checklistItems.map((item) => (
                <li
                  key={item.key}
                  className="flex flex-col gap-1 md:flex-row md:items-start md:gap-2"
                >
                  <Pill level={checklistStateToLevel(item.state)}>
                    {item.state.replaceAll("_", " ")}
                  </Pill>
                  <div className="min-w-0">
                    <p className="text-[13px] text-[var(--foreground)]">{item.label}</p>
                    <p className="text-[11px] text-[var(--foreground-subtle)]">{item.detail}</p>
                  </div>
                </li>
              ))}
            </ul>
            {!verificationOpened && legalSearchUrl ? (
              <a
                href={legalSearchUrl}
                target="_blank"
                rel="noreferrer"
                onClick={() => openVerification("Operator checklist legal-search verification")}
                className="mt-3 inline-flex h-8 items-center rounded-full border border-[var(--border)] bg-white/80 px-3 text-[12px] font-semibold text-[var(--brand)] hover:bg-white"
              >
                Open legal-search verification
              </a>
            ) : null}
          </div>

          <div className="space-y-2">
            {health.stages.map((stage) => {
              const level = pipelineHealthToLevel(stage.status);
              const action = stageActionTarget(stage, {
                legalSearchUrl,
                evidenceRunbookPath: EVIDENCE_RUNBOOK_PATH,
              });
              const isHealthy = stage.status === "ok";
              const emitRemediationClick = () => {
                if (firstRemediationEventEmittedRef.current) return;
                emitOperatorJourneyEvent("remediation_action_clicked", {
                  run_id: run.run_id,
                  source_id: run.source_id,
                  source_version_id: run.source_version_id,
                  mode: run.mode,
                  stage: stage.stage,
                  action_label: action.label,
                  // Keep the historical `#section-id` shape so the telemetry
                  // series stays continuous across this fix.
                  action_href: action.kind === "section" ? `#${action.sectionId}` : action.href,
                });
                firstRemediationEventEmittedRef.current = true;
              };
              return (
                <div
                  key={stage.stage}
                  className="rounded-[12px] border border-[var(--border-faint)] bg-white/70 p-3"
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
                  {!isHealthy ? (
                    <div className="mt-2 flex flex-wrap items-center justify-between gap-2 rounded-[10px] border border-[var(--status-degraded)]/20 bg-[var(--status-degraded-subtle)] p-2.5">
                      <p className="text-[12px] font-semibold text-[var(--foreground)]">
                        Next action: {stageNextAction(stage)}
                      </p>
                      {action.kind === "section" ? (
                        <button
                          type="button"
                          onClick={() => {
                            emitRemediationClick();
                            onJumpToSection(action.sectionId);
                          }}
                          className={JUMP_BUTTON_CLASS}
                        >
                          {action.label}
                        </button>
                      ) : (
                        <a
                          href={action.href}
                          target="_blank"
                          rel="noreferrer"
                          onClick={emitRemediationClick}
                          className={JUMP_BUTTON_CLASS}
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

          <div className="flex flex-wrap items-center gap-2">
            {legalSearchUrl ? (
              <a
                href={legalSearchUrl}
                target="_blank"
                rel="noreferrer"
                onClick={() => openVerification("Pipeline section legal-search verification")}
                className="inline-flex h-8 items-center rounded-full border border-[var(--border)] bg-white/80 px-3 text-[12px] font-semibold text-[var(--brand)] hover:bg-white"
              >
                Open legal-search verification
              </a>
            ) : null}
            <a
              href={EVIDENCE_RUNBOOK_PATH}
              target="_blank"
              rel="noreferrer"
              className="inline-flex h-8 items-center rounded-full px-3 text-[12px] font-semibold text-[var(--brand)] hover:underline"
            >
              Open related evidence runbook
            </a>
          </div>
        </div>
      ) : null}
    </section>
  );
}

function DecisionCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="space-y-0.5 rounded-[10px] border border-[var(--border-faint)] bg-white/80 p-3">
      <span className="block text-[11px] font-semibold uppercase tracking-[0.08em] leading-[1.2] text-[var(--foreground-subtle)]">
        {label}
      </span>
      <p className="text-[13px] leading-snug text-[var(--foreground-muted)]">{value}</p>
    </div>
  );
}

/**
 * `PrimaryDecisionCell` — elevated, full-width variant of `DecisionCell` that
 * leads the pipeline decision-support block (issue #393). Mirrors the sibling
 * in `RunShow.tsx` so the two decision-support surfaces stay visually in sync.
 */
function PrimaryDecisionCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="space-y-1 rounded-[12px] border border-[var(--border)] bg-white p-4 shadow-[var(--shadow-card-hover)]">
      <span className="block text-[15px] font-semibold uppercase tracking-[0.08em] leading-[1.2] text-[var(--foreground-muted)]">
        {label}
      </span>
      <p className="text-[14px] leading-snug text-[var(--foreground)]">{value}</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Generic accordion-wrapped section for the five run sub-resources.
// ---------------------------------------------------------------------------

interface RunSectionProps<TRecord extends { id: Identifier }> {
  value: string;
  sectionId?: string;
  title: string;
  description: string;
  rows: TRecord[] | undefined;
  isPending: boolean;
  error: unknown;
  emptyMessage: string;
  columns: DataTableColumn<TRecord>[];
  getRowId: (record: TRecord) => string;
}

function RunAccordionSection<TRecord extends { id: Identifier }>({
  value,
  sectionId,
  title,
  description,
  rows,
  isPending,
  error,
  emptyMessage,
  columns,
  getRowId,
}: RunSectionProps<TRecord>) {
  const count = rows?.length ?? 0;
  return (
    <AccordionItem value={value} id={sectionId}>
      <AccordionTrigger>
        <span className="text-[15px] font-semibold text-[var(--foreground)]">{title}</span>
        {isPending ? (
          <Pill variant="meta">Loading…</Pill>
        ) : error ? (
          <Pill level="critical">Error</Pill>
        ) : (
          <Pill variant="meta">{`${count} ${count === 1 ? "row" : "rows"}`}</Pill>
        )}
      </AccordionTrigger>
      <AccordionContent>
        <div className="space-y-3">
          <p className="text-[13px] text-[var(--foreground-subtle)]">{description}</p>

          {isPending ? (
            <p className="text-[13px] text-[var(--foreground-subtle)]">
              Loading {title.toLowerCase()}…
            </p>
          ) : error ? (
            <div
              role="alert"
              className="rounded-[12px] border border-[var(--status-critical)]/40 bg-[var(--status-critical-subtle)] p-3 text-[13px] text-[var(--status-critical)]"
            >
              {error instanceof Error ? error.message : `Unable to load ${title.toLowerCase()}.`}
            </div>
          ) : count === 0 ? (
            <p className="text-[13px] text-[var(--foreground-subtle)]">{emptyMessage}</p>
          ) : (
            <DataTable<TRecord>
              records={rows}
              columns={columns}
              getRowId={getRowId}
              isLoading={false}
            />
          )}
        </div>
      </AccordionContent>
    </AccordionItem>
  );
}

// ---------------------------------------------------------------------------
// Column definitions — 1:1 with v1 (labels, order, renderers).
// ---------------------------------------------------------------------------

const providerJobColumns: DataTableColumn<ProviderJobRecord>[] = [
  { key: "provider", header: "Provider", render: (job) => job.provider },
  {
    key: "external_job_id",
    header: "External job",
    render: (job) => renderInlineValue(job.external_job_id),
  },
  {
    key: "status",
    header: "Status",
    render: (job) => <Pill level={rowFailureLevel(job.status === "failed")}>{job.status}</Pill>,
  },
  {
    key: "last_event_type",
    header: "Last event",
    render: (job) => renderInlineValue(job.last_event_type),
  },
  { key: "updated_at", header: "Updated", render: (job) => formatDateTime(job.updated_at) },
  {
    key: "payloads",
    header: "Payloads",
    render: (job) => (
      <div>
        <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--foreground-subtle)]">
          Request
        </p>
        <CodeBlock value={job.request_payload} />
        <p className="mt-2 text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--foreground-subtle)]">
          Response
        </p>
        <CodeBlock value={job.response_payload} />
      </div>
    ),
  },
];

const capturedResourceColumns: DataTableColumn<CapturedResourceRecord>[] = [
  {
    key: "resource",
    header: "Resource",
    render: (resource) => (
      <div>
        <p className="text-[13px] font-semibold text-[var(--foreground)]">
          {resource.title ?? "Untitled resource"}
        </p>
        <a
          href={resource.final_url}
          target="_blank"
          rel="noreferrer"
          className="text-[12px] text-[var(--brand)] underline-offset-2 hover:underline"
        >
          {resource.final_url}
        </a>
      </div>
    ),
  },
  { key: "content_type", header: "Type", render: (resource) => resource.content_type },
  {
    key: "http_status",
    header: "HTTP",
    render: (resource) => renderInlineValue(resource.http_status),
  },
  {
    key: "discovery_depth",
    header: "Depth",
    render: (resource) => renderInlineValue(resource.discovery_depth),
  },
  {
    key: "checksum",
    header: "Checksum",
    render: (resource) => renderInlineValue(resource.checksum),
  },
  {
    key: "fetched_at",
    header: "Fetched",
    render: (resource) => formatDateTime(resource.fetched_at),
  },
];

const rawArtifactColumns: DataTableColumn<RawArtifactRecord>[] = [
  { key: "artifact_id", header: "Artifact", render: (artifact) => artifact.artifact_id },
  { key: "content_type", header: "Type", render: (artifact) => artifact.content_type },
  { key: "storage_path", header: "Storage path", render: (artifact) => artifact.storage_path },
  {
    key: "created_at",
    header: "Created",
    render: (artifact) => formatDateTime(artifact.created_at),
  },
  {
    key: "metadata",
    header: "Metadata",
    render: (artifact) => <CodeBlock value={artifact.artifact_metadata} />,
  },
];

const processingStatusColumns: DataTableColumn<ProcessingStatusRecord>[] = [
  {
    key: "status",
    header: "Status",
    render: (update) => (
      <Pill level={rowFailureLevel(update.status === "failed")}>{update.status}</Pill>
    ),
  },
  {
    key: "document",
    header: "Document",
    render: (update) =>
      update.document_id ? `${update.document_id} rev ${update.document_revision ?? "—"}` : "—",
  },
  {
    key: "manifest",
    header: "Manifest",
    render: (update) => update.processing_manifest_id,
  },
  {
    key: "occurred_at",
    header: "Occurred",
    render: (update) => formatDateTime(update.occurred_at),
  },
  {
    key: "error_summary",
    header: "Error",
    render: (update) => renderInlineValue(update.error_summary),
  },
];

const documentLifecycleColumns: DataTableColumn<DocumentLifecycleRecord>[] = [
  { key: "event_type", header: "Event", render: (event) => event.event_type },
  {
    key: "document",
    header: "Document",
    render: (event) => `${event.document_id} rev ${event.document_revision}`,
  },
  {
    key: "lifecycle_status",
    header: "Lifecycle",
    render: (event) => renderInlineValue(event.lifecycle_status),
  },
  {
    key: "reason_code",
    header: "Reason",
    render: (event) => renderInlineValue(event.reason_code),
  },
  {
    key: "occurred_at",
    header: "Occurred",
    render: (event) => formatDateTime(event.occurred_at),
  },
];

// ---------------------------------------------------------------------------
// Section navigation strip — jump anchors into the stage that needs attention.
// ---------------------------------------------------------------------------

function RunSectionNav({ onJumpToSection }: { onJumpToSection: (sectionId: string) => void }) {
  return (
    <section className="space-y-3 rounded-[14px] border border-[var(--border-faint)] bg-[var(--admin-panel-bg)] p-4">
      <div className="space-y-1">
        <h2 className="text-[15px] font-semibold text-[var(--foreground)]">Lifecycle sections</h2>
        <p className="text-[13px] text-[var(--foreground-subtle)]">
          Jump straight to the stage that needs attention.
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {RUN_JUMP_SECTIONS.map((section) => (
          <button
            key={section.sectionId}
            type="button"
            onClick={() => onJumpToSection(section.sectionId)}
            className={JUMP_BUTTON_CLASS}
          >
            {section.label}
          </button>
        ))}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Preview Summary (preview-mode runs only) — heuristic signals before promotion.
// ---------------------------------------------------------------------------

interface PreviewPageRow {
  id: Identifier;
  title: string | null;
  final_url: string;
  content_type: string;
  reason: string;
}

const previewPageColumns: DataTableColumn<PreviewPageRow>[] = [
  { key: "title", header: "Title", render: (page) => page.title ?? "Untitled" },
  {
    key: "final_url",
    header: "URL",
    render: (page) => (
      <a
        href={page.final_url}
        target="_blank"
        rel="noreferrer"
        className="text-[12px] text-[var(--brand)] underline-offset-2 hover:underline"
      >
        {page.final_url}
      </a>
    ),
  },
  { key: "content_type", header: "Type", render: (page) => page.content_type },
  { key: "reason", header: "Reason", render: (page) => page.reason },
];

function PreviewPageTable({
  title,
  description,
  rows,
  emptyMessage,
}: {
  title: string;
  description: string;
  rows: PreviewPageRow[];
  emptyMessage: string;
}) {
  return (
    <div className="space-y-2">
      <div>
        <h4 className="text-[14px] font-semibold text-[var(--foreground)]">{title}</h4>
        <p className="text-[12px] text-[var(--foreground-subtle)]">{description}</p>
      </div>
      {rows.length === 0 ? (
        <p className="text-[13px] text-[var(--foreground-subtle)]">{emptyMessage}</p>
      ) : (
        <DataTable<PreviewPageRow>
          records={rows}
          columns={previewPageColumns}
          getRowId={(page) => String(page.id)}
          isLoading={false}
        />
      )}
    </div>
  );
}

function PreviewSummarySection({ run }: { run: RunRecord }) {
  const [summary, setSummary] = useState<RunPreviewSummary | null>(null);
  const [isPending, setIsPending] = useState(run.mode === "preview");
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    if (run.mode !== "preview") {
      setSummary(null);
      setError(null);
      setIsPending(false);
      return;
    }

    let cancelled = false;
    setIsPending(true);
    setError(null);

    void controlPlaneActions
      .getRunPreviewSummary(run.run_id)
      .then((response) => {
        if (!cancelled) {
          setSummary(response);
        }
      })
      .catch((reason) => {
        if (!cancelled) {
          setError(reason);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsPending(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [run.mode, run.run_id]);

  if (run.mode !== "preview") {
    return null;
  }

  return (
    <section className="space-y-4 rounded-[18px] border border-[var(--border-faint)] bg-[var(--admin-panel-bg)] p-5 shadow-[var(--shadow-card)] backdrop-blur-[12px] sm:p-6">
      <header className="space-y-1">
        <h2 className="text-[16px] font-semibold text-[var(--foreground)]">Preview Summary</h2>
        <p className="text-[13px] text-[var(--foreground-subtle)]">
          Review heuristic signals before promoting this source version into production.
        </p>
      </header>

      {isPending ? (
        <p className="text-[13px] text-[var(--foreground-subtle)]">Loading preview summary…</p>
      ) : null}

      {!isPending && error ? (
        <div
          role="alert"
          className="rounded-[12px] border border-[var(--status-critical)]/40 bg-[var(--status-critical-subtle)] p-3 text-[13px] text-[var(--status-critical)]"
        >
          {error instanceof Error ? error.message : "Unable to load preview summary."}
        </div>
      ) : null}

      {!isPending && !error && summary ? (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-1.5">
            <Pill variant="meta">{`URLs ${summary.captured_url_count}`}</Pill>
            <Pill variant="meta">{`Artifacts ${summary.artifacts_count}`}</Pill>
            <Pill variant="meta">{`Captured ${summary.captured_resources_count}`}</Pill>
            <Pill variant="meta">{`PDFs ${summary.pdf_count}`}</Pill>
            <Pill variant="meta">{`Decision pages ${summary.likely_decision_page_count}`}</Pill>
            <Pill variant="meta">{`Boilerplate ${summary.likely_boilerplate_page_count}`}</Pill>
            <Pill variant="meta">{`Duplicates ${summary.likely_duplicate_page_count}`}</Pill>
          </div>

          <div className="space-y-2">
            <h3 className="text-[14px] font-semibold text-[var(--foreground)]">Drift Checks</h3>
            <div className="flex flex-wrap items-center gap-1.5">
              {summary.drift_checks.map((check) => (
                <Pill key={check.name} level={check.status === "warn" ? "degraded" : "neutral"}>
                  {`${check.name}: ${check.detail}`}
                </Pill>
              ))}
            </div>
          </div>

          <div className="space-y-2">
            <div>
              <h4 className="text-[14px] font-semibold text-[var(--foreground)]">
                Content Type Breakdown
              </h4>
              <p className="text-[12px] text-[var(--foreground-subtle)]">
                Observed content types for captured resources.
              </p>
            </div>
            {summary.content_type_breakdown.length === 0 ? (
              <p className="text-[13px] text-[var(--foreground-subtle)]">
                No content types were observed.
              </p>
            ) : (
              <DataTable<{ id: Identifier; content_type: string; count: number }>
                records={summary.content_type_breakdown.map((entry, index) => ({
                  id: `${entry.content_type}-${index}`,
                  content_type: entry.content_type,
                  count: entry.count,
                }))}
                columns={[
                  {
                    key: "content_type",
                    header: "Content type",
                    render: (entry) => entry.content_type,
                  },
                  { key: "count", header: "Count", render: (entry) => entry.count },
                ]}
                getRowId={(entry) => String(entry.id)}
                isLoading={false}
              />
            )}
          </div>

          <PreviewPageTable
            title="Likely Decision Pages"
            description="Pages heuristically identified as candidate decisions."
            emptyMessage="No likely decision pages were identified."
            rows={summary.likely_decision_pages.map((page) => ({
              id: page.captured_resource_id,
              title: page.title,
              final_url: page.final_url,
              content_type: page.content_type,
              reason: page.reason,
            }))}
          />

          <PreviewPageTable
            title="Likely Boilerplate Pages"
            description="Pages heuristically identified as boilerplate."
            emptyMessage="No likely boilerplate pages were identified."
            rows={summary.likely_boilerplate_pages.map((page) => ({
              id: page.captured_resource_id,
              title: page.title,
              final_url: page.final_url,
              content_type: page.content_type,
              reason: page.reason,
            }))}
          />

          <PreviewPageTable
            title="Likely Duplicate Pages"
            description="Pages that look duplicated based on checksum matching."
            emptyMessage="No likely duplicate pages were identified."
            rows={summary.likely_duplicate_pages.map((page) => ({
              id: page.captured_resource_id,
              title: page.title,
              final_url: page.final_url,
              content_type: page.content_type,
              reason: page.reason,
            }))}
          />
        </div>
      ) : null}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Root — binds the five `useGetList` fetches and renders the accordion stack.
// ---------------------------------------------------------------------------

export default function RunDetailSections() {
  const run = useRecordContext<RunRecord>();
  // Sections start collapsed; a jump expands its target so the operator lands
  // on the rows, not on a closed header.
  const [openSections, setOpenSections] = useState<string[]>([]);

  const jumpToSection = useCallback((sectionId: string) => {
    const section = RUN_JUMP_SECTIONS.find((candidate) => candidate.sectionId === sectionId);
    if (!section) return;
    setOpenSections((previous) =>
      previous.includes(section.value) ? previous : [...previous, section.value],
    );
    // Scroll after the expand has committed, so the item is at its open
    // height and lands in view rather than under the fold.
    requestAnimationFrame(() => {
      document.getElementById(sectionId)?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }, []);

  const providerJobs = useGetList<ProviderJobRecord>(
    "run-provider-jobs",
    { ...LIST_PARAMS, filter: { run_id: run?.run_id } },
    { enabled: Boolean(run?.run_id) },
  );
  const capturedResources = useGetList<CapturedResourceRecord>(
    "run-captured-resources",
    { ...LIST_PARAMS, filter: { run_id: run?.run_id } },
    { enabled: Boolean(run?.run_id) },
  );
  const rawArtifacts = useGetList<RawArtifactRecord>(
    "run-raw-artifacts",
    { ...LIST_PARAMS, filter: { run_id: run?.run_id } },
    { enabled: Boolean(run?.run_id) },
  );
  const processingStatus = useGetList<ProcessingStatusRecord>(
    "run-processing-status",
    { ...LIST_PARAMS, filter: { run_id: run?.run_id } },
    { enabled: Boolean(run?.run_id) },
  );
  const documentLifecycle = useGetList<DocumentLifecycleRecord>(
    "run-document-lifecycle",
    { ...LIST_PARAMS, filter: { run_id: run?.run_id } },
    { enabled: Boolean(run?.run_id) },
  );

  if (!run) {
    return null;
  }

  return (
    <div className="space-y-4">
      <RunSectionNav onJumpToSection={jumpToSection} />
      <PipelineHealthBanner run={run} onJumpToSection={jumpToSection} />
      <PreviewSummarySection run={run} />

      <AccordionRoot
        type="multiple"
        value={openSections}
        onValueChange={setOpenSections}
        className="flex flex-col gap-3"
      >
        <RunAccordionSection<ProviderJobRecord>
          value="provider-jobs"
          sectionId="provider-jobs-section"
          title="Provider Jobs"
          description="Provider-level crawl job state and webhook progression for this run."
          rows={providerJobs.data}
          isPending={providerJobs.isPending}
          error={providerJobs.error}
          emptyMessage="No provider jobs were recorded for this run."
          columns={providerJobColumns}
          getRowId={(job) => job.provider_job_id}
        />
        <RunAccordionSection<CapturedResourceRecord>
          value="captured-resources"
          title="Captured Resources"
          description="Pages and files captured from the source during this run."
          rows={capturedResources.data}
          isPending={capturedResources.isPending}
          error={capturedResources.error}
          emptyMessage="No captured resources were recorded for this run."
          columns={capturedResourceColumns}
          getRowId={(resource) => resource.captured_resource_id}
        />
        <RunAccordionSection<RawArtifactRecord>
          value="raw-artifacts"
          title="Raw Artifacts"
          description="Stored raw artifacts published by the acquisition provider for this run."
          rows={rawArtifacts.data}
          isPending={rawArtifacts.isPending}
          error={rawArtifacts.error}
          emptyMessage="No raw artifacts were recorded for this run."
          columns={rawArtifactColumns}
          getRowId={(artifact) => artifact.artifact_id}
        />
        <RunAccordionSection<ProcessingStatusRecord>
          value="processing-status"
          sectionId="di-processing-status-section"
          title="DI Processing Status"
          description="Document-intelligence processing updates correlated to this run."
          rows={processingStatus.data}
          isPending={processingStatus.isPending}
          error={processingStatus.error}
          emptyMessage="No DI processing status updates have been received for this run."
          columns={processingStatusColumns}
          getRowId={(update) => update.event_id}
        />
        <RunAccordionSection<DocumentLifecycleRecord>
          value="document-lifecycle"
          sectionId="document-lifecycle-section"
          title="Document Lifecycle"
          description="Published or withdrawn document lifecycle events emitted by document-intelligence."
          rows={documentLifecycle.data}
          isPending={documentLifecycle.isPending}
          error={documentLifecycle.error}
          emptyMessage="No document lifecycle events have been received for this run."
          columns={documentLifecycleColumns}
          getRowId={(event) => event.event_id}
        />
      </AccordionRoot>
    </div>
  );
}
