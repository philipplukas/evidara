/**
 * `SidebarMenu` — Tailwind-rendered admin sidebar.
 *
 * Replaces `EvidaraAdminMenu` (MUI). Auto-renders one link per registered
 * resource (via `useResourceDefinitions` from `ra-core`) plus any extra
 * items passed through from `AppShell` (v2-preview entries today).
 *
 * Selected-state styling uses `ACCENT_CORE_SUBTLE` from the shared token
 * palette — matches the v1 MUI `Mui-selected` background, so the "where am
 * I" cue stays consistent for operators across the P4a cutover.
 */
"use client";

import { FlaskConical, LayoutDashboard } from "lucide-react";
import { useResourceDefinitions } from "ra-core";
import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { publicConfig } from "../../config/publicConfig";
import {
  describeLegalSearchHandoff,
  type LegalSearchHandoff,
  resolveLegalSearchHandoff,
} from "../../lib/admin/navigationContext";
import { formatBuildLabel } from "../../lib/format/buildLabel";

// Reads the config boundary rather than `process.env` directly (publicConfig's
// own rule). The literal-snapshot mechanism there is what makes NEXT_PUBLIC_*
// reach the client bundle at all, so a second ad-hoc read is not merely
// duplication — it is a second, weaker source of truth.
const LEGAL_SEARCH_URL = publicConfig.legalSearchBaseUrl;

export interface SidebarMenuExtraItem {
  to: string;
  label: string;
  icon?: ReactNode;
  /** `"preview"` marks v2-preview entries; we render a FlaskConical icon. */
  kind?: "preview" | "custom";
  /** Match only the exact route. Useful for create/setup entries. */
  exact?: boolean;
  /** Prefixes that should not activate this broader nav item. */
  inactiveOnPrefixes?: string[];
}

interface SidebarMenuProps {
  extraItems?: SidebarMenuExtraItem[];
}

function navItemClass(isActive: boolean): string {
  const base =
    "flex items-center gap-3 mx-[10px] my-1 px-[14px] py-[10px] min-h-[44px] rounded-[14px] text-sm font-semibold leading-tight no-underline transition-[background-color,transform] duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)] focus-visible:ring-offset-2";
  if (isActive) {
    // Violet (ACCENT_CORE_SUBTLE) background + violet text matches the v1 MUI
    // Mui-selected state. Operators recognise this as the "current page" cue.
    return `${base} bg-[var(--accent-core-subtle)] text-[var(--accent-core)] shadow-[var(--shadow-ring-accent)] hover:bg-[var(--accent-core-muted)]`;
  }
  return `${base} text-[var(--foreground)] hover:bg-[var(--interactive-accent-subtle)]`;
}

function labelForResource(name: string, options: { label?: string } | undefined): string {
  const raw = options?.label ?? name;
  // Capitalise first letter if ra-core didn't supply a human label.
  return raw.charAt(0).toUpperCase() + raw.slice(1);
}

/**
 * A resource's top-level link uses a prefix match (`end={false}`), so it also
 * lights up on the resource's own `/create` route — which is owned by the
 * matching "… setup" workflow shortcut. Yield to that workflow item on its
 * exact route so only a single nav item is ever active at once (fixes the
 * dual-highlight on `/authorities/create`, and the same class of collision on
 * `/sources/create` and `/jurisdictions/create`).
 */
export function resourceLinkIsActive(
  navIsActive: boolean,
  pathname: string,
  workflowExactPaths: readonly string[],
): boolean {
  return navIsActive && !workflowExactPaths.includes(pathname);
}

export function SidebarMenu({ extraItems = [] }: SidebarMenuProps) {
  const definitions = useResourceDefinitions();
  const location = useLocation();
  const [handoff, setHandoff] = useState<LegalSearchHandoff>(() =>
    resolveLegalSearchHandoff(null, LEGAL_SEARCH_URL),
  );

  useEffect(() => {
    setHandoff(
      resolveLegalSearchHandoff(new URLSearchParams(window.location.search), LEGAL_SEARCH_URL),
    );
  }, []);

  const resourceEntries = Object.values(definitions).filter((r) => r?.hasList);
  // Exact routes owned by the "… setup" workflow shortcuts; a resource link
  // must not stay highlighted when the operator is on one of these.
  const workflowExactPaths = extraItems.filter((item) => item.exact).map((item) => item.to);
  const footerLabel =
    handoff.hasOrigin && handoff.query ? "Return to active search" : "Back to legal search";
  const footerSecondary = describeLegalSearchHandoff(handoff);
  const buildLabel = formatBuildLabel(publicConfig.buildSha, publicConfig.buildDate);

  return (
    <nav
      aria-label="Primary navigation"
      className="flex flex-col h-full min-h-[calc(100vh-80px)] pt-4 md:pt-6"
    >
      <ul className="flex-shrink-0 list-none m-0 p-0">
        {/*
         * The dashboard, which nothing linked to.
         *
         * `useResourceDefinitions` enumerates *resources*, and the dashboard is
         * not one — it is `<Admin dashboard={…}>` at `/`. So all thirteen
         * generated links pointed at resources or create forms and the overview
         * became unreachable the moment an operator navigated away from it.
         * `end` (exact match) because every other route is a prefix of "/".
         */}
        <li>
          <NavLink to="/" end className={({ isActive }) => navItemClass(isActive)}>
            <span className="text-[var(--accent-core)] flex items-center" aria-hidden>
              <LayoutDashboard size={16} strokeWidth={2} />
            </span>
            <span>Overview</span>
          </NavLink>
        </li>
        {resourceEntries.map((resource) => {
          const to = `/${resource.name}`;
          // Replicate NavLink's prefix match (`end={false}`) ourselves so that
          // `aria-current` and the active class share one source of truth.
          // NavLink sets `aria-current` from its own internal match, which we
          // cannot override — so it would leave two items marked current on a
          // resource's `/create` route even after the class yields (#6).
          const prefixActive = location.pathname === to || location.pathname.startsWith(`${to}/`);
          const active = resourceLinkIsActive(prefixActive, location.pathname, workflowExactPaths);
          return (
            <li key={resource.name}>
              <Link
                to={to}
                className={navItemClass(active)}
                aria-current={active ? "page" : undefined}
              >
                <span>{labelForResource(resource.name, resource.options)}</span>
              </Link>
            </li>
          );
        })}
        {extraItems.length > 0 ? (
          <li className="mx-[10px] my-2">
            <div className="text-[10px] font-semibold tracking-[0.12em] uppercase text-[var(--text-meta)] px-[14px]">
              Workflows
            </div>
          </li>
        ) : null}
        {extraItems.map((item) => (
          <li key={item.to}>
            <NavLink
              to={item.to}
              end={item.exact}
              className={({ isActive }) =>
                navItemClass(
                  isActive &&
                    !item.inactiveOnPrefixes?.some((prefix) =>
                      location.pathname.startsWith(prefix),
                    ),
                )
              }
            >
              <span className="text-[var(--accent-core)] flex items-center" aria-hidden>
                {item.icon ?? <FlaskConical size={16} strokeWidth={2} />}
              </span>
              <span>{item.label}</span>
            </NavLink>
          </li>
        ))}
      </ul>

      {/* Footer — "Back to legal search" */}
      <div className="mt-auto pb-3">
        <div
          className="py-2"
          style={{
            background: "var(--admin-sidebar-footer-bg)",
            backdropFilter: "blur(8px)",
          }}
        >
          <div className="mx-4 mb-2 border-t border-[var(--border)]" />
          <a
            href={handoff.returnToUrl}
            className="flex items-center gap-3 mx-[10px] px-[14px] py-[10px] min-h-[44px] rounded-[14px] text-sm font-semibold text-[var(--brand)] no-underline hover:bg-[var(--interactive-accent-subtle)] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)] focus-visible:ring-offset-2"
          >
            {/* lucide ArrowLeft lives in AppBar; keep sidebar dep-light */}
            <span aria-hidden className="text-[var(--brand)]">
              ←
            </span>
            <span className="flex flex-col min-w-0">
              <span className="leading-tight">{footerLabel}</span>
              <span className="text-[11px] font-normal text-[var(--text-meta)] truncate">
                {footerSecondary}
              </span>
            </span>
          </a>

          {/*
            Build provenance. Renders only when this bundle was built from a
            tagged image — under `npm run dev` there is none, and a blank where a
            version belongs reads as "no version" rather than "not applicable".
            Full SHA in the title so it can be copied for a `git show`.
          */}
          {buildLabel ? (
            <a
              href={`https://github.com/philipplukas/evidara/commit/${publicConfig.buildSha}`}
              target="_blank"
              rel="noreferrer"
              title={publicConfig.buildSha}
              className="mx-[10px] block px-[14px] pt-1 font-mono text-[11px] text-[var(--text-meta)] no-underline hover:text-[var(--brand)] hover:underline"
            >
              {buildLabel}
            </a>
          ) : null}
        </div>
      </div>
    </nav>
  );
}
