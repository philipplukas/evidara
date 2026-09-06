/**
 * Column definitions for the run-detail stage sections.
 *
 * This is the seam. Every new section historically meant editing the one file
 * that held every other section — #885, #897 and #887 all landed in
 * `RunDetailSectionsV2.tsx` and had to be a stack; #905 added a section to it
 * from a different session entirely. Nothing collided semantically, and nothing
 * would have said so if it had.
 *
 * Adding a section is now: a columns array here (or its own module) plus one
 * `<RunAccordionSection>` in the root.
 */
"use client";

import { publicConfig } from "../../config/publicConfig";
import type {
  CapturedResourceRecord,
  DocumentLifecycleRecord,
  ProcessingStatusRecord,
  ProviderJobRecord,
  RawArtifactRecord,
} from "../../lib/admin/dataProvider";
import { type DataTableColumn, Pill } from "../../ui/primitives";
import { ArtifactPayloadPanel } from "./ArtifactPayloadPanel";
import {
  CodeBlock,
  ExternalValueLink,
  formatDateTime,
  renderInlineValue,
  rowFailureLevel,
} from "./runCells";
import { buildDocumentSearchHref, buildMinioObjectHref } from "./runDeepLinks";
import type { RunTimelineEntry } from "./runTimeline";

export const providerJobColumns: DataTableColumn<ProviderJobRecord>[] = [
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

export const capturedResourceColumns: DataTableColumn<CapturedResourceRecord>[] = [
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

export const rawArtifactColumns: DataTableColumn<RawArtifactRecord>[] = [
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

export const processingStatusColumns: DataTableColumn<ProcessingStatusRecord>[] = [
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

export const timelineColumns: DataTableColumn<RunTimelineEntry>[] = [
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

export const documentLifecycleColumns: DataTableColumn<DocumentLifecycleRecord>[] = [
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
