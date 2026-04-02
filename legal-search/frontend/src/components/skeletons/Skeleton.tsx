"use client";

import { cn } from "@/lib/utils";

interface SkeletonProps {
  className?: string;
  width?: string;
  height?: string;
}

/**
 * Base skeleton primitive — an animated pulse placeholder.
 * Uses design tokens for consistent appearance.
 */
export function Skeleton({ className, width, height }: SkeletonProps) {
  return (
    <div className={cn("animate-pulse rounded bg-muted/60", className)} style={{ width, height }} />
  );
}

/** Multi-line text skeleton */
export function TextSkeleton({ lines = 3, className }: { lines?: number; className?: string }) {
  const widths = ["100%", "95%", "70%", "85%", "60%"];
  return (
    <div className={cn("space-y-2", className)}>
      {Array.from({ length: lines }, (_, i) => (
        <Skeleton key={i} height="0.75rem" width={widths[i % widths.length]} />
      ))}
    </div>
  );
}
