"use client";

import { ArrowRight, BookOpen, FileText, Globe, Link as LinkIcon, MapPin } from "lucide-react";
import { useTranslations } from "next-intl";
import { ShareButton } from "@/components/ui/ShareButton";
import { getFlagSrc, getIcon, isFlagIcon } from "@/lib/icons";
import type { SearchResultViewModel } from "@/lib/types";
import { AccentButton, Badge } from "../primitives";
import { HighlightedSnippet } from "./HighlightedSnippet";

/**
 * Variant of ResultCard for `record_kind=commentary_insight` /
 * `document_type=commentary` rows. Visually distinct from the default
 * card so commentary is recognizable in mixed result lists, with a
 * "Commentary on:" block exposing source-document links so operators
 * can pivot to the primary statute or decision the commentary
 * references. Styling uses existing design tokens — no hardcoded
 * colors per `legal-search/frontend/src/app/globals.css`.
 */

const iconComponents: Record<string, React.ComponentType<{ className?: string }>> = {
  "file-text": FileText,
  "book-open": BookOpen,
  "arrow-right": ArrowRight,
  link: LinkIcon,
  globe: Globe,
};

function IconCell({ iconKey, className }: { iconKey?: string; className?: string }) {
  if (!iconKey) return null;
  if (isFlagIcon(iconKey)) {
    return (
      <img
        src={getFlagSrc(iconKey)!}
        alt={iconKey.toUpperCase()}
        width={14}
        height={14}
        className={className}
      />
    );
  }
  const text = getIcon(iconKey);
  if (!text) return null;
  return <span className={className}>{text}</span>;
}

interface CommentaryResultCardProps {
  result: SearchResultViewModel;
  isSelected: boolean;
  onFocus: (id: string) => void;
  onPivot?: (label: string, sourceId: string) => void;
  onPin?: (id: string, title: string, type: string) => void;
  isPinned?: boolean;
}

export function CommentaryResultCard({
  result,
  isSelected,
  onFocus,
  onPivot,
  onPin,
  isPinned,
}: CommentaryResultCardProps) {
  const t = useTranslations("results.card");
  const tCommentary = useTranslations("results.commentaryCard");
  const sourceDocumentIds = result.sourceDocumentIds ?? [];

  return (
    <article
      aria-current={isSelected ? "true" : undefined}
      aria-label={t("openResult", { title: result.title })}
      data-record-kind="commentary_insight"
      onClick={() => onFocus(result.id)}
      className={`group cursor-pointer border-b border-border/60 bg-attention-subtle/30 px-4 py-3.5
        transition-all transition-motion-medium focus-within:ring-2 focus-within:ring-focus-ring sm:px-5
        ${
          isSelected
            ? "border-l-2 border-l-attention bg-attention-subtle shadow-ring-accent"
            : "border-l-2 border-l-attention/60 hover:-translate-y-px hover:bg-attention-subtle/50 hover:shadow-ring-subtle"
        }`}
    >
      {/* Commentary kind marker — visible at the top of the card so the
          variant is unambiguous in dense lists. */}
      <div className="mb-1 flex items-center gap-1.5">
        <BookOpen aria-hidden="true" className="h-3 w-3 text-attention" />
        <span className="text-tiny font-semibold uppercase tracking-[0.14em] text-attention">
          {tCommentary("kindLabel")}
        </span>
        {result.structuralContext && (
          <>
            <span aria-hidden="true" className="text-tiny text-text-meta">
              ·
            </span>
            <span className="text-tiny font-semibold uppercase tracking-[0.14em] text-text-meta">
              {result.structuralContext}
            </span>
          </>
        )}
      </div>

      {/* Title row */}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between sm:gap-3">
        <h3 className="min-w-0 flex-1">
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onFocus(result.id);
            }}
            className="text-left text-[15px] font-semibold leading-5 text-foreground hover:text-attention focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring focus-visible:rounded"
          >
            {result.title}
          </button>
        </h3>
        <ShareButton size="sm" className="opacity-0 group-hover:opacity-100 transition-opacity" />
        <div className="flex flex-wrap items-center gap-1.5 sm:justify-end">
          {isSelected && (
            <span className="inline-flex items-center rounded-full border border-attention/20 bg-attention/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-attention">
              {t("selected")}
            </span>
          )}
          {result.badges.map((badge, i) => (
            <span key={i} className="inline-flex items-center gap-1">
              <IconCell iconKey={badge.iconKey} className="text-xs leading-none" />
              <Badge label={badge.label} colorKey={badge.colorKey} />
            </span>
          ))}
        </div>
      </div>

      {/* Subtitle */}
      <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-text-meta">
        <span className="min-w-0">{result.subtitle}</span>
        {result.contentLanguage?.isTranslation && (
          <span className="inline-flex items-center gap-0.5 rounded bg-attention-subtle px-1.5 py-0.5 text-tiny font-medium text-attention">
            <Globe className="h-2.5 w-2.5" />
            {result.contentLanguage.label}
          </span>
        )}
      </div>

      {/* Snippet */}
      <HighlightedSnippet className="mb-3 line-clamp-3" snippet={result.snippet} />

      {/* Source documents — the commentary's "Commentary on:" block. */}
      {sourceDocumentIds.length > 0 && (
        <section
          aria-label={tCommentary("sourceDocumentsAriaLabel", { count: sourceDocumentIds.length })}
          className="mb-3 flex flex-wrap items-center gap-x-2 gap-y-1 rounded-md border border-attention/20 bg-attention-subtle/40 px-2.5 py-1.5"
        >
          <span className="inline-flex items-center gap-1 text-tiny font-semibold uppercase tracking-[0.14em] text-attention">
            <LinkIcon className="h-2.5 w-2.5" />
            {tCommentary("commentaryOn")}
          </span>
          <ul className="flex flex-wrap gap-x-2 gap-y-1">
            {sourceDocumentIds.map((docId) => (
              <li key={docId} className="inline-flex">
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    onFocus(docId);
                  }}
                  className="inline-flex items-center gap-1 rounded-full border border-attention/30
                    bg-background px-2 py-0.5 text-[11px] font-medium text-attention
                    hover:border-attention/60 hover:bg-attention/10
                    focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
                >
                  <FileText className="h-2.5 w-2.5" />
                  {docId}
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Metadata rows */}
      {result.metadataRows.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-x-3 gap-y-1">
          {result.metadataRows.map((row, i) => (
            <span key={i} className="inline-flex items-center gap-1 text-[11px] text-text-meta">
              <IconCell iconKey={row.iconKey} className="text-xs text-text-meta" />
              <span className="font-medium text-text-meta">{row.label}:</span>
              <span className="text-foreground/80">{row.value}</span>
            </span>
          ))}
        </div>
      )}

      {/* Bottom row: related counts + actions */}
      <div className="flex flex-col gap-3 border-t border-border/60 pt-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap gap-2">
          {result.relatedCounts.map((rc, i) => (
            <button
              type="button"
              key={i}
              aria-label={t("seeRelated", { count: rc.count, label: rc.label })}
              onClick={(e) => {
                e.stopPropagation();
                onPivot?.(rc.label, result.id);
              }}
              className="inline-flex items-center gap-1.5 min-h-11 sm:min-h-0 rounded-full border border-border/70
                bg-muted/20 px-2.5 py-2 sm:py-1 text-[11px] font-medium text-text-meta transition-colors
                hover:border-attention/30 hover:bg-attention/5 hover:text-attention"
            >
              <span className="font-semibold text-text-meta">{rc.count}</span>
              {rc.label}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-1">
          {onPin && (
            <AccentButton
              onClick={(e) => {
                e.stopPropagation();
                onPin(result.id, result.title, result.type);
              }}
              active={isPinned}
              title={isPinned ? t("unpinResult") : t("pinResult")}
              className="border border-border/70 bg-background shadow-sm"
            >
              <MapPin className="w-3 h-3" />
              {isPinned ? t("pinned") : t("pin")}
            </AccentButton>
          )}
          {result.actions.map((action, i) => {
            const IconComp = iconComponents[action.icon] || ArrowRight;
            return (
              <AccentButton
                key={i}
                onClick={(e) => e.stopPropagation()}
                title={action.label}
                className="border border-border/70 bg-background shadow-sm"
              >
                <IconComp className="w-3 h-3" />
                {action.label}
              </AccentButton>
            );
          })}
        </div>
      </div>
    </article>
  );
}

/**
 * Returns true when this result should render as a commentary card.
 * Pure helper, exported so dispatch logic can be unit-tested cheaply.
 */
export function isCommentaryResult(result: SearchResultViewModel): boolean {
  return result.recordKind === "commentary_insight" || result.type === "commentary";
}
