"use client";

import { useEffect, useState } from "react";
import { type ReadingRailState, readingRailStateFor } from "@/lib/reading-layout";

/**
 * The rail state for the current window width.
 *
 * Deliberately not a `matchMedia` per rail: two media queries is two places the
 * collapse order can be edited, and the order is the decision (see
 * `lib/reading-layout.ts`). One width in, one state out.
 *
 * Starts at `"full"` so the server and the first client render agree; the
 * effect corrects it before paint on anything narrower.
 */
export function useReadingRailState(): ReadingRailState {
  const [state, setState] = useState<ReadingRailState>("full");

  useEffect(() => {
    const update = () => setState(readingRailStateFor(window.innerWidth));
    update();
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, []);

  return state;
}
