"use client";

import type { KeyboardEvent, ReactNode } from "react";

interface InteractiveRowProps {
  children: ReactNode;
  onClick?: () => void;
  className?: string;
}

/**
 * Consistent clickable row used in related, references, and structure panels.
 * Replaces the repeated pattern:
 *   flex items-center gap-2 px-3 py-2 rounded-md hover:bg-muted/50
 *   cursor-pointer transition-colors
 */
export function InteractiveRow({ children, onClick, className = "" }: InteractiveRowProps) {
  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (!onClick) return;
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onClick();
    }
  };

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={handleKeyDown}
      className={`flex items-center gap-2 px-3 py-2 rounded-md hover:bg-muted/50 cursor-pointer transition-colors ${className}`}
    >
      {children}
    </div>
  );
}
