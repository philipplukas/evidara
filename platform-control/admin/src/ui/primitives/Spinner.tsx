"use client";

import { cn } from "./cn";

export function Spinner({ label = "Loading", className }: { label?: string; className?: string }) {
  return (
    <span
      className={cn("inline-flex items-center gap-2 text-sm text-[var(--text-meta)]", className)}
    >
      <span
        className="h-4 w-4 rounded-full border-2 border-[var(--border)] border-t-[var(--accent-core)] motion-safe:animate-spin"
        aria-hidden
      />
      <span>{label}</span>
    </span>
  );
}
