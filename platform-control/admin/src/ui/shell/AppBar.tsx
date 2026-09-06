/**
 * `AppBar` — Tailwind-rendered admin header.
 *
 * Replaces `EvidaraAdminAppBar` (MUI). Reads the legal-search handoff from
 * the query string, drives the page subtitle from the current route (fixes
 * UX-12.5 — v1 always showed "Source lifecycle, approval state, and run
 * operations" regardless of where the operator was), and renders a "back to
 * legal search" CTA using the primitive `<Button>`.
 *
 * Gradient + typography match the v1 MUI chrome exactly so screenshot-pack
 * captures for v1 resource pages stay visually stable during P4a.
 */
"use client";

import { BrandMark } from "@evidara/shell";
import { ArrowLeft } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { publicConfig } from "../../config/publicConfig";
import {
  describeLegalSearchHandoff,
  type LegalSearchHandoff,
  resolveLegalSearchHandoff,
} from "../../lib/admin/navigationContext";
import { ThemeToggle } from "./ThemeToggle";

// See SidebarMenu.tsx — publicConfig is the single read point for NEXT_PUBLIC_*.
const LEGAL_SEARCH_URL = publicConfig.legalSearchBaseUrl;

/**
 * Map the current pathname to a friendly title. Replaces MUI's `<TitlePortal>`
 * which depended on resource-page `<Title>` wiring we're dropping.
 *
 * Every list page sets its own header here so the app-bar title always agrees
 * with the sidebar nav label; the default (`"Control plane"`) is a safe
 * fallback for any future / unknown route.
 */
export function titleForPath(pathname: string): string {
  if (pathname.startsWith("/runs")) {
    // Header agrees with the "Runs" nav label; the `/runs-v2` legacy paths
    // redirect to `/runs`, so no separate "Run queue" title is needed (#520).
    return /\/runs\/[^/]+/.test(pathname) ? "Run detail" : "Runs";
  }
  if (pathname.startsWith("/sources")) {
    if (pathname.endsWith("/create")) return "Create source";
    return /\/sources\/[^/]+/.test(pathname) ? "Source detail" : "Sources";
  }
  if (pathname.startsWith("/authorities")) {
    if (pathname.endsWith("/create")) return "Create authority";
    return /\/authorities\/[^/]+/.test(pathname) ? "Edit authority" : "Authorities";
  }
  if (pathname.startsWith("/jurisdictions")) {
    if (pathname.endsWith("/create")) return "Create jurisdiction";
    return /\/jurisdictions\/[^/]+/.test(pathname) ? "Edit jurisdiction" : "Jurisdictions";
  }
  if (pathname.startsWith("/preview-review")) return "Preview approvals";
  if (pathname.startsWith("/commentary-insights")) {
    return /\/commentary-insights\/[^/]+/.test(pathname)
      ? "Commentary insight"
      : "Commentary insights";
  }
  if (pathname.startsWith("/corrections")) {
    return /\/corrections\/[^/]+/.test(pathname) ? "Correction detail" : "Corrections";
  }
  if (pathname === "/" || pathname === "") return "Dashboard";

  return "Control plane";
}

/**
 * Map the current pathname to a subtitle describing *that* page.
 *
 * The header previously hardcoded the runs-flavoured "Source lifecycle,
 * approval state, and run operations." on every route, so Jurisdictions,
 * Sources and Corrections all described work they do not do. Mirrors
 * `titleForPath`: each mapped area names itself, everything else falls back to
 * the (accurate at the whole-app level) default.
 */
export const DEFAULT_SUBTITLE = "Source lifecycle, approval state, and run operations.";

export function subtitleForPath(pathname: string): string {
  if (pathname.startsWith("/runs")) {
    return /\/runs\/[^/]+/.test(pathname)
      ? "Pipeline health, provider jobs, and remediation for a single run."
      : "Launch, monitor, and cancel acquisition runs.";
  }
  if (pathname.startsWith("/sources")) {
    return "Source registration, versions, and approval state.";
  }
  if (pathname.startsWith("/authorities")) {
    return "Reference data: publishing authorities behind each source.";
  }
  if (pathname.startsWith("/jurisdictions")) {
    return "Reference data: the jurisdiction hierarchy sources are scoped to.";
  }
  if (pathname.startsWith("/preview-review")) {
    return "Review preview runs before promoting a source version to production.";
  }
  if (pathname.startsWith("/commentary-insights")) {
    return "Extracted commentary signals awaiting operator review.";
  }
  if (pathname.startsWith("/corrections")) {
    return "Operator corrections raised against canonical documents.";
  }
  if (pathname === "/" || pathname === "") {
    return "Control-plane overview: run throughput and pipeline health.";
  }

  return DEFAULT_SUBTITLE;
}

export function AppBar() {
  const location = useLocation();
  const [handoff, setHandoff] = useState<LegalSearchHandoff>(() =>
    resolveLegalSearchHandoff(null, LEGAL_SEARCH_URL),
  );

  useEffect(() => {
    setHandoff(
      resolveLegalSearchHandoff(new URLSearchParams(window.location.search), LEGAL_SEARCH_URL),
    );
  }, []);

  const title = useMemo(() => titleForPath(location.pathname), [location.pathname]);
  const handoffLabel = describeLegalSearchHandoff(handoff);
  const subtitle = handoff.hasOrigin
    ? `Entered from legal search. ${handoffLabel}.`
    : subtitleForPath(location.pathname);
  const ctaLabel = handoff.query ? "Return to active search" : "Back to legal search";

  return (
    <header
      className="w-full min-h-[80px] flex items-stretch text-[var(--admin-on-brand)] border-b border-[var(--admin-header-border)] shadow-[var(--admin-header-shadow)] backdrop-blur-[16px]"
      style={{
        background: "var(--admin-header-bg)",
      }}
    >
      {/*
       * Stack brand / title / CTA vertically until `lg`. Between `md` (768px,
       * where the sidebar claims a 288px column) and `lg`, the content column
       * is only ~480px — too narrow for three side-by-side blocks without the
       * title colliding with the brand and CTA. Row layout waits for `lg`,
       * where the column is wide enough to breathe.
       */}
      <div className="flex flex-col lg:flex-row items-stretch lg:items-center justify-between gap-3 lg:gap-4 w-full px-3 sm:px-6 py-2 lg:py-3 min-w-0">
        {/*
         * Brand mark + product, and the way back to the dashboard.
         *
         * Every one of the thirteen sidebar links targets a resource or a
         * create form; none targets `/`. The logo was not a link either, so once
         * an operator left the dashboard the only route back was editing the
         * URL. A clickable wordmark is the convention operators already expect;
         * the sidebar also carries an explicit "Overview" entry, because a
         * convention is not a discoverable affordance.
         */}
        <Link
          to="/"
          aria-label="Evidara control plane — dashboard"
          className="flex items-center gap-3 min-w-0 flex-1 no-underline rounded-lg transition-colors hover:bg-[var(--admin-on-brand-wash)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)] focus-visible:ring-offset-2 -mx-1 px-1 py-1"
        >
          {/*
           * The shared `BrandMark` draws its lattice in `currentColor`. Admin's
           * header is a dark navy gradient, so it inherits the near-white
           * `--admin-on-brand` here — the navy the workspace uses would be
           * invisible against this ground. The accent node is likewise lifted
           * via `--admin-brand-mark-accent`.
           */}
          <BrandMark
            size={42}
            className="shrink-0 text-[var(--admin-on-brand)] [--brand-mark-accent:var(--admin-brand-mark-accent)]"
          />
          <div className="min-w-0">
            <div className="text-[10px] font-semibold tracking-[0.16em] text-[var(--admin-on-brand-muted)] uppercase leading-[1.15]">
              Evidara
            </div>
            <div className="text-sm text-[var(--admin-on-brand-muted)] font-medium leading-tight">
              Control plane
            </div>
          </div>
        </Link>

        {/* Title block (route-aware) */}
        <div className="flex flex-col items-start lg:items-center text-left lg:text-center min-w-0 flex-1 gap-[2px]">
          <span className="inline-flex items-center h-[22px] px-2 rounded-full text-[10px] font-semibold tracking-[0.06em] text-[var(--admin-on-brand-faint)] bg-[var(--admin-on-brand-wash)] border border-[var(--admin-header-border)]">
            Operator · Control plane
          </span>
          {/*
           * Rendered as a styled <p>, not a heading, so each page's own
           * <h1> in the main content area remains the sole h1 — keeps
           * screen readers and role-based tests (getByRole("heading"))
           * unambiguous. The title portal is visual wayfinding, not
           * document structure.
           */}
          <p
            className="text-base font-semibold leading-tight text-[var(--admin-on-brand)] m-0"
            style={{ fontFamily: "var(--font-admin-serif), Georgia, serif" }}
          >
            {title}
          </p>
          <p className="text-[13px] leading-snug text-[var(--admin-on-brand-muted)] m-0">
            {subtitle}
          </p>
          {handoff.hasOrigin ? (
            <div className="flex flex-wrap justify-start lg:justify-center gap-[6px] pt-[4px]">
              {handoff.query ? (
                <span className="inline-flex items-center h-6 px-2 rounded-full text-[11px] text-[var(--admin-on-brand)] bg-[var(--admin-on-brand-subtle)] border border-[var(--admin-on-brand-border)]">
                  Search: {handoff.query}
                </span>
              ) : null}
              {handoff.selectedId ? (
                <span className="inline-flex items-center h-6 px-2 rounded-full text-[11px] text-[var(--admin-on-brand)] bg-[var(--admin-on-brand-wash-hover)] border border-[var(--admin-on-brand-border)]">
                  Selected item: {handoff.selectedId}
                </span>
              ) : null}
              {handoff.scopeLabel ? (
                <span className="inline-flex items-center h-6 px-2 rounded-full text-[11px] text-[var(--admin-on-brand-muted)] bg-[var(--admin-on-brand-wash)] border border-[var(--admin-on-brand-border-subtle)]">
                  {handoff.scopeLabel}
                </span>
              ) : null}
            </div>
          ) : null}
        </div>

        {/* Theme toggle + back-to-legal-search CTA */}
        <div className="flex items-stretch lg:items-center gap-2 self-stretch lg:self-auto">
          <ThemeToggle />
          <a
            href={handoff.returnToUrl}
            className="inline-flex items-center justify-center gap-2 rounded-full font-semibold no-underline transition-[background-color,border-color,transform,box-shadow] duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)] focus-visible:ring-offset-2 px-4 min-h-11 sm:h-10 text-sm bg-[var(--admin-on-brand-wash)] border border-[var(--admin-on-brand-border)] text-[var(--admin-on-brand)] hover:bg-[var(--admin-on-brand-wash-hover)] hover:border-[var(--admin-on-brand-border-hover)] whitespace-nowrap self-stretch lg:self-auto w-full lg:w-auto"
          >
            <span aria-hidden>
              <ArrowLeft size={14} strokeWidth={2.2} />
            </span>
            <span>{ctaLabel}</span>
          </a>
        </div>
      </div>
    </header>
  );
}
