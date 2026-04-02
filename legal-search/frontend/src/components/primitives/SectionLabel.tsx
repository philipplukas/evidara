"use client";

import type { ReactNode } from "react";

interface SectionLabelProps {
  children: ReactNode;
  className?: string;
}

/**
 * Consistent section header used across panels.
 * Replaces the repeated pattern:
 *   text-xs font-semibold uppercase tracking-wider text-muted-foreground
 */
export function SectionLabel({ children, className = "" }: SectionLabelProps) {
  return (
    <p
      className={`text-xs font-semibold uppercase tracking-wider text-muted-foreground ${className}`}
    >
      {children}
    </p>
  );
}
