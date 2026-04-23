/**
 * `RunDetailSectionsV2` — Tailwind + `ra-core` port of v1's `RunDetailSections`.
 *
 * Pipeline Health renders as an expanded banner at the top (matches v1's
 * default-expanded accordion). The five data stages below — Provider Jobs,
 * Captured Resources, Raw Artifacts, DI Processing Status, Document Lifecycle
 * — render as collapsed accordion items; each binds a `useGetList` with the
 * same `run_id` filter v1 used and draws rows via the `DataTable` primitive.
 *
 * Reuses pure helpers from v1 (`buildPipelineDecisionSupport`,
 * `overallSummaryByStatus`, `stageNextAction`, `stageActionTarget`) so the
 * operator cues stay identical while MUI chrome is replaced with primitives.
 * Stateful pieces from v1 that aren't in this slice — operator checklist
 * (`deriveOperatorChecklist`), preview summary, navigation button strip,
 * telemetry emission — stay in the v1 file and port alongside the shell.
 */
"use client";

import { type Identifier, useGetList, useRecordContext } from "ra-core";
import { useEffect, useMemo, useState } from "react";
import type {
  CapturedResourceRecord,
  DocumentLifecycleRecord,
  ProcessingStatusRecord,
  ProviderJobRecord,
  RawArtifactRecord,
  RunPipelineHealth,
  RunRecord,
} from "../../lib/admin/dataProvider";
import { controlPlaneActions } from "../../lib/admin/dataProvider";
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
import { pipelineHealthToLevel } from "../shared/StatusBadge";
import {
  buildPipelineDecisionSupport,
  overallSummaryByStatus,
  stageActionTarget,
  stageNextAction,
} from "./RunDetailSections";

const LIST_PARAMS = {
  pagination: { page: 1, perPage: 50 },
  sort: { field: "created_at", order: "DESC" as const },
};

const formatDateTime = (value: string | null | undefined): string =>
  formatSwissDateTime(value) || "—";

const formatJson = (value: unknown): string => JSON.stringify(value, null, 2);

const renderInlineValue = (value: string | number | null | undefined) =>
  value ?? <span className="text-[rgba(29,41,61,0.4)]">—</span>;

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

function PipelineHealthBanner({ run }: { run: RunRecord }) {
  const [health, setHealth] = useState<RunPipelineHealth | null>(null);
  const [isPending, setIsPending] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const legalSearchUrl = process.env.NEXT_PUBLIC_LEGAL_SEARCH_URL?.trim();
  const evidenceRunbookPath =
    "https://github.com/philipplukas/evidara/blob/main/docs/runbooks/interaction-flow-validation.md";

  useEffect(() => {
    let cancelled = false;
    setIsPending(true);
    setError(null);

    void controlPlaneActions
      .getRunPipelineHealth(run.run_id)
      .then((response) => {
        if (!cancelled) {
          setHealth(response);
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
  }, [run.run_id]);

  const decisionSupport = useMemo(
    () => buildPipelineDecisionSupport({ run, health }),
    [health, run],
  );

  return (
    <section className="space-y-4 rounded-[18px] border border-[rgba(29,41,61,0.08)] bg-white/85 p-5 shadow-[var(--shadow-card)] backdrop-blur-[12px] sm:p-6">
      <header className="space-y-1">
        <h2 className="text-[16px] font-semibold text-[var(--foreground)]">Pipeline Health</h2>
        <p className="text-[13px] text-[rgba(29,41,61,0.65)]">
          Expanded by default so the overall signal is visible without a click; drill into the stage
          sections below for row-level detail.
        </p>
      </header>

      {isPending ? (
        <p className="text-[13px] text-[rgba(29,41,61,0.6)]">Loading pipeline health…</p>
      ) : null}

      {!isPending && error ? (
        <div
          role="alert"
          className="rounded-[12px] border border-[rgba(198,40,40,0.4)] bg-[rgba(198,40,40,0.06)] p-3 text-[13px] text-[#b71c1c]"
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

          <div className="rounded-[14px] border border-[rgba(29,41,61,0.08)] bg-[var(--brand-wash-3)] p-4">
            <div className="mb-3">
              <h3 className="text-[14px] font-semibold text-[var(--foreground)]">
                Pipeline decision support
              </h3>
              <p className="text-[12px] text-[rgba(29,41,61,0.65)]">
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
            {health.stages.map((stage) => {
              const level = pipelineHealthToLevel(stage.status);
              const action = stageActionTarget(stage, {
                legalSearchUrl,
                evidenceRunbookPath,
              });
              const isInPageAnchor = action.href.startsWith("#");
              const isHealthy = stage.status === "ok";
              return (
                <div
                  key={stage.stage}
                  className="rounded-[12px] border border-[rgba(29,41,61,0.08)] bg-white/70 p-3"
                >
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="text-[13px] font-semibold capitalize text-[var(--foreground)]">
                        {stage.stage.replaceAll("_", " ")}
                      </p>
                      <p className="text-[11px] text-[rgba(29,41,61,0.6)]">
                        {formatDateTime(stage.updated_at)}
                      </p>
                    </div>
                    <Pill level={level}>{stage.status.replaceAll("_", " ")}</Pill>
                  </div>
                  <p className="mt-1.5 text-[13px] text-[rgba(29,41,61,0.75)]">{stage.detail}</p>
                  {!isHealthy ? (
                    <div className="mt-2 flex flex-wrap items-center justify-between gap-2 rounded-[10px] border border-[rgba(237,108,2,0.2)] bg-[rgba(237,108,2,0.06)] p-2.5">
                      <p className="text-[12px] font-semibold text-[var(--foreground)]">
                        Next action: {stageNextAction(stage)}
                      </p>
                      <a
                        href={action.href}
                        target={isInPageAnchor ? undefined : "_blank"}
                        rel={isInPageAnchor ? undefined : "noreferrer"}
                        className="inline-flex h-8 items-center rounded-full border border-[var(--border)] bg-white/80 px-3 text-[12px] font-semibold text-[var(--brand)] hover:bg-white"
                      >
                        {action.label}
                      </a>
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
    <div className="space-y-0.5 rounded-[10px] border border-[rgba(29,41,61,0.08)] bg-white/80 p-3">
      <span className="block text-[11px] font-semibold uppercase tracking-[0.08em] leading-[1.2] text-[rgba(29,41,61,0.6)]">
        {label}
      </span>
      <p className="text-[13px] leading-snug text-[rgba(29,41,61,0.8)]">{value}</p>
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
    <div className="space-y-1 rounded-[12px] border border-[rgba(29,41,61,0.1)] bg-white p-4 shadow-[var(--shadow-card-hover)]">
      <span className="block text-[15px] font-semibold uppercase tracking-[0.08em] leading-[1.2] text-[rgba(29,41,61,0.8)]">
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
    <AccordionItem value={value}>
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
          <p className="text-[13px] text-[rgba(29,41,61,0.65)]">{description}</p>

          {isPending ? (
            <p className="text-[13px] text-[rgba(29,41,61,0.6)]">Loading {title.toLowerCase()}…</p>
          ) : error ? (
            <div
              role="alert"
              className="rounded-[12px] border border-[rgba(198,40,40,0.4)] bg-[rgba(198,40,40,0.06)] p-3 text-[13px] text-[#b71c1c]"
            >
              {error instanceof Error ? error.message : `Unable to load ${title.toLowerCase()}.`}
            </div>
          ) : count === 0 ? (
            <p className="text-[13px] text-[rgba(29,41,61,0.55)]">{emptyMessage}</p>
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
        <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-[rgba(29,41,61,0.6)]">
          Request
        </p>
        <CodeBlock value={job.request_payload} />
        <p className="mt-2 text-[11px] font-semibold uppercase tracking-[0.06em] text-[rgba(29,41,61,0.6)]">
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
// Root — binds the five `useGetList` fetches and renders the accordion stack.
// ---------------------------------------------------------------------------

export default function RunDetailSectionsV2() {
  const run = useRecordContext<RunRecord>();

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
      <PipelineHealthBanner run={run} />

      <AccordionRoot type="multiple" className="flex flex-col gap-3">
        <RunAccordionSection<ProviderJobRecord>
          value="provider-jobs"
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
