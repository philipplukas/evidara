"use client";

import { Skeleton, TextSkeleton } from "./Skeleton";

/**
 * Skeleton matching ResultCard layout — title, badges, subtitle,
 * snippet (3 lines), metadata, actions.
 */
export function ResultCardSkeleton() {
  return (
    <div className="px-5 py-4 border-b border-border/60 border-l-2 border-l-transparent">
      {/* Title + badges */}
      <div className="flex items-start gap-2 mb-1.5">
        <Skeleton height="0.875rem" width="60%" />
        <div className="flex gap-1.5 shrink-0">
          <Skeleton className="rounded-full" height="1.25rem" width="3.5rem" />
          <Skeleton className="rounded-full" height="1.25rem" width="2.5rem" />
        </div>
      </div>

      {/* Subtitle */}
      <Skeleton height="0.75rem" width="40%" className="mb-2" />

      {/* Snippet */}
      <TextSkeleton lines={3} className="mb-3" />

      {/* Metadata */}
      <div className="flex gap-4 mb-3">
        <Skeleton height="0.625rem" width="5rem" />
        <Skeleton height="0.625rem" width="4rem" />
      </div>

      {/* Actions */}
      <div className="flex gap-2">
        <Skeleton height="0.625rem" width="4rem" />
        <Skeleton height="0.625rem" width="3rem" />
      </div>
    </div>
  );
}

/**
 * Skeleton for the full result list — count header + N cards.
 */
export function ResultListSkeleton({ count = 6 }: { count?: number }) {
  return (
    <div>
      {/* Result count bar */}
      <div className="px-5 py-3 border-b border-border/60">
        <Skeleton height="0.75rem" width="8rem" />
      </div>
      {Array.from({ length: count }, (_, i) => (
        <ResultCardSkeleton key={i} />
      ))}
    </div>
  );
}
