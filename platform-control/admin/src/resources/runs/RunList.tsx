/**
 * `RunList` shared helpers — after the v1→v2 runs consolidation (#520) the MUI
 * `<List>` page component was retired; the canonical runs table is `RunListV2`
 * wired through the `runs` resource. This module retains only the pure,
 * framework-free helpers that `RunListV2` (and the run-queue unit tests) still
 * consume: attention-run selection, filter summarisation, operator-language
 * state copy, and the keyboard-shortcut resolver.
 */
import type { RunRecord } from "../../lib/admin/dataProvider";

type RunQueueFilterValues = Partial<Pick<RunRecord, "mode" | "status">>;

const ACTIONABLE_STATUSES: RunRecord["status"][] = ["failed", "running", "pending"];

export const describeRunState = (record: RunRecord): string => {
  if (record.status === "pending") {
    return "Queued. Review readiness or open the run when it becomes active.";
  }
  if (record.status === "running") {
    return "Active now. Watch the pipeline sections for the next operator cue.";
  }
  if (record.status === "failed") {
    return "Blocked. Review the failure reason in the detail page.";
  }
  if (record.status === "completed") {
    return "Finished successfully. Use the detail view for audit evidence.";
  }
  return "Stopped by an operator. Review the detail page if this was unexpected.";
};

export const summarizeRunFilters = (filterValues: RunQueueFilterValues): string => {
  const segments = [
    filterValues.mode ? `mode: ${String(filterValues.mode)}` : null,
    filterValues.status ? `status: ${String(filterValues.status)}` : null,
  ].filter((segment): segment is string => segment !== null);

  return segments.join(" · ");
};

export const selectAttentionRun = (runs: RunRecord[]): RunRecord | null => {
  for (const status of ACTIONABLE_STATUSES) {
    const candidate = runs.find((run) => run.status === status);
    if (candidate) {
      return candidate;
    }
  }

  return runs[0] ?? null;
};

export const isKeyboardShortcutInputTarget = (target: EventTarget | null): boolean => {
  if (!target || typeof target !== "object") {
    return false;
  }

  const element = target as {
    tagName?: string;
    isContentEditable?: boolean;
    contentEditable?: string;
    closest?: (selector: string) => unknown;
  };

  const tagName = element.tagName?.toUpperCase();

  return (
    tagName === "INPUT" ||
    tagName === "TEXTAREA" ||
    tagName === "SELECT" ||
    element.isContentEditable === true ||
    element.contentEditable === "true" ||
    (typeof element.closest === "function" && element.closest("[contenteditable='true']") !== null)
  );
};

export type RunQueueKeyboardShortcutAction =
  | { type: "focus-attention" }
  | { type: "open-attention"; runId: string };

export const getRunQueueKeyboardShortcutAction = (
  event: Pick<KeyboardEvent, "altKey" | "ctrlKey" | "defaultPrevented" | "key" | "metaKey">,
  target: EventTarget | null,
  attentionRun: RunRecord | null,
): RunQueueKeyboardShortcutAction | null => {
  if (
    event.defaultPrevented ||
    event.metaKey ||
    event.ctrlKey ||
    event.altKey ||
    isKeyboardShortcutInputTarget(target)
  ) {
    return null;
  }

  if (event.key === "/") {
    return { type: "focus-attention" };
  }

  if ((event.key === "o" || event.key === "O") && attentionRun) {
    return { type: "open-attention", runId: attentionRun.run_id };
  }

  return null;
};
