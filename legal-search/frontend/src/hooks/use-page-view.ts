"use client";

import { useEffect, useRef } from "react";
import { AnalyticsEvent, track } from "@/lib/analytics";

/**
 * Track page views on route changes. Fires once per unique pathname
 * (does not re-fire when only query params change).
 *
 * Usage: call `usePageView()` once in a root client layout or provider.
 */
export function usePageView(): void {
  const lastPathRef = useRef<string | null>(null);

  useEffect(() => {
    const path = window.location.pathname;
    if (path === lastPathRef.current) return;
    lastPathRef.current = path;

    track(AnalyticsEvent.PAGE_VIEW, {
      path,
      referrer: document.referrer || undefined,
    });
  });
}
