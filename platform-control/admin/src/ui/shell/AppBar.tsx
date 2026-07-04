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

import { ArrowLeft } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import {
  describeLegalSearchHandoff,
  type LegalSearchHandoff,
  resolveLegalSearchHandoff,
} from "../../lib/admin/navigationContext";

const LEGAL_SEARCH_URL =
  process.env.NEXT_PUBLIC_LEGAL_SEARCH_URL?.trim() || "http://localhost:3101";

/**
 * Map the current pathname to a friendly title. Replaces MUI's `<TitlePortal>`
 * which depended on resource-page `<Title>` wiring we're dropping.
 *
 * Only v1 canonical + v2 preview routes are covered today; the default
 * (`"Control plane"`) is safe for any future / unknown route.
 */
function titleForPath(pathname: string): string {
  // Exact matches first (order matters — longer paths before shorter ones).
  if (pathname.startsWith("/runs-v2")) {
    return pathname.includes("/") && /\/runs-v2\/[^/]+/.test(pathname) ? "Run detail" : "Run queue";
  }
  if (pathname.startsWith("/authorities-v2/create")) return "Create authority";
  if (/\/authorities-v2\/[^/]+\/edit/.test(pathname)) return "Edit authority";
  if (pathname.startsWith("/jurisdictions-v2/create")) return "Create jurisdiction";
  if (/\/jurisdictions-v2\/[^/]+\/edit/.test(pathname)) return "Edit jurisdiction";

  if (pathname.startsWith("/runs")) {
    return /\/runs\/[^/]+/.test(pathname) ? "Run detail" : "Run queue";
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
  if (pathname === "/" || pathname === "") return "Dashboard";

  return "Control plane";
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
    : "Source lifecycle, approval state, and run operations.";
  const ctaLabel = handoff.query ? "Return to active search" : "Back to legal search";

  return (
    <header
      className="w-full min-h-[80px] flex items-stretch text-[var(--admin-on-brand)] border-b border-[var(--admin-header-border)] shadow-[var(--admin-header-shadow)] backdrop-blur-[16px]"
      style={{
        background: "var(--admin-header-bg)",
      }}
    >
      <div className="flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3 md:gap-4 w-full px-3 sm:px-6 py-2 md:py-3 min-w-0">
        {/* Brand mark + product */}
        <div className="flex items-center gap-3 min-w-0 flex-1">
          <div
            aria-hidden
            className="w-[42px] h-[42px] rounded-2xl grid place-items-center text-[18px] font-bold leading-none border border-[var(--admin-on-brand-border-subtle)] shadow-[var(--admin-brand-mark-shadow)]"
            style={{
              background: "var(--brand-mark-gradient)",
              fontFamily: "var(--font-brand-mark)",
            }}
          >
            E
          </div>
          <div className="min-w-0">
            <div className="text-[10px] font-semibold tracking-[0.16em] text-[var(--admin-on-brand-muted)] uppercase leading-[1.15]">
              Evidara
            </div>
            <div className="text-sm text-[var(--admin-on-brand-muted)] font-medium leading-tight">
              Control plane
            </div>
          </div>
        </div>

        {/* Title block (route-aware) */}
        <div className="flex flex-col items-start md:items-center text-left md:text-center min-w-0 flex-1 gap-[2px]">
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
            <div className="flex flex-wrap justify-start md:justify-center gap-[6px] pt-[4px]">
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

        {/* Back-to-legal-search CTA */}
        <div className="flex md:items-center self-stretch md:self-auto">
          <a
            href={handoff.returnToUrl}
            className="inline-flex items-center justify-center gap-2 rounded-full font-semibold no-underline transition-[background-color,border-color,transform,box-shadow] duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)] focus-visible:ring-offset-2 px-4 min-h-11 sm:h-10 text-sm bg-[var(--admin-on-brand-wash)] border border-[var(--admin-on-brand-border)] text-[var(--admin-on-brand)] hover:bg-[var(--admin-on-brand-wash-hover)] hover:border-[var(--admin-on-brand-border-hover)] whitespace-nowrap self-stretch md:self-auto w-full md:w-auto"
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
