import { describe, expect, it } from "vitest";
import { describeReadinessDetail } from "../../lib/admin/readiness-messages";

describe("describeReadinessDetail", () => {
  it("returns plain-language title and action for known readiness codes", () => {
    expect(describeReadinessDetail("mode_compatible_with_version_status")).toEqual({
      title: "Version not approved for production",
      action:
        "Production runs require an approved version. Approve the selected version or switch to Preview mode.",
    });
  });

  it("falls back to generic title and action for unknown readiness codes", () => {
    expect(describeReadinessDetail("custom_code")).toEqual({
      title: "Preflight check failed",
      action: "Review the selected source/version pair and retry.",
    });
  });
});
