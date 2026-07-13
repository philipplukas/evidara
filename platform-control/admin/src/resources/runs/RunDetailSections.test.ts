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
      kind: "section",
      label: "Jump to provider jobs",
      sectionId: "provider-jobs-section",
    });
  });

  // Regression: in-page targets must stay `kind: "section"` and never become a
  // `#…` href. The admin runs on a HashRouter, so a fragment href is a route —
  // clicking "Jump to DI processing" navigated to "page not found".
  it("points in-page stage targets at a section id, not a hash href", () => {
    const target = stageActionTarget(
      { ...acquisitionStage, stage: "document_intelligence" },
      { evidenceRunbookPath: "/runbook" },
    );
    expect(target).toEqual({
      kind: "section",
      label: "Jump to DI processing",
      sectionId: "di-processing-status-section",
    });
  });

  it("keeps verification/runbook targets as external hrefs", () => {
    expect(
      stageActionTarget(
        { ...acquisitionStage, stage: "search" },
        { legalSearchUrl: "https://search.example", evidenceRunbookPath: "/runbook" },
      ),
    ).toEqual({
      kind: "external",
      label: "Open legal-search verification",
      href: "https://search.example",
    });
  });
});
