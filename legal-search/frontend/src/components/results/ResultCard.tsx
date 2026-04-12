"use client";

import { ArrowRight, Bookmark, BookOpen, FileText, Globe, Link, MapPin, Scale } from "lucide-react";
import { getIcon } from "@/lib/icons";
import type { SearchResultViewModel } from "@/lib/types";
import { AccentButton, Badge } from "../primitives";

const iconComponents: Record<string, React.ComponentType<{ className?: string }>> = {
  "file-text": FileText,
  scale: Scale,
  "book-open": BookOpen,
  bookmark: Bookmark,
  "arrow-right": ArrowRight,
  link: Link,
  globe: Globe,
};

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
  return (
    <article
      aria-current={isSelected ? "true" : undefined}
      onClick={() => onFocus(result.id)}
      className={`group px-4 py-4 border-b border-border/60 cursor-pointer transition-all rounded-sm
        sm:px-5
        ${
          isSelected
            ? "bg-brand/[0.06] border-l-2 border-l-brand shadow-[inset_0_0_0_1px_rgba(15,76,129,0.22)]"
            : "hover:bg-muted/30 border-l-2 border-l-transparent hover:shadow-[inset_0_0_0_1px_rgba(15,23,42,0.08)]"
        }`}
    >
      {/* Title row */}
      <div className="mb-2 flex flex-col gap-2 sm:flex-row sm:items-start sm:gap-2">
        <h3 className="min-w-0 flex-1 text-sm font-semibold leading-snug text-foreground">
          {result.title}
        </h3>
        <div className="flex flex-wrap items-center gap-1.5 sm:justify-end">
          {isSelected && (
            <span className="inline-flex items-center rounded-full border border-brand/20 bg-brand/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-brand">
              Selected
            </span>
          )}
          {result.badges.map((badge, i) => {
            const icon = getIcon(badge.iconKey);
            return (
              <span key={i} className="inline-flex items-center gap-1">
                {icon && <span className="text-xs leading-none">{icon}</span>}
                <Badge label={badge.label} colorKey={badge.colorKey} />
              </span>
            );
          })}
        </div>
      </div>

      {/* Subtitle */}
      <div className="mb-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <span>{result.subtitle}</span>
        {result.contentLanguage?.isTranslation && (
          <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-amber-50 text-amber-700 text-tiny font-medium">
            <Globe className="w-2.5 h-2.5" />
            {result.contentLanguage.label}
          </span>
        )}
      </div>

      {/* Structural context */}
      {result.structuralContext && (
        <div className="text-micro text-muted-foreground/70 mb-2 font-medium">
          {result.structuralContext}
        </div>
      )}

      {/* Snippet */}
      <p className="text-sm text-foreground/80 leading-relaxed mb-3 line-clamp-3 font-document">
        {result.snippet}
      </p>

      {/* Metadata rows */}
      {result.metadataRows.length > 0 && (
        <div className="flex flex-wrap gap-x-4 gap-y-1 mb-3">
          {result.metadataRows.map((row, i) => {
            const icon = getIcon(row.iconKey);
            return (
              <span key={i} className="text-micro text-muted-foreground">
                <span className="font-medium text-foreground/60">{row.label}:</span>{" "}
                {icon && <span className="text-xs">{icon}</span>} {row.value}
              </span>
            );
          })}
        </div>
      )}

      {/* Bottom row: related counts (pivots) + actions */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap gap-2">
          {result.relatedCounts.map((rc, i) => (
            <button
              type="button"
              key={i}
              onClick={(e) => {
                e.stopPropagation();
                onPivot?.(rc.label, result.id);
              }}
              className="inline-flex items-center gap-1 text-micro text-muted-foreground
                hover:text-brand transition-colors cursor-pointer"
            >
              <span className="font-semibold text-foreground/60">{rc.count}</span>
              {rc.label}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-1 opacity-70 transition-opacity group-hover:opacity-100">
          {onPin && (
            <AccentButton
              onClick={(e) => {
                e.stopPropagation();
                onPin(result.id, result.title, result.type);
              }}
              active={isPinned}
            >
              <MapPin className="w-3 h-3" />
              {isPinned ? "Pinned" : "Pin"}
            </AccentButton>
          )}
          {result.actions.map((action, i) => {
            const IconComp = iconComponents[action.icon] || ArrowRight;
            return (
              <AccentButton key={i} onClick={(e) => e.stopPropagation()}>
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
