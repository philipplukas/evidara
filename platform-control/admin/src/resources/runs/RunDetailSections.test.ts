import { afterEach, describe, expect, it, vi } from "vitest";
import type { RunPipelineHealthStage } from "../../lib/admin/dataProvider";
import {
  overallSummaryByStatus,
  scrollToInPageSection,
  sectionIdFromAnchor,
  stageActionTarget,
  stageNextAction,
} from "./RunDetailSections";

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
