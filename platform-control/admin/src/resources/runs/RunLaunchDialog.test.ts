import { describe, expect, it } from "vitest";
import { describeReadinessAction } from "./RunLaunchDialog";

describe("describeReadinessAction", () => {
  it("returns a direct next action for known readiness codes", () => {
    expect(describeReadinessAction("mode_compatible_with_version_status")).toBe(
      "For production runs, approve the selected version before launch.",
    );
  });

  it("falls back to a generic remediation prompt for unknown readiness codes", () => {
    expect(describeReadinessAction("custom_code")).toBe(
      "Review the selected source/version pair and retry.",
    );
  });
});
