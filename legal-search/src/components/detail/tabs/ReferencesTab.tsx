"use client";

import type { ReferenceGroup } from "@/lib/types";
import {
  SectionLabel,
  ActionTextLink,
  InteractiveRow,
} from "../../primitives";
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
            <SectionLabel>
              {group.direction}
              <span className="text-[10px] font-normal text-muted-foreground/60 ml-1">
                ({group.items.length})
              </span>
            </SectionLabel>
            {onPivot && group.items.length > 0 && (
              <ActionTextLink
                onClick={() => onPivot(`${group.direction} ${sourceTitle}`, sourceId)}
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
              </InteractiveRow>
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
