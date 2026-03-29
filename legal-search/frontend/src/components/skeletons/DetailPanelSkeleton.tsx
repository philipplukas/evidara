"use client";

import { Skeleton, TextSkeleton } from "./Skeleton";

/**
 * Skeleton matching DetailPanel — breadcrumbs, title, subtitle,
 * tab bar, content area.
 */
export function DetailPanelSkeleton() {
  return (
    <div className="h-full flex flex-col">
      {/* Header area */}
      <div className="px-4 pt-4 pb-3 border-b border-border/60">
        {/* Breadcrumbs */}
        <div className="flex gap-1 mb-3">
          <Skeleton height="0.625rem" width="3rem" />
          <Skeleton height="0.625rem" width="0.5rem" />
          <Skeleton height="0.625rem" width="5rem" />
        </div>
        {/* Title */}
        <Skeleton height="1rem" width="70%" className="mb-2" />
        {/* Subtitle */}
        <Skeleton height="0.75rem" width="50%" className="mb-3" />
        {/* Metadata rows */}
        <div className="space-y-2">
          <div className="flex gap-4">
            <Skeleton height="0.625rem" width="4rem" />
            <Skeleton height="0.625rem" width="6rem" />
          </div>
          <div className="flex gap-4">
            <Skeleton height="0.625rem" width="5rem" />
            <Skeleton height="0.625rem" width="3rem" />
          </div>
        </div>
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 px-2 border-b border-border/60 py-2">
        {Array.from({ length: 5 }, (_, i) => (
          <Skeleton key={i} height="1.5rem" width={`${3 + (i % 3)}rem`} />
        ))}
      </div>

      {/* Content area */}
      <div className="flex-1 p-4">
        <TextSkeleton lines={8} />
      </div>
    </div>
  );
}
