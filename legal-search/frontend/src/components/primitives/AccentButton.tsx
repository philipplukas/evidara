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
 *   px-2 py-1 rounded text-micro font-medium transition-all
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
      type="button"
      onClick={onClick}
      title={title}
      aria-label={title}
      className={`flex items-center gap-1 min-h-11 sm:min-h-0 px-3 py-2 sm:px-2 sm:py-1 rounded text-micro font-medium transition-all
        ${
          active
            ? "text-accent-core bg-interactive-accent-muted"
            : "text-muted-foreground hover:text-accent-core hover:bg-interactive-accent-subtle"
        } ${className}`}
    >
      {children}
    </button>
  );
}
