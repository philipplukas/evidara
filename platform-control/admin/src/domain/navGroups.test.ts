import { describe, expect, it } from "vitest";
import { groupForResource, groupResources, NAV_GROUPS, UNGROUPED_ID } from "./navGroups";
import { ResourceName } from "./resourceNames";

/**
 * Every resource `AdminApp.tsx` registers with a list view. Kept as a literal
 * rather than imported from the component, so that adding a `<Resource>` without
 * placing it in a nav group fails HERE with a clear message instead of silently
 * appearing under "More" in the running app.
 */
const REGISTERED_WITH_LIST = [
  ResourceName.Jurisdictions,
  ResourceName.Authorities,
  ResourceName.Sources,
  ResourceName.BlueprintTemplates,
  ResourceName.PreviewReview,
  ResourceName.Runs,
  ResourceName.Corrections,
  ResourceName.AcquisitionCoverage,
];

describe("NAV_GROUPS", () => {
  it("claims every registered resource — nothing falls through to More", () => {
    const unclaimed = REGISTERED_WITH_LIST.filter((name) => groupForResource(name) === undefined);
    expect(unclaimed).toEqual([]);
  });

  it("does not claim a resource twice", () => {
    const all = NAV_GROUPS.flatMap((group) => group.resources);
    expect(all.length).toBe(new Set(all).size);
  });

  it("puts Blueprints before Sources — a source version instantiates a template", () => {
    const build = NAV_GROUPS.find((group) => group.id === "build");
    expect(build?.resources).toEqual([ResourceName.BlueprintTemplates, ResourceName.Sources]);
  });

  it("no longer carries commentary insights, which is parked", () => {
    const all = NAV_GROUPS.flatMap((group) => group.resources);
    expect(all).not.toContain(ResourceName.CommentaryInsights);
  });
});

describe("groupResources", () => {
  const stub = (name: string) => [name, { name }] as [string, { name: string }];

  it("returns groups in loop order with their resources ordered", () => {
    const grouped = groupResources(REGISTERED_WITH_LIST.map(stub));
    expect(grouped.map((g) => g.id)).toEqual(["scope", "build", "verify", "learn"]);
    expect(grouped[0]?.items.map((i) => i.name)).toEqual([
      ResourceName.Jurisdictions,
      ResourceName.Authorities,
    ]);
  });

  it("omits a group whose resources are not registered", () => {
    const grouped = groupResources([stub(ResourceName.Runs)]);
    expect(grouped.map((g) => g.id)).toEqual(["verify"]);
  });

  /**
   * The guard that matters: an unclassified resource must still be reachable.
   * Silent disappearance from navigation is worse than an ugly section — the
   * operator concludes the capability does not exist.
   *
   * Remove the leftovers block in `groupResources` and this fails.
   */
  it("surfaces an unclassified resource under More rather than dropping it", () => {
    const grouped = groupResources([stub(ResourceName.Runs), stub("brand-new-thing")]);
    const more = grouped.find((g) => g.id === UNGROUPED_ID);
    expect(more).toBeDefined();
    expect(more?.items.map((i) => i.name)).toEqual(["brand-new-thing"]);
  });
});
