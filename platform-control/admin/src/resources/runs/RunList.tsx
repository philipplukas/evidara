/**
 * `RunList` shared helpers — after the v1→v2 runs consolidation (#520) the MUI
 * `<List>` page component was retired; the canonical runs table is `RunListV2`
 * wired through the `runs` resource. This module retains only the pure,
 * framework-free helpers that `RunListV2` (and the run-queue unit tests) still
 * consume: attention-run selection, filter summarisation, operator-language
 * state copy, and the keyboard-shortcut resolver.
 */
import type { RunRecord } from "../../lib/admin/dataProvider";

type RunQueueFilterValues = Partial<Pick<RunRecord, "mode" | "status" | "refused">>;

const ACTIONABLE_STATUSES: RunRecord["status"][] = ["failed", "running", "pending"];

/**
 * How much of the queue the loaded page actually accounts for.
 *
 * `unknown`    — the list query failed; we have no counts at all.
 * `complete`   — every run the server reports is in hand, so counts are the
 *                whole queue.
 * `partial`    — only the current page is loaded; counts describe the view.
 */
export type QueueCountScope = "unknown" | "complete" | "partial";

export const resolveQueueCountScope = ({
  hasError,
  isPending,
  loadedCount,
  total,
}: {
  hasError: boolean;
  isPending: boolean;
  loadedCount: number;
  total: number | undefined;
}): QueueCountScope => {
  if (hasError || isPending || total === undefined) {
    return "unknown";
  }
  return loadedCount >= total ? "complete" : "partial";
};

/**
 * Render a per-status count for the preset chips.
 *
 * Zero and "I could not ask" must not look the same. During an API outage the
 * queue rendered `Pending 0 · Running 0 · Completed 0 · Failed 0 · Cancelled 0`
 * over a real 10-completed/1-failed queue, with the only truthful signal a line
 * of small red text inside the table body (#669). An em dash is the honest
 * rendering of a number nobody checked.
 */
export const formatQueueCount = (count: number, scope: QueueCountScope): string =>
  scope === "unknown" ? "—" : String(count);

/**
 * The caption under the preset bar. Says which of the three worlds we are in
 * rather than always asserting "N runs in view".
 */
export const describeQueueScope = ({
  scope,
  loadedCount,
  total,
  filterSummary,
}: {
  scope: QueueCountScope;
  loadedCount: number;
  total: number | undefined;
  filterSummary: string;
}): string => {
  if (scope === "unknown") {
    // Two different reasons produce `unknown`, and telling an operator the queue
    // "could not be loaded" while it is plainly on screen teaches them to ignore
    // the line. A narrowing filter (status, or either refusal preset) means the
    // page holds only that slice, so the other chips are unknowable — which is
    // still not zero, and the sentence has to keep saying so.
    return filterSummary.length > 0
      ? `Filtering ${filterSummary} · per-status counts unavailable while the queue is narrowed — the chips show “—”, not zero.`
      : "Run counts unavailable — the queue could not be loaded, so these are not zeros.";
  }

  const base =
    scope === "partial"
      ? `Showing ${loadedCount} of ${total} runs · counts describe this page only`
      : `${loadedCount} run${loadedCount === 1 ? "" : "s"} in view`;

  return filterSummary.length > 0 ? `Filtering ${filterSummary} · ${base}` : base;
};

/**
 * Takes only the field it reads.
 *
 * It used to take a full `RunRecord`, and the run queue passed it a
 * `RunListRecord` — which compiled only because both aliased one hand-written
 * `RunBase`. The contract distinguishes them (`RunResponse` carries `scope` and
 * `replay`; `RunListItemResponse` carries `source_name`/`version_label`), so
 * once the types were derived from it (#737) the mismatch became visible. The
 * fix is to ask for what is used, not to widen either record.
 */
export const describeRunState = (
  record: Pick<RunRecord, "status"> & Partial<Pick<RunRecord, "refused">>,
): string => {
  // A refusal outranks the status it wears. ADR-0035 persists a refused dispatch
  // as terminal FAILED, so without this branch the queue tells an operator to go
  // "review the failure reason" of a provider that was never called — sending
  // them to debug acquisition when the remedy is a config or code key (#634).
  if (record.refused === true) {
    return "Refused before dispatch by the ADR-0030 two-key lock. Nothing was fetched — fix the key, not the provider.";
  }
  if (record.status === "pending") {
    return "Queued. Review readiness or open the run when it becomes active.";
  }
  if (record.status === "running") {
    return "Active now. Watch the pipeline sections for the next operator cue.";
  }
  if (record.status === "failed") {
    // Was "Review the failure reason in the detail page." — which stopped being
    // true twice over: the reason is now legible in the row above this sentence
    // (it used to clip at one line), and Retry is now on the row. Sending an
    // operator to another page for something in front of them is the kind of
    // stale instruction that trains people to ignore the copy.
    return "Blocked. Fix the cause, then retry.";
  }
  if (record.status === "completed") {
    return "Finished successfully. Use the detail view for audit evidence.";
  }
  return "Stopped by an operator. Review the detail page if this was unexpected.";
};

/**
 * Whether the queue row needs to spell out its state in prose.
 *
 * It did so on every row, including eight identical repetitions of "Finished
 * successfully. Use the detail view for audit evidence." — three lines each,
 * under a badge that already said `completed`. Thirteen rows came to 2,230px of
 * page, and every one of those lines was bought at the cost of vertical space
 * while CREATED, UPDATED and ACTIONS stayed off the right edge.
 *
 * A terminal state that went the way it was supposed to needs no sentence: its
 * badge is the whole message. The states that are *not* self-explanatory — the
 * ones where the operator has to decide something — keep theirs.
 */
export const runStateNeedsExplanation = (record: Pick<RunRecord, "status">): boolean =>
  record.status !== "completed";

/**
 * How long the run has been in its current, still-moving state.
 *
 * The gap this fills: a run queued thirty seconds ago and one stuck for three
 * days rendered *pixel-identically* — same badge, same "Queued. Review readiness
 * or open the run when it becomes active", no age, no dispatch attempt. The one
 * column that would let an operator infer staleness, CREATED, is also one of the
 * two clipped off the right edge at 1440px. So the queue had no staleness signal
 * at all.
 *
 * Only emitted for `pending` and `running`: on a terminal run "age" is not a
 * thing that is still accruing, and the CREATED/UPDATED columns are the right
 * place to read one.
 *
 * `now` is injected so the formatting is testable without freezing the clock.
 */
export const describeRunAge = (
  record: Pick<RunRecord, "status" | "created_at" | "started_at">,
  now: Date = new Date(),
): string | null => {
  if (record.status !== "pending" && record.status !== "running") {
    return null;
  }
  const since = record.status === "running" ? record.started_at : record.created_at;
  if (!since) {
    return null;
  }
  const elapsedMs = now.getTime() - new Date(since).getTime();
  // A negative elapsed time is clock skew between writers, not a duration we
  // know — the same reason the dashboard refuses to print one (#674). Say
  // nothing rather than "-3m".
  if (!Number.isFinite(elapsedMs) || elapsedMs < 0) {
    return null;
  }
  const verb = record.status === "running" ? "running" : "queued";
  const minutes = Math.floor(elapsedMs / 60_000);
  if (minutes < 1) {
    return `${verb} <1 min`;
  }
  if (minutes < 60) {
    return `${verb} ${minutes} min`;
  }
  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    return `${verb} ${hours}h`;
  }
  const days = Math.floor(hours / 24);
  return `${verb} ${days}d`;
};

/**
 * Past which age a still-moving run should be called out rather than merely
 * timed. Two hours is long enough that a healthy local or CI dispatch has
 * finished, and short enough that a genuinely stuck run is flagged the same
 * working session it stalls in.
 */
export const RUN_STALE_AFTER_MS = 2 * 60 * 60 * 1000;

export const runLooksStalled = (
  record: Pick<RunRecord, "status" | "created_at" | "started_at">,
  now: Date = new Date(),
): boolean => {
  if (record.status !== "pending" && record.status !== "running") {
    return false;
  }
  const since = record.status === "running" ? record.started_at : record.created_at;
  if (!since) {
    return false;
  }
  const elapsedMs = now.getTime() - new Date(since).getTime();
  return Number.isFinite(elapsedMs) && elapsedMs >= RUN_STALE_AFTER_MS;
};

export const summarizeRunFilters = (filterValues: RunQueueFilterValues): string => {
  const segments = [
    filterValues.mode ? `mode: ${String(filterValues.mode)}` : null,
    filterValues.status ? `status: ${String(filterValues.status)}` : null,
    // `false` is a real filter value here ("exclude refusals"), so this tests for
    // the boolean rather than for truthiness.
    typeof filterValues.refused === "boolean" ? `refused: ${filterValues.refused}` : null,
  ].filter((segment): segment is string => segment !== null);

  return segments.join(" · ");
};

/**
 * The run an operator should open first, or `null` when there is not one.
 *
 * `null` is the load-bearing return value. This used to end
 * `return runs[0] ?? null` — so on a queue where every run had finished it
 * picked the newest *completed* run and the list rendered an amber
 * "Open attention run · <source>" chip pointing at it. On the same dataset the
 * dashboard said "No run is failing, pending, or running… nothing needing
 * attention" and disabled its button. Two screens, one queue, opposite claims,
 * and the list was the one that was wrong: nothing about a completed run needs
 * attention. An operator who learns that the amber chip means nothing stops
 * reading it on the day it means something.
 *
 * Generic over the record shape so `RunListV2` can pass its richer
 * `RunListRecord` (which carries `source_name`) and get it back — the inlined
 * copy that existed for exactly that reason is what let the two drift.
 */
export const selectAttentionRun = <T extends Pick<RunRecord, "status">>(runs: T[]): T | null => {
  for (const status of ACTIONABLE_STATUSES) {
    const candidate = runs.find((run) => run.status === status);
    if (candidate) {
      return candidate;
    }
  }

  return null;
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
  // Only the id is read; see `describeRunState` for why this is a `Pick`.
  attentionRun: Pick<RunRecord, "run_id"> | null,
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
