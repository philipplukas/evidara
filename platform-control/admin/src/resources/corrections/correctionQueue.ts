/**
 * Pure helpers for the correction queue (`/v1/corrections/queue`).
 *
 * These are split out from `CorrectionQueueList.tsx` so the queue's
 * behaviour — operator labels, status colour mapping, default filter
 * shape, and short-rationale truncation — can be unit-tested without
 * spinning up React or `ra-core`. The page module is a thin shell that
 * binds these helpers to `useListController`.
 */

import type {
  CorrectionRecord,
  CorrectionStatus,
  CorrectionTargetEntityType,
  CorrectionType,
} from "../../lib/admin/dataProvider";
import type { PillLevel } from "../../ui/primitives";

export const CORRECTION_TYPE_LABEL: Record<CorrectionType, string> = {
  field_edit: "Field edit",
  annotation: "Annotation",
  reject: "Reject",
  rescore_request: "Rescore request",
};

export const CORRECTION_STATUS_LABEL: Record<CorrectionStatus, string> = {
  pending: "Pending",
  applied: "Applied",
  rejected: "Rejected",
  superseded: "Superseded",
};

export const CORRECTION_TARGET_LABEL: Record<CorrectionTargetEntityType, string> = {
  commentary_insight: "Commentary insight",
  search_projection: "Search projection",
  document: "Document",
  section: "Section",
  citation: "Citation",
};

/**
 * Default filter shape for the queue page. Surfaced as a constant so the
 * dataProvider tests and the page-level tests can compare against the
 * same canonical default — reproducing the platform-control router's
 * `status=pending` default at the UI layer keeps the view stable even if
 * the operator clears the filter chip.
 */
export const DEFAULT_CORRECTION_QUEUE_FILTER: {
  status: CorrectionStatus;
} = {
  status: "pending",
};

/**
 * Map a `CorrectionStatus` onto a pill level. We keep `pending` neutral
 * (the queue always has pending items; colouring them critical would
 * scream at the operator), `applied` healthy, and the terminal states
 * (`rejected`/`superseded`) degraded.
 */
export function correctionStatusToLevel(status: CorrectionStatus): PillLevel {
  switch (status) {
    case "applied":
      return "healthy";
    case "rejected":
    case "superseded":
      return "degraded";
    case "pending":
      return "info";
    default:
      return "neutral";
  }
}

/** Truncate the rationale for the queue row preview, preserving meaning. */
export function summarizeRationale(rationale: string, maxLength = 120): string {
  const trimmed = rationale.trim();
  if (trimmed.length <= maxLength) return trimmed;
  // Cut at the last space before the limit so we don't slice mid-word.
  const slice = trimmed.slice(0, maxLength);
  const lastSpace = slice.lastIndexOf(" ");
  const cutoff = lastSpace > maxLength * 0.6 ? lastSpace : maxLength;
  return `${trimmed.slice(0, cutoff).trimEnd()}…`;
}

/**
 * Surface a one-line description of which entity a correction targets so
 * the row can show the operator "what" they're triaging at a glance.
 */
export function describeTarget(record: CorrectionRecord): string {
  const label = CORRECTION_TARGET_LABEL[record.target_entity_type] ?? record.target_entity_type;
  return `${label} · ${record.target_entity_id}`;
}

/**
 * Resolve a follow-up href for the correction. Field edits, annotations,
 * and rejects on a commentary insight all link to the insight's edit
 * page so the operator can drill into the diff in context. Other entity
 * types fall back to the queue itself (no destination yet — Sprint 3).
 */
export function buildCorrectionFollowUpHref(record: CorrectionRecord): string | null {
  if (record.target_entity_type === "commentary_insight") {
    return `/${"commentary-insights"}/${encodeURIComponent(record.target_entity_id)}`;
  }
  return null;
}
