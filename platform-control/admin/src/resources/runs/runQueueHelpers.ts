/**
 * Pure run-queue helpers shared by the runs list page and its tests. Extracted
 * from the retired MUI `RunList.tsx` during the ADR-0026 cutover so the logic
 * survives independent of the component that renders it.
 */
import type { RunRecord } from "../../lib/admin/dataProvider";

export type RunQueueFilterValues = Partial<Pick<RunRecord, "mode" | "status">>;

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
