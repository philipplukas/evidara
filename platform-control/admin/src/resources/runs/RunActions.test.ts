import { describe, expect, it } from "vitest";
import { buildRunRecord } from "../../lib/admin/__fixtures__/runs";
import { canPromoteRunToProduction } from "./RunActions";

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
