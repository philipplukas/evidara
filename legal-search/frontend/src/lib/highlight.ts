import DOMPurify from "dompurify";

/**
 * The search API returns snippets with the matched terms wrapped in `<mark>`
 * (OpenSearch's highlighter — see `opensearch.adapter.ts`). `<mark>` is the
 * only markup a snippet may carry; everything else is document text we do not
 * trust and must not render as HTML.
 */
const ALLOWED_TAGS = ["mark"];

/** Sanitize a snippet for rendering, keeping only the highlight markup. */
export function sanitizeSnippetHtml(snippet: string): string {
  if (!snippet) return "";
  return DOMPurify.sanitize(snippet, {
    ALLOWED_TAGS,
    ALLOWED_ATTR: [],
  });
}

/**
 * Strip the highlight markup, leaving plain text. For contexts that are not
 * HTML — CSV export, `aria-label`, anything copied to a clipboard.
 */
export function stripHighlightTags(snippet: string): string {
  if (!snippet) return "";
  return DOMPurify.sanitize(snippet, {
    ALLOWED_TAGS: [],
    ALLOWED_ATTR: [],
  });
}
