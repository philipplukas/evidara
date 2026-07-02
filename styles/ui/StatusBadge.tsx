/**
 * Shared `StatusBadge` primitive — semantic status pill with icon + label.
 *
 * First real component to land in `@evidara/ui` after the scaffolding gate
 * (ADR-0028). Both surfaces consume this via the path alias declared in
 * their respective `tsconfig.json`:
 *
 *   "@evidara/ui":   ["../../styles/ui"],
 *   "@evidara/ui/*": ["../../styles/ui/*"]
 *
 * Implements ADR-0016 Contract 5 (`StatusBadge`): redundant encoding (icon
 * + colour + label) on top of the shared `--status-*` token vocabulary.
 *
 * Tailwind utilities (`text-status-{level}`, `bg-status-{level}-subtle`)
 * resolve through the `@theme inline` block in each surface's `globals.css`,
 * which maps onto the shared CSS custom properties from
 * `styles/tokens/tokens.css`. Lucide and React are present on both surfaces
 * already; consumers do not gain a new runtime dependency.
 */
"use client";

import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";
import { STATUS_TOKEN_MAP, type StatusLevel } from "./status-tokens";

export interface StatusBadgeProps {
  status: StatusLevel;
  label: string;
  size?: "sm" | "md";
  className?: string;
}

export function StatusBadge({ status, label, size = "sm", className }: StatusBadgeProps) {
  const tokens = STATUS_TOKEN_MAP[status];
  const Icon = tokens.icon;

  return (
    <span
      className={twMerge(
        clsx(
          "inline-flex items-center gap-1.5 rounded-full border font-medium",
          tokens.subtleBg,
          tokens.color,
          size === "sm"
            ? "px-2 py-0.5 text-tiny border-current/15"
            : "px-2.5 py-1 text-xs border-current/15",
          className,
        ),
      )}
    >
      <Icon className={size === "sm" ? "h-3 w-3" : "h-3.5 w-3.5"} />
      {label}
    </span>
  );
}
