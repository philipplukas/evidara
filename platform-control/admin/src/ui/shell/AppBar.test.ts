import { describe, expect, it } from "vitest";
import { titleForPath } from "./AppBar";

describe("titleForPath", () => {
  it("names the runs list and detail to agree with the 'Runs' nav label", () => {
    // #520 consolidation: the app-bar header must read "Runs" (not the old
    // "Run queue"), matching the sidebar label and the page's own <h1>.
    expect(titleForPath("/runs")).toBe("Runs");
    expect(titleForPath("/runs/run_01/show")).toBe("Run detail");
  });

  it("gives Corrections and Commentary insights their own titles, not 'Control plane'", () => {
    // Bug #4: these two list pages previously fell through to the generic
    // default while every other list page showed its own name.
    expect(titleForPath("/corrections")).toBe("Corrections");
    expect(titleForPath("/corrections/cor_01/show")).toBe("Correction detail");
    expect(titleForPath("/commentary-insights")).toBe("Commentary insights");
    expect(titleForPath("/commentary-insights/ins_01/show")).toBe("Commentary insight");
  });

  it("keeps the existing list pages naming themselves", () => {
    expect(titleForPath("/sources")).toBe("Sources");
    expect(titleForPath("/authorities")).toBe("Authorities");
    expect(titleForPath("/jurisdictions")).toBe("Jurisdictions");
    expect(titleForPath("/preview-review")).toBe("Preview approvals");
    expect(titleForPath("/")).toBe("Dashboard");
  });

  it("falls back to 'Control plane' only for unknown routes", () => {
    expect(titleForPath("/something-unmapped")).toBe("Control plane");
  });
});
