"use client";

import { useMemo } from "react";
import { buildDocumentOutline, type DocumentOutline } from "@/lib/document-structure";
import type { DetailViewModel } from "@/lib/types";

/**
 * The document's outline aligned to its body.
 *
 * Reading mode renders the outline (the left rail) and the body (the centre
 * column) in two different components, and both need the same answer to
 * "which sections were actually placed in the text" — a rail that offered a
 * jump the body cannot honour is the #1040 defect with a new layout.
 *
 * So the alignment goes through one function with one set of inputs. Callers
 * memoize separately, which costs a second linear pass over the body, and buys
 * the guarantee that the two cannot disagree: there is no second rule to drift.
 */
export function useDocumentOutline(detail: DetailViewModel | null): DocumentOutline {
  const contentText = detail?.contentText;
  const structureItems = detail?.localStructure?.items;

  return useMemo(
    () => buildDocumentOutline(contentText, structureItems ?? []),
    [contentText, structureItems],
  );
}
