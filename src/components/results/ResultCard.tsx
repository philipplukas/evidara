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
import { getBadgeColor } from "./ExactMatchStrip";

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
            ? "bg-[#2563eb]/[0.03] border-l-2 border-l-[#2563eb]"
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
            const colors = getBadgeColor(badge.colorKey);
            return (
              <span
                key={i}
                className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wide"
                style={{ backgroundColor: colors.bg, color: colors.text }}
              >
                {icon && <span className="text-xs leading-none">{icon}</span>}
                {badge.label}
              </span>
            );
          })}
        </div>
      </div>

      {/* Subtitle */}
      <div className="flex items-center gap-2 text-xs text-muted-foreground mb-2">
        <span>{result.subtitle}</span>
        {result.contentLanguage?.isTranslation && (
          <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-amber-50 text-amber-700 text-[10px] font-medium">
            <Globe className="w-2.5 h-2.5" />
            {result.contentLanguage.label}
          </span>
        )}
      </div>

      {/* Structural context */}
      {result.structuralContext && (
        <div className="text-[11px] text-muted-foreground/70 mb-2 font-medium">
          {result.structuralContext}
        </div>
      )}

      {/* Snippet */}
      <p className="text-sm text-foreground/80 leading-relaxed mb-3 line-clamp-3"
         style={{ fontFamily: "'Source Serif 4', 'Georgia', serif" }}>
        {result.snippet}
      </p>

      {/* Metadata rows */}
      {result.metadataRows.length > 0 && (
        <div className="flex flex-wrap gap-x-4 gap-y-1 mb-3">
          {result.metadataRows.map((row, i) => {
            const icon = getIcon(row.iconKey);
            return (
              <span key={i} className="text-[11px] text-muted-foreground">
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
              className="inline-flex items-center gap-1 text-[11px] text-muted-foreground
                hover:text-[#2563eb] transition-colors cursor-pointer"
            >
              <span className="font-semibold text-foreground/60">{rc.count}</span>
              {rc.label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          {/* Pin button */}
          {onPin && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onPin(result.id, result.title, result.type);
              }}
              className={`flex items-center gap-1 px-2 py-1 rounded text-[11px] font-medium transition-all
                ${isPinned
                  ? "text-[#2563eb] bg-[#2563eb]/5"
                  : "text-muted-foreground hover:text-[#2563eb] hover:bg-[#2563eb]/5"
                }`}
            >
              <MapPin className="w-3 h-3" />
              {isPinned ? "Pinned" : "Pin"}
            </button>
          )}
          {result.actions.map((action, i) => {
            const IconComp = iconComponents[action.icon] || ArrowRight;
            return (
              <button
                key={i}
                className="flex items-center gap-1 px-2 py-1 rounded text-[11px] font-medium
                  text-muted-foreground hover:text-[#2563eb] hover:bg-[#2563eb]/5 transition-all"
                onClick={(e) => {
                  e.stopPropagation();
                }}
              >
                <IconComp className="w-3 h-3" />
                {action.label}
              </button>
            );
          })}
        </div>
      </div>
    </article>
  );
}
