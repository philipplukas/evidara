"use client";

import type { ReactNode } from "react";

interface AccentButtonProps {
  children: ReactNode;
  onClick?: (e: React.MouseEvent) => void;
  active?: boolean;
  title?: string;
  className?: string;
}

/**
 * Small accent action button used for pin, copy, and result card actions.
 * Replaces the repeated pattern:
 *   px-2 py-1 rounded text-[11px] font-medium transition-all
 *   text-muted-foreground hover:text-brand hover:bg-interactive-accent-subtle
 */
export function AccentButton({
  children,
  onClick,
  active = false,
  title,
  className = "",
}: AccentButtonProps) {
  return (
    <button
      onClick={onClick}
      title={title}
      className={`flex items-center gap-1 px-2 py-1 rounded text-[11px] font-medium transition-all
        ${
          active
            ? "text-brand bg-interactive-accent-muted"
            : "text-muted-foreground hover:text-brand hover:bg-interactive-accent-subtle"
        } ${className}`}
    >
      {children}
    </button>
  );
}
