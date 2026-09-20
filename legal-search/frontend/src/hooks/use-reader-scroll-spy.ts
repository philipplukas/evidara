"use client";

import { type RefObject, useCallback, useEffect, useRef } from "react";
import { activeSectionAt, type SectionOffset } from "@/lib/reader-scroll-spy";

/**
 * Report which section the reader is inside, as it scrolls.
 *
 * Reads the offsets from the DOM (the headings `DocumentBody` emits carry
 * `data-section-id`) and hands them to {@link activeSectionAt}, which owns the
 * rule. Offsets are re-measured on scroll rather than cached: the body is
 * plain text of unknown length and a re-wrap on resize moves every heading.
 *
 * `IntersectionObserver` would be the obvious mechanism and is deliberately not
 * used — it answers "is this visible", which for a 539,396px statute is a dozen
 * headings at once, and the question here is which single one the reader is in.
 *
 * @param containerRef the scrolling element that holds the body.
 * @param bodyKey changes whenever the rendered body does, forcing a re-measure.
 * @param onChange called with the active section id, or `null` when the
 *   document places no heading at all. Must be stable.
 */
export function useReaderScrollSpy(
  containerRef: RefObject<HTMLElement | null>,
  bodyKey: string,
  onChange: (sectionId: string | null) => void,
): void {
  const lastReportedRef = useRef<string | null | undefined>(undefined);

  const measure = useCallback(() => {
    const container = containerRef.current;
    if (!container) return;

    // Offsets are taken from rectangles, not from `offsetTop`: that is
    // measured against the nearest POSITIONED ancestor, which the scroll
    // container need not be. When it is not, every offset is stated in a
    // different origin from `scrollTop` and the spy reports a section the
    // reader is nowhere near — measured in Playwright before this was fixed.
    const containerTop = container.getBoundingClientRect().top;
    const offsets: SectionOffset[] = Array.from(
      container.querySelectorAll<HTMLElement>("[data-section-id]"),
    ).map((element) => ({
      id: element.dataset.sectionId ?? "",
      top: element.getBoundingClientRect().top - containerTop + container.scrollTop,
    }));

    const active = activeSectionAt(offsets, container.scrollTop);
    if (active === lastReportedRef.current) return;
    lastReportedRef.current = active;
    onChange(active);
  }, [containerRef, onChange]);

  // biome-ignore lint/correctness/useExhaustiveDependencies: `bodyKey` is the re-measure trigger, not a read
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    // Re-measure from scratch whenever the body changes — the previous
    // document's answer must not survive into the next one.
    lastReportedRef.current = undefined;
    measure();

    container.addEventListener("scroll", measure, { passive: true });
    window.addEventListener("resize", measure);
    return () => {
      container.removeEventListener("scroll", measure);
      window.removeEventListener("resize", measure);
    };
  }, [containerRef, measure, bodyKey]);
}
