/**
 * What is left to test in the browser after #908: the DOM concerns.
 *
 * The stage projection and the four decision-support questions were tested here
 * and are now tested in `platform-control/tests/unit/test_run_pipeline_health.py`,
 * because they are computed there. `run-decision-support.guard.test.ts` is what
 * stops them coming back.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  scrollToInPageSection,
  sectionIdFromAnchor,
  stageActionTarget,
} from "./run-decision-support";

describe("stageActionTarget", () => {
  /**
   * Stays client-side deliberately: the target is an in-page anchor into THIS
   * page's DOM, which no server can know about.
   */
  it("routes each stage to the section that explains it", () => {
    const runbook = { evidenceRunbookPath: "/runbook" };
    expect(stageActionTarget({ stage: "acquisition" }, runbook)).toEqual({
      label: "Jump to provider jobs",
      href: "#provider-jobs-section",
    });
    expect(stageActionTarget({ stage: "document_intelligence" }, runbook)).toEqual({
      label: "Jump to DI processing",
      href: "#di-processing-status-section",
    });
  });

  it("falls back to the runbook when legal-search is not configured", () => {
    expect(stageActionTarget({ stage: "search" }, { evidenceRunbookPath: "/runbook" })).toEqual({
      label: "Open evidence runbook",
      href: "/runbook",
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
