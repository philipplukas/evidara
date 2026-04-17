"use client";

import { getBadgeColor } from "@/lib/badge-tokens";

interface BadgeProps {
  label: string;
  colorKey?: string;
  size?: "sm" | "xs";
  className?: string;
}

/**
 * Centralized badge component.
 *
 * Renders a colored pill using the generic badge palette.
 * The `colorKey` comes from the BFF — the UI has no knowledge of
 * what document types map to which colors.
 *
 * Sizes:
 * - "sm" (default): standard badges in result cards and exact match strips
 * - "xs": smaller badges in preview surfaces (related/reference tabs)
 */
export function Badge({ label, colorKey, size = "sm", className = "" }: BadgeProps) {
  const colors = getBadgeColor(colorKey);

  const sizeClasses = size === "xs" ? "px-1 py-0.5 text-[10px]" : "px-1.5 py-0.5 text-tiny";

  return (
    <span
      className={`inline-flex items-center gap-1 rounded border font-semibold uppercase tracking-wide leading-none shrink-0 ${sizeClasses} ${className}`}
      style={{ backgroundColor: colors.bg, borderColor: colors.text, color: colors.text }}
    >
      {label}
    </span>
  );
}
