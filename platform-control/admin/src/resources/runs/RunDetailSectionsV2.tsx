/**
 * `RunDetailSectionsV2` — the run detail sections, Tailwind + `ra-core`.
 *
 * Pipeline Health renders as an expanded banner at the top. The stage sections
 * below — Provider Jobs, Captured Resources, Raw Artifacts, DI Processing Status,
 * Document Lifecycle, Timeline, Pipeline Stages — render as collapsed accordion
 * items; each binds a `useGetList` with the same `run_id` filter and draws rows
 * via the `DataTable` primitive.
 *
 * This file used to be 978 lines and hold all of it. Every section added since
 * landed here — #885, #897 and #887 had to be a stack because of it, and #905
 * added one from a different session. Nothing collided semantically; nothing
 * would have said so if it had. The file offered no seam.
 *
 * It now composes:
 *   - `runCells`             shared cell primitives
 *   - `runColumns`           one array per section — the seam a new section uses
 *   - `RunAccordionSection`  the accordion wrapper
 *   - `PipelineHealthBanner` the health banner and its decision support
 *   - `ArtifactPayloadPanel` / `PipelineStagesSection`
 *
 * Adding a section is now a columns array plus one element below.
 */
"use client";

import { useGetList, useRecordContext } from "ra-core";
import { useCallback, useMemo, useState } from "react";
import type {
  CapturedResourceRecord,
  DocumentLifecycleRecord,
  ProcessingStatusRecord,
  ProviderJobRecord,
  RawArtifactRecord,
  RunPipelineHealth,
  RunRecord,
} from "../../lib/admin/dataProvider";
import {
  AccordionContent,
  AccordionItem,
  AccordionRoot,
  AccordionTrigger,
  Pill,
} from "../../ui/primitives";
import { PipelineHealthBanner } from "./PipelineHealthBanner";
import { RunAccordionSection } from "./RunAccordionSection";
import { scrollToInPageSection, sectionIdFromAnchor } from "./run-decision-support";
import {
  capturedResourceColumns,
  documentLifecycleColumns,
  processingStatusColumns,
  providerJobColumns,
  rawArtifactColumns,
  timelineColumns,
} from "./runColumns";
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
          total={providerJobs.total}
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
          total={capturedResources.total}
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
          total={rawArtifacts.total}
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
          total={processingStatus.total}
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
          total={documentLifecycle.total}
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
 * What document-intelligence did to each document, stage by stage (#905).
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
