import { describe, expect, it } from "vitest";
import type { RunRecord } from "../../lib/admin/dataProvider";
import type { LegalSearchHandoff } from "../../lib/admin/navigationContext";
import { buildRunHandoffGuidance } from "./RunShow";

const baseRun: RunRecord = {
  id: "run-123",
  run_id: "run-123",
  source_id: "source-1",
  source_version_id: "version-1",
  mode: "production",
  status: "running",
  started_at: "2026-04-10T09:00:00Z",
  completed_at: null,
  artifacts_count: 3,
  captured_resources_count: 12,
  failure_reason: null,
  created_at: "2026-04-10T08:59:00Z",
  updated_at: "2026-04-10T09:15:00Z",
};

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
