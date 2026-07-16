/**
 * Splitting the document body into renderable paragraphs.
 *
 * `DetailView.content` is plain text, not markup: document-intelligence builds
 * it by joining the parsed blocks with a blank line (`NormalizedDocumentIR.
 * body_text`), and the BFF passes that string through untouched. So the only
 * structure the body carries is the blank line between paragraphs.
 *
 * Single newlines inside a paragraph are hard wraps, not breaks — court
 * decisions in the corpus arrive wrapped at ~60 characters mid-sentence. They
 * are collapsed to spaces so the text reflows to the reader's column width
 * instead of keeping the source file's ragged right edge.
 */
export function toParagraphs(text: string | undefined): string[] {
  if (!text) return [];
  return text
    .split(/\n[ \t]*\n+/)
    .map((paragraph) => paragraph.replace(/\s*\n\s*/g, " ").trim())
    .filter((paragraph) => paragraph.length > 0);
}
