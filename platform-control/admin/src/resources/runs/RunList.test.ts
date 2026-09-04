import { describe, expect, it } from "vitest";
import { buildRunRecord } from "../../lib/admin/__fixtures__/runs";
import {
  describeQueueScope,
  describeRunAge,
  describeRunState,
  formatQueueCount,
  getRunQueueKeyboardShortcutAction,
  isKeyboardShortcutInputTarget,
  resolveQueueCountScope,
  runLooksStalled,
  runStateNeedsExplanation,
  selectAttentionRun,
  summarizeRunFilters,
} from "./RunList";

const completedRun = buildRunRecord({
  id: "run_completed",
  run_id: "run_completed",
  source_id: "src_01",
  source_version_id: "sv_01",
  mode: "production",
  status: "completed",
});

const pendingRun = buildRunRecord({
  ...completedRun,
  id: "run_pending",
  run_id: "run_pending",
  status: "pending",
  started_at: null,
  completed_at: null,
});

const runningRun = buildRunRecord({
  ...completedRun,
  id: "run_running",
  run_id: "run_running",
  status: "running",
  started_at: "2026-04-15T09:10:00Z",
  completed_at: null,
});

const failedRun = buildRunRecord({
  ...completedRun,
  id: "run_failed",
  run_id: "run_failed",
  status: "failed",
  failure_reason: "Provider jobs were throttled.",
  started_at: "2026-04-15T09:05:00Z",
  completed_at: null,
});

describe("RunList helpers", () => {
  it("summarizes active filters for the operator inbox", () => {
    expect(summarizeRunFilters({})).toBe("");
    expect(summarizeRunFilters({ mode: "production", status: "pending" })).toBe(
      "mode: production · status: pending",
    );
  });

  it("prioritizes failed runs over running and pending work", () => {
    expect(selectAttentionRun([completedRun, pendingRun, runningRun, failedRun])).toBe(failedRun);
    expect(selectAttentionRun([completedRun, pendingRun, runningRun])).toBe(runningRun);
    expect(selectAttentionRun([completedRun, pendingRun])).toBe(pendingRun);
  });

  it("reports no attention run when nothing is actionable", () => {
    // The defect this replaces: the selector fell back to `runs[0]`, so a queue
    // of five completed runs produced an amber "Open attention run" chip
    // pointing at a completed run — on the same data where the dashboard
    // correctly reported nothing needing attention.
    expect(selectAttentionRun([completedRun])).toBeNull();
    expect(selectAttentionRun([])).toBeNull();
  });

  it("describes the queue state in operator language", () => {
    expect(describeRunState(failedRun)).toBe("Blocked. Fix the cause, then retry.");
    expect(describeRunState(completedRun)).toContain("Finished successfully");
  });

  it("ignores slash shortcuts inside text-entry targets", () => {
    expect(
      isKeyboardShortcutInputTarget({
        tagName: "input",
      } as unknown as EventTarget),
    ).toBe(true);
    expect(
      isKeyboardShortcutInputTarget({
        tagName: "div",
        isContentEditable: true,
      } as unknown as EventTarget),
    ).toBe(true);
    expect(isKeyboardShortcutInputTarget({ tagName: "button" } as unknown as EventTarget)).toBe(
      false,
    );
    expect(
      isKeyboardShortcutInputTarget({
        tagName: "select",
      } as unknown as EventTarget),
    ).toBe(true);
  });

  it("maps slash to attention focus and O to opening the attention run", () => {
    expect(
      getRunQueueKeyboardShortcutAction(
        {
          key: "/",
          altKey: false,
          ctrlKey: false,
          metaKey: false,
          defaultPrevented: false,
        } as Pick<KeyboardEvent, "altKey" | "ctrlKey" | "defaultPrevented" | "key" | "metaKey">,
        null,
        failedRun,
      ),
    ).toEqual({ type: "focus-attention" });

    expect(
      getRunQueueKeyboardShortcutAction(
        {
          key: "o",
          altKey: false,
          ctrlKey: false,
          metaKey: false,
          defaultPrevented: false,
        } as Pick<KeyboardEvent, "altKey" | "ctrlKey" | "defaultPrevented" | "key" | "metaKey">,
        null,
        failedRun,
      ),
    ).toEqual({ type: "open-attention", runId: "run_failed" });

    expect(
      getRunQueueKeyboardShortcutAction(
        {
          key: "o",
          altKey: false,
          ctrlKey: false,
          metaKey: false,
          defaultPrevented: false,
        } as Pick<KeyboardEvent, "altKey" | "ctrlKey" | "defaultPrevented" | "key" | "metaKey">,
        { tagName: "input" } as unknown as EventTarget,
        failedRun,
      ),
    ).toBeNull();
  });
});

/**
 * #669: with platform-control down the queue rendered
 * "Pending 0 · Running 0 · Completed 0 · Failed 0 · Cancelled 0 · 0 runs in view"
 * over a real 10-completed / 1-failed queue. Zero and unknown must not render
 * identically.
 */
describe("queue count honesty during an outage", () => {
  it("reports counts as unknown — not zero — when the list query failed", () => {
    const scope = resolveQueueCountScope({
      hasError: true,
      isPending: false,
      loadedCount: 0,
      total: undefined,
    });

    expect(scope).toBe("unknown");
    expect(formatQueueCount(0, scope)).toBe("—");
    expect(
      describeQueueScope({ scope, loadedCount: 0, total: undefined, filterSummary: "" }),
    ).toContain("not zeros");
  });

  it("reports a genuinely empty queue as zero", () => {
    const scope = resolveQueueCountScope({
      hasError: false,
      isPending: false,
      loadedCount: 0,
      total: 0,
    });

    expect(scope).toBe("complete");
    expect(formatQueueCount(0, scope)).toBe("0");
  });

  it("flags counts that only describe the loaded page", () => {
    const scope = resolveQueueCountScope({
      hasError: false,
      isPending: false,
      loadedCount: 25,
      total: 120,
    });

    expect(scope).toBe("partial");
    expect(describeQueueScope({ scope, loadedCount: 25, total: 120, filterSummary: "" })).toBe(
      "Showing 25 of 120 runs · counts describe this page only",
    );
  });

  it("does not claim counts while the first page is still loading", () => {
    expect(
      resolveQueueCountScope({
        hasError: false,
        isPending: true,
        loadedCount: 0,
        total: undefined,
      }),
    ).toBe("unknown");
  });
});

/**
 * A pending run and a stalled run rendered pixel-identically: same badge, same
 * "Queued. Review readiness…" sentence, no age. The `CREATED` column that would
 * let an operator infer staleness is one of the two clipped off the right edge
 * at 1440px, so the queue carried no staleness signal at all.
 */
describe("run age and staleness", () => {
  const now = new Date("2026-04-15T10:00:00Z");

  it("ages a pending run from when it was created", () => {
    const queued = { ...pendingRun, created_at: "2026-04-15T09:26:00Z" };
    expect(describeRunAge(queued, now)).toBe("queued 34 min");
  });

  it("ages a running run from when it started, not when it was created", () => {
    // A run that sat in the queue for an hour and has been running for five
    // minutes is a five-minute-old *run*, not an hour-old one.
    const running = {
      ...runningRun,
      created_at: "2026-04-15T09:00:00Z",
      started_at: "2026-04-15T09:55:00Z",
    };
    expect(describeRunAge(running, now)).toBe("running 5 min");
  });

  it("scales to hours and days", () => {
    expect(describeRunAge({ ...pendingRun, created_at: "2026-04-15T07:00:00Z" }, now)).toBe(
      "queued 3h",
    );
    expect(describeRunAge({ ...pendingRun, created_at: "2026-04-12T10:00:00Z" }, now)).toBe(
      "queued 3d",
    );
  });

  it("says nothing for a terminal run — its age is not still accruing", () => {
    expect(describeRunAge(completedRun, now)).toBeNull();
    expect(describeRunAge(failedRun, now)).toBeNull();
  });

  it("refuses to print a negative duration from clock skew", () => {
    // Same rule as the dashboard's `formatDuration` (#674): an impossible
    // number is worse than no number.
    expect(describeRunAge({ ...pendingRun, created_at: "2026-04-15T11:00:00Z" }, now)).toBeNull();
  });

  it("flags a run that has sat in a moving state for over two hours", () => {
    expect(runLooksStalled({ ...pendingRun, created_at: "2026-04-15T09:30:00Z" }, now)).toBe(false);
    expect(runLooksStalled({ ...pendingRun, created_at: "2026-04-15T07:00:00Z" }, now)).toBe(true);
    // A completed run is not stalled, however old.
    expect(runLooksStalled({ ...completedRun, created_at: "2026-01-01T00:00:00Z" }, now)).toBe(
      false,
    );
  });
});

describe("runStateNeedsExplanation", () => {
  it("drops the sentence only where the badge already says everything", () => {
    // Eight identical three-line repetitions of "Finished successfully. Use the
    // detail view for audit evidence." made the 13-row list 2,230px tall — space
    // paid for while ACTIONS stayed clipped off the right edge.
    expect(runStateNeedsExplanation(completedRun)).toBe(false);
    for (const run of [pendingRun, runningRun, failedRun]) {
      expect(runStateNeedsExplanation(run)).toBe(true);
    }
  });
});
