"use client";

import { ArrowRight } from "lucide-react";
import type { ReactNode } from "react";

interface ActionTextLinkProps {
  children: ReactNode;
  onClick?: () => void;
  showArrow?: boolean;
  className?: string;
}

/**
 * Small accent text link for "Show all", "Back", and similar navigation actions.
 * Replaces the repeated pattern:
 *   text-micro font-medium text-brand hover:text-brand-hover transition-colors
 */
export function ActionTextLink({
  children,
  onClick,
  showArrow = false,
  className = "",
}: ActionTextLinkProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex items-center gap-0.5 text-micro font-medium text-accent-core hover:text-accent-core/80 transition-colors ${className}`}
    >
      {children}
      {showArrow && <ArrowRight className="w-3 h-3" />}
    </button>
  );
}
