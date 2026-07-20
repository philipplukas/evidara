import { describe, expect, it } from "vitest";
import { runModeToLevel } from "../resources/shared/statusLevels";
import { describeRunMode, runModeLabel } from "./runMode";

describe("runModeLabel", () => {
  it("names an acceptance run as itself, not as a preview", () => {
    // #743: three render sites used `mode === "production" ? "Production" : "Preview"`,
    // so an acceptance run was labelled Preview — falsifying the claim that the
    // mode is recorded so it "can never be mistaken for production ingest".
    expect(runModeLabel("acceptance")).toBe("Acceptance");
    expect(runModeLabel("preview")).toBe("Preview");
    expect(runModeLabel("production")).toBe("Production");
  });

  it("echoes an unrecognised mode rather than falling back to a familiar label", () => {
    // Defaulting to "Preview" for anything unknown is exactly how the acceptance
    // mode got mislabelled. A mode this build does not know must look unknown.
    expect(runModeLabel("something_new")).toBe("Unknown (something_new)");
    // Inherited Object.prototype keys must not resolve to a descriptor —
    // `"constructor" in RUN_MODES` is true, which would render an empty badge.
    expect(runModeLabel("constructor")).toBe("Unknown (constructor)");
    expect(runModeLabel("toString")).toBe("Unknown (toString)");
    expect(runModeLabel(undefined)).toBe("Unknown");
    expect(runModeLabel(null)).toBe("Unknown");
  });
});

describe("describeRunMode", () => {
  it("keeps the caveat that an acceptance pass turns no keys", () => {
    // The label alone loses what an operator needs before flipping `enabled`.
    const detail = describeRunMode("acceptance").detail;
    expect(detail).toContain("not production ingest");
    expect(detail).toContain("does not imply either key is turned");
  });
});

describe("runModeToLevel", () => {
  it("does not give an acceptance run the same calm tone as a preview", () => {
    // An acceptance run reaches a live portal on a provider with no accepted
    // evidence; a preview only runs on a template both keys already cleared.
    expect(runModeToLevel("acceptance")).toBe("degraded");
    expect(runModeToLevel("preview")).toBe("info");
    expect(runModeToLevel("production")).toBe("healthy");
  });
});
