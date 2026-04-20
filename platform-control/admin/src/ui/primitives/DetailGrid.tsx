/**
 * `DetailGrid` + `FieldCell` — the two-column show-page pattern
 * (M-9/M-15/M-16 treatment) in Tailwind. `FieldCell` renders the
 * overline-label → value cascade; `DetailGrid` wraps them in the shared
 * card chrome. Used by every detail view.
 */
"use client";

import type { ReactNode } from "react";
import { cn } from "./cn";

export function DetailGrid({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={cn(
        "rounded-[18px] border border-[rgba(29,41,61,0.08)] bg-white/85 p-5 sm:p-6",
        "shadow-[var(--shadow-card)] backdrop-blur-[12px]",
        "grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-5",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function FieldCell({
  label,
  children,
  span = "half",
}: {
  label: string;
  children: ReactNode;
  /** `half` spans one column (default), `full` spans both. */
  span?: "half" | "full";
}) {
  return (
    <div className={cn("flex flex-col gap-1", span === "full" && "md:col-span-2")}>
      <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[rgba(29,41,61,0.6)] leading-[1.2]">
        {label}
      </span>
      <div className="text-sm text-[var(--foreground)]">{children}</div>
    </div>
  );
}
