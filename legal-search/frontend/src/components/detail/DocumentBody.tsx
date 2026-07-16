import { toParagraphs } from "@/lib/document-body";

interface DocumentBodyProps {
  text: string;
}

/**
 * The document's body text.
 *
 * Rendered as text nodes, never as markup: the body is plain text (see
 * `toParagraphs`), so React's escaping is both correct and the reason this
 * component needs no sanitizer. `dangerouslySetInnerHTML` here would render a
 * document that happened to mention `<script>` as markup while doing nothing
 * for the newline structure the body actually carries.
 */
export function DocumentBody({ text }: DocumentBodyProps) {
  const paragraphs = toParagraphs(text);
  if (paragraphs.length === 0) return null;

  return (
    <div className="max-w-[72ch] space-y-3 font-document text-sm leading-7 text-foreground/88">
      {paragraphs.map((paragraph, index) => (
        // Paragraphs have no stable id — the body is a flat string. Index keys
        // are safe here because the list is derived, never reordered.
        // biome-ignore lint/suspicious/noArrayIndexKey: derived, static list
        <p key={index}>{paragraph}</p>
      ))}
    </div>
  );
}
