import { describe, expect, it } from "vitest";
import { buildRunRecord } from "../../lib/admin/__fixtures__/runs";
import { canPromoteRunToProduction, canRetryRun } from "./RunActions";

const completedPreviewRun = buildRunRecord({ mode: "preview", status: "completed" });

describe("run promotion actions", () => {
  it("allows promotion only for completed preview runs", () => {
    expect(canPromoteRunToProduction(completedPreviewRun)).toBe(true);
    expect(
      canPromoteRunToProduction({
        ...completedPreviewRun,
        mode: "production",
      }),
    ).toBe(false);
    expect(
      canPromoteRunToProduction({
        ...completedPreviewRun,
        status: "running",
        completed_at: null,
      }),
    ).toBe(false);
  });
});

/**
 * `POST /v1/runs/{id}/retry` existed since runs did and no UI called it, so the
 * queue offered CANCEL on the two states that are still moving and nothing at
 * all on the one state that has stopped and needs a decision.
 */
describe("run retry action", () => {
  it("mirrors the server's own guard: failed and cancelled only", () => {
    // `RunService.retry_run` raises InvalidStateTransitionError for anything
    // else, so offering the button elsewhere would advertise an action the API
    // rejects.
    expect(canRetryRun({ status: "failed" })).toBe(true);
    expect(canRetryRun({ status: "cancelled" })).toBe(true);
    expect(canRetryRun({ status: "completed" })).toBe(false);
    expect(canRetryRun({ status: "pending" })).toBe(false);
    expect(canRetryRun({ status: "running" })).toBe(false);
  });

  it("never overlaps with cancel", () => {
    // Cancel is for pending/running, retry for failed/cancelled: no run offers
    // both, so the pinned Actions cell holds exactly one control.
    const cancellable = ["pending", "running"] as const;
    for (const status of cancellable) {
      expect(canRetryRun({ status })).toBe(false);
    }
  });
});
