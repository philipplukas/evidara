/**
 * Docling Wrapper — Thin abstraction over @docling/docling-core
 *
 * WHY THIS EXISTS:
 * @docling/docling-core is v0.0.7 and explicitly marked as "unstable draft".
 * This wrapper:
 * 1. Re-exports only what we use (isolates us from API changes)
 * 2. Adds our own legal-domain metadata types
 * 3. Provides a typed iterator with legal metadata
 *
 * If the upstream API breaks, we fix this one file — not every component.
 */

import {
  type CodeItem,
  type DoclingDocument,
  isDoclingDocItem,
  iterateDocumentItems,
  type ListItem,
  type NodeItem,
  type PictureItem,
  type SectionHeaderItem,
  type TableCell,
  type TableData,
  type TableItem,
  type TextItem,
} from "@docling/docling-core";

// Re-export upstream types we use
export type {
  CodeItem,
  DoclingDocument,
  ListItem,
  NodeItem,
  PictureItem,
  SectionHeaderItem,
  TableCell,
  TableData,
  TableItem,
  TextItem,
};

export { isDoclingDocItem, iterateDocumentItems };

// ─── Legal-domain metadata extensions ───

/** Highlight range for search term matches */
export interface HighlightRange {
  start: number;
  end: number;
}

/** Cross-reference to another legal document */
export interface LegalRef {
  targetId: string;
  label: string; // e.g. "Art. 754 OR"
}

/** Legal metadata attached to content items */
export interface LegalMetadata {
  /** Marginal number (Swiss article paragraphs: "1", "2", etc.) */
  marginal?: string;
  /** Cross-references to other legal documents */
  legalRefs?: LegalRef[];
  /** Search term highlights */
  highlights?: HighlightRange[];
}

// ─── Typed content item (what our renderer receives) ───

export interface ContentItem {
  item: NodeItem;
  level: number;
  meta?: LegalMetadata;
}

/**
 * Iterate over document items in reading order, with optional legal metadata.
 * Wraps @docling/docling-core's iterateDocumentItems.
 */
export function* iterateContent(doc: DoclingDocument): Generator<ContentItem> {
  for (const [item, level] of iterateDocumentItems(doc)) {
    yield {
      item,
      level,
      // metadata is our extension — may be attached by the BFF
      meta: (item as unknown as Record<string, unknown>).legalMetadata as LegalMetadata | undefined,
    };
  }
}
