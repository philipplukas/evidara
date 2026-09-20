/**
 * Placing a document's sections inside its body text.
 *
 * The two arrive from different indices and neither references the other by
 * offset: `content` is one plain string (see `document-body.ts`), and the
 * `sections` index carries `{title, ordinal, depth, content_preview}` rows. So
 * the only way to turn an outline entry into somewhere the reader can go is to
 * find where that section's text begins in the body.
 *
 * Two rules, applied in document order, and no others:
 *
 *   1. A paragraph that IS the section's title becomes the heading — the body
 *      already carried the heading line, it was simply rendered as another
 *      `<p>` ("A. Allgemeine Bestimmungen" was indistinguishable from prose).
 *   2. A paragraph that starts with the section's `content_preview` gets the
 *      heading inserted before it — the body carried no heading line, so the
 *      outline supplies one.
 *
 * **A section that matches neither is reported as not anchored, and that is a
 * first-class outcome.** It renders in the outline with its text and is not
 * clickable, because there is nowhere in the body to send the reader. The
 * alternative — accept the click and scroll nowhere — is the silent abstention
 * this repo keeps paying for: it looks identical to a jump that worked.
 *
 * Matching is greedy and forward-only: a cursor advances past each anchored
 * paragraph, so section N+1 can never anchor above section N however similar
 * their text. Lookups go through two prefix indices rather than a rescan per
 * section, which keeps the ZGB (1,377 sections over 6,809 paragraphs) linear
 * instead of quadratic.
 */

import { toParagraphs } from "@/lib/document-body";
import type { LocalStructureItem } from "@/lib/types";

export type DocumentBlock =
  | { kind: "heading"; sectionId: string; label: string; depth: number }
  | { kind: "paragraph"; text: string };

export interface DocumentOutline {
  /** The body, in reading order, with section headings placed in it. */
  blocks: DocumentBlock[];
  /**
   * The sections that found a place in the body. Only these can be scrolled
   * to; every other outline entry is a label and its text, nothing more.
   */
  anchored: ReadonlySet<string>;
}

/**
 * How many leading characters of a section preview must match a paragraph.
 *
 * Long enough that two different articles of the same statute do not collide
 * on boilerplate ("Der Regierungsrat erlässt…"), short enough to survive the
 * index truncating `content_preview` at 200 characters and the body carrying
 * a paragraph shorter than that.
 */
const PREFIX_LENGTH = 24;

/** Indent levels the outline renders. Deeper sections render at the deepest. */
export const MAX_OUTLINE_DEPTH = 5;

/**
 * Indent per outline level, as static class names so Tailwind keeps them.
 *
 * Shared by every surface that renders the outline — the tab and the reading
 * rail (#1053). Two copies would let the same document nest differently
 * depending on which one you were looking at, which is the drift AGENTS.md
 * names ("the same rule enforced in two clients rather than once behind them").
 * Indexed by the depth `relativeDepths` returns, so it is exactly
 * `MAX_OUTLINE_DEPTH + 1` long.
 */
export const OUTLINE_INDENT_CLASS = ["ps-0", "ps-4", "ps-8", "ps-12", "ps-16", "ps-20"];

/** The DOM id a section heading carries, so the reader can be sent to it. */
export function sectionAnchorId(sectionId: string): string {
  return `section-${sectionId}`;
}

/**
 * Compare-form of a string: case-folded, whitespace-collapsed, and with the
 * several dashes Swiss legal text mixes ("Art. 754 – Haftung", "Art. 754 -
 * Haftung") folded to one. Nothing else is stripped — punctuation carries
 * meaning in a citation.
 */
function normalize(value: string): string {
  return value.toLowerCase().replace(/[‐-―]/g, "-").replace(/\s+/g, " ").trim();
}

function indexBy(map: Map<string, number[]>, key: string, index: number): void {
  const existing = map.get(key);
  if (existing) existing.push(index);
  else map.set(key, [index]);
}

/** First index in an ascending list that is at or after `cursor`, or -1. */
function firstAtOrAfter(indices: number[] | undefined, cursor: number): number {
  if (!indices) return -1;
  for (const index of indices) {
    if (index >= cursor) return index;
  }
  return -1;
}

/**
 * Outline depths rebased so the shallowest section present renders flush.
 *
 * Sources disagree about whether the top level is 0 or 1, and one that starts
 * at 1 would otherwise render its entire outline indented by one step with
 * nothing at the left edge.
 */
export function relativeDepths(items: LocalStructureItem[]): Map<string, number> {
  let base = Number.POSITIVE_INFINITY;
  for (const item of items) base = Math.min(base, item.depth ?? 0);
  if (!Number.isFinite(base)) base = 0;

  return new Map(
    items.map((item) => [
      item.id,
      Math.min(Math.max((item.depth ?? 0) - base, 0), MAX_OUTLINE_DEPTH),
    ]),
  );
}

/**
 * Interleave the outline into the body.
 *
 * `text` undefined or empty yields no blocks and no anchors — a document with
 * no body has nowhere to put its sections, which the caller must render as
 * "cannot jump" rather than as an outline that does nothing.
 */
export function buildDocumentOutline(
  text: string | undefined,
  items: LocalStructureItem[] = [],
): DocumentOutline {
  const paragraphs = toParagraphs(text);
  if (paragraphs.length === 0) return { blocks: [], anchored: new Set() };
  if (items.length === 0) {
    return {
      blocks: paragraphs.map((paragraph) => ({ kind: "paragraph", text: paragraph })),
      anchored: new Set(),
    };
  }

  const normalized = paragraphs.map(normalize);
  const byTitle = new Map<string, number[]>();
  const byPrefix = new Map<string, number[]>();
  normalized.forEach((paragraph, index) => {
    indexBy(byTitle, paragraph, index);
    if (paragraph.length >= PREFIX_LENGTH) {
      indexBy(byPrefix, paragraph.slice(0, PREFIX_LENGTH), index);
    }
  });

  const depths = relativeDepths(items);
  /** Paragraph index → the heading that replaces it (rule 1). */
  const replaceAt = new Map<number, DocumentBlock>();
  /** Paragraph index → the heading inserted before it (rule 2). */
  const insertAt = new Map<number, DocumentBlock>();
  const anchored = new Set<string>();

  let cursor = 0;
  for (const item of items) {
    const titleIndex = firstAtOrAfter(byTitle.get(normalize(item.label)), cursor);
    const preview = item.text ? normalize(item.text).slice(0, PREFIX_LENGTH) : "";
    const textIndex =
      preview.length >= PREFIX_LENGTH ? firstAtOrAfter(byPrefix.get(preview), cursor) : -1;

    if (titleIndex < 0 && textIndex < 0) continue;

    const heading: DocumentBlock = {
      kind: "heading",
      sectionId: item.id,
      label: item.label,
      depth: depths.get(item.id) ?? 0,
    };

    // The title line wins a tie: it means the body already holds this heading,
    // so replacing it keeps the reader's text exactly as published instead of
    // printing the same line twice.
    const replaces = titleIndex >= 0 && (textIndex < 0 || titleIndex <= textIndex);
    const index = replaces ? titleIndex : textIndex;
    if (replaces) replaceAt.set(index, heading);
    else insertAt.set(index, heading);

    anchored.add(item.id);
    cursor = index + 1;
  }

  const blocks: DocumentBlock[] = [];
  paragraphs.forEach((paragraph, index) => {
    const inserted = insertAt.get(index);
    if (inserted) blocks.push(inserted);
    const replacement = replaceAt.get(index);
    if (replacement) blocks.push(replacement);
    else blocks.push({ kind: "paragraph", text: paragraph });
  });

  return { blocks, anchored };
}
