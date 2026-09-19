import { toParagraphs } from "@/lib/document-body";
import {
  type DocumentBlock,
  type DocumentOutline,
  sectionAnchorId,
} from "@/lib/document-structure";

interface DocumentBodyProps {
  text: string;
  /**
   * The body with its sections placed in it, from `buildDocumentOutline`.
   *
   * Optional, and its absence is not "no structure" — it is "the caller did
   * not compute one", which is why the fallback below renders the same
   * paragraphs this component has always rendered rather than an empty body.
   * `DetailPanel` computes it once and hands the same value to every surface
   * that renders the body, so the outline and the text cannot disagree about
   * where a section starts.
   */
  outline?: DocumentOutline;
}

/** Heading size by outline depth. Deeper sections share the last step. */
const HEADING_CLASS = [
  "text-sm font-semibold text-foreground",
  "text-xs font-semibold text-foreground",
  "text-xs font-semibold text-foreground/85",
  "text-xs font-medium text-foreground/80",
  "text-xs font-medium text-foreground/75",
  "text-xs font-medium text-foreground/70",
];

/**
 * The document's body text.
 *
 * Rendered as text nodes, never as markup: the body is plain text (see
 * `toParagraphs`), so React's escaping is both correct and the reason this
 * component needs no sanitizer. `dangerouslySetInnerHTML` here would render a
 * document that happened to mention `<script>` as markup while doing nothing
 * for the newline structure the body actually carries.
 *
 * Section headings are real elements with ids, which is what lets the outline
 * move the reader. Before #1040 this component emitted `<p>` and nothing else
 * — measured live, a rendered statute contained zero headings and zero
 * anchors, so "A. Allgemeine Bestimmungen" was a paragraph like any other and
 * the outline had nowhere to point.
 */
export function DocumentBody({ text, outline }: DocumentBodyProps) {
  const blocks: DocumentBlock[] =
    outline?.blocks ??
    toParagraphs(text).map((paragraph) => ({ kind: "paragraph", text: paragraph }));

  if (blocks.length === 0) return null;

  return (
    <div className="max-w-[72ch] space-y-3 font-document text-sm leading-7 text-foreground/88">
      {blocks.map((block, index) =>
        block.kind === "heading" ? (
          <h3
            key={block.sectionId}
            id={sectionAnchorId(block.sectionId)}
            data-section-id={block.sectionId}
            style={{ marginInlineStart: `${block.depth * 0.75}rem`, scrollMarginTop: "0.5rem" }}
            className={`pt-2 font-sans ${HEADING_CLASS[block.depth] ?? HEADING_CLASS[0]}`}
          >
            {block.label}
          </h3>
        ) : (
          // Paragraphs have no stable id — the body is a flat string. Index
          // keys are safe here because the list is derived, never reordered.
          <p key={index}>{block.text}</p>
        ),
      )}
    </div>
  );
}
