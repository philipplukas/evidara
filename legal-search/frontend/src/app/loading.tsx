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

      {/* Body — matches workspace shell layout with rounded panels and correct spacing */}
      <div className="flex min-h-0 flex-1 flex-col px-3 pb-3 pt-2 lg:flex-row lg:gap-2">
        {/* Filter panel skeleton — rounded to match workspace */}
        <div className="hidden min-h-0 w-[18%] min-w-[180px] overflow-hidden rounded-[1.35rem] border border-border/60 bg-surface-panel lg:block">
          <FilterPanelSkeleton />
        </div>

        {/* Resize handle stub */}
        <div className="hidden w-2 shrink-0 items-center justify-center lg:flex">
          <div className="h-8 w-0.5 rounded-full bg-border/40" />
        </div>

        {/* Result list skeleton — rounded to match workspace */}
        <div className="min-h-0 flex-1 overflow-hidden rounded-[1.35rem] border border-border/60 bg-surface-panel">
          <ResultListSkeleton count={6} />
        </div>
      </div>
    </div>
  );
}
