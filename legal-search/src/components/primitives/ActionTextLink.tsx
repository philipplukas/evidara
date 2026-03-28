"use client";

import type { ReactNode } from "react";
import { ArrowRight } from "lucide-react";

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
      onClick={onClick}
      className={`flex items-center gap-0.5 text-micro font-medium text-brand hover:text-brand-hover transition-colors ${className}`}
    >
      {children}
      {showArrow && <ArrowRight className="w-3 h-3" />}
    </button>
  );
}
