"use client";

import { ExternalLink, ArrowRight } from "lucide-react";
import type { RelatedGroup } from "@/lib/types";
import { getBadgeColor } from "../../results/ExactMatchStrip";
import { EmptySection } from "../EmptySection";

interface RelatedTabProps {
  groups: RelatedGroup[];
  onFocus?: (id: string) => void;
  onPivot?: (label: string, sourceId: string) => void;
  sourceId: string;
}

/**
 * Preview surface for related items.
 *
 * Design rule: this is NOT a mini result system.
 * It must not grow its own filters, sorting, or deep navigation.
 * "Show all" is the escape hatch → PIVOT → center panel context switch.
 */
export function RelatedTab({
  groups,
  onFocus,
  onPivot,
  sourceId,
}: RelatedTabProps) {
  return (
    <div className="p-5 space-y-5">
      {groups.map((group, i) => (
        <div key={i}>
          <div className="flex items-center justify-between mb-3">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
              {group.groupLabel}
              <span className="text-[10px] font-normal text-muted-foreground/60">
                ({group.items.length})
              </span>
            </h4>
            {onPivot && group.items.length > 0 && (
              <button
                onClick={() => onPivot(group.groupLabel, sourceId)}
                className="flex items-center gap-0.5 text-[11px] font-medium text-[#2563eb] hover:text-[#1d4ed8] transition-colors"
              >
                Show all
                <ArrowRight className="w-3 h-3" />
              </button>
            )}
          </div>
          <div className="space-y-1">
            {group.items.map((item) => (
              <div
                key={item.id}
                onClick={() => onFocus?.(item.id)}
                className="flex items-center gap-2 px-3 py-2 rounded-md hover:bg-muted/50 cursor-pointer transition-colors group"
              >
                {item.badge && (
                  <span
                    className="px-1 py-0.5 rounded text-[9px] font-semibold uppercase tracking-wide shrink-0"
                    style={{
                      backgroundColor: getBadgeColor(item.badge.colorKey).bg,
                      color: getBadgeColor(item.badge.colorKey).text,
                    }}
                  >
                    {item.badge.label}
                  </span>
                )}
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-medium text-foreground truncate">
                    {item.title}
                  </div>
                  {item.subtitle && (
                    <div className="text-[11px] text-muted-foreground truncate">
                      {item.subtitle}
                    </div>
                  )}
                </div>
                <ExternalLink className="w-3 h-3 text-muted-foreground/30 group-hover:text-[#2563eb] transition-colors shrink-0" />
              </div>
            ))}
          </div>
        </div>
      ))}
      {groups.length === 0 && (
        <EmptySection label="No related materials" />
      )}
    </div>
  );
}
