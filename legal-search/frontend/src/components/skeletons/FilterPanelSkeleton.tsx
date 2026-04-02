"use client";

import { Skeleton } from "./Skeleton";

/**
 * Skeleton matching FilterPanel — section label + 4 filter groups,
 * each with a label and 3–4 checkbox-sized placeholders.
 */
export function FilterPanelSkeleton() {
  return (
    <div className="py-4 space-y-1">
      {/* Section label */}
      <div className="px-4 pb-3">
        <Skeleton height="0.625rem" width="3rem" />
      </div>

      {Array.from({ length: 4 }, (_, groupIdx) => (
        <div key={groupIdx} className="border-b border-border/60 last:border-0">
          {/* Group header */}
          <div className="flex items-center justify-between px-4 py-2.5">
            <Skeleton height="0.75rem" width={`${5 + groupIdx}rem`} />
            <Skeleton height="0.75rem" width="0.75rem" />
          </div>

          {/* Options */}
          <div className="px-4 pb-3 space-y-2">
            {Array.from({ length: 3 + (groupIdx % 2) }, (_, optIdx) => (
              <div key={optIdx} className="flex items-center gap-2">
                <Skeleton className="rounded-sm shrink-0" height="0.875rem" width="0.875rem" />
                <Skeleton height="0.625rem" width={`${4 + optIdx * 2}rem`} />
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
