"use client";

import { useSyncExternalStore } from "react";

const MOBILE_BREAKPOINT_QUERY = "(max-width: 767px)";

const subscribe = (callback: () => void) => {
  if (typeof window === "undefined") return () => {};
  const mq = window.matchMedia(MOBILE_BREAKPOINT_QUERY);
  mq.addEventListener("change", callback);
  return () => mq.removeEventListener("change", callback);
};

const getSnapshot = () => {
  if (typeof window === "undefined") return false;
  return window.matchMedia(MOBILE_BREAKPOINT_QUERY).matches;
};

const getServerSnapshot = () => false;

/**
 * Narrow viewport breakpoint (max-width: 767px) — the threshold below the
 * Tailwind `md` breakpoint. Use for native-feel mobile affordances like
 * bottom sheets; keep `useDesktop` (min-width: 1024px) for the three-pane
 * vs single-pane layout switch.
 *
 * useSyncExternalStore reads matchMedia synchronously after hydration so
 * the first post-hydration render already reflects the real viewport.
 * A useState + useEffect combo would leave the first paint as
 * desktop-default, which would show a right-drawer flash on mobile when
 * the detail sheet is open on initial load.
 */
export function useIsMobile() {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
