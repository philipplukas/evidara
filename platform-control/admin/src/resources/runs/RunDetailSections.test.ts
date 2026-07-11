import { describe, expect, it } from "vitest";
import type { RunPipelineHealthStage } from "../../lib/admin/dataProvider";
import {
  overallSummaryByStatus,
  stageActionTarget,
  stageNextAction,
} from "./pipelineDecisionSupport";

const acquisitionStage: RunPipelineHealthStage = {
  stage: "acquisition",
  status: "blocked",
  detail: "Provider jobs are waiting on retry.",
  updated_at: "2026-04-07T10:00:00Z",
};

describe("RunDetailSections helpers", () => {
  it("describes blocked and healthy pipeline status clearly", () => {
    expect(overallSummaryByStatus("ok")).toBe("Pipeline stages are healthy.");
    expect(overallSummaryByStatus("blocked")).toBe(
      "One or more stages need remediation before the run can progress.",
    );
  });

  it("returns scan-friendly remediation guidance for blocked stages", () => {
    expect(stageNextAction(acquisitionStage)).toContain("provider jobs");
    expect(stageActionTarget(acquisitionStage, { evidenceRunbookPath: "/runbook" })).toEqual({
      label: "Jump to provider jobs",
      href: "#provider-jobs-section",
    });
  });
});
