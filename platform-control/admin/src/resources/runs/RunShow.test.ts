import { describe, expect, it } from "vitest";
import { buildRunRecord } from "../../lib/admin/__fixtures__/runs";
import type { LegalSearchHandoff } from "../../lib/admin/navigationContext";
import { buildRunHandoffGuidance } from "./RunShow";
import { formatDuration } from "./RunShowV2";

const baseRun = buildRunRecord({
  id: "run-123",
  run_id: "run-123",
  mode: "production",
  status: "running",
  started_at: "2026-04-10T09:00:00Z",
  completed_at: null,
  artifacts_count: 3,
  created_at: "2026-04-10T08:59:00Z",
  updated_at: "2026-04-10T09:15:00Z",
});

const handoff: LegalSearchHandoff = {
  hasOrigin: true,
  returnToUrl: "http://localhost:3101/?q=Art.%20754",
  query: "Art. 754 OR Verantwortlichkeit",
  scopeLabel: "Swiss federal law",
  selectedId: "decision-1",
};

describe("RunShow handoff guidance", () => {
  it("frames the legal-search context for run detail operators", () => {
    const guidance = buildRunHandoffGuidance(baseRun, handoff);

    expect(guidance?.whyYouAreHere).toContain("legal search");
    expect(guidance?.whyYouAreHere).toContain("Selected item: decision-1");
    expect(guidance?.whatToCheckNext).toContain("selected item (decision-1)");
    expect(guidance?.whatToCheckNext).toContain("source/version pair");
  });
});

describe("formatDuration", () => {
  it("formats a normal elapsed time", () => {
    expect(
      formatDuration({
        ...baseRun,
        started_at: "2026-07-18T17:45:24.412Z",
        completed_at: "2026-07-18T17:45:24.685Z",
      }),
    ).toBe("273ms");
  });

  it("returns a placeholder when the run has not finished", () => {
    expect(formatDuration({ ...baseRun, completed_at: null })).toBe("\u2014");
  });

  it("refuses to render a negative duration", () => {
    // The failed ZH repro run rendered "Duration -1ms" on the run detail page:
    // completed_at preceded started_at. Say nothing rather than say something
    // impossible.
    expect(
      formatDuration({
        ...baseRun,
        started_at: "2026-07-17T20:16:20.945182Z",
        completed_at: "2026-07-17T20:16:20.944165Z",
      }),
    ).toBe("\u2014");
  });
});
