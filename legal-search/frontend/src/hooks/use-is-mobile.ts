"use client";

import { useEffect, useState } from "react";

/**
 * Narrow viewport breakpoint (max-width: 767px) — the threshold below the
 * Tailwind `md` breakpoint. Use this for native-feel mobile affordances like
 * bottom sheets; keep `useDesktop` (min-width: 1024px) for the three-pane
 * vs single-pane layout switch.
 */
export function useIsMobile() {
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia("(max-width: 767px)");
    const update = () => setIsMobile(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);

  return isMobile;
}
