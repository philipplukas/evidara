/**
 * Navigation grouping for the admin sidebar and the per-page sibling tabs.
 *
 * The nine resources were never nine peers — they are four kinds of thing, and
 * the flat list hid the dependency order that the operator loop actually runs
 * in (ADR-0033's build order; ADR-0030's enablement lifecycle):
 *
 *   SCOPE   what exists in the world      jurisdictions, authorities
 *   BUILD   what we mean to acquire       blueprints, sources
 *   VERIFY  what actually happened        runs, preview approvals
 *   LEARN   what we measured back         coverage, corrections
 *
 * Ordering is deliberate: Blueprints precedes Sources because a source version
 * is an *instance* of a blueprint template, and the old list had it backwards.
 *
 * This map drives BOTH the sidebar sections and the tab strip on each resource
 * page, so the two cannot disagree. Adding a resource to `AdminApp.tsx` without
 * adding it here does NOT hide it — `groupResources` puts unclassified
 * resources in a trailing "More" group, and `navGroups.test.ts` fails if any
 * registered resource lands there. Silent disappearance is the failure mode
 * this shape has to avoid.
 */
import { ResourceName } from "./resourceNames";

export interface NavGroup {
  /** Stable key, used for React keys and test assertions. */
  id: string;
  /** Section heading rendered in the sidebar. */
  label: string;
  /** One-line description of what the group answers. Used as tab-strip caption. */
  caption: string;
  /** Resource names in display order. */
  resources: string[];
}

export const NAV_GROUPS: NavGroup[] = [
  {
    id: "scope",
    label: "Scope",
    caption: "What exists in the world, and who speaks for it.",
    resources: [ResourceName.Jurisdictions, ResourceName.Authorities],
  },
  {
    id: "build",
    label: "Build",
    caption: "What we mean to acquire. A source version is an instance of a blueprint.",
    resources: [ResourceName.BlueprintTemplates, ResourceName.Sources],
  },
  {
    id: "verify",
    label: "Verify",
    caption: "What actually happened, and the gate that turns evidence into permission.",
    resources: [ResourceName.Runs, ResourceName.PreviewReview],
  },
  {
    id: "learn",
    label: "Learn",
    caption: "What the corpus reports back. Projections, not things to edit.",
    resources: [ResourceName.AcquisitionCoverage, ResourceName.Corrections],
  },
];

/** Trailing catch-all so a newly registered resource can never vanish. */
export const UNGROUPED_ID = "more";

export interface GroupedResource<T> {
  name: string;
  resource: T;
}

export interface GroupedNav<T> {
  id: string;
  label: string;
  caption: string;
  items: GroupedResource<T>[];
}

/**
 * Bucket the registered resources into `NAV_GROUPS`, preserving group order and
 * the declared order within each group. Registered resources that no group
 * claims are returned in a trailing "More" group rather than dropped.
 */
export function groupResources<T>(
  registered: Map<string, T> | Array<[string, T]>,
): GroupedNav<T>[] {
  const byName = registered instanceof Map ? registered : new Map(registered);
  const claimed = new Set<string>();
  const groups: GroupedNav<T>[] = [];

  for (const group of NAV_GROUPS) {
    const items: GroupedResource<T>[] = [];
    for (const name of group.resources) {
      const resource = byName.get(name);
      if (resource === undefined) continue; // not registered — e.g. parked
      claimed.add(name);
      items.push({ name, resource });
    }
    if (items.length > 0) {
      groups.push({ id: group.id, label: group.label, caption: group.caption, items });
    }
  }

  const leftovers: GroupedResource<T>[] = [];
  for (const [name, resource] of byName) {
    if (!claimed.has(name)) leftovers.push({ name, resource });
  }
  if (leftovers.length > 0) {
    groups.push({
      id: UNGROUPED_ID,
      label: "More",
      caption: "Not yet placed in a section.",
      items: leftovers,
    });
  }

  return groups;
}

/** The group a resource belongs to, or undefined when nothing claims it. */
export function groupForResource(name: string): NavGroup | undefined {
  return NAV_GROUPS.find((group) => group.resources.includes(name));
}
