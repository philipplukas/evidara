/**
 * Which section the reader is currently inside.
 *
 * The outline is only navigation if it answers "where am I" as well as "where
 * can I go". Before #1053 it could answer neither at once: the outline lived
 * behind a tab that replaced the text, so seeing your position and reading your
 * position were two different screens.
 *
 * The rule, stated once here so the rail and any future surface cannot disagree
 * about it:
 *
 *   The active section is the LAST heading whose top edge is at or above the
 *   reading line — a band just below the top of the scroll viewport. Above the
 *   first heading, the first heading is active; a document with no placed
 *   heading has no active section, which is `null` and not "the first one".
 *
 * `null` is a real answer. `buildDocumentOutline` reports sections it could not
 * place in the body, and a rail that highlighted one of those would be claiming
 * a position the reader is not at.
 *
 * Kept as a pure function of measured offsets so it can be asserted without a
 * browser — jsdom implements no layout, so a spy written directly against
 * `getBoundingClientRect` is untestable at the unit layer and was the sort of
 * thing that ships unasserted. `use-reader-scroll-spy.ts` supplies the real
 * offsets; `e2e/workspace-panels.spec.ts` checks the wiring against a rendered
 * document, which is the case whose answer does not come from this file.
 */

/** A placed section heading and its offset from the top of the scrolled content. */
export interface SectionOffset {
  id: string;
  /** `offsetTop` within the scroll container, in px. */
  top: number;
}

/**
 * How far below the top of the viewport the reading line sits, in px.
 *
 * Without it, a heading scrolled to exactly the top edge flickers between
 * itself and its predecessor on sub-pixel scrolls, and a heading one pixel
 * below the fold still counts as "above" — the reader sees the next section
 * highlighted while still reading the previous one's last paragraph.
 */
export const READING_LINE_OFFSET_PX = 96;

/**
 * The section containing the reading line.
 *
 * @param offsets placed headings in document order.
 * @param scrollTop the scroll container's `scrollTop`.
 */
export function activeSectionAt(
  offsets: readonly SectionOffset[],
  scrollTop: number,
): string | null {
  if (offsets.length === 0) return null;

  const readingLine = scrollTop + READING_LINE_OFFSET_PX;
  let active: string | null = null;
  for (const offset of offsets) {
    if (offset.top > readingLine) break;
    active = offset.id;
  }
  // Above the first heading the reader is in the document's preamble; report
  // the first section rather than nothing, so the rail is never blank while a
  // placed outline exists.
  return active ?? offsets[0].id;
}
