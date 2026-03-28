"use client";

import { ExternalLink } from "lucide-react";
import type { RelatedGroup } from "@/lib/types";
import {
  SectionLabel,
  ActionTextLink,
  InteractiveRow,
  Badge,
} from "../../primitives";
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
            <SectionLabel className="flex items-center gap-1.5">
              {group.groupLabel}
              <span className="text-[10px] font-normal text-muted-foreground/60">
                ({group.items.length})
              </span>
            </SectionLabel>
            {onPivot && group.items.length > 0 && (
              <ActionTextLink
                onClick={() => onPivot(group.groupLabel, sourceId)}
                showArrow
              >
                Show all
              </ActionTextLink>
            )}
          </div>
          <div className="space-y-1">
            {group.items.map((item) => (
              <InteractiveRow
                key={item.id}
                onClick={() => onFocus?.(item.id)}
                className="group"
              >
                {item.badge && (
                  <Badge
                    label={item.badge.label}
                    colorKey={item.badge.colorKey}
                    size="xs"
                  />
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
                <ExternalLink className="w-3 h-3 text-muted-foreground/30 group-hover:text-brand transition-colors shrink-0" />
              </InteractiveRow>
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
