"use client";

import { ArrowRight, Bookmark, BookOpen, FileText, Globe, Link, MapPin, Scale } from "lucide-react";
import { useTranslations } from "next-intl";
import { ShareButton } from "@/components/ui/ShareButton";
import { getFlagSrc, getIcon, isFlagIcon } from "@/lib/icons";
import type { SearchResultViewModel } from "@/lib/types";
import { AccentButton, Badge } from "../primitives";
import { HighlightedSnippet } from "./HighlightedSnippet";

const iconComponents: Record<string, React.ComponentType<{ className?: string }>> = {
  "file-text": FileText,
  scale: Scale,
  "book-open": BookOpen,
  bookmark: Bookmark,
  "arrow-right": ArrowRight,
  link: Link,
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

interface ResultCardProps {
  result: SearchResultViewModel;
  isSelected: boolean;
  onFocus: (id: string) => void;
  onPivot?: (label: string, sourceId: string) => void;
  onPin?: (id: string, title: string, type: string) => void;
  isPinned?: boolean;
}

export function ResultCard({
  result,
  isSelected,
  onFocus,
  onPivot,
  onPin,
  isPinned,
}: ResultCardProps) {
  const t = useTranslations("results.card");
  return (
    <article
      aria-current={isSelected ? "true" : undefined}
      aria-label={t("openResult", { title: result.title })}
      onClick={() => onFocus(result.id)}
      className={`group cursor-pointer border-b border-border/60 px-4 py-3.5 transition-all
        transition-motion-medium focus-within:ring-2 focus-within:ring-focus-ring sm:px-5
        ${
          isSelected
            ? "border-l-2 border-l-accent-core bg-interactive-accent-subtle shadow-ring-accent"
            : "border-l-2 border-l-transparent hover:-translate-y-px hover:bg-muted/30 hover:shadow-ring-subtle"
        }`}
    >
      {result.structuralContext && (
        <div className="mb-1 text-tiny font-semibold uppercase tracking-[0.14em] text-text-meta">
          {result.structuralContext}
        </div>
      )}

      {/* Title row */}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between sm:gap-3">
        <h3 className="min-w-0 flex-1">
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onFocus(result.id);
            }}
            className="text-left text-[15px] font-semibold leading-5 text-foreground hover:text-accent-core focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring focus-visible:rounded"
          >
            {result.title}
          </button>
        </h3>
        <div className="flex flex-wrap items-center gap-1.5 sm:justify-end">
          {isSelected && (
            <span className="inline-flex items-center rounded-full border border-accent-core/20 bg-accent-core/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-accent-core">
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
      <HighlightedSnippet className="mb-3 mt-3 line-clamp-3" snippet={result.snippet} />

      {/* Metadata rows */}
      {result.metadataRows.length > 0 && (
        <div className="mb-3 grid gap-1.5 rounded-lg border border-border/60 bg-muted/25 px-3 py-2 sm:grid-cols-[repeat(auto-fit,minmax(11rem,1fr))]">
          {result.metadataRows.map((row, i) => (
            <span
              key={i}
              className="inline-flex min-w-0 items-center gap-1 text-[11px] text-text-meta"
            >
              <IconCell iconKey={row.iconKey} className="shrink-0 text-xs text-text-meta" />
              <span className="shrink-0 font-medium text-text-meta">{row.label}:</span>
              <span className="min-w-0 truncate text-foreground/80">{row.value}</span>
            </span>
          ))}
        </div>
      )}

      {/* Bottom row: related counts (pivots) + actions */}
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
                hover:border-accent-core/30 hover:bg-accent-core/5 hover:text-accent-core"
            >
              <span className="font-semibold text-text-meta">{rc.count}</span>
              {rc.label}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-1">
          <ShareButton
            size="sm"
            className="border border-border/70 bg-background shadow-sm"
            label={t("shareResult")}
          />
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
