"use client";

import { useMemo } from "react";
import { sanitizeSnippetHtml, stripHighlightTags } from "@/lib/highlight";
import { cn } from "@/lib/utils";

interface HighlightedSnippetProps {
  snippet: string;
  className?: string;
}

/**
 * Render a search snippet with the matched terms emphasised. The API marks
 * them with `<mark>`; rendering the string as a text child would show those
 * tags to the user as literal text, so the snippet is sanitized down to
 * `<mark>` and rendered as HTML.
 */
export function HighlightedSnippet({ snippet, className }: HighlightedSnippetProps) {
  const html = useMemo(() => sanitizeSnippetHtml(snippet), [snippet]);

  if (!html.trim()) {
    return null;
  }

  return (
    <p
      className={cn(
        "font-document text-[13px] leading-6 text-foreground/80",
        "[&_mark]:rounded-[2px] [&_mark]:bg-attention-subtle [&_mark]:px-0.5",
        "[&_mark]:font-semibold [&_mark]:text-attention",
        className,
      )}
      // Sanitized above: `<mark>` only, no attributes.
      dangerouslySetInnerHTML={{ __html: html }}
      title={stripHighlightTags(snippet)}
    />
  );
}
