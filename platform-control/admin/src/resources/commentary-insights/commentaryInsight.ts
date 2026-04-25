/**
 * Pure helpers for the commentary insight pages.
 *
 * Same split as `corrections/correctionQueue.ts` — keep state-machine,
 * label, diff, and validation logic in a node-test-friendly module so
 * the page modules stay thin and we can land Vitest coverage without
 * spinning up jsdom.
 */

import type {
  CommentaryInsightRecord,
  CommentaryInsightReviewState,
  CorrectionRecord,
} from "../../lib/admin/dataProvider";
import type { PillLevel } from "../../ui/primitives";

/**
 * Whitelisted patchable fields for `EditCommentaryInsightRequest.payload`
 * (see `contracts/api/platform-control.openapi.yaml` — the description on
 * `payload` lists `claim`, `display_text`, `review_state`, and
 * `referenced_authorities`). We surface the first three in Sprint 2;
 * `referenced_authorities` is structured and lands with a follow-up
 * editor in Sprint 3.
 */
export const PATCHABLE_INSIGHT_FIELDS = ["claim", "display_text", "review_state"] as const;
export type PatchableInsightField = (typeof PATCHABLE_INSIGHT_FIELDS)[number];

export const REVIEW_STATE_LABEL: Record<CommentaryInsightReviewState, string> = {
  machine_generated_unreviewed: "Machine-generated (unreviewed)",
  machine_verified: "Machine-verified",
  editor_approved: "Editor-approved",
  rejected: "Rejected",
  stale: "Stale",
};

export const REVIEW_STATE_VALUES: CommentaryInsightReviewState[] = [
  "machine_generated_unreviewed",
  "machine_verified",
  "editor_approved",
  "rejected",
  "stale",
];

export function reviewStateToLevel(state: CommentaryInsightReviewState): PillLevel {
  switch (state) {
    case "editor_approved":
      return "healthy";
    case "machine_verified":
      return "info";
    case "machine_generated_unreviewed":
      return "neutral";
    case "rejected":
    case "stale":
      return "degraded";
    default:
      return "neutral";
  }
}

export type FieldEditDraft = {
  claim: string;
  display_text: string;
  review_state: CommentaryInsightReviewState;
  rationale: string;
};

export function draftFromInsight(insight: CommentaryInsightRecord): FieldEditDraft {
  return {
    claim: insight.claim,
    display_text: insight.display_text,
    review_state: insight.review_state,
    rationale: "",
  };
}

/**
 * Compute the (payload, original_snapshot) pair that needs to be sent to
 * the PATCH endpoint. Only fields whose value actually changed are
 * included; this keeps the correction envelope tight and avoids
 * recording no-op edits.
 */
export function buildFieldEditEnvelope(
  insight: CommentaryInsightRecord,
  draft: FieldEditDraft,
): {
  payload: Record<string, unknown>;
  original_snapshot: Record<string, unknown>;
  hasChanges: boolean;
} {
  const payload: Record<string, unknown> = {};
  const originalSnapshot: Record<string, unknown> = {};
  for (const field of PATCHABLE_INSIGHT_FIELDS) {
    const draftValue = draft[field];
    const originalValue = insight[field];
    if (!Object.is(draftValue, originalValue)) {
      payload[field] = draftValue;
      originalSnapshot[field] = originalValue;
    }
  }
  return {
    payload,
    original_snapshot: originalSnapshot,
    hasChanges: Object.keys(payload).length > 0,
  };
}

export type FieldEditValidation = {
  ok: boolean;
  errors: Partial<Record<keyof FieldEditDraft, string>> & { _form?: string };
};

/**
 * Mirror the OpenAPI contract for `EditCommentaryInsightRequest`:
 * `rationale` is required, 1..2000 chars; `claim` and `display_text` are
 * non-empty when present.
 */
export function validateFieldEditDraft(draft: FieldEditDraft): FieldEditValidation {
  const errors: FieldEditValidation["errors"] = {};
  if (draft.claim.trim().length === 0) {
    errors.claim = "Claim cannot be empty.";
  }
  if (draft.display_text.trim().length === 0) {
    errors.display_text = "Display text cannot be empty.";
  }
  const rationale = draft.rationale.trim();
  if (rationale.length === 0) {
    errors.rationale = "A rationale is required so the correction can be audited.";
  } else if (rationale.length > 2000) {
    errors.rationale = "Rationale must be 2000 characters or fewer.";
  }
  return { ok: Object.keys(errors).length === 0, errors };
}

export type DiffEntry = {
  field: string;
  before: unknown;
  after: unknown;
};

/**
 * Build a stable list of (field, before, after) entries from a
 * correction envelope. Used by the history list and the queue diff
 * preview. We sort fields alphabetically so the diff is deterministic.
 */
export function buildCorrectionDiff(record: CorrectionRecord): DiffEntry[] {
  const before = record.original_snapshot ?? {};
  const after = record.payload ?? {};
  const fields = Array.from(new Set([...Object.keys(before), ...Object.keys(after)])).sort();
  return fields.map((field) => ({
    field,
    before: (before as Record<string, unknown>)[field],
    after: (after as Record<string, unknown>)[field],
  }));
}

/**
 * Format a diff value for inline display. We never collapse `null` /
 * `undefined` to "" because operators legitimately need to see "this
 * field was empty before" — render it as a literal so the diff stays
 * lossless.
 */
export function formatDiffValue(value: unknown): string {
  if (value === null) return "null";
  if (value === undefined) return "—";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

/** Sort corrections newest-first; oldest-API responses come ascending. */
export function sortCorrectionsNewestFirst(corrections: CorrectionRecord[]): CorrectionRecord[] {
  return [...corrections].sort((left, right) => {
    if (left.created_at === right.created_at) return 0;
    return left.created_at < right.created_at ? 1 : -1;
  });
}
