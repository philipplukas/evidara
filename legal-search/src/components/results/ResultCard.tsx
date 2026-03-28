"use client";

import {
  FileText,
  Scale,
  BookOpen,
  Bookmark,
  ArrowRight,
  Link,
  Globe,
  MapPin,
} from "lucide-react";
import type { SearchResultViewModel } from "@/lib/types";
import { getIcon } from "@/lib/icons";
import { Badge, AccentButton } from "../primitives";

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
      onClick={() => onFocus(result.id)}
      className={`group px-5 py-4 border-b border-border/60 cursor-pointer transition-all
        ${
          isSelected
            ? "bg-brand/[0.03] border-l-2 border-l-brand"
            : "hover:bg-muted/30 border-l-2 border-l-transparent"
        }`}
    >
      {/* Title row */}
      <div className="flex items-start gap-2 mb-1.5">
        <h3 className="text-sm font-semibold text-foreground flex-1 leading-snug">
          {result.title}
        </h3>
        <div className="flex items-center gap-1.5 shrink-0">
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
      <div className="flex items-center gap-2 text-xs text-muted-foreground mb-2">
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
                {icon && <span className="text-xs">{icon}</span>}{" "}
                {row.value}
              </span>
            );
          })}
        </div>
      )}

      {/* Bottom row: related counts (pivots) + actions */}
      <div className="flex items-center justify-between">
        <div className="flex flex-wrap gap-2">
          {result.relatedCounts.map((rc, i) => (
            <button
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
        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
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
              <AccentButton
                key={i}
                onClick={(e) => e.stopPropagation()}
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
