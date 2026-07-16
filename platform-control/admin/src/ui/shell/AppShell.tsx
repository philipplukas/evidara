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
 * Workflow shortcuts rendered below the auto-registered resource links. The
 * "setup" entries jump straight to a resource's create page; the remaining
 * `kind: "preview"` entries advertise the coexisting Tailwind ports until they
 * graduate and replace the v1 MUI resources.
 *
 * Sources and reference data (authorities, jurisdictions) have graduated
 * (ADR-0026 / #501): their resource links and create shortcuts are canonical
 * Tailwind, so only the runs preview remains.
 */
const DEFAULT_EXTRA_ITEMS: SidebarMenuExtraItem[] = [
  { to: "/runs-v2", label: "Run queue", kind: "preview" },
  {
    to: "/sources/create",
    label: "Source setup",
    kind: "custom",
    exact: true,
  },
  {
    to: "/authorities/create",
    label: "Authority setup",
    kind: "custom",
    exact: true,
  },
  {
    to: "/jurisdictions/create",
    label: "Jurisdiction setup",
    kind: "custom",
    exact: true,
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

  // Esc closes the drawer. The scrim is `tabIndex={-1}`, so it can't be focused
  // and activated by keyboard; without this the only keyboard exit is tabbing
  // forward to the drawer's own close button.
  useEffect(() => {
    if (!isMobileOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMobileOpen(false);
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [isMobileOpen]);

  return (
    <div className="admin-app-shell min-h-screen grid">
      {/* Header row (spans the main-content column on desktop) */}
      <div
        style={{ gridArea: "header" }}
        className="relative z-20 flex items-stretch border-b border-[var(--admin-header-border)]"
      >
        {/* Mobile hamburger — hidden on md+. Sits inside the header so the
            header still spans full width on narrow viewports. */}
        <button
          type="button"
          onClick={openMobile}
          aria-label="Open navigation"
          aria-expanded={isMobileOpen}
          className="md:hidden inline-flex items-center justify-center w-12 self-stretch text-[var(--admin-on-brand-muted)] hover:text-[var(--admin-on-brand)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-4px] focus-visible:outline-[var(--admin-on-brand-muted)]"
          style={{
            background: "var(--admin-header-bg)",
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
        className="hidden md:block row-span-2 border-r border-[var(--admin-sidebar-border)] bg-[image:var(--admin-sidebar-bg)] backdrop-blur-[14px]"
      >
        <SidebarMenu extraItems={extraSidebarItems} />
      </aside>

      {/* Main content area */}
      <main style={{ gridArea: "main" }} className="relative overflow-x-hidden">
        <div className="w-full max-w-[var(--container-max)] mx-auto px-4 sm:px-6 pt-5 sm:pt-10 pb-8 sm:pb-10">
          {children}
        </div>
      </main>

      {/* Mobile drawer + scrim */}
      {isMobileOpen ? (
        <>
          {/* Click-scrim. Deliberately out of the tab order: the drawer's own
              close button is the keyboard affordance, plus Esc above. */}
          <button
            type="button"
            className="md:hidden fixed inset-0 z-40 bg-black/40 backdrop-blur-sm cursor-default"
            onClick={closeMobile}
            aria-label="Close navigation"
            tabIndex={-1}
          />
          <aside
            className="md:hidden fixed inset-y-0 left-0 z-50 w-[288px] border-r border-[var(--admin-sidebar-border)] bg-[image:var(--admin-sidebar-bg-strong)] backdrop-blur-[14px]"
            aria-label="Primary navigation"
          >
            <div className="flex items-center justify-end p-2">
              <button
                type="button"
                onClick={closeMobile}
                aria-label="Close navigation"
                className="inline-flex items-center justify-center w-10 h-10 rounded-full text-[var(--foreground)] hover:bg-[var(--brand-wash-8)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)] focus-visible:ring-offset-2"
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
