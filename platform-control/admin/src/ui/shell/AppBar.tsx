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
    return pathname.includes("/") && /\/runs-v2\/[^/]+/.test(pathname)
      ? "Run detail (v2 preview)"
      : "Run queue (v2 preview)";
  }
  if (pathname.startsWith("/sources-v2")) {
    return /\/sources-v2\/[^/]+/.test(pathname)
      ? "Source detail (v2 preview)"
      : "Sources (v2 preview)";
  }
  if (pathname.startsWith("/authorities-v2/create")) return "Create authority (v2 preview)";
  if (/\/authorities-v2\/[^/]+\/edit/.test(pathname)) return "Edit authority (v2 preview)";
  if (pathname.startsWith("/jurisdictions-v2/create")) return "Create jurisdiction (v2 preview)";
  if (/\/jurisdictions-v2\/[^/]+\/edit/.test(pathname)) return "Edit jurisdiction (v2 preview)";

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
  if (pathname.startsWith("/preview-review")) return "Preview review";
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
      className="w-full min-h-[80px] flex items-stretch text-[#fffdf8] border-b border-[rgba(255,253,248,0.12)] shadow-[0_18px_40px_rgba(15,76,129,0.12)] backdrop-blur-[16px]"
      style={{
        background: "linear-gradient(120deg, rgba(13, 58, 98, 0.98), rgba(9, 48, 83, 0.95))",
      }}
    >
      <div className="flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3 md:gap-4 w-full px-3 sm:px-6 py-2 md:py-3 min-w-0">
        {/* Brand mark + product */}
        <div className="flex items-center gap-3 min-w-0 flex-1">
          <div
            aria-hidden
            className="w-[42px] h-[42px] rounded-2xl grid place-items-center text-[18px] font-bold leading-none border border-[rgba(255,253,248,0.16)] shadow-[0_12px_24px_rgba(7,23,40,0.16)]"
            style={{
              background: "linear-gradient(135deg, var(--brand), var(--brand-hover))",
              fontFamily: "var(--font-admin-serif), Georgia, serif",
            }}
          >
            E
          </div>
          <div className="min-w-0">
            <div className="text-[10px] font-semibold tracking-[0.16em] text-white/80 uppercase leading-[1.15]">
              Evidara
            </div>
            <div className="text-sm text-white/80 font-medium leading-tight">Control plane</div>
          </div>
        </div>

        {/* Title block (route-aware) */}
        <div className="flex flex-col items-start md:items-center text-left md:text-center min-w-0 flex-1 gap-[2px]">
          <span className="inline-flex items-center h-[22px] px-2 rounded-full text-[10px] font-semibold tracking-[0.06em] text-white/70 bg-white/[0.08] border border-white/10">
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
            className="text-base font-semibold leading-tight text-white m-0"
            style={{ fontFamily: "var(--font-admin-serif), Georgia, serif" }}
          >
            {title}
          </p>
          <p className="text-[13px] leading-snug text-white/75 m-0">{subtitle}</p>
          {handoff.hasOrigin ? (
            <div className="flex flex-wrap justify-start md:justify-center gap-[6px] pt-[4px]">
              {handoff.query ? (
                <span className="inline-flex items-center h-6 px-2 rounded-full text-[11px] text-white bg-white/[0.12] border border-white/20">
                  Search: {handoff.query}
                </span>
              ) : null}
              {handoff.selectedId ? (
                <span className="inline-flex items-center h-6 px-2 rounded-full text-[11px] text-white bg-white/[0.16] border border-white/20">
                  Selected item: {handoff.selectedId}
                </span>
              ) : null}
              {handoff.scopeLabel ? (
                <span className="inline-flex items-center h-6 px-2 rounded-full text-[11px] text-white/90 bg-white/[0.08] border border-white/[0.14]">
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
            className="inline-flex items-center justify-center gap-2 rounded-full font-semibold transition-[background-color,border-color,transform,box-shadow] duration-150 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand-focus-ring)] px-4 min-h-11 sm:h-10 text-sm bg-white/[0.08] border border-white/[0.28] text-[#fffdf8] hover:bg-white/[0.16] hover:border-white/[0.42] whitespace-nowrap self-stretch md:self-auto w-full md:w-auto"
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
