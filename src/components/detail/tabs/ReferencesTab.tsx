"use client";

import { ArrowRight } from "lucide-react";
import type { ReferenceGroup } from "@/lib/types";
import { EmptySection } from "../EmptySection";

interface ReferencesTabProps {
  references: ReferenceGroup[];
  onFocus?: (id: string) => void;
  onPivot?: (label: string, sourceId: string) => void;
  sourceId: string;
  sourceTitle: string;
}

/**
 * Preview surface for references (incoming/outgoing).
 *
 * Design rule: this is NOT a mini result system.
 * It must not grow its own filters, sorting, or deep navigation.
 * "Show all" is the escape hatch → PIVOT → center panel context switch.
 */
export function ReferencesTab({
  references,
  onFocus,
  onPivot,
  sourceId,
  sourceTitle,
}: ReferencesTabProps) {
  return (
    <div className="p-5 space-y-5">
      {references.map((group, i) => (
        <div key={i}>
          <div className="flex items-center justify-between mb-3">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              {group.direction}
              <span className="text-[10px] font-normal text-muted-foreground/60 ml-1">
                ({group.items.length})
              </span>
            </h4>
            {onPivot && group.items.length > 0 && (
              <button
                onClick={() => onPivot(`${group.direction} ${sourceTitle}`, sourceId)}
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
                className="flex items-center gap-2 px-3 py-2 rounded-md hover:bg-muted/50 cursor-pointer transition-colors"
              >
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
              </div>
            ))}
          </div>
        </div>
      ))}
      {references.length === 0 && (
        <EmptySection label="No references" />
      )}
    </div>
  );
}
