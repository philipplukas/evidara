import { afterEach, describe, expect, it, vi } from "vitest";
import type { RunPipelineHealth, RunPipelineHealthStage } from "../../lib/admin/dataProvider";
import {
  overallSummaryByStatus,
  projectPipelineStages,
  scrollToInPageSection,
  sectionIdFromAnchor,
  stageActionTarget,
  stageNeedsAction,
  stageNextAction,
} from "./run-decision-support";

const acquisitionStage: RunPipelineHealthStage = {
  stage: "acquisition",
  status: "blocked",
  detail: "Provider jobs are waiting on retry.",
  updated_at: "2026-04-07T10:00:00Z",
};

const health = (
  runStatus: RunPipelineHealth["run_status"],
  stages: RunPipelineHealthStage[],
): RunPipelineHealth => ({
  run_id: "run_01",
  source_id: "src_01",
  source_version_id: "sv_01",
  mode: "production",
  run_status: runStatus,
  overall_status: runStatus === "completed" ? "ok" : "blocked",
  stages,
  processing_status_event_count: 0,
  document_lifecycle_event_count: 0,
});

const pendingStage = (stage: RunPipelineHealthStage["stage"]): RunPipelineHealthStage => ({
  stage,
  status: "pending",
  detail: "Awaiting DI processing signal before projection stage starts.",
  updated_at: null,
});

describe("run pipeline stage helpers", () => {
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

describe("projectPipelineStages", () => {
  it("marks stages that can no longer run as not applicable on a failed run", () => {
    const stages = projectPipelineStages(
      health("failed", [
        { ...acquisitionStage, status: "failed" },
        pendingStage("projection"),
        pendingStage("search"),
      ]),
    );

    expect(stages.map((stage) => stage.status)).toEqual([
      "failed",
      "not_applicable",
      "not_applicable",
    ]);
    // The API's "awaiting …" copy implies work is still coming; it is not.
    expect(stages[1].detail).toBe("Not applicable — the run failed before this stage could start.");
    expect(stageNeedsAction(stages[1].status)).toBe(false);
    expect(stageNextAction(stages[1])).toBe("No action — this stage will not run for this run.");
  });

  it("says cancelled, not failed, for a cancelled run", () => {
    const [stage] = projectPipelineStages(health("cancelled", [pendingStage("search")]));

    expect(stage.status).toBe("not_applicable");
    expect(stage.detail).toBe(
      "Not applicable — the run was cancelled before this stage could start.",
    );
  });

  it("leaves pending alone while the run can still progress", () => {
    // Only terminal failures get the treatment: on a run that is still moving,
    // "pending" is the honest state and downstream work really is coming.
    for (const runStatus of ["pending", "running", "completed"] as const) {
      const stages = projectPipelineStages(health(runStatus, [pendingStage("projection")]));
      expect(stages[0].status).toBe("pending");
      expect(stages[0].detail).toContain("Awaiting DI processing signal");
    }
  });

  it("never rewrites a stage that already reported real progress", () => {
    const stages = projectPipelineStages(
      health("failed", [
        { ...acquisitionStage, status: "ok" },
        { ...acquisitionStage, stage: "document_intelligence", status: "blocked" },
      ]),
    );

    expect(stages.map((stage) => stage.status)).toEqual(["ok", "blocked"]);
    expect(stageNeedsAction("blocked")).toBe(true);
    expect(stageNeedsAction("ok")).toBe(false);
  });
});

describe("in-page jump helpers", () => {
  afterEach(() => {
    document.body.innerHTML = "";
    vi.restoreAllMocks();
  });

  it("strips the leading hash so an anchor href resolves to a DOM id", () => {
    expect(sectionIdFromAnchor("#di-processing-status-section")).toBe(
      "di-processing-status-section",
    );
    // Already-bare ids pass through unchanged.
    expect(sectionIdFromAnchor("document-lifecycle-section")).toBe("document-lifecycle-section");
  });

  it("scrolls to the target section WITHOUT driving the HashRouter", () => {
    const target = document.createElement("section");
    target.id = "di-processing-status-section";
    const scrollIntoView = vi.fn();
    // jsdom does not implement scrollIntoView; provide a spy to observe the call.
    target.scrollIntoView = scrollIntoView;
    document.body.appendChild(target);

    const hashBefore = window.location.hash;
    scrollToInPageSection("#di-processing-status-section");

    // The whole point of the fix: scroll happens, but the location hash is
    // never mutated (a `#...` hash would bounce the run detail to Not Found).
    expect(scrollIntoView).toHaveBeenCalledWith({ behavior: "smooth", block: "start" });
    expect(window.location.hash).toBe(hashBefore);
  });

  it("no-ops safely when the target section is absent", () => {
    expect(() => scrollToInPageSection("#missing-section")).not.toThrow();
    expect(window.location.hash).toBe("");
  });
});
