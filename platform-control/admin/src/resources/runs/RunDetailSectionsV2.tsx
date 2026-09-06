/**
 * `RunDetailSectionsV2` — the run detail sections, Tailwind + `ra-core`.
 *
 * Pipeline Health renders as an expanded banner at the top (matches v1's
 * default-expanded accordion). The five data stages below — Provider Jobs,
 * Captured Resources, Raw Artifacts, DI Processing Status, Document Lifecycle
 * — render as collapsed accordion items; each binds a `useGetList` with the
 * same `run_id` filter v1 used and draws rows via the `DataTable` primitive.
 *
 * Operator cues come from `./run-decision-support` — the framework-free
 * helpers (`buildPipelineDecisionSupport`, `overallSummaryByStatus`,
 * `stageNextAction`, `stageActionTarget`, …) that the retired MUI page used to
 * host (#649).
 *
 * Not carried over from that page: the operator checklist
 * (`deriveOperatorChecklist`, still in `./operatorChecklist`), preview summary,
 * navigation button strip, and telemetry emission.
 */
"use client";

import { type Identifier, useGetList, useRecordContext } from "ra-core";
import { type ReactNode, useCallback, useMemo, useState } from "react";
import { publicConfig } from "../../config/publicConfig";
import type {
  CapturedResourceRecord,
  DocumentLifecycleRecord,
  ProcessingStatusRecord,
  ProviderJobRecord,
  RawArtifactRecord,
  RunPipelineHealth,
  RunRecord,
} from "../../lib/admin/dataProvider";
import { formatSwissDateTime } from "../../lib/format/date";
import {
  AccordionContent,
  AccordionItem,
  AccordionRoot,
  AccordionTrigger,
  DataTable,
  type DataTableColumn,
  InlineAlert,
  Pill,
  type PillLevel,
} from "../../ui/primitives";
import { pipelineHealthToLevel } from "../shared/statusLevels";
import {
  extractArtifactContent,
  remainingPayload,
  summarizeArtifactPayload,
} from "./artifactPayload";
import {
  buildPipelineDecisionSupport,
  overallSummaryByStatus,
  projectPipelineStages,
  scrollToInPageSection,
  sectionIdFromAnchor,
  stageActionTarget,
  stageNeedsAction,
  stageNextAction,
} from "./run-decision-support";
import { buildDocumentSearchHref, buildMinioObjectHref } from "./runDeepLinks";
import { buildRunTimeline, type RunTimelineEntry } from "./runTimeline";
import { StageTimeline } from "./StageTimeline";

/**
 * Maps an in-page anchor id (the `stageActionTarget` targets, shared with v1)
 * to the `AccordionItem` value it should reveal in this v2 layout, so a jump
 * expands the collapsed section before scrolling to it.
 */
const ANCHOR_TO_ACCORDION_VALUE: Record<string, string> = {
  "provider-jobs-section": "provider-jobs",
  "di-processing-status-section": "processing-status",
  "document-lifecycle-section": "document-lifecycle",
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

/**
 * Render `label` as an external link when `href` is non-null, and as the same
 * plain text when it is not.
 *
 * The fallback is the point, not a nicety: the link targets are tailnet-only and
 * some deployments configure none of them, so the unconfigured case must degrade
 * to exactly what this column showed before deep links existed. `runDeepLinks`
 * returns `null` for every unconfigured or unparseable input precisely so this
 * decision is made in one place.
 */
function ExternalValueLink({ href, label }: { href: string | null; label: string }) {
  if (!href) {
    return <span className="font-mono text-[12px]">{label}</span>;
  }
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="font-mono text-[12px] text-[var(--brand)] underline-offset-2 hover:underline"
    >
      {label}
    </a>
  );
}

function CodeBlock({ value }: { value: unknown }) {
  return (
    <pre className="mt-1 overflow-x-auto rounded-[8px] bg-[var(--brand-wash-6)] px-3 py-2 text-[12px] leading-[1.4] text-[var(--foreground)]">
      {formatJson(value)}
    </pre>
  );
}

/**
 * A raw artifact's payload, made readable.
 *
 * Replaces a single `JSON.stringify` dump with: the facts an operator reads
 * first as labelled rows, the document body in a scrollable block, and
 * everything not already shown as JSON underneath.
 *
 * SECURITY: the body is captured third-party web content and is rendered as
 * TEXT — inside `<pre>`, via a React child, never `dangerouslySetInnerHTML`.
 * `rawHtml` and `html` are among the keys this can select, so rendering it as
 * markup would execute arbitrary scraped script in the operator's authenticated
 * admin session. Showing markup as text is the whole point; it is not a
 * rendering limitation to be "fixed" later.
 */
function ArtifactPayloadPanel({ payload }: { payload: unknown }) {
  const [showRaw, setShowRaw] = useState(false);
  const fields = useMemo(() => summarizeArtifactPayload(payload), [payload]);
  const content = useMemo(() => extractArtifactContent(payload), [payload]);
  const rest = useMemo(() => remainingPayload(payload), [payload]);

  // Nothing recognisable — fall back to exactly the old behaviour rather than
  // rendering an empty panel that implies the payload was empty.
  if (fields.length === 0 && !content && !rest) {
    return <CodeBlock value={payload} />;
  }

  return (
    <div className="mt-1 space-y-2">
      {fields.length > 0 ? (
        <dl className="grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1 text-[12px]">
          {fields.map((field) => (
            <div key={field.label} className="contents">
              <dt className="text-[var(--foreground-subtle)]">{field.label}</dt>
              <dd className="break-all font-mono text-[var(--foreground)]">{field.value}</dd>
            </div>
          ))}
        </dl>
      ) : null}

      {content ? (
        <details open>
          <summary className="cursor-pointer text-[12px] font-semibold text-[var(--foreground)]">
            Body{" "}
            <span className="font-normal text-[var(--foreground-subtle)]">({content.key})</span>
          </summary>
          <pre className="mt-1 max-h-[320px] overflow-auto whitespace-pre-wrap break-words rounded-[8px] bg-[var(--brand-wash-6)] px-3 py-2 text-[12px] leading-[1.4] text-[var(--foreground)]">
            {content.value}
          </pre>
        </details>
      ) : null}

      {rest ? (
        <div>
          <button
            type="button"
            onClick={() => setShowRaw((previous) => !previous)}
            className="text-[12px] font-semibold text-[var(--brand)] underline-offset-2 hover:underline"
          >
            {showRaw ? "Hide" : "Show"} remaining fields
          </button>
          {showRaw ? <CodeBlock value={rest} /> : null}
        </div>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Pipeline Health (expanded banner, not inside an accordion — matches v1).
// ---------------------------------------------------------------------------

function PipelineHealthBanner({
  run,
  health,
  isPending,
  error,
  onJumpToSection,
}: {
  run: RunRecord;
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

  const decisionSupport = useMemo(
    () => buildPipelineDecisionSupport({ run, health }),
    [health, run],
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

          <div className="space-y-2">
            {projectPipelineStages(health).map((stage) => {
              const level = pipelineHealthToLevel(stage.status);
              const action = stageActionTarget(stage, {
                legalSearchUrl,
                evidenceRunbookPath,
              });
              const isInPageAnchor = action.href.startsWith("#");
              const needsAction = stageNeedsAction(stage.status);
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
                        Next action: {stageNextAction(stage)}
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

/**
 * `PrimaryDecisionCell` — elevated, full-width variant of `DecisionCell` that
 * leads the pipeline decision-support block (issue #393). Mirrors the sibling
 * in `RunShowV2.tsx` so the two decision-support surfaces stay visually in sync.
 */
function PrimaryDecisionCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="space-y-1 rounded-[12px] border border-[var(--border)] bg-[var(--surface-panel)] p-4 shadow-[var(--shadow-card-hover)]">
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
  /** DOM id used as an in-page scroll target for the pipeline jump links. */
  sectionId?: string;
  title: string;
  description: string;
  /**
   * What this section cannot tell you, rendered above the rows.
   *
   * Not decoration: a section whose rows are honest but whose *absence of rows*
   * is not (the DI stage cannot see a quarantine at all) has to say so where the
   * rows are, not in a doc comment.
   */
  caveat?: ReactNode;
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
  caveat,
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

          {caveat ? <InlineAlert tone="warning">{caveat}</InlineAlert> : null}

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
  {
    key: "storage_path",
    header: "Storage path",
    render: (artifact) => (
      <ExternalValueLink
        href={buildMinioObjectHref(publicConfig.minioConsoleBaseUrl, artifact.storage_path)}
        label={artifact.storage_path}
      />
    ),
  },
  {
    key: "created_at",
    header: "Created",
    render: (artifact) => formatDateTime(artifact.created_at),
  },
  {
    key: "metadata",
    header: "Metadata",
    render: (artifact) => <ArtifactPayloadPanel payload={artifact.artifact_metadata} />,
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
      update.document_id ? (
        <span>
          <ExternalValueLink
            href={buildDocumentSearchHref(
              publicConfig.legalSearchBaseUrlOrUndefined,
              update.document_id,
            )}
            label={update.document_id}
          />
          <span className="text-[12px] text-[var(--foreground-subtle)]">
            {" "}
            rev {update.document_revision ?? "—"}
          </span>
        </span>
      ) : (
        "—"
      ),
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

const timelineColumns: DataTableColumn<RunTimelineEntry>[] = [
  {
    key: "occurred",
    header: "When",
    // An undated entry says so rather than borrowing its neighbour's time.
    render: (item) =>
      item.occurredAt ? (
        formatDateTime(item.occurredAt)
      ) : (
        <span className="text-[var(--foreground-faint)]">no timestamp</span>
      ),
  },
  {
    key: "stage",
    header: "Stage",
    render: (item) => <Pill variant="meta">{item.stageLabel}</Pill>,
  },
  {
    key: "summary",
    header: "Event",
    render: (item) => (
      <span className={item.isFailure ? "text-[var(--status-critical)]" : undefined}>
        {item.summary}
      </span>
    ),
  },
  { key: "detail", header: "Detail", render: (item) => renderInlineValue(item.detail) },
];

const documentLifecycleColumns: DataTableColumn<DocumentLifecycleRecord>[] = [
  { key: "event_type", header: "Event", render: (event) => event.event_type },
  {
    key: "document",
    header: "Document",
    render: (event) => (
      <span>
        <ExternalValueLink
          href={buildDocumentSearchHref(
            publicConfig.legalSearchBaseUrlOrUndefined,
            event.document_id,
          )}
          label={event.document_id}
        />
        <span className="text-[12px] text-[var(--foreground-subtle)]">
          {" "}
          rev {event.document_revision}
        </span>
      </span>
    ),
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
// Root — binds the five `useGetList` fetches and renders the accordion stack.
// ---------------------------------------------------------------------------

export default function RunDetailSectionsV2({
  health,
  healthIsPending,
  healthError,
}: {
  health: RunPipelineHealth | null;
  healthIsPending: boolean;
  healthError: unknown;
}) {
  const run = useRecordContext<RunRecord>();

  // Controls which accordion sections are open. The pipeline jump links reveal
  // their target here and then scroll to it — never via the hash, which the
  // HashRouter would treat as a (bad) route change.
  const [openSections, setOpenSections] = useState<string[]>([]);

  const handleJumpToSection = useCallback((href: string) => {
    const value = ANCHOR_TO_ACCORDION_VALUE[sectionIdFromAnchor(href)];
    if (value) {
      setOpenSections((prev) => (prev.includes(value) ? prev : [...prev, value]));
    }
    scrollToInPageSection(href);
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

  const timelineRows = useMemo(
    () =>
      buildRunTimeline({
        providerJobs: providerJobs.data,
        capturedResources: capturedResources.data,
        rawArtifacts: rawArtifacts.data,
        processingStatus: processingStatus.data,
        documentLifecycle: documentLifecycle.data,
      }),
    [
      providerJobs.data,
      capturedResources.data,
      rawArtifacts.data,
      processingStatus.data,
      documentLifecycle.data,
    ],
  );
  const timelineIsPending =
    providerJobs.isPending ||
    capturedResources.isPending ||
    rawArtifacts.isPending ||
    processingStatus.isPending ||
    documentLifecycle.isPending;
  const timelineError =
    providerJobs.error ??
    capturedResources.error ??
    rawArtifacts.error ??
    processingStatus.error ??
    documentLifecycle.error;

  if (!run) {
    return null;
  }

  return (
    <div className="space-y-4">
      <PipelineHealthBanner
        run={run}
        health={health}
        isPending={healthIsPending}
        error={healthError}
        onJumpToSection={handleJumpToSection}
      />

      <AccordionRoot
        type="multiple"
        value={openSections}
        onValueChange={setOpenSections}
        className="flex flex-col gap-3"
      >
        <RunAccordionSection<RunTimelineEntry>
          value="timeline"
          title="Timeline"
          description="All five stages in one sequence, oldest first — the last entry is how far this run got."
          rows={timelineRows}
          // Pending until every stage has loaded, and any single stage's error
          // is surfaced rather than swallowed: a timeline assembled from four of
          // five lists looks complete and is not, which would point the operator
          // at the wrong stall.
          isPending={timelineIsPending}
          error={timelineError}
          emptyMessage="No stage events were recorded for this run."
          columns={timelineColumns}
          getRowId={(entry) => entry.id}
        />
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
          caveat={
            <div className="space-y-1">
              <p className="font-semibold text-[var(--foreground)]">
                Quarantined documents do not appear here
              </p>
              <p>
                ADR-0047 withholds a manifestation whose extracted text cannot support the claim
                that it is law. document-intelligence records that on its own processing-manifest
                surface with a reason slug and a metric, and deliberately emits{" "}
                <strong>no further status event</strong> — the status flow ends at{" "}
                <code>processing</code>. platform-control&apos;s own status vocabulary has no{" "}
                <code>quarantined</code> member either, so nothing on this screen can count them.
              </p>
              <p>
                Read the rows below as “what DI reported”, never as “nothing was withheld”. A
                document can be quarantined and leave this list looking clean.
              </p>
            </div>
          }
          rows={processingStatus.data}
          isPending={processingStatus.isPending}
          error={processingStatus.error}
          emptyMessage="No DI processing status updates have been received for this run. That is not the same as “nothing was withheld” — see the note above."
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
        <PipelineStagesSection
          events={documentLifecycle.data}
          isPending={documentLifecycle.isPending}
          error={documentLifecycle.error}
        />
      </AccordionRoot>
    </div>
  );
}

/**
 * What document-intelligence did to each document, stage by stage (#903).
 *
 * Reads the same `run-document-lifecycle` fetch as the section above rather than
 * issuing its own — the ledger rides on those events, so a second request would
 * be the same rows twice.
 *
 * The count in the trigger is "documents WITH timings", never the row count: a
 * run whose events all predate stage recording has rows and no timings, and
 * saying "5 documents" over five empty timelines would misreport absence as data.
 */
function PipelineStagesSection({
  events,
  isPending,
  error,
}: {
  events: DocumentLifecycleRecord[] | undefined;
  isPending: boolean;
  error: unknown;
}) {
  const withStages = (events ?? []).filter(
    (event) => event.stages != null && event.stages.length > 0,
  );
  const total = events?.length ?? 0;

  return (
    <AccordionItem value="pipeline-stages" id="pipeline-stages-section">
      <AccordionTrigger>
        <span className="text-[15px] font-semibold text-[var(--foreground)]">Pipeline Stages</span>
        {isPending ? (
          <Pill variant="meta">Loading…</Pill>
        ) : error ? (
          <Pill level="critical">Error</Pill>
        ) : (
          <Pill variant="meta">
            {`${withStages.length} of ${total} ${total === 1 ? "document" : "documents"} timed`}
          </Pill>
        )}
      </AccordionTrigger>
      <AccordionContent>
        <div className="space-y-3">
          <p className="text-[13px] text-[var(--foreground-subtle)]">
            Per-stage timings and counts recorded by document-intelligence while processing each
            document.
          </p>
          {isPending ? (
            <p className="text-[13px] text-[var(--text-meta)] m-0">Loading pipeline stages…</p>
          ) : error ? (
            <p className="text-[13px] text-[var(--text-meta)] m-0">
              {error instanceof Error
                ? error.message
                : "Unable to load pipeline stages. This is unavailable, not empty."}
            </p>
          ) : total === 0 ? (
            <p className="text-[13px] text-[var(--text-meta)] m-0">
              No document lifecycle events have been received for this run, so there is nothing to
              time.
            </p>
          ) : withStages.length === 0 ? (
            <p className="text-[13px] text-[var(--text-meta)] m-0">
              None of this run&rsquo;s {total} document
              {total === 1 ? "" : "s"} carries stage timings. Their processing predates stage
              recording, or the producer emits none — this is not a report that the pipeline did no
              work.
            </p>
          ) : (
            <div className="space-y-5">
              {withStages.map((event) => (
                <div key={event.event_id}>
                  <p className="text-[13px] font-mono text-[var(--text-meta)] mt-0 mb-2">
                    {event.document_id} · rev {event.document_revision}
                  </p>
                  <StageTimeline stages={event.stages} />
                </div>
              ))}
            </div>
          )}
        </div>
      </AccordionContent>
    </AccordionItem>
  );
}
