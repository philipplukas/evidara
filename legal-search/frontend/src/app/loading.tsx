import { FilterPanelSkeleton, ResultListSkeleton, Skeleton } from "@/components/skeletons";

/**
 * Next.js route-level Suspense fallback.
 * Shows the workspace shell with skeleton panels while page.tsx loads.
 */
export default function Loading() {
  return (
    <div className="flex flex-col h-screen bg-surface-page">
      {/* Header skeleton */}
      <header className="border-b border-border bg-surface-panel">
        <div className="flex items-center gap-6 px-6 py-3">
          <div className="flex items-center gap-2 shrink-0">
            <Skeleton className="rounded-lg" width="1.75rem" height="1.75rem" />
            <Skeleton width="4.5rem" height="1.125rem" />
          </div>
          <div className="flex-1 max-w-2xl">
            <Skeleton className="rounded-lg" height="2.5rem" width="100%" />
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <Skeleton width="3rem" height="1rem" />
            <Skeleton width="3rem" height="1rem" />
          </div>
        </div>
      </header>

      {/* Body */}
      <div className="flex-1 flex min-h-0">
        {/* Filters */}
        <div className="w-[18%] min-w-[180px] border-r border-border bg-surface-panel overflow-hidden">
          <FilterPanelSkeleton />
        </div>

        {/* Results */}
        <div className="flex-1 bg-surface-panel overflow-hidden">
          <ResultListSkeleton count={6} />
        </div>
      </div>
    </div>
  );
}
