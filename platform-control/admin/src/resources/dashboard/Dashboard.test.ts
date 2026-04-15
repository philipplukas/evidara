import { describe, expect, it } from "vitest";
import { selectAttentionRun, summarizeRecentHealth } from "./Dashboard";

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
      selectAttentionRun(
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
    expect(selectAttentionRun([], [{ run_id: "run-3", status: "pending" }] as never)).toEqual({
      run_id: "run-3",
      reason: "pending run status",
    });
  });
});
