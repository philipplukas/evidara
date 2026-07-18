import { afterEach, describe, expect, it, vi } from "vitest";
import {
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
      run_id: "run-1",
      reason: "blocked pipeline health",
    });
  });

  it("falls back to recent run status when health is unavailable", () => {
    expect(
      selectDashboardAttentionRun([], [{ run_id: "run-3", status: "pending" }] as never),
    ).toEqual({
      run_id: "run-3",
      reason: "pending run status",
    });
  });
});
