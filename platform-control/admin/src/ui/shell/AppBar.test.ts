import { describe, expect, it } from "vitest";
import { NAV_GROUPS } from "../../domain/navGroups";
import { DEFAULT_SUBTITLE, subtitleForPath, titleForPath } from "./AppBar";

describe("titleForPath", () => {
  it("names the runs list and detail to agree with the 'Runs' nav label", () => {
    // #520 consolidation: the app-bar header must read "Runs" (not the old
    // "Run queue"), matching the sidebar label and the page's own <h1>.
    expect(titleForPath("/runs")).toBe("Runs");
    expect(titleForPath("/runs/run_01/show")).toBe("Run detail");
  });

  it("gives Corrections its own title, not 'Control plane'", () => {
    // Bug #4: this list page previously fell through to the generic default
    // while every other list page showed its own name.
    expect(titleForPath("/corrections")).toBe("Corrections");
    expect(titleForPath("/corrections/cor_01/show")).toBe("Correction detail");
  });

  it("names every entry the sidebar can reach", () => {
    /**
     * Derived from NAV_GROUPS, not hand-listed, so it cannot drift.
     *
     * Coverage, Blueprints and the onboarding wizard were all missing from the
     * map and showed the generic "Control plane / Source lifecycle, approval
     * state, and run operations." — three of eight nav entries, measured on the
     * live app. A hand-written list of expectations would have gone stale the
     * same way the map did.
     */
    const reachable = NAV_GROUPS.flatMap((group) => group.resources);
    for (const resource of reachable) {
      expect(titleForPath(`/${resource}`), `no title mapped for /${resource}`).not.toBe(
        "Control plane",
      );
      expect(subtitleForPath(`/${resource}`), `no subtitle mapped for /${resource}`).not.toBe(
        DEFAULT_SUBTITLE,
      );
    }
    // The wizard is a CustomRoute rather than a resource, so it is not in
    // NAV_GROUPS — but the sidebar renders it, so it is named here explicitly.
    expect(titleForPath("/workflows/onboard")).toBe("Onboard a source");
    expect(subtitleForPath("/workflows/onboard")).not.toBe(DEFAULT_SUBTITLE);
  });

  it("does not name a route the app cannot reach", () => {
    // `commentary-insights` is PARKED (`AdminApp.tsx`): its <Resource> is
    // removed, so nothing navigates there. It had a mapping while three
    // reachable views did not — a map that describes what the app used to have
    // is how you stop noticing what it does have.
    expect(titleForPath("/commentary-insights")).toBe("Control plane");
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

describe("subtitleForPath", () => {
  it("stops describing run operations on pages that are not runs", () => {
    // The header used to hardcode the runs-flavoured default everywhere, so
    // Jurisdictions/Sources/Corrections all claimed to be about run operations.
    for (const path of ["/jurisdictions", "/sources", "/corrections", "/authorities"]) {
      expect(subtitleForPath(path)).not.toBe(DEFAULT_SUBTITLE);
    }
    expect(subtitleForPath("/jurisdictions")).toContain("jurisdiction");
    expect(subtitleForPath("/sources")).toContain("Source");
    expect(subtitleForPath("/corrections")).toContain("corrections");
  });

  it("distinguishes the runs list from a single run detail", () => {
    expect(subtitleForPath("/runs")).toBe("Launch, monitor, and cancel acquisition runs.");
    expect(subtitleForPath("/runs/run_01/show")).toContain("single run");
  });

  it("gives every titled area its own subtitle", () => {
    const titledPaths = [
      "/",
      "/runs",
      "/sources",
      "/authorities",
      "/jurisdictions",
      "/preview-review",
      "/commentary-insights",
      "/corrections",
    ];
    const subtitles = titledPaths.map(subtitleForPath);
    expect(new Set(subtitles).size).toBe(titledPaths.length);
  });

  it("falls back to the generic app description for unknown routes", () => {
    expect(subtitleForPath("/something-unmapped")).toBe(DEFAULT_SUBTITLE);
  });
});
