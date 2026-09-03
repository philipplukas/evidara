"use client";

import { ChevronDown, ChevronUp } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toParagraphs } from "@/lib/document-body";
import { SectionLabel } from "../primitives";

interface RegesteProps {
  text: string | undefined;
}

/**
 * The official headnote (Regeste) of a court decision.
 *
 * Rendered as prose, not as a metadata row: it is the paragraph a lawyer reads
 * first to decide whether a decision is worth opening at all. It lives in the
 * panel header rather than inside a tab so it is visible whichever tab is
 * active — the search snippet already quotes fragments of it, so hiding it
 * behind a click would leave the result list carrying more legal signal than
 * the document it links to (#760).
 *
 * Three lengths have to work:
 *   - **absent / blank** — render nothing. A labelled box around no text is
 *     worse than no box, and most documents have no Regeste at all (the
 *     projection does not emit the field; see `lib/types.ts`).
 *   - **short** — one or two sentences, shown whole, with no expand control:
 *     a toggle that reveals nothing is noise.
 *   - **long** — several paragraphs. Clamped to four lines, expanded in place,
 *     and the expanded block scrolls inside its own bounded box. The header
 *     shares its height with the tab body, so an unbounded headnote would push
 *     the tabs off the panel.
 *
 * Plain text, rendered as text nodes — the same reasoning as `DocumentBody`,
 * and the reason no sanitizer is needed here.
 */
export function Regeste({ text }: RegesteProps) {
  const t = useTranslations("detail");
  const [expanded, setExpanded] = useState(false);
  const paragraphs = toParagraphs(text);

  if (paragraphs.length === 0) return null;

  // Whether the clamp actually bites depends on the rendered column width,
  // which this component cannot measure without a layout effect. A length
  // heuristic is enough to keep a two-sentence headnote from carrying a
  // control that does nothing; guessing slightly wrong only costs a toggle
  // that reveals a line or two.
  const isTruncatable = paragraphs.length > 1 || paragraphs[0].length > 280;
  const isOpen = expanded || !isTruncatable;

  return (
    <section aria-label={t("regeste.heading")} className="mt-3">
      <div className="rounded-lg border-l-2 border-accent-core-muted bg-interactive-accent-subtle px-3 py-2.5">
        <SectionLabel>{t("regeste.heading")}</SectionLabel>
        <div
          // A scrollable region has to be reachable by keyboard, so the
          // expanded box takes a tab stop. The collapsed box scrolls nothing
          // and takes none.
          tabIndex={isOpen && isTruncatable ? 0 : undefined}
          className={`mt-1.5 font-document text-xs leading-6 text-foreground/85 [&>p+p]:mt-2 ${
            isOpen ? "max-h-[40vh] overflow-y-auto" : "line-clamp-4"
          }`}
        >
          {paragraphs.map((paragraph, index) => (
            // Index keys are safe here: the list is derived from the string
            // and never reordered — same rationale as `DocumentBody`.
            <p key={index}>{paragraph}</p>
          ))}
        </div>
        {isTruncatable && (
          <button
            type="button"
            aria-expanded={expanded}
            onClick={() => setExpanded(!expanded)}
            className="mt-1.5 inline-flex items-center gap-1 rounded-md px-1 py-0.5 text-tiny font-medium text-text-meta transition-colors hover:text-foreground"
          >
            {expanded ? (
              <>
                <ChevronUp className="h-3 w-3" />
                {t("showLess")}
              </>
            ) : (
              <>
                <ChevronDown className="h-3 w-3" />
                {t("regeste.showMore")}
              </>
            )}
          </button>
        )}
      </div>
    </section>
  );
}
