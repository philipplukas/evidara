import { describe, expect, it, vi } from "vitest";
import { createOperatorJourneyEvent } from "./operatorJourneyTelemetry";

describe("operatorJourneyTelemetry", () => {
  it("builds structured event payloads with timestamp", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-04-07T10:00:00.000Z"));

    const event = createOperatorJourneyEvent("preflight_blocked", {
      run_id: "run_01",
      readiness_codes: ["acquisition_seed_present"],
    });

    expect(event).toEqual({
      event: "preflight_blocked",
      occurred_at: "2026-04-07T10:00:00.000Z",
      run_id: "run_01",
      readiness_codes: ["acquisition_seed_present"],
    });
    vi.useRealTimers();
  });
});
