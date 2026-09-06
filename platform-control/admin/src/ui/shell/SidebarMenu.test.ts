import { describe, expect, it } from "vitest";
import { DEFAULT_EXTRA_ITEMS } from "./AppShell";
import { resourceLinkIsActive } from "./SidebarMenu";

describe("resourceLinkIsActive", () => {
  const workflowExactPaths = ["/sources/create", "/authorities/create", "/jurisdictions/create"];

  it("keeps a resource link active on its list and detail routes", () => {
    expect(resourceLinkIsActive(true, "/authorities", workflowExactPaths)).toBe(true);
    expect(resourceLinkIsActive(true, "/authorities/auth_fedlex", workflowExactPaths)).toBe(true);
  });

  it("yields to the '… setup' workflow item on the resource's own create route", () => {
    // Bug #6: on /authorities/create both the "Authorities" resource link
    // (prefix match) and the "Authority setup" workflow link (exact match)
    // used to highlight. The resource link must stand down there.
    expect(resourceLinkIsActive(true, "/authorities/create", workflowExactPaths)).toBe(false);
    expect(resourceLinkIsActive(true, "/sources/create", workflowExactPaths)).toBe(false);
    expect(resourceLinkIsActive(true, "/jurisdictions/create", workflowExactPaths)).toBe(false);
  });

  it("never activates a link the router already considers inactive", () => {
    expect(resourceLinkIsActive(false, "/authorities/create", workflowExactPaths)).toBe(false);
  });
});

describe("sidebar nav consolidation (#520)", () => {
  it("no longer registers a separate 'Run queue' / runs preview nav entry", () => {
    // Bug #2: runs are reached through the single "Runs" resource link now,
    // not a duplicate "Run queue" -> /runs-v2 preview item.
    expect(DEFAULT_EXTRA_ITEMS.some((item) => item.to.includes("runs"))).toBe(false);
    expect(DEFAULT_EXTRA_ITEMS.some((item) => item.label === "Run queue")).toBe(false);
    expect(DEFAULT_EXTRA_ITEMS.some((item) => item.kind === "preview")).toBe(false);
  });

  /**
   * The three "… setup" entries were deep links to `/sources/create`,
   * `/authorities/create` and `/jurisdictions/create` — the same routes as three
   * resource pages, not workflows. `resourceLinkIsActive` exists purely because
   * of that collision. Creating a record now belongs on its own resource page;
   * WORKFLOWS carries only the task that genuinely crosses nav groups.
   */
  it("carries one real workflow, not create-form deep links", () => {
    expect(DEFAULT_EXTRA_ITEMS.map((item) => item.to)).toEqual(["/workflows/onboard"]);
  });

  it("no longer points any workflow entry at a resource create form", () => {
    expect(DEFAULT_EXTRA_ITEMS.some((item) => item.to.endsWith("/create"))).toBe(false);
  });

  /**
   * Prefix-match, not exact: an open project lives at
   * `/workflows/onboard/:projectId`, and an `exact: true` entry would go dark
   * the moment an operator opened one — i.e. for the whole time they are
   * actually using it.
   */
  it("keeps the onboarding entry highlighted on an open project", () => {
    const onboard = DEFAULT_EXTRA_ITEMS.find((item) => item.to === "/workflows/onboard");
    expect(onboard?.exact).toBe(false);
  });
});
