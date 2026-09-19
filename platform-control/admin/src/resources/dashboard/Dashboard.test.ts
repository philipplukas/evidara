import { afterEach, describe, expect, it, vi } from "vitest";
import { selectAttentionRun } from "../runs/RunList";
import {
  describeAttentionTarget,
  formatDuration,
  loadDashboardStats,
  selectDashboardAttentionRun,
  summarizeRecentHealth,
} from "./Dashboard";

const originalFetch = global.fetch;

const jsonResponse = (body: unknown, status: number): Response =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });

const healthyStats = {
  source_count: 2,
  total_runs: 5,
  run_by_status: { completed: 4, failed: 1 },
  total_artifacts: 9,
  recent_runs: [],
};

afterEach(() => {
  global.fetch = originalFetch;
  vi.restoreAllMocks();
});

/**
 * #623 — the dashboard is the default landing route, and every one of these
 * responses used to reach `stats.run_by_status.completed` and take down the
 * whole SPA via react-admin's error boundary. `null` is what routes the page to
 * its InlineAlert instead.
 */
describe("loadDashboardStats", () => {
  it("returns the payload when /stats is healthy", async () => {
    global.fetch = vi.fn().mockResolvedValue(jsonResponse(healthyStats, 200)) as typeof fetch;
    await expect(loadDashboardStats()).resolves.toEqual(healthyStats);
  });

  it("returns null for a 500 that carries a JSON body", async () => {
    global.fetch = vi
      .fn()
      .mockResolvedValue(jsonResponse({ detail: "Internal Server Error" }, 500)) as typeof fetch;
    await expect(loadDashboardStats()).resolves.toBeNull();
  });

  it("returns null for a 200 whose JSON is missing the counters", async () => {
    global.fetch = vi.fn().mockResolvedValue(jsonResponse({}, 200)) as typeof fetch;
    await expect(loadDashboardStats()).resolves.toBeNull();
  });

  it("returns null when the request rejects", async () => {
    global.fetch = vi.fn().mockRejectedValue(new TypeError("network")) as typeof fetch;
    await expect(loadDashboardStats()).resolves.toBeNull();
  });
});

describe("Dashboard helpers", () => {
  it("summarizes recent health probes including unavailable entries", () => {
    expect(
      summarizeRecentHealth([
        {
          run_id: "run-ok",
          health: { overall_status: "ok" } as never,
          error: null,
        },
        {
          run_id: "run-blocked",
          health: { overall_status: "blocked" } as never,
          error: null,
        },
        {
          run_id: "run-none",
          health: null,
          error: "boom",
        },
      ]),
    ).toEqual({
      ok: 1,
      blocked: 1,
      failed: 0,
      in_progress: 0,
      stalled: 0,
      unavailable: 1,
    });
  });

  it("counts a stalled run as stalled, not as unavailable", () => {
    // #951: the server reports `stalled` for a run that ended while downstream
    // stages never reported. Without a bucket of its own it falls through to
    // `unavailable` — turning a state the server did report into "we don't know",
    // which is worse than the `in_progress` it replaced.
    const summary = summarizeRecentHealth([
      {
        run_id: "run-stalled",
        health: { overall_status: "stalled" } as never,
        error: null,
      },
    ]);
    expect(summary.stalled).toBe(1);
    expect(summary.unavailable).toBe(0);
  });

  it("prioritizes blocked health over other attention signals", () => {
    expect(
      selectDashboardAttentionRun(
        [
          {
            run_id: "run-1",
            // `run_status` is not optional in the real payload — every
            // `/pipeline-health` response carries it — and this fixture used to
            // omit it, describing a response the API cannot return.
            health: { overall_status: "blocked", run_status: "running" } as never,
            error: null,
          },
        ],
        [
          {
            run_id: "run-2",
            status: "failed",
          },
        ] as never,
      ),
    ).toEqual({
      kind: "run",
      run_id: "run-1",
      reason: "blocked pipeline health",
    });
  });

  it.each([
    ["cancelled"],
    ["completed"],
  ])("never nominates a %s run, however bad its pipeline health", (runStatus) => {
    // The defect this pins, measured on a seeded stack 2026-09-07: the card
    // read "Open run_demo_cancelled first. It is the newest run with blocked
    // pipeline health." A cancelled run is terminal — nothing an operator
    // does advances it — so the landing screen's first click went somewhere
    // they could not act, while the run queue on the same data correctly
    // offered a failed run.
    expect(
      selectDashboardAttentionRun(
        [
          {
            run_id: "run-terminal",
            health: { overall_status: "blocked", run_status: runStatus } as never,
            error: null,
          },
        ],
        [] as never,
        {},
      ),
    ).toBeNull();
  });

  it("skips a terminal run and nominates the actionable one behind it", () => {
    // Stronger than the test above: it is not enough to reject the cancelled
    // run, the card has to still find the work. Filtering that returned null
    // here would trade a wrong answer for no answer.
    expect(
      selectDashboardAttentionRun(
        [
          {
            run_id: "run-cancelled",
            health: { overall_status: "blocked", run_status: "cancelled" } as never,
            error: null,
          },
          {
            run_id: "run-live",
            health: { overall_status: "blocked", run_status: "running" } as never,
            error: null,
          },
        ],
        [] as never,
        {},
      ),
    ).toEqual({
      kind: "run",
      run_id: "run-live",
      reason: "blocked pipeline health",
    });
  });

  it("agrees with the run queue about which run needs attention", () => {
    // The two selectors are the two screens that contradicted each other. They
    // now read one definition of "actionable" (`ACTIONABLE_RUN_STATUSES`), and
    // this asserts the agreement rather than trusting the shared import.
    const runs = [
      { run_id: "run-cancelled", status: "cancelled" as const },
      { run_id: "run-failed", status: "failed" as const },
    ];
    const health = runs.map((run) => ({
      run_id: run.run_id,
      health: { overall_status: "blocked", run_status: run.status } as never,
      error: null,
    }));

    const dashboardPick = selectDashboardAttentionRun(health, runs as never, {});
    const queuePick = selectAttentionRun(runs);

    expect(queuePick?.run_id).toBe("run-failed");
    expect(dashboardPick).toEqual({
      kind: "run",
      run_id: "run-failed",
      reason: "blocked pipeline health",
    });
  });

  it("falls back to recent run status when health is unavailable", () => {
    expect(
      selectDashboardAttentionRun([], [{ run_id: "run-3", status: "pending" }] as never),
    ).toEqual({
      kind: "run",
      run_id: "run-3",
      reason: "pending run status",
    });
  });
});

describe("formatDuration", () => {
  it("formats a normal elapsed time", () => {
    expect(formatDuration("2026-07-18T17:43:04.966Z", "2026-07-18T17:45:24.685Z")).toBe("2m 20s");
    expect(formatDuration("2026-07-18T17:43:04.000Z", "2026-07-18T17:43:04.273Z")).toBe("273ms");
  });

  it("returns a placeholder when either endpoint is missing", () => {
    expect(formatDuration(null, "2026-07-18T17:45:24.685Z")).toBe("-");
    expect(formatDuration("2026-07-18T17:43:04.966Z", null)).toBe("-");
  });

  it("refuses to render a negative duration", () => {
    // Live repro on the failed ZH run: completed_at (…944165Z) preceded
    // created_at (…945184Z) by 1ms, and the dashboard printed "-1ms" as if it
    // were a real measurement. A negative elapsed time is not a duration.
    expect(formatDuration("2026-07-17T20:16:20.945184Z", "2026-07-17T20:16:20.944165Z")).toBe("-");
  });

  it("refuses to render a duration from an unparseable timestamp", () => {
    expect(formatDuration("not-a-date", "2026-07-18T17:45:24.685Z")).toBe("-");
  });
});

/**
 * #670: the ATTENTION card said "No blocked or stalled run is visible yet" on a
 * screen that simultaneously rendered `failed: 1`, because the selector only
 * ever saw the 5-item `recent_runs` window and the failed run was 11th.
 */
describe("dashboard attention beyond the recent-runs window", () => {
  it("points at the failed queue when the counters disagree with the recent window", () => {
    const target = selectDashboardAttentionRun(
      [],
      // Five healthy runs — exactly what `/stats` returned in the bug report.
      [
        { run_id: "r1", status: "completed" },
        { run_id: "r2", status: "completed" },
        { run_id: "r3", status: "completed" },
        { run_id: "r4", status: "completed" },
        { run_id: "r5", status: "completed" },
      ] as never,
      { completed: 10, failed: 1 },
    );

    expect(target).toEqual({ kind: "queue", status: "failed", count: 1, reason: "failed" });
    // And it must not render as the disabled dead end it used to.
    expect(describeAttentionTarget(target).buttonLabel).toBe("Open failed queue");
  });

  it("still reports nothing to do only when the counters themselves are zero", () => {
    const target = selectDashboardAttentionRun([], [] as never, {
      completed: 10,
      failed: 0,
      pending: 0,
      running: 0,
    });

    expect(target).toBeNull();
    expect(describeAttentionTarget(target).description).toContain("not just the recent five");
  });

  it("prefers a concrete run id over the queue fallback when one is in the window", () => {
    const target = selectDashboardAttentionRun(
      [],
      [{ run_id: "run-9", status: "failed" }] as never,
      { failed: 3 },
    );

    expect(target).toEqual({ kind: "run", run_id: "run-9", reason: "failed run status" });
  });
});
