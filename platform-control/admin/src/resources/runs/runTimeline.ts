/**
 * One chronological view across the five run stages.
 *
 * The stage sections each answer "what happened in this stage", and all five
 * carry a timestamp — `updated_at`, `fetched_at`, `created_at`, `occurred_at`.
 * But they render as five independent tables, each sorted newest-first, so the
 * question an operator actually arrives with — *where did this run stall?* —
 * requires reading five lists and interleaving them by hand.
 *
 * This merges them into one ordered sequence. The stall diagnosis already
 * computes a cause from `pipeline-health`; the timeline is what lets an operator
 * see it rather than take it on trust.
 *
 * Two decisions worth stating:
 *
 *  - **Ascending (oldest first)**, unlike the tables. A timeline read top-down
 *    should run the direction the pipeline ran; the last entry is then where it
 *    got to, which is the answer being looked for.
 *  - **Undated entries are kept, not dropped.** A row whose timestamp is
 *    missing or unparseable still happened, and silently omitting it would make
 *    the timeline quietly disagree with the table above it. They sort last and
 *    are flagged so the UI can say so.
 */

export type RunTimelineStage =
  | "provider-job"
  | "captured-resource"
  | "raw-artifact"
  | "processing-status"
  | "document-lifecycle";

export interface RunTimelineEntry {
  /** Unique within a timeline: the stage plus the row's own id. */
  readonly id: string;
  readonly stage: RunTimelineStage;
  readonly stageLabel: string;
  /** The source timestamp, verbatim. `null` when absent or unparseable. */
  readonly occurredAt: string | null;
  /** Sort key: epoch ms, or `null` when undated. */
  readonly sortKey: number | null;
  readonly summary: string;
  readonly detail: string | null;
  readonly isFailure: boolean;
}

const STAGE_LABELS: Record<RunTimelineStage, string> = {
  "provider-job": "Provider job",
  "captured-resource": "Captured",
  "raw-artifact": "Artifact",
  "processing-status": "Processing",
  "document-lifecycle": "Lifecycle",
};

/**
 * Epoch ms for a timestamp, or `null` when it is absent or not parseable.
 *
 * `Date.parse` returns `NaN` rather than throwing, and `NaN` compares false
 * against everything — so an unchecked value would sort unpredictably instead
 * of landing in the undated bucket.
 */
function toSortKey(value: string | null | undefined): number | null {
  if (!value) {
    return null;
  }
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? null : parsed;
}

function entry(
  stage: RunTimelineStage,
  id: string,
  occurredAt: string | null | undefined,
  summary: string,
  detail: string | null,
  isFailure: boolean,
): RunTimelineEntry {
  const sortKey = toSortKey(occurredAt);
  return {
    id: `${stage}:${id}`,
    stage,
    stageLabel: STAGE_LABELS[stage],
    occurredAt: sortKey === null ? null : (occurredAt ?? null),
    sortKey,
    summary,
    detail,
    isFailure,
  };
}

/** Minimal structural types — only the fields the timeline reads. */
interface ProviderJobLike {
  provider_job_id: string;
  provider?: string | null;
  status?: string | null;
  last_event_type?: string | null;
  updated_at?: string | null;
}
interface CapturedResourceLike {
  captured_resource_id: string;
  title?: string | null;
  final_url?: string | null;
  http_status?: number | null;
  fetched_at?: string | null;
}
interface RawArtifactLike {
  artifact_id: string;
  content_type?: string | null;
  created_at?: string | null;
}
interface ProcessingStatusLike {
  event_id: string;
  status?: string | null;
  document_id?: string | null;
  error_summary?: string | null;
  occurred_at?: string | null;
}
interface DocumentLifecycleLike {
  event_id: string;
  event_type?: string | null;
  document_id?: string | null;
  lifecycle_status?: string | null;
  reason_code?: string | null;
  occurred_at?: string | null;
}

export interface RunTimelineInput {
  providerJobs?: readonly ProviderJobLike[] | null;
  capturedResources?: readonly CapturedResourceLike[] | null;
  rawArtifacts?: readonly RawArtifactLike[] | null;
  processingStatus?: readonly ProcessingStatusLike[] | null;
  documentLifecycle?: readonly DocumentLifecycleLike[] | null;
}

/**
 * Merge the five stage lists into one ascending sequence.
 *
 * Undated entries keep their relative input order and sort after every dated
 * one. Stable within equal timestamps, so two events recorded in the same
 * millisecond keep the order the API returned them in rather than swapping
 * between renders.
 */
export function buildRunTimeline(input: RunTimelineInput): RunTimelineEntry[] {
  const entries: RunTimelineEntry[] = [];

  for (const job of input.providerJobs ?? []) {
    entries.push(
      entry(
        "provider-job",
        job.provider_job_id,
        job.updated_at,
        `${job.provider ?? "provider"} job ${job.status ?? "unknown"}`,
        job.last_event_type ? `last event: ${job.last_event_type}` : null,
        job.status === "failed",
      ),
    );
  }

  for (const resource of input.capturedResources ?? []) {
    const status = resource.http_status;
    entries.push(
      entry(
        "captured-resource",
        resource.captured_resource_id,
        resource.fetched_at,
        resource.title?.trim() || resource.final_url || "Untitled resource",
        status == null ? null : `HTTP ${status}`,
        // Anything outside 2xx was not a successful capture. `>= 400` alone
        // would treat a 3xx that never resolved as fine.
        status != null && (status < 200 || status >= 300),
      ),
    );
  }

  for (const artifact of input.rawArtifacts ?? []) {
    entries.push(
      entry(
        "raw-artifact",
        artifact.artifact_id,
        artifact.created_at,
        `Artifact ${artifact.artifact_id}`,
        artifact.content_type ?? null,
        false,
      ),
    );
  }

  for (const update of input.processingStatus ?? []) {
    entries.push(
      entry(
        "processing-status",
        update.event_id,
        update.occurred_at,
        `Processing ${update.status ?? "unknown"}${
          update.document_id ? ` — ${update.document_id}` : ""
        }`,
        update.error_summary ?? null,
        update.status === "failed",
      ),
    );
  }

  for (const event of input.documentLifecycle ?? []) {
    entries.push(
      entry(
        "document-lifecycle",
        event.event_id,
        event.occurred_at,
        `${event.event_type ?? "event"}${event.document_id ? ` — ${event.document_id}` : ""}`,
        event.reason_code ? `reason: ${event.reason_code}` : (event.lifecycle_status ?? null),
        false,
      ),
    );
  }

  return entries
    .map((value, index) => ({ value, index }))
    .sort((a, b) => {
      const aKey = a.value.sortKey;
      const bKey = b.value.sortKey;
      if (aKey === null && bKey === null) {
        return a.index - b.index;
      }
      // Undated last, regardless of direction.
      if (aKey === null) {
        return 1;
      }
      if (bKey === null) {
        return -1;
      }
      return aKey === bKey ? a.index - b.index : aKey - bKey;
    })
    .map(({ value }) => value);
}
