/**
 * `AppShell` — Tailwind-rendered top-level layout for the admin app.
 *
 * Replaces the MUI `<Layout>` chrome from `AdminApp.tsx`. `ra-core`'s
 * `CoreAdmin` passes the active route as `children`, which we render in the
 * `<main>` slot. The header (80px) + sidebar (288px) match the v1 MUI
 * dimensions so the outer dimensions of resource pages don't change.
 *
 * Mobile (<768px): sidebar becomes an off-canvas drawer behind a hamburger
 * toggle; closes when the route changes (handled inside `SidebarMenu`).
 *
 * The shell also mounts `ToastAdapter` so `useNotify()` calls from anywhere
 * in the app render into our Tailwind-based toast stack instead of MUI's
 * Snackbar.
 */
"use client";

import { X as CloseIcon, Menu as MenuIcon } from "lucide-react";
import type { ReactNode } from "react";
import { useCallback, useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { AppBar } from "./AppBar";
import { SidebarMenu, type SidebarMenuExtraItem } from "./SidebarMenu";
import { ToastAdapter } from "./ToastAdapter";

interface AppShellProps {
  children: ReactNode;
  /** Extra links rendered below the auto-registered resource links. */
  extraSidebarItems?: SidebarMenuExtraItem[];
}

/**
 * v2-preview menu items that historically lived in `EvidaraAdminMenu`. Kept
 * as explicit entries so the sidebar still advertises the coexisting
 * Tailwind ports until they graduate and replace the v1 MUI resources.
 */
const DEFAULT_EXTRA_ITEMS: SidebarMenuExtraItem[] = [
  { to: "/sources-v2", label: "Sources (v2 preview)", kind: "preview" },
  { to: "/runs-v2", label: "Runs (v2 preview)", kind: "preview" },
  {
    to: "/sources-v2/create",
    label: "Source form (v2 preview)",
    kind: "preview",
  },
  {
    to: "/authorities-v2/create",
    label: "Authority form (v2 preview)",
    kind: "preview",
  },
  {
    to: "/jurisdictions-v2/create",
    label: "Jurisdiction form (v2 preview)",
    kind: "preview",
  },
];

export function AppShell({ children, extraSidebarItems = DEFAULT_EXTRA_ITEMS }: AppShellProps) {
  const [isMobileOpen, setMobileOpen] = useState(false);
  const location = useLocation();

  // Close the mobile drawer whenever the route changes — matches v1 behaviour
  // where MUI's <Drawer> auto-dismissed on nav.
  // Close the mobile drawer when the route path changes. The effect
  // body doesn't *read* pathname, but re-firing on pathname changes is
  // the whole point — it's how we detect navigation. Biome's exhaustive-
  // deps rule flags this as "extra"; suppress.
  // biome-ignore lint/correctness/useExhaustiveDependencies: pathname re-fire is the intent
  useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname]);

  const openMobile = useCallback(() => setMobileOpen(true), []);
  const closeMobile = useCallback(() => setMobileOpen(false), []);

  return (
    <div
      className="min-h-screen grid"
      style={{
        gridTemplateColumns: "288px 1fr",
        gridTemplateRows: "80px 1fr",
        gridTemplateAreas: `"sidebar header" "sidebar main"`,
      }}
    >
      {/* Header row (spans the main-content column on desktop) */}
      <div
        style={{ gridArea: "header" }}
        className="relative z-20 flex items-stretch border-b border-white/10"
      >
        {/* Mobile hamburger — hidden on md+. Sits inside the header so the
            header still spans full width on narrow viewports. */}
        <button
          type="button"
          onClick={openMobile}
          aria-label="Open navigation"
          aria-expanded={isMobileOpen}
          className="md:hidden inline-flex items-center justify-center w-12 self-stretch text-white/80 hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-4px] focus-visible:outline-[rgba(255,253,248,0.6)]"
          style={{
            background: "linear-gradient(120deg, rgba(13, 58, 98, 0.98), rgba(9, 48, 83, 0.95))",
          }}
        >
          <MenuIcon size={22} strokeWidth={2} aria-hidden />
        </button>
        <div className="flex-1 min-w-0">
          <AppBar />
        </div>
      </div>

      {/* Desktop sidebar */}
      <aside
        style={{ gridArea: "sidebar" }}
        className="hidden md:block row-span-2 border-r border-[rgba(29,41,61,0.08)] bg-[linear-gradient(180deg,rgba(255,253,248,0.98),rgba(248,243,235,0.92))] backdrop-blur-[14px]"
      >
        <SidebarMenu extraItems={extraSidebarItems} />
      </aside>

      {/* Main content area */}
      <main style={{ gridArea: "main" }} className="relative overflow-x-hidden">
        <div className="w-full max-w-[1600px] mx-auto px-4 sm:px-6 pt-5 sm:pt-10 pb-8 sm:pb-10">
          {children}
        </div>
      </main>

      {/* Mobile drawer + scrim */}
      {isMobileOpen ? (
        <>
          {/* `<button>` is the accessible equivalent of a click-scrim —
              keyboard users can Esc or click/space the scrim equally. */}
          <button
            type="button"
            className="md:hidden fixed inset-0 z-40 bg-black/40 backdrop-blur-sm cursor-default"
            onClick={closeMobile}
            aria-label="Close navigation"
            tabIndex={-1}
          />
          <aside
            className="md:hidden fixed inset-y-0 left-0 z-50 w-[288px] border-r border-[rgba(29,41,61,0.08)] bg-[linear-gradient(180deg,rgba(255,253,248,0.98),rgba(248,243,235,0.98))] backdrop-blur-[14px]"
            aria-label="Primary navigation"
          >
            <div className="flex items-center justify-end p-2">
              <button
                type="button"
                onClick={closeMobile}
                aria-label="Close navigation"
                className="inline-flex items-center justify-center w-10 h-10 rounded-full text-[var(--foreground)] hover:bg-[var(--brand-wash-8)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand-focus-ring)]"
              >
                <CloseIcon size={18} strokeWidth={2} aria-hidden />
              </button>
            </div>
            <SidebarMenu extraItems={extraSidebarItems} />
          </aside>
        </>
      ) : null}

      {/* Notifications portal */}
      <ToastAdapter />
    </div>
  );
}
