import { afterEach, describe, expect, it, vi } from "vitest";
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
      unavailable: 1,
    });
  });

  it("prioritizes blocked health over other attention signals", () => {
    expect(
      selectDashboardAttentionRun(
        [
          {
            run_id: "run-1",
            health: { overall_status: "blocked" } as never,
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
