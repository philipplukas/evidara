import { afterEach, describe, expect, it, vi } from "vitest";
import { describeReadinessDetail } from "../../lib/admin/readiness-messages";
import { buildPreflightRetryPayload } from "./RunLaunchDialog";

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

describe("buildPreflightRetryPayload", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("carries the current form-state context and the previous error message", () => {
    const payload = buildPreflightRetryPayload(
      {
        source_id: "source-42",
        source_version_id: "version-7",
        mode: "production",
      },
      "Upstream auth token expired",
    );

    expect(payload).toEqual({
      source_id: "source-42",
      source_version_id: "version-7",
      mode: "production",
      previous_error_message: "Upstream auth token expired",
    });
  });

  it("normalizes a missing previous error message to null", () => {
    const payload = buildPreflightRetryPayload(
      {
        source_id: "source-1",
        source_version_id: "version-1",
        mode: "preview",
      },
      null,
    );

    expect(payload.previous_error_message).toBeNull();
  });
});

describe("preflight retry telemetry", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    if (typeof globalThis !== "undefined") {
      (globalThis as { window?: unknown }).window = undefined;
    }
  });

  it("emits a preflight_retry event with the retry payload shape", async () => {
    // Polyfill a minimal window so emitOperatorJourneyEvent can buffer events.
    (globalThis as { window?: { __EVIDARA_OPERATOR_JOURNEY_EVENTS__?: unknown[] } }).window = {};

    const infoSpy = vi.spyOn(console, "info").mockImplementation(() => {});

    const { emitOperatorJourneyEvent } = await import("../../lib/admin/operatorJourneyTelemetry");

    const payload = buildPreflightRetryPayload(
      {
        source_id: "source-1",
        source_version_id: "version-1",
        mode: "preview",
      },
      "transient network error",
    );

    const event = emitOperatorJourneyEvent("preflight_retry", payload);

    expect(event.event).toBe("preflight_retry");
    expect(event.source_id).toBe("source-1");
    expect(event.source_version_id).toBe("version-1");
    expect(event.mode).toBe("preview");
    expect(event.previous_error_message).toBe("transient network error");
    expect(typeof event.occurred_at).toBe("string");
    expect(infoSpy).toHaveBeenCalledWith(
      "[operator-journey]",
      expect.stringContaining("preflight_retry"),
    );
  });
});
