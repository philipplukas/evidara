"use client";

/**
 * `ResourceTabs` — the "fine" half of the coarse/fine navigation split.
 *
 * The sidebar carries four coarse sections (SCOPE / BUILD / VERIFY / LEARN);
 * this strip sits at the top of the content area and carries the siblings
 * *within* the section you are in. Both read `NAV_GROUPS`, so they cannot
 * disagree about what belongs where.
 *
 * Rendered once, in `AppShell`'s `<main>`, rather than added to each list
 * component: a per-page copy is a second producer of the same structure and
 * would drift the moment a resource moved group.
 *
 * It renders NOTHING when the route is not a grouped resource list — the
 * dashboard, create/edit/show routes, and the wizard get no strip. A tab bar
 * on a detail page competes with that page's own back-navigation and implies
 * the tabs would switch a record rather than the whole view.
 */

import { useResourceDefinitions } from "ra-core";
import { Link, useLocation } from "react-router-dom";
import { groupForResource } from "../../domain/navGroups";

/** The resource segment of a pathname, or null for non-resource routes. */
export function resourceFromPathname(pathname: string): string | null {
  const segments = pathname.split("/").filter(Boolean);
  if (segments.length !== 1) return null; // list routes only, never /x/create or /x/1/show
  return segments[0] ?? null;
}

function tabClass(isActive: boolean): string {
  const base =
    "inline-flex items-center px-3 py-2 text-sm font-semibold rounded-[10px] no-underline transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)] focus-visible:ring-offset-2";
  return isActive
    ? `${base} bg-[var(--accent-core-subtle)] text-[var(--accent-core)]`
    : `${base} text-[var(--text-meta)] hover:text-[var(--foreground)] hover:bg-[var(--interactive-accent-subtle)]`;
}

export function ResourceTabs() {
  const location = useLocation();
  const definitions = useResourceDefinitions();

  const current = resourceFromPathname(location.pathname);
  if (!current) return null;

  const group = groupForResource(current);
  if (!group) return null;

  // Only offer siblings that are actually registered and have a list route —
  // a tab pointing at an unregistered resource is a 404 with a friendly label.
  const siblings = group.resources.filter((name) => definitions[name]?.hasList);
  if (siblings.length < 2) return null; // a single-item group needs no tabs

  return (
    <nav aria-label={`${group.label} sections`} className="mb-5">
      <div className="flex items-center gap-1 flex-wrap">
        {siblings.map((name) => (
          <Link
            key={name}
            to={`/${name}`}
            className={tabClass(name === current)}
            aria-current={name === current ? "page" : undefined}
          >
            {definitions[name]?.options?.label ?? name}
          </Link>
        ))}
      </div>
      <p className="mt-2 mb-0 text-[13px] text-[var(--text-meta)]">{group.caption}</p>
    </nav>
  );
}
